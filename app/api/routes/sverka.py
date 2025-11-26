from fastapi import APIRouter, UploadFile, File, Form, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path as PathlibPath
from typing import Annotated
import uuid
import asyncio
import json

from ...core.utils import (
    process_pdf,
    save_files,
    display_analysis,
    norm_tg,
    process_docx,
    process_txt,
    process_rtf,
)
from ...core.gpt import gpt_generator
from ...core.generate_wl_resume import parse_json_loose
from ...core.redis_tasks import set_task, get_task  # 👈 добавили
from ...database.vacancy_db import VacancyRepository
from ...models.vacancy import ClarificationsMail

router = APIRouter(tags=["sverka"])

templates_dir = str(PathlibPath(__file__).resolve().parent.parent.parent / "templates")
templates = Jinja2Templates(directory=templates_dir)
vacancy_repository = VacancyRepository()

# Больше НЕ используем in-memory TASKS
# TASKS: dict[str, dict] = {}
TYPES = ["pdf", "docx", "txt", "rtf"]


async def process_sverka_task(
    vacancy_text: str,
    resumes: list[dict],
    task_id: str,
    vacancy_id: str,
    tg_username: str,
):
    """
    resumes: список словарей вида:
    {
        "text": <текст резюме>,
        "filename": <имя файла>
    }
    """
    try:
        tasks = []
        for item in resumes:
            tasks.append(
                gpt_generator.generate_sverka(
                    vacancy_text,
                    item["text"],
                    item["filename"],
                )
            )
        gpt_results = await asyncio.gather(*tasks)

        results: list[dict] = []
        for raw, src in zip(gpt_results, resumes):
            try:
                data_dict = parse_json_loose(raw)
            except Exception as e:
                error_str = str(e)
                is_truncated = "Unterminated string" in error_str or "unterminated" in error_str.lower()

                error_msg = (
                    f"Ошибка парсинга JSON для файла "
                    f"{src.get('filename', 'unknown')}: {e}"
                )

                if is_truncated:
                    error_msg += (
                        "\n⚠️ ВНИМАНИЕ: JSON-ответ был обрезан (слишком длинный). "
                        "Попробуйте увеличить max_output_tokens или сократить входные данные."
                    )

                raw_length = len(raw) if raw else 0
                error_msg += f"\nДлина ответа: {raw_length} символов"

                if raw_length > 1000:
                    error_msg += f"\nСырой ответ (первые 1000 символов): {raw[:1000]}"
                    error_msg += f"\nСырой ответ (последние 1000 символов): {raw[-1000:]}"
                elif raw_length > 500:
                    error_msg += f"\nСырой ответ (первые 500 символов): {raw[:500]}"
                    error_msg += f"\nСырой ответ (последние 500 символов): {raw[-500:]}"
                else:
                    error_msg += f"\nСырой ответ: {raw}"

                raise ValueError(error_msg)

            cand_name = None
            candidate = data_dict.get("candidate") if isinstance(data_dict, dict) else None
            if isinstance(candidate, dict):
                cand_name = candidate.get("full_name")

            results.append(
                {
                    "resume_json": data_dict,
                    "filename": src["filename"],
                    "candidate_fullname": cand_name,
                }
            )

        # сохраняем полный результат задачи в Redis
        await set_task(
            task_id,
            {
                "status": "completed",
                "vacancy_id": vacancy_id,
                "results": results,
                "tg_username": tg_username,
            },
        )
    except Exception as e:
        await set_task(
            task_id,
            {
                "status": "error",
                "error": str(e),
            },
        )


@router.get("/sverka", response_class=HTMLResponse)
async def sverka_get(request: Request):
    topics = await vacancy_repository.get_topics()
    return templates.TemplateResponse(
        "sverka/sverka_start.html",
        {"request": request, "topics": topics},
    )


