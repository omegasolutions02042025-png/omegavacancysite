from pathlib import Path
from uuid import uuid4
import asyncio
import json
import os
from typing import List

from fastapi import (
    APIRouter,
    Depends,
    Request,
    UploadFile,
    File,
    HTTPException,
    Body,
)
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from redis.asyncio import Redis

from app.core.current_user import get_current_user_from_cookie
from app.core.gpt import gpt_generator

from app.database.candidate_db import CandidateProfileDB, CandidateRepository
from app.models.candidate import GPTCandidateProfile
from app.core.utils import process_pdf, process_docx, process_txt, process_rtf

router = APIRouter(prefix="/candidate", tags=["candidates"])

BASE_DIR = Path(__file__).resolve().parents[1]
templates_dir = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

candidate_repo = CandidateRepository()

# =========================
# Redis для задач импорта
# =========================

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis: Redis = Redis.from_url(REDIS_URL, decode_responses=True)

CAND_UPLOAD_PREFIX = "candidate_upload:"
CAND_UPLOAD_TTL_SECONDS = 60 * 60  # 1 час


@router.get("/upload/result/{task_id}")
async def upload_result_page(
    task_id: str,
    request: Request,
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Страница с результатами импорта нескольких кандидатов.
    Данные берём из Redis по task_id, чтобы при обновлении страницы ничего не терялось.
    """
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)

    key = f"{CAND_UPLOAD_PREFIX}{task_id}"
    raw = await redis.get(key)
    if not raw:
        raise HTTPException(status_code=404, detail="Задача импорта не найдена или устарела")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Некорректные данные задачи импорта")

    # Простая защита: показываем только свои задачи
    if data.get("user_id") != current_user.id:
        raise HTTPException(status_code=403, detail="Доступ запрещён")

    raw_results = data.get("results") or []
    errors = data.get("errors") or []

    # Проверяем актуальное состояние профиля в БД:
    # если хотя бы одно поле профиля = None → подсвечиваем жёлтым,
    # если None нет вообще → зелёным.
    results: list[dict] = []
    for item in raw_results:
        cid = item.get("candidate_id")
        if not cid:
            item["completeness"] = "unknown"
            results.append(item)
            continue

        db_candidate = await candidate_repo.get_candidate_by_id_and_user_id(
            number_for_user=int(cid),
            user_id=current_user.id,
        )
        if not db_candidate:
            item["completeness"] = "unknown"
            results.append(item)
            continue

        data_dict = db_candidate.model_dump()
        # Эти служебные поля не учитываем при проверке заполненности
        ignore_keys = {"id", "user_id", "number_for_user"}
        has_none = any(
            (v is None)
            for k, v in data_dict.items()
            if k not in ignore_keys
        )

        item["completeness"] = "incomplete" if has_none else "complete"
        results.append(item)

    return templates.TemplateResponse(
        "candidate/candidate_upload_results.html",
        {
            "request": request,
            "user_email": current_user.email,
            "user_id": current_user.id,
            "results": results,
            "errors": errors,
        },
    )


@router.get("/")
async def get_candidates(
    request: Request,
    current_user=Depends(get_current_user_from_cookie),
):
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)

    candidates = await candidate_repo.get_all_candidates_for_user(current_user.id)
    return templates.TemplateResponse(
        "candidate/candidate.html",
        {
            "request": request,
            "user_email": current_user.email,
            "user_id": current_user.id,
            "candidates": candidates,
        },
    )


@router.get("/add")
async def add_candidate(
    request: Request,
    current_user=Depends(get_current_user_from_cookie),
):
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)
    return templates.TemplateResponse(
        "candidate/candidate_add.html",
        {
            "request": request,
            "user_email": current_user.email,
            "user_id": current_user.id,
        },
    )


# ============================================
# СТРАНИЦА РЕДАКТИРОВАНИЯ КАНДИДАТА (HTML)
# ============================================

@router.get("/edit/{candidate_id}")
async def edit_candidate_page(
    candidate_id: int,
    request: Request,
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Рендерим страницу профиля кандидата.
    JS на странице сам сходит в /candidate/api/{id}, подставит данные и позволит сохранить изменения.
    """
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)

    candidate = await candidate_repo.get_candidate_profile_for_candidate_id_and_user_id(
        int(candidate_id), current_user.id
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Кандидат не найден")

    return templates.TemplateResponse(
        "candidate/candidate_profile.html",
        {
            "request": request,
            "candidate_id": candidate_id,
            "user_email": current_user.email,
            "user_id": current_user.id,
            
        },
    )


# ============================================
# API: ПОЛУЧИТЬ ПРОФИЛЬ КАНДИДАТА (JSON)
# ============================================

@router.get("/api/{candidate_id}", response_class=JSONResponse)
async def get_candidate_api(
    candidate_id: int,
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Возвращаем JSON профиля кандидата для фронта.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    candidate = await candidate_repo.get_candidate_profile_for_candidate_id_and_user_id(
        candidate_id, current_user.id
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Кандидат не найден")

    # SQLModel → dict
    return JSONResponse(candidate.model_dump())


# ============================================
# API: ОБНОВИТЬ ПРОФИЛЬ КАНДИДАТА (JSON)
# ============================================

@router.put("/edit/{candidate_id}", response_class=JSONResponse)
async def update_candidate_api(
    candidate_id: int,
    payload: dict = Body(...),
    current_user=Depends(get_current_user_from_cookie),
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    candidate = await candidate_repo.get_candidate_profile_for_candidate_id_and_user_id(
        candidate_id, current_user.id
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Кандидат не найден")

    success = await candidate_repo.update_candidate_for_user(
        candidate_id, current_user.id, payload
    )
    if not success:
        raise HTTPException(status_code=400, detail="Не удалось обновить кандидата")

    return JSONResponse({"status": "ok", "redirect_url": "/candidate"})


# ============================================
# UPLOAD: СОХРАНИТЬ НЕСКОЛЬКО РЕЗЮМЕ → GPT → БД
# ============================================

@router.post("/upload")
async def upload_candidate(
    request: Request,
    current_user=Depends(get_current_user_from_cookie),
    # alias="files" чтобы совпало с name="files" в <input>
    resume_files: List[UploadFile] = File(..., alias="files"),
):
    """
    Загружаем одно или несколько резюме, вытаскиваем текст, отправляем ВСЕ в GPT параллельно,
    валидируем ответы и создаём записи кандидатов в БД.
    После этого делаем редирект на страницу результатов импорта.
    """
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)

    if not resume_files:
        return JSONResponse(
            status_code=400,
            content={"error": "Не передано ни одного файла."},
        )

    try:
        upload_dir = Path("uploaded_resumes")
        upload_dir.mkdir(parents=True, exist_ok=True)

        # 1. Сохраняем файлы и вытаскиваем текст
        texts: List[str] = []
        filenames: List[str] = []
        errors: List[dict] = []

        for file in resume_files:
            original_name = file.filename or "resume"
            ext = Path(original_name).suffix.lower()  # .pdf / .docx / .txt / .rtf

            if ext not in (".pdf", ".docx", ".txt", ".rtf"):
                errors.append({
                    "filename": original_name,
                    "status": "error",
                    "error": f"Неподдерживаемый формат файла: {ext}",
                })
                continue

            safe_name = f"{uuid4().hex}{ext}"
            file_path = upload_dir / safe_name

            file_bytes = await file.read()
            with file_path.open("wb") as f:
                f.write(file_bytes)
            print("File saved:", file_path)

            if ext == ".pdf":
                text = process_pdf(file_path)
            elif ext == ".docx":
                text = process_docx(file_path)
            elif ext == ".txt":
                text = process_txt(file_path)
            else:  # .rtf
                text = process_rtf(file_path)

            if not text.strip():
                errors.append({
                    "filename": original_name,
                    "status": "error",
                    "error": "Файл не содержит текста после извлечения.",
                })
                continue

            texts.append(text)
            filenames.append(original_name)

        if not texts and errors:
            # Все файлы невалидны
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Ни одно резюме не удалось обработать.",
                    "details": errors,
                },
            )

        # 2. GPT → сырые JSON по всем резюме параллельно
        gpt_tasks = [gpt_generator.create_candidate_profile(t) for t in texts]
        gpt_results = await asyncio.gather(*gpt_tasks, return_exceptions=True)

        # 3. Валидация и сохранение в БД
        created_candidates: List[dict] = []

        for original_name, gpt_raw in zip(filenames, gpt_results):
            if isinstance(gpt_raw, Exception):
                errors.append({
                    "filename": original_name,
                    "status": "error",
                    "error": f"Ошибка при вызове GPT: {gpt_raw}",
                })
                continue

            try:
                if isinstance(gpt_raw, str):
                    gpt_profile = GPTCandidateProfile.model_validate_json(gpt_raw)
                else:
                    gpt_profile = GPTCandidateProfile.model_validate(gpt_raw)
            except Exception as e:
                errors.append({
                    "filename": original_name,
                    "status": "error",
                    "error": "Ошибка получения результата от модели GPT. Извините, не удалось корректно разобрать это резюме.",
                })
                continue

            db_candidate = await candidate_repo.candidate_profile_to_db(
                profile=gpt_profile,
                user_id=current_user.id,
            )
            created_candidates.append({
                "filename": original_name,
                "status": "ok",
                "candidate_id": db_candidate.number_for_user,
                "full_name": db_candidate.first_name + " " + db_candidate.last_name + " " + db_candidate.middle_name if db_candidate.middle_name else "",
                "title": db_candidate.title if db_candidate.title else "",
            })

        # 4. Если никого не удалось создать – возвращаем ошибку
        if not created_candidates:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Не удалось создать ни одного кандидата.",
                    "details": errors,
                },
            )

        # 5. Сохраняем задачу в Redis и редиректим на страницу результатов
        task_id = uuid4().hex
        key = f"{CAND_UPLOAD_PREFIX}{task_id}"
        task_data = {
            "user_id": current_user.id,
            "results": created_candidates,
            "errors": errors,
        }
        await redis.set(
            key,
            json.dumps(task_data, ensure_ascii=False),
            ex=CAND_UPLOAD_TTL_SECONDS,
        )

        return RedirectResponse(
            url=f"/candidate/upload/result/{task_id}",
            status_code=303,
        )

    except Exception as e:
        print("Error in /candidate/upload:", e)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )


@router.delete("/delete/{candidate_id}")
async def delete_candidate(
    candidate_id: int,
    current_user=Depends(get_current_user_from_cookie),
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    success = await candidate_repo.delete_candidate_for_user(candidate_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Кандидат не найден")
    
    return JSONResponse({"status": "ok"})