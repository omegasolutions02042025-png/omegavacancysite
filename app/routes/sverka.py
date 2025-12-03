from fastapi import APIRouter, UploadFile, File, Form, Request, Query, Depends, Body, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path as PathlibPath
from typing import Annotated
import uuid
import asyncio
import json
import os

from redis.asyncio import Redis

from app.core.utils import (
    process_pdf,
    save_files,
    display_analysis,
    norm_tg,
    process_docx,
    process_txt,
    process_rtf,
)
from app.core.gpt import gpt_generator
from app.core.current_user import get_current_user_from_cookie
from app.database.vacancy_db import VacancyRepository
from app.models.vacancy import ClarificationsMail
from app.models.candidate import GPTCandidateProfile, SverkaFromCandidateRequest
from app.database.candidate_db import CandidateRepository
from app.database.user_db import UserRepository
import string
import random



router = APIRouter(tags=["sverka"])

templates_dir = str(PathlibPath(__file__).resolve().parent.parent / "templates")
templates = Jinja2Templates(directory=templates_dir)
vacancy_repository = VacancyRepository()
candidate_repository = CandidateRepository()
user_repository = UserRepository()

TYPES = ["pdf", "docx", "txt", "rtf"]

# =========================
# Redis для хранения задач
# =========================

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

redis: Redis = Redis.from_url(
    REDIS_URL,
    decode_responses=True,  # строки вместо bytes
)

TASK_KEY_PREFIX = "sverka_task:"
TASK_TTL_SECONDS = 60 * 60  # 1 час


async def set_task(task_id: str, data: dict) -> None:
    """Сохранить/обновить задачу сверки в Redis."""
    key = f"{TASK_KEY_PREFIX}{task_id}"
    await redis.set(key, json.dumps(data, ensure_ascii=False), ex=TASK_TTL_SECONDS)


async def get_task(task_id: str) -> dict | None:
    """Получить задачу сверки из Redis."""
    key = f"{TASK_KEY_PREFIX}{task_id}"
    raw = await redis.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def delete_task(task_id: str) -> None:
    """Удалить задачу (если понадобится)."""
    key = f"{TASK_KEY_PREFIX}{task_id}"
    await redis.delete(key)


# =========================
# Логика сверки
# =========================


async def process_candidate_profiles_task(
    resumes: list[dict],
    task_id: str,
    user_id: int,
):
    """
    Обрабатывает резюме по одному через create_candidate_profile.
    Не загружает GPT сразу всеми резюме.
    
    resumes: список словарей вида:
    {
        "text": <текст резюме>,
        "filename": <имя файла>
    }
    """
    
    for item in resumes:
        profile = await gpt_generator.create_candidate_profile(
            text=item["text"],
        )
        if isinstance(profile, str):
            profile = GPTCandidateProfile.model_validate_json(profile)
        else:
            profile = GPTCandidateProfile.model_validate(profile)
        
        profile_db = await candidate_repository.candidate_profile_to_db(
            profile=profile,
            user_id=user_id,
            )
        print(f"[CANDIDATE_PROFILES_TASK] Сохранен профиль кандидата в БД: {profile_db.model_dump()}")

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
            print("Processing resume:", item["filename"])
            
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
                data_dict = json.loads(raw)
            except Exception as e:
                # Битый JSON — логируем и ПРОПУСКАЕМ этот файл
                print(
                    f"[sverka] Ошибка парсинга JSON для файла "
                    f"{src.get('filename', 'unknown')}: {e}"
                )
                print(f"[sverka] Сырой ответ (первые 500 символов): {raw[:500] if raw else ''}")
                continue

            # вытащим ФИО из ответа, если оно есть
            cand_name = None
            candidate = (
                data_dict.get("candidate") if isinstance(data_dict, dict) else None
            )
            if isinstance(candidate, dict):
                cand_name = candidate.get("full_name")

            results.append(
                {
                    "resume_json": data_dict,
                    "filename": src["filename"],
                    "candidate_fullname": cand_name,
                }
            )

        # Если вообще ни одного валидного результата — считаем это ошибкой задачи
        if not results:
            await set_task(
                task_id,
                {
                    "status": "error",
                    "error": "Все ответы модели содержали битый JSON, ни одно резюме не удалось разобрать.",
                },
            )
            return

        # Иначе — задача успешно завершена по тем резюме, которые удалось разобрать
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
        print(f"[sverka] Ошибка при обработке задачи {task_id}: {e}")
        await set_task(
            task_id,
            {
                "status": "error",
                "error": str(e),
            },
        )