@router.post("/sverka", response_class=HTMLResponse)
async def sverka_post(
    request: Request,
    vacancy_id: str = Form(...),
    tg_username: str = Form(...),
    resume_file: list[UploadFile] = File(...),
):
    # 1. проверка вакансии
    if not vacancy_id.strip():
        topics = await vacancy_repository.get_topics()
        return templates.TemplateResponse(
            "sverka/sverka_start.html",
            {
                "request": request,
                "topics": topics,
                "error": "Пожалуйста, выберите вакансию из списка.",
            },
            status_code=400,
        )

    vacancy = await vacancy_repository.get_vacancy_by_vacancy_id(vacancy_id)
    if not vacancy:
        topics = await vacancy_repository.get_topics()
        return templates.TemplateResponse(
            "sverka/sverka_start.html",
            {
                "request": request,
                "topics": topics,
                "error": "Вакансия не найдена в базе данных.",
            },
            status_code=400,
        )

    # 2. валидируем расширения
    for f in resume_file:
        ext = f.filename.rsplit(".", 1)[-1].lower()
        if ext not in TYPES:
            topics = await vacancy_repository.get_topics()
            return templates.TemplateResponse(
                "sverka/sverka_start.html",
                {
                    "request": request,
                    "topics": topics,
                    "error": "Формат файла не поддерживается. Разрешены: PDF, DOCX, TXT.",
                },
                status_code=400,
            )

    # 3. сохраняем все файлы в папку вакансии
    files_paths = await save_files(resume_file, vacancy_id)

    # 4. вытаскиваем текст из каждого
    resumes_to_process: list[dict] = []
    for fpath, upload in zip(files_paths, resume_file):
        if upload.filename.lower().endswith(".docx"):
            text = process_docx(fpath)
        elif upload.filename.lower().endswith(".txt"):
            text = process_txt(fpath)
        elif upload.filename.lower().endswith(".rtf"):
            text = process_rtf(fpath)
        elif upload.filename.lower().endswith(".pdf"):
            text = process_pdf(fpath)
        else:
            text = ""

        if not text.strip():
            continue  # пропускаем пустые файлы
        resumes_to_process.append(
            {
                "text": text,
                "filename": upload.filename,
            }
        )

    # 5. создаём задачу
    task_id = str(uuid.uuid4())
    tg_username = norm_tg(tg_username)

    # сохраняем начальный статус в Redis
    await set_task(task_id, {"status": "processing"})

    asyncio.create_task(
        process_sverka_task(
            vacancy.vacancy_text,
            resumes_to_process,
            task_id,
            vacancy_id,
            tg_username,
        )
    )

    # 6. показываем страницу ожидания
    return templates.TemplateResponse(
        "sverka/wait_sverka.html",
        {"request": request, "task_id": task_id, "status": "processing"},
    )


@router.get("/sverka/status/{task_id}")
async def sverka_status(task_id: str):
    task = await get_task(task_id)
    if not task:
        return {"status": "not_found"}
    return {"status": task.get("status")}


@router.get("/sverka/result/{task_id}", response_class=HTMLResponse)
async def sverka_result_list(request: Request, task_id: str):
    """
    Показать страницу со ВСЕМИ результатами для этого task_id (если файлов было несколько).
    Тут просто список: файл / кандидат / ссылка на подробный результат.
    """
    task = await get_task(task_id)
    if not task:
        topics = await vacancy_repository.get_topics()
        return templates.TemplateResponse(
            "sverka/sverka_start.html",
            {
                "request": request,
                "topics": topics,
                "error": "Задача не найдена.",
            },
            status_code=404,
        )

    if task["status"] == "processing":
        return templates.TemplateResponse(
            "sverka/wait_sverka.html",
            {"request": request, "task_id": task_id, "status": "processing"},
        )
    if task["status"] == "error":
        topics = await vacancy_repository.get_topics()
        return templates.TemplateResponse(
            "sverka/sverka_start.html",
            {
                "request": request,
                "topics": topics,
                "error": f"Ошибка при обработке: {task['error']}",
            },
            status_code=500,
        )

    # тут уже completed
    results = task["results"]

    return templates.TemplateResponse(
        "sverka/sverka_result_list.html",
        {
            "request": request,
            "task_id": task_id,
            "vacancy_id": task["vacancy_id"],
            "results": results,
            "tg_username": task["tg_username"],
        },
    )


@router.get("/sverka/result/{task_id}/{index}", response_class=HTMLResponse)
async def sverka_result_one(
    request: Request,
    task_id: str,
    index: int,
    tg_username: Annotated[str, Query(...)],
):
    """
    Конкретный результат по одному файлу из пачки.
    Тут используем твой привычный шаблон sverka_result.html
    """
    task = await get_task(task_id)
    if not task:
        topics = await vacancy_repository.get_topics()
        return templates.TemplateResponse(
            "sverka/sverka_start.html",
            {
                "request": request,
                "topics": topics,
                "error": "Задача не найдена.",
            },
            status_code=404,
        )

    if task["status"] != "completed":
        return templates.TemplateResponse(
            "sverka/wait_sverka.html",
            {"request": request, "task_id": task_id, "status": task["status"]},
        )

    results = task["results"]
    if index < 0 or index >= len(results):
        topics = await vacancy_repository.get_topics()
        return templates.TemplateResponse(
            "sverka/sverka_start.html",
            {
                "request": request,
                "topics": topics,
                "error": "Результат с таким индексом не найден.",
            },
            status_code=404,
        )

    item = results[index]
    resume_json = item["resume_json"]

    # формируем html анализа
    data = display_analysis(resume_json)

    candidate_fullname = item.get("candidate_fullname")
    vac_id = task["vacancy_id"]
    if not candidate_fullname or candidate_fullname == "Нет (требуется уточнение)":
        candidate_fullname = item.get("filename")  # хоть что-то показать

    # сохраняем в БД сверку (если надо по каждой)
    contacts = resume_json.get("candidate", {}).get("contacts", {})
    await vacancy_repository.add_sverka(
        resume_json,
        vac_id,
        candidate_fullname,
        tg_username,
    )

    return templates.TemplateResponse(
        "sverka/sverka_result.html",
        {
            "request": request,
            "task_id": task_id,
            "ai_text": data,
            "vacancy_id": task["vacancy_id"],
            "candidate_fullname": candidate_fullname,
            "contacts": contacts,
            "tg_username": tg_username,
        },
    )