@router.get("/sverka", response_class=HTMLResponse)
async def sverka_get(
    request: Request,
    vacancy_id: str = Query(..., description="ID вакансии для сверки"),
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Страница сверки: открывается по ссылке /sverka?vacancy_id=BD-10271
    Вакансию берём из БД и сразу показываем в форме.
    """
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)
    vacancy = await vacancy_repository.get_vacancy_by_vacancy_id(vacancy_id)
    if not vacancy:
        raise HTTPException(status_code=404, detail="Вакансия не найдена")

    return templates.TemplateResponse(
        "sverka/sverka_start.html",
        {"request": request, "vacancy": vacancy, "user_email": current_user.email, 'telegram_username' : current_user.work_telegram, 'user_id' : current_user.id},
    )



@router.post("/sverka", response_class=HTMLResponse)
async def sverka_post(
    request: Request,
    vacancy_id: str = Form(...),
    resume_file: list[UploadFile] = File(...),
    current_user = Depends(get_current_user_from_cookie)
):
    # 1. проверка vacancy_id и самой вакансии
    if not vacancy_id.strip():
        raise HTTPException(status_code=400, detail="vacancy_id не указан")

    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)
    
    tg_username = current_user.work_telegram
    vacancy = await vacancy_repository.get_vacancy_by_vacancy_id(vacancy_id)
    if not vacancy:
        raise HTTPException(status_code=404, detail="Вакансия не найдена")

    # 2. валидируем расширения
    for f in resume_file:
        ext = f.filename.rsplit(".", 1)[-1].lower()
        if ext not in TYPES:
            return templates.TemplateResponse(
                "sverka/sverka_start.html",
                {
                    "request": request,
                    "vacancy": vacancy,
                    "error": "Формат файла не поддерживается. Разрешены: PDF, DOCX, TXT.",
                    'user_email': current_user.email,
                    'telegram_username' : current_user.work_telegram,
                    'user_id' : current_user.id
                },
                status_code=400,
            )

    # 3. сохраняем все файлы в папку вакансии
    files_paths = await save_files(resume_file, vacancy_id)

    # 4. вытаскиваем текст из каждого
    resumes_to_process: list[dict] = []
    for fpath, upload in zip(files_paths, resume_file):
        fname = upload.filename.lower()
        if fname.endswith(".docx"):
            text = process_docx(fpath)
        elif fname.endswith(".txt"):
            text = process_txt(fpath)
        elif fname.endswith(".rtf"):
            text = process_rtf(fpath)
        elif fname.endswith(".pdf"):
            text = process_pdf(fpath)
        else:
            text = ""

        if not text.strip():
            continue  # пропускаем пустые файлы
        resumes_to_process.append(
            {"text": text, "filename": upload.filename}
        )

    if not resumes_to_process:
        return templates.TemplateResponse(
            "sverka/sverka_start.html",
            {
                "request": request,
                "vacancy": vacancy,
                "error": "Не удалось прочитать ни одно резюме. Проверьте файлы.",
                'user_email': current_user.email,
                'telegram_username' : current_user.work_telegram,
                'user_id' : current_user.id
            },
            status_code=400,
        )

    # 5. создаём задачу для сверки
    task_id = str(uuid.uuid4())
    tg_username = norm_tg(tg_username)

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
    
    # 5.1. создаём фоновую задачу для создания профилей кандидатов
    # Обрабатываем резюме по одному через create_candidate_profile
    profiles_task_id = str(uuid.uuid4())
    
    print(f"[SVERKA_POST] Создана фоновая задача {profiles_task_id} для создания профилей из {len(resumes_to_process)} резюме")
    
    asyncio.create_task(
        process_candidate_profiles_task(
            resumes_to_process,
            profiles_task_id,
            current_user.id,
        )
    )

    # 6. показываем страницу ожидания
    return templates.TemplateResponse(
        "sverka/wait_sverka.html",
        {"request": request, "task_id": task_id, "status": "processing", 'user_email': current_user.email,
                'telegram_username' : current_user.work_telegram,
                'user_id' : current_user.id},
    )

@router.get("/sverka/status/{task_id}")
async def sverka_status(task_id: str):
    task = await get_task(task_id)
    if not task:
        return {"status": "not_found"}
    return {"status": task.get("status")}


@router.get("/sverka/result/{task_id}", response_class=HTMLResponse)
async def sverka_result_list(request: Request, task_id: str, current_user=Depends(get_current_user_from_cookie)):
    """
    Показать страницу со ВСЕМИ результатами для этого task_id (если файлов было несколько).
    Тут просто список: файл / кандидат / ссылка на подробный результат.
    """
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)
    task = await get_task(task_id)
    if not task:
        return templates.TemplateResponse(
            "sverka/sverka_start.html",
            {
                "request": request,
                "error": "Задача не найдена.",
                "user_email": current_user.email,
                "user_id" : current_user.id,
                "telegram_username" : current_user.work_telegram,
            },
            status_code=404,
        )

    if task["status"] == "processing":
        return templates.TemplateResponse(
            "sverka/wait_sverka.html",
            {"request": request, "task_id": task_id, "status": "processing"},
        )
    if task["status"] == "error":
        return templates.TemplateResponse(
            "sverka/sverka_start.html",
            {
                "request": request,
                "error": f"Ошибка при обработке: {task['error']}",
                "user_email": current_user.email,
                "user_id" : current_user.id,
                "telegram_username" : current_user.work_telegram,
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
            "user_email": current_user.email,
            "user_id": current_user.id,
        },
    )


@router.get("/sverka/result/{task_id}/{index}", response_class=HTMLResponse)
async def sverka_result_one(
    request: Request,
    task_id: str,
    index: int,
    tg_username: Annotated[str, Query(...)],
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Конкретный результат по одному файлу из пачки.
    Тут используем твой привычный шаблон sverka_result.html
    """
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)
    task = await get_task(task_id)
    if not task:
        return templates.TemplateResponse(
            "sverka/sverka_start.html",
            {
                "request": request,
                "error": "Задача не найдена.",
                "user_email": current_user.email,
                "user_id": current_user.id,
                "telegram_username" : current_user.work_telegram,
            },
            status_code=404,
        )

    if task["status"] != "completed":
        return templates.TemplateResponse(
            "sverka/wait_sverka.html",
            {"request": request, "task_id": task_id, "status": task["status"], "user_email": current_user.email},
        )

    results = task["results"]
    if index < 0 or index >= len(results):
        return templates.TemplateResponse(
            "sverka/sverka_start.html",
            {
                "request": request,
                "topics": [],
                "error": "Результат с таким индексом не найден.",
                "user_email": current_user.email,
                "user_id": current_user.id,
                "telegram_username" : current_user.work_telegram,
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
    def slug6() -> str:
        chars = string.ascii_lowercase + string.digits
        return ''.join(random.choice(chars) for _ in range(6))
    slug = slug6()
    await vacancy_repository.add_sverka(
        resume_json,
        slug,
        vac_id,
        candidate_fullname,
        current_user.id,
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
            "user_email": current_user.email,
            "user_id": current_user.id,
            
        },
    )


@router.get("/api/vacancy/{vacancy_id}")
async def get_vacancy_details(vacancy_id: str):
    vacancy = await vacancy_repository.get_vacancy_by_vacancy_id(vacancy_id)
    if not vacancy:
        return {"error": "Vacancy not found"}
    return {
        "vacancy_id": vacancy.vacancy_id,
        "title": vacancy.title,
        "vacancy_text": vacancy.vacancy_text,
    }


@router.get("/api/mail/{mail_type}/stream")
async def generate_mail_stream(
    mail_type: str, vacancy_id: str, candidate_fullname: str, tg_username: str, current_user=Depends(get_current_user_from_cookie)
):
    """
    Стриминговый эндпоинт для генерации писем с эффектом набираемого текста.
    Использует Server-Sent Events (SSE) для передачи данных в реальном времени.
    """
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)
    
    async def event_generator():
        try:
            sverka = await vacancy_repository.get_sverka_by_vacancy_and_candidate_and_user_id(
                vacancy_id,
                candidate_fullname,
                current_user.id,
            )
            if not sverka:
                yield f"data: {json.dumps({'error': 'Сверка не найдена в базе данных'}, ensure_ascii=False)}\n\n"
                return

            resume_json = sverka.sverka_json

            # Выбираем соответствующий метод стриминга
            if mail_type == "finalist":
                stream_gen = gpt_generator.create_finalist_mail_stream(resume_json, tg_username)
            elif mail_type == "utochnenie":
                vac = await vacancy_repository.get_vacancy_by_vacancy_id(vacancy_id)
                vacancy_text = vac.vacancy_text if vac else ""
                stream_gen = gpt_generator.create_utochnenie_mail_stream(resume_json, tg_username, vacancy_text)
            elif mail_type == "otkaz":
                stream_gen = gpt_generator.create_otkaz_mail_stream(resume_json, tg_username)
            elif mail_type == "client":
                stream_gen = gpt_generator.create_klient_mail_stream(resume_json, tg_username)
            else:
                yield f"data: {json.dumps({'error': 'Неизвестный тип письма'}, ensure_ascii=False)}\n\n"
                return

            # Отправляем чанки по мере генерации
            full_text = ""
            async for chunk in stream_gen:
                if chunk:
                    # Очищаем от маркеров Markdown и других символов
                    clean_chunk = chunk.replace("*", "")
                    full_text += clean_chunk
                    # Отправляем каждый чанк
                    yield f"data: {json.dumps({'chunk': clean_chunk, 'type': 'chunk'}, ensure_ascii=False)}\n\n"
            
            # Отправляем финальное сообщение с полным текстом
            yield f"data: {json.dumps({'type': 'done', 'full_text': full_text}, ensure_ascii=False)}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e), 'type': 'error'}, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/mail/{mail_type}")
async def generate_mail(
    mail_type: str, vacancy_id: str, candidate_fullname: str, tg_username: str,  current_user=Depends(get_current_user_from_cookie)
):
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)
    try:
        sverka = await vacancy_repository.get_sverka_by_vacancy_and_candidate_and_user_id(
                vacancy_id,
                candidate_fullname,
                current_user.id,
            )
        if not sverka:
            return {"error": "Сверка не найдена в базе данных"}

        resume_json = sverka.sverka_json

        if mail_type == "finalist":
            mail_text = await gpt_generator.create_finalist_mail(
                resume_json, tg_username
            )
        elif mail_type == "utochnenie":
            vac = await vacancy_repository.get_vacancy_by_vacancy_id(vacancy_id)
            vacancy_text = vac.vacancy_text if vac else ""
            mail_text = await gpt_generator.create_utochnenie_mail(
                resume_json, tg_username, vacancy_text
            )
        elif mail_type == "otkaz":
            mail_text = await gpt_generator.create_otkaz_mail(
                resume_json, tg_username
            )
        elif mail_type == "client":
            mail_text = await gpt_generator.create_klient_mail(
                resume_json, tg_username
            )
        else:
            return {"error": "Неизвестный тип письма"}

        return {"mail_text": mail_text.replace("*", "")}
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/wl/create/")
async def generate_wl_resume(
    vacancy_id: str, candidate_fullname: str, current_user=Depends(get_current_user_from_cookie)
):
    """Создать White Label резюме (GET запрос с query параметрами)"""
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)
    sverka = (
        await vacancy_repository.get_sverka_by_vacancy_and_candidate_and_user_id(
            vacancy_id,
            candidate_fullname,
            current_user.id,
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
        username=current_user.work_telegram,
    )

    download_link = filename["download_link"]
    filename = filename["filename"]
    return JSONResponse(
        {"download_link": download_link, "filename": filename, "message": "WL-резюме сформировано"}
    )


@router.post("/api/mail/utochnenie/save")
async def generate_wl_resume_post(data: ClarificationsMail, current_user=Depends(get_current_user_from_cookie)):
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)
    vacancy_id = data.vacancy_id
    candidate_fullname = data.candidate_fullname
    tg_username = data.tg_username
    utochnenie = data.clarifications
    print("Utochnenie:", utochnenie)
    sverka = (
        await vacancy_repository.get_sverka_by_vacancy_and_candidate_and_user_id(
            vacancy_id,
            candidate_fullname,
            current_user.id,
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
        resume_json, tg_username, additional_notes=utochnenie
    )
    return JSONResponse(
        {
            "ok": True,
            "client_mail_text": mail_text,
            "wl_download_link": download_link,
            "filename": filename,
        }
    )





@router.post("/api/sverka/from-candidate")
async def sverka_from_candidate(
    request: Request,
    payload: SverkaFromCandidateRequest,
    current_user=Depends(get_current_user_from_cookie),
    
):
    """
    Запуск сверки по одному или нескольким кандидатам из базы.
    candidate_ids — список ID кандидатов.
    """
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)
    print("RAW payload in /api/sverka/from-candidate:", payload) 
    vacancy_id = payload.vacancy_id
    candidate_ids = payload.candidate_numbers or []

    if not candidate_ids:
        raise HTTPException(status_code=401, detail="Не переданы candidate_ids")

    tg_username = norm_tg(current_user.work_telegram or "")
    print("TG username:", tg_username)
    if not tg_username:
        raise HTTPException(status_code=401, detail="Не переданы tg_username")
    vacancy = await vacancy_repository.get_vacancy_by_vacancy_id(vacancy_id)
    if not vacancy:
        raise HTTPException(status_code=404, detail="Вакансия не найдена")

    resumes_to_process: list[dict] = []

    # 2. достаём всех кандидатов и собираем тексты резюме
    for cid in candidate_ids:
        candidate = await candidate_repository.get_candidate_by_id_and_user_id(cid, current_user.id)
        if not candidate:
            # можно пропустить или упасть — здесь мягко пропускаем
            continue
        
        

        resumes_to_process.append(
            {
                "text": candidate.model_dump_json(),
                "filename": candidate.full_name + "_" + str(candidate.salary_usd)+"_"+str(candidate.currencies),
            }
        )
    print("Resumes to process:", resumes_to_process)
    if not resumes_to_process:
        raise HTTPException(
            status_code=400,
            detail="Ни по одному кандидату не найден текст резюме",
        )

    # 3. создаём задачу в Redis
    task_id = str(uuid.uuid4())
    print("Task ID:", task_id)

    await set_task(task_id, {"status": "processing"})

    # 4. запускаем асинхронную сверку
    asyncio.create_task(
        process_sverka_task(
            vacancy_text=vacancy.vacancy_text,
            resumes=resumes_to_process,
            task_id=task_id,
            vacancy_id=vacancy.vacancy_id,
            tg_username=tg_username,
        )
    )
    
    return JSONResponse({"task_id": task_id})