@router.get("/api/vacancies/by-topic/{topic_name}")
async def get_vacancies_by_topic(topic_name: str):
    vacancies = await vacancy_repository.get_vacancies_by_topic(topic_name)
    return [{"vacancy_id": v.vacancy_id, "title": v.title} for v in vacancies]


@router.get("/api/vacancy/{vacancy_id}")
async def get_vacancy_details(vacancy_id: str):
    vacancy = await vacancy_repository.get_vacancy_by_vacancy_id(vacancy_id)
    if not vacancy:
        return {"error": "Vacancy not found"}
    return {
        "vacancy_id": vacancy.vacancy_id,
        "title": vacancy.title,
        "vacancy_text": vacancy.vacancy_text,
        "topic_name": vacancy.topic_name,
    }


@router.get("/api/mail/{mail_type}")
async def generate_mail(
    mail_type: str,
    vacancy_id: str,
    candidate_fullname: str,
    tg_username: str,
):
    """Создать письмо (GET запрос с query параметрами)"""
    try:
        sverka = (
            await vacancy_repository.get_sverka_by_vacancy_and_candidate_and_username(
                vacancy_id,
                candidate_fullname,
                tg_username,
            )
        )
        if not sverka:
            return {"error": "Сверка не найдена в базе данных"}

        resume_json = sverka.sverka_json

        if mail_type == "finalist":
            mail_text = await gpt_generator.create_finalist_mail(
                resume_json,
                tg_username,
            )
        elif mail_type == "utochnenie":
            vac = await vacancy_repository.get_vacancy_by_vacancy_id(vacancy_id)
            vacancy_text = vac.vacancy_text if vac else ""
            mail_text = await gpt_generator.create_utochnenie_mail(
                resume_json,
                tg_username,
                vacancy_text,
            )
        elif mail_type == "otkaz":
            mail_text = await gpt_generator.create_otkaz_mail(
                resume_json,
                tg_username,
            )
        elif mail_type == "client":
            mail_text = await gpt_generator.create_klient_mail(
                resume_json,
                tg_username,
            )
        else:
            return {"error": "Неизвестный тип письма"}

        return {"mail_text": mail_text}
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/wl/create/")
async def generate_wl_resume(
    vacancy_id: str,
    candidate_fullname: str,
    tg_username: str,
):
    """Создать White Label резюме (GET запрос с query параметрами)"""

    sverka = (
        await vacancy_repository.get_sverka_by_vacancy_and_candidate_and_username(
            vacancy_id,
            candidate_fullname,
            tg_username,
        )
    )
    if not sverka:
        return {"error": "Сверка не найдена в базе данных"}

    resume_json = sverka.sverka_json

    vac = await vacancy_repository.get_vacancy_by_vacancy_id(vacancy_id)
    vacancy_text = vac.vacancy_text if vac else ""

    filename = await gpt_generator.generate_wl_resume(
        candidate_text=resume_json,
        vacancy_text=vacancy_text,
        username=tg_username,
    )

    download_link = filename["download_link"]
    filename = filename["filename"]
    return JSONResponse(
        {
            "download_link": download_link,
            "filename": filename,
            "message": "WL-резюме сформировано",
        }
    )


@router.post("/api/mail/utochnenie/save")
async def generate_wl_resume_post(data: ClarificationsMail):
    vacancy_id = data.vacancy_id
    candidate_fullname = data.candidate_fullname
    tg_username = data.tg_username
    utochnenie = data.clarifications
    print("Utochnenie:", utochnenie)

    sverka = (
        await vacancy_repository.get_sverka_by_vacancy_and_candidate_and_username(
            vacancy_id,
            candidate_fullname,
            tg_username,
        )
    )
    if not sverka:
        return {"error": "Сверка не найдена в базе данных"}

    vac = await vacancy_repository.get_vacancy_by_vacancy_id(vacancy_id)
    vacancy_text = vac.vacancy_text if vac else ""

    resume_json = sverka.sverka_json

    filename = await gpt_generator.generate_wl_resume(
        candidate_text=resume_json,
        vacancy_text=vacancy_text,
        utochnenie=utochnenie,
        username=tg_username,
    )

    download_link = filename["download_link"]
    filename = filename["filename"]
    mail_text = await gpt_generator.create_klient_mail(
        resume_json,
        tg_username,
        additional_notes=utochnenie,
    )
    return JSONResponse(
        {
            "ok": True,
            "client_mail_text": mail_text,
            "wl_download_link": download_link,
            "filename": filename,
        }
    )