@router.get("/sverka/history")
async def sverka_history(request: Request, current_user=Depends(get_current_user_from_cookie)):
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)
    history = await user_repository.get_sverka_history(current_user.id)


    return templates.TemplateResponse(
        "sverka/sverka_history.html",
        {
            "request": request,
            "items": history,
            "user_email": current_user.email,
            "user_id": current_user.id,
            "telegram_username": current_user.work_telegram,
        },
    )
    
    
@router.get("/sverka/history/detail", response_class=HTMLResponse)
async def sverka_history_detail(
    request: Request,
    vacancy_id: str = Query(...),
    current_user = Depends(get_current_user_from_cookie),
):
    """
    Берёт ВСЕ сверки по user_id + vacancy_id
    и отдаёт их в шаблон sverka_result_list.html.
    """
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)

    rows = await vacancy_repository.get_sverka_history_by_user_and_vacancy(
        user_id=current_user.id,
        vacancy_id=vacancy_id,
    )

    # приводим к формату, как у тебя в /sverka/result/{task_id}
    # и генерируем slug для записей, у которых его нет
    def slug6() -> str:
        chars = string.ascii_lowercase + string.digits
        return ''.join(random.choice(chars) for _ in range(6))
    
    results: list[dict] = []
    for row in rows:
        # Если slug отсутствует, генерируем его и обновляем в БД
        if not row.slug:
            new_slug = slug6()
            await vacancy_repository.update_sverka_slug(row.id, new_slug)
            row.slug = new_slug
        
        results.append(
            {
                "resume_json": row.sverka_json,
                "filename": row.candidate_fullname or f"candidate_{row.id}",
                "candidate_fullname": row.candidate_fullname,
                'slug': row.slug,
            }
        )

    tg_username = norm_tg(current_user.work_telegram or "")
    task_id = f"history-{vacancy_id}"

    return templates.TemplateResponse(
        "sverka/sverka_history_result.html",
        {
            "request": request,
            "task_id": task_id,
            "vacancy_id": vacancy_id,
            "results": results,
            "tg_username": tg_username,
            "user_email": current_user.email,
            "user_id": current_user.id,
        },
    )


@router.get("/sverka/history/result-{vacancy_id}/{slug}", response_class=HTMLResponse)
async def sverka_result_history_one(
    request: Request,
    vacancy_id: str,
    slug: str,
    tg_username: Annotated[str, Query(...)],
    current_user = Depends(get_current_user_from_cookie),
):
    """
    Показать ОДНУ уже сохранённую сверку из истории:
    - vacancy_id берём из URL (history-DO10493 → DO10493),
    - index — номер сверки по этой вакансии для текущего пользователя.
    НИКАКОЙ новой сверки, только подставляем сохранённый JSON в шаблон.
    """
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)

    # 1. Достаём все сверки по вакансии и пользователю
    sverkas = await user_repository.get_sverka_by_vac_id_and_slug(
        vacancy_id=vacancy_id,
        user_id=current_user.id,
        slug=slug,
    )

    if not sverkas:
        raise HTTPException(status_code=404, detail="Сверки по этой вакансии не найдены")


    # 2. Берём нужную запись
    resume_json = sverkas.sverka_json or {}
    candidate_fullname = sverkas.candidate_fullname or "Кандидат"

    # 3. Формируем HTML анализа из УЖЕ сохранённого JSON
    ai_text = display_analysis(resume_json)

    # 4. Контакты для блока и кнопок
    contacts = resume_json.get("candidate", {}).get("contacts", {})

    # 5. Просто рендерим твой sverka_result.html
    return templates.TemplateResponse(
        "sverka/sverka_result.html",
        {
            "request": request,
            "task_id": f"history-{vacancy_id}",  # для шаблона можно что-то подставить
            "ai_text": ai_text,
            "vacancy_id": vacancy_id,
            "candidate_fullname": candidate_fullname,
            "contacts": contacts,
            "tg_username": tg_username,
            "user_email": current_user.email,
            "user_id": current_user.id,
        },
    )


    
