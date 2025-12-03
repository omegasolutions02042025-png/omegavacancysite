from pathlib import Path
from uuid import uuid4
import asyncio
import json
import os
import logging
import traceback
import re
from typing import List

from fastapi import (
    APIRouter,
    Depends,
    Request,
    UploadFile,
    File,
    HTTPException,
    Body,
    Query,
)
from typing import Optional
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from redis.asyncio import Redis
import time

from app.core.current_user import get_current_user_from_cookie
from app.core.gpt import gpt_generator

from app.database.candidate_db import CandidateProfileDB, CandidateRepository
from app.database.candidate_profile_db import CandidateProfileRepository
from app.database.user_db import UserRepository
from app.models.candidate import GPTCandidateProfile
from app.models.users import Grade, CandidateProfile
from app.core.utils import process_pdf, process_docx, process_txt, process_rtf
from app.database.database import UserRole
import logging

router = APIRouter(prefix="/candidate", tags=["candidates"])

BASE_DIR = Path(__file__).resolve().parents[1]
templates_dir = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

candidate_repo = CandidateRepository()
candidate_profile_repo = CandidateProfileRepository()
user_repo = UserRepository()

logger = logging.getLogger(__name__)

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
    Страница подписывается на SSE для получения результатов в реальном времени.
    """
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)

    key = f"{CAND_UPLOAD_PREFIX}{task_id}"
    raw = await redis.get(key)
    
    # Если задача не найдена, всё равно показываем страницу (может быть ещё не создана)
    initial_results = []
    initial_errors = []
    status = "processing"
    
    if raw:
        try:
            data = json.loads(raw)
            # Простая защита: показываем только свои задачи
            if data.get("user_id") != current_user.id:
                raise HTTPException(status_code=403, detail="Доступ запрещён")
            
            initial_results = data.get("results") or []
            initial_errors = data.get("errors") or []
            status = data.get("status", "processing")
        except json.JSONDecodeError:
            pass

    return templates.TemplateResponse(
        "candidate/candidate_upload_results.html",
        {
            "request": request,
            "user_email": current_user.email,
            "user_id": current_user.id,
            "results": initial_results,
            "errors": initial_errors,
            "task_id": task_id,
            "status": status,
        },
    )


@router.get("/upload/stream/{task_id}")
async def upload_result_stream(
    task_id: str,
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Server-Sent Events endpoint для получения результатов обработки в реальном времени.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    key = f"{CAND_UPLOAD_PREFIX}{task_id}"
    
    async def event_generator():
        last_processed = 0
        last_results_count = 0
        last_errors_count = 0
        
        while True:
            raw = await redis.get(key)
            if not raw:
                # Задача ещё не создана или удалена
                await asyncio.sleep(0.5)
                continue
            
            try:
                data = json.loads(raw)
                
                # Проверка доступа
                if data.get("user_id") != current_user.id:
                    yield f"data: {json.dumps({'error': 'Доступ запрещён'}, ensure_ascii=False)}\n\n"
                    break
                
                status = data.get("status", "processing")
                processed = data.get("processed", 0)
                total = data.get("total", 0)
                raw_results = data.get("results", [])
                raw_errors = data.get("errors", [])
                
                # Проверяем, появились ли новые результаты
                new_results = raw_results[last_results_count:]
                new_errors = raw_errors[last_errors_count:]
                
                if new_results or new_errors or processed != last_processed:
                    # Обновляем completeness для новых результатов
                    results_with_completeness = []
                    for item in raw_results:
                        cid = item.get("candidate_id")
                        if cid:
                            try:
                                db_candidate = await candidate_repo.get_candidate_by_id_and_user_id(
                                    number_for_user=int(cid),
                                    user_id=current_user.id,
                                )
                                if db_candidate:
                                    data_dict = db_candidate.model_dump()
                                    ignore_keys = {"id", "user_id", "number_for_user"}
                                    has_none = any(
                                        (v is None)
                                        for k, v in data_dict.items()
                                        if k not in ignore_keys
                                    )
                                    item["completeness"] = "incomplete" if has_none else "complete"
                                else:
                                    item["completeness"] = "unknown"
                            except:
                                item["completeness"] = "unknown"
                        else:
                            item["completeness"] = "unknown"
                        results_with_completeness.append(item)
                    
                    # Отправляем обновление
                    update_data = {
                        "status": status,
                        "processed": processed,
                        "total": total,
                        "results": results_with_completeness,
                        "errors": raw_errors,
                        "new_results": new_results,
                        "new_errors": new_errors,
                    }
                    yield f"data: {json.dumps(update_data, ensure_ascii=False)}\n\n"
                    
                    last_processed = processed
                    last_results_count = len(raw_results)
                    last_errors_count = len(raw_errors)
                
                # Если обработка завершена, отправляем финальное сообщение и закрываем соединение
                if status == "completed":
                    yield f"data: {json.dumps({'status': 'completed'}, ensure_ascii=False)}\n\n"
                    break
                
            except json.JSONDecodeError:
                pass
            
            await asyncio.sleep(0.5)  # Проверяем каждые 500ms
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/")
async def get_candidates(
    request: Request,
    current_user=Depends(get_current_user_from_cookie),
    search: Optional[str] = Query(None, alias="search"),
    specialization: Optional[str] = Query(None, alias="specialization"),
):
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)

    from app.database.dropdown_db import DropdownOptions
    
    dropdown_repo = DropdownOptions()
    candidates_raw = await candidate_repo.get_all_candidates_for_user(
        current_user.id,
        search_query=search,
        specialization_filter=specialization,
    )
    specializations = await dropdown_repo.get_candidate_specializations(current_user.id)
    
    # Проверяем полноту заполнения для каждого кандидата
    candidates_with_completeness = []
    for candidate in candidates_raw:
        data_dict = candidate.model_dump()
        # Эти служебные поля не учитываем при проверке заполненности
        ignore_keys = {"id", "user_id", "number_for_user"}
        has_none = any(
            (v is None)
            for k, v in data_dict.items()
            if k not in ignore_keys
        )
        
        # Добавляем поле completeness к объекту кандидата
        candidate_dict = {
            "candidate": candidate,
            "completeness": "incomplete" if has_none else "complete"
        }
        candidates_with_completeness.append(candidate_dict)
    
    return templates.TemplateResponse(
        "candidate/candidate.html",
        {
            "request": request,
            "user_email": current_user.email,
            "user_id": current_user.id,
            "candidates": candidates_with_completeness,
            "specializations": specializations,
            "current_search": search or "",
            "current_specialization": specialization or "",
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
# ДАШБОРД КАНДИДАТА (ЛИЧНЫЙ КАБИНЕТ)
# ============================================

@router.get("/dashboard", response_class=HTMLResponse)
async def candidate_dashboard(
    request: Request,
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Страница личного кабинета кандидата.
    
    Показывает профиль кандидата, загруженное резюме, статистику откликов и сообщения.
    Использует новый шаблон candidate/dashboard.html с "Dark Tech" дизайном.
    """
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)
    
    # Проверяем, что пользователь имеет роль CANDIDATE
    if current_user.role != UserRole.CANDIDATE:
        raise HTTPException(
            status_code=403,
            detail="Доступ разрешен только кандидатам"
        )
    
    # Получаем профиль кандидата (используем relationship или репозиторий)
    # Сначала пробуем через relationship, если доступно
    profile: Optional[CandidateProfile] = None
    if hasattr(current_user, 'candidate_profile') and current_user.candidate_profile:
        profile = current_user.candidate_profile
    else:
        # Если relationship не загружен, используем репозиторий
        profile = await candidate_profile_repo.get_by_user_id(current_user.id)
    
    # Формируем данные профиля для шаблона (если профиль существует)
    profile_data = None
    if profile:
        profile_data = {
            "id": profile.id,
            "user_id": profile.user_id,
            "grade": profile.grade.value if profile.grade else None,
            "stack": profile.stack if profile.stack else None,
            "bio": profile.bio if profile.bio else None,
            "experience_years": profile.experience_years if profile.experience_years else None,
            "resume_url": profile.resume_url if profile.resume_url else None,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        }
    
    # Рендерим новый шаблон candidate/dashboard.html
    return templates.TemplateResponse(
        "candidate/dashboard.html",
        {
            "request": request,
            "user": current_user,
            "profile": profile_data,
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
    task_id: Optional[str] = Query(None),
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
            "task_id": task_id,  # Передаем task_id в шаблон
        },
    )


@router.get("/open/{candidate_id}")
async def open_candidate_readonly(
    candidate_id: int,
    request: Request,
    current_user=Depends(get_current_user_from_cookie),
):
    """
    HTML-страница только для просмотра карточки кандидата.
    Никаких форм/редактирования — только отображение данных из БД.
    """
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)

    candidate = await candidate_repo.get_candidate_profile_for_candidate_id_and_user_id(
        int(candidate_id), current_user.id
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Кандидат не найден")

    return templates.TemplateResponse(
        "candidate/candidate_open.html",
        {
            "request": request,
            "candidate_id": candidate_id,
            "candidate": candidate,
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

@router.post("/create", response_class=JSONResponse)
async def create_candidate_api(
    payload: dict = Body(...),
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Создать нового кандидата вручную через форму
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Преобразуем payload в GPTCandidateProfile для использования candidate_profile_to_db
    # Формируем минимальный профиль из payload
    from app.models.candidate import PersonalBlock, MainBlock, LocationBlock
    
    personal = PersonalBlock(
        first_name=payload.get("first_name"),
        last_name=payload.get("last_name"),
        middle_name=payload.get("middle_name"),
        title=payload.get("title"),
        email=payload.get("email"),
        telegram=payload.get("telegram"),
        phone=payload.get("phone"),
        linkedin=payload.get("linkedin"),
        github=payload.get("github"),
        portfolio=payload.get("portfolio"),
        about=payload.get("about"),
    )
    
    main = MainBlock(
        salary_usd=payload.get("salary_usd"),
        currencies=payload.get("currencies"),
        grade=payload.get("grade"),
        work_format=payload.get("work_format"),
        employment_type=payload.get("employment_type"),
        company_types=payload.get("company_types"),
        specializations=payload.get("specializations"),
        skills=payload.get("skills"),
    )
    
    location = LocationBlock(
        city=payload.get("city"),
        timezone=payload.get("timezone"),
        regions=payload.get("regions"),
        countries=payload.get("countries"),
        relocation=payload.get("relocation"),
    )
    
    gpt_profile = GPTCandidateProfile(
        personal=personal,
        main=main,
        location=location,
        experience=payload.get("experience", []),
        education=payload.get("education", []),
        courses=payload.get("courses", []),
        projects=payload.get("projects", []),
        english_level=payload.get("english_level"),
    )
    
    # Создаем кандидата (это автоматически создаст чат, если есть telegram или email)
    db_candidate = await candidate_repo.candidate_profile_to_db(
        profile=gpt_profile,
        user_id=current_user.id,
    )
    
    # Обновляем дополнительные поля, которые не вошли в GPTCandidateProfile
    if payload.get("experience") or payload.get("education") or payload.get("courses") or payload.get("projects"):
        await candidate_repo.update_candidate_for_user(
            db_candidate.number_for_user,
            current_user.id,
            {
                "experience": payload.get("experience", []),
                "education": payload.get("education", []),
                "courses": payload.get("courses", []),
                "projects": payload.get("projects", []),
            }
        )
    
    return JSONResponse({
        "status": "ok",
        "redirect_url": f"/candidate/edit/{db_candidate.number_for_user}"
    })


@router.put("/edit/{candidate_id}", response_class=JSONResponse)
async def update_candidate_api(
    candidate_id: int,
    payload: dict = Body(...),
    current_user=Depends(get_current_user_from_cookie),
    task_id: Optional[str] = Query(None),
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    candidate = await candidate_repo.get_candidate_profile_for_candidate_id_and_user_id(
        candidate_id, current_user.id
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Кандидат не найден")

    # Сохраняем старые значения telegram и email для проверки
    old_telegram = candidate.telegram
    old_email = candidate.email

    success = await candidate_repo.update_candidate_for_user(
        candidate_id, current_user.id, payload
    )
    if not success:
        raise HTTPException(status_code=400, detail="Не удалось обновить кандидата")

    # Если есть task_id - возвращаем на страницу результатов, иначе на список кандидатов
    redirect_url = f"/candidate/upload/result/{task_id}" if task_id else "/candidate"
    return JSONResponse({"status": "ok", "redirect_url": redirect_url})


# ============================================
# ФОНОВАЯ ОБРАБОТКА ФАЙЛОВ
# ============================================

async def process_candidate_files_background(
    files_data: List[dict],
    user_id: int,
    task_id: str,
):
    """
    Фоновая обработка файлов резюме.
    Обрабатывает каждый файл последовательно и обновляет Redis по мере готовности.
    """
    key = f"{CAND_UPLOAD_PREFIX}{task_id}"
    results: List[dict] = []
    errors: List[dict] = []
    
    # Проверяем, есть ли уже данные в Redis (начальные ошибки)
    existing_raw = await redis.get(key)
    if existing_raw:
        try:
            existing_data = json.loads(existing_raw)
            errors = existing_data.get("errors", [])
            results = existing_data.get("results", [])
            total_files = existing_data.get("total", len(files_data))
            initial_processed = existing_data.get("processed", 0)
        except:
            total_files = len(files_data)
            initial_processed = 0
    else:
        total_files = len(files_data)
        initial_processed = 0
        # Инициализируем задачу в Redis
        initial_data = {
            "user_id": user_id,
            "status": "processing",
            "total": total_files,
            "processed": initial_processed,
            "results": [],
            "errors": [],
        }
        await redis.set(
            key,
            json.dumps(initial_data, ensure_ascii=False),
            ex=CAND_UPLOAD_TTL_SECONDS,
        )
    
    upload_dir = Path("uploaded_resumes")
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    for idx, file_data in enumerate(files_data):
        original_name = file_data["filename"]
        file_bytes = file_data["bytes"]
        ext = file_data["ext"]
        
        try:
            # Сохраняем файл
            safe_name = f"{uuid4().hex}{ext}"
            file_path = upload_dir / safe_name
            with file_path.open("wb") as f:
                f.write(file_bytes)
            
            # Извлекаем текст
            if ext == ".pdf":
                text = process_pdf(file_path)
            elif ext == ".docx":
                text = process_docx(file_path)
            elif ext == ".txt":
                text = process_txt(file_path)
            else:  # .rtf
                text = process_rtf(file_path)
            
            if not text.strip():
                error_item = {
                    "filename": original_name,
                    "status": "error",
                    "error": "Файл не содержит текста после извлечения.",
                }
                errors.append(error_item)
                # Обновляем Redis
                await update_task_progress(key, results, errors, idx + 1, total_files)
                continue
            
            # Отправляем в GPT
            try:
                gpt_raw = await gpt_generator.create_candidate_profile(text)
            except Exception as e:
                error_item = {
                    "filename": original_name,
                    "status": "error",
                    "error": f"Ошибка при вызове GPT: {str(e)}",
                }
                errors.append(error_item)
                await update_task_progress(key, results, errors, idx + 1, total_files)
                continue
            
            # Валидируем ответ GPT
            try:
                if isinstance(gpt_raw, str):
                    gpt_profile = GPTCandidateProfile.model_validate_json(gpt_raw)
                else:
                    gpt_profile = GPTCandidateProfile.model_validate(gpt_raw)
            except Exception as e:
                error_item = {
                    "filename": original_name,
                    "status": "error",
                    "error": "Ошибка получения результата от модели GPT. Извините, не удалось корректно разобрать это резюме.",
                }
                errors.append(error_item)
                await update_task_progress(key, results, errors, idx + 1, total_files)
                continue
            
            # Сохраняем в БД
            db_candidate = await candidate_repo.candidate_profile_to_db(
                profile=gpt_profile,
                user_id=user_id,
            )
            
            # Формируем полное имя
            name_parts = []
            if db_candidate.first_name:
                name_parts.append(db_candidate.first_name)
            if db_candidate.last_name:
                name_parts.append(db_candidate.last_name)
            if db_candidate.middle_name:
                name_parts.append(db_candidate.middle_name)
            full_name = " ".join(name_parts) if name_parts else "Без имени"
            
            result_item = {
                "filename": original_name,
                "status": "ok",
                "candidate_id": db_candidate.number_for_user,
                "full_name": full_name,
                "title": db_candidate.title if db_candidate.title else "",
            }
            results.append(result_item)
            
            # Обновляем Redis после каждого успешного кандидата
            await update_task_progress(key, results, errors, initial_processed + idx + 1, total_files)
            
        except Exception as e:
            print(f"Error processing file {original_name}:", e)
            error_item = {
                "filename": original_name,
                "status": "error",
                "error": f"Внутренняя ошибка при обработке: {str(e)}",
            }
            errors.append(error_item)
            await update_task_progress(key, results, errors, initial_processed + idx + 1, total_files)
    
    # Финальное обновление со статусом "completed"
    final_data = {
        "user_id": user_id,
        "status": "completed",
        "total": total_files,
        "processed": total_files,
        "results": results,
        "errors": errors,
    }
    await redis.set(
        key,
        json.dumps(final_data, ensure_ascii=False),
        ex=CAND_UPLOAD_TTL_SECONDS,
    )


async def update_task_progress(
    key: str,
    results: List[dict],
    errors: List[dict],
    processed: int,
    total: int,
):
    """Обновляет прогресс задачи в Redis."""
    data = {
        "status": "processing",
        "total": total,
        "processed": processed,
        "results": results,
        "errors": errors,
    }
    # Получаем user_id из существующих данных
    existing = await redis.get(key)
    if existing:
        try:
            existing_data = json.loads(existing)
            data["user_id"] = existing_data.get("user_id")
        except:
            pass
    
    await redis.set(
        key,
        json.dumps(data, ensure_ascii=False),
        ex=CAND_UPLOAD_TTL_SECONDS,
    )


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
    Загружаем файлы, валидируем их и запускаем фоновую обработку.
    Сразу возвращаем task_id и редиректим на страницу результатов.
    """
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)

    if not resume_files:
        return JSONResponse(
            status_code=400,
            content={"error": "Не передано ни одного файла."},
        )

    try:
        # 1. Валидация и сохранение файлов в память
        files_data: List[dict] = []
        initial_errors: List[dict] = []

        for file in resume_files:
            original_name = file.filename or "resume"
            ext = Path(original_name).suffix.lower()

            if ext not in (".pdf", ".docx", ".txt", ".rtf"):
                initial_errors.append({
                    "filename": original_name,
                    "status": "error",
                    "error": f"Неподдерживаемый формат файла: {ext}",
                })
                continue

            file_bytes = await file.read()
            files_data.append({
                "filename": original_name,
                "bytes": file_bytes,
                "ext": ext,
            })

        if not files_data and initial_errors:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Ни одно резюме не удалось обработать.",
                    "details": initial_errors,
                },
            )

        # 2. Создаём задачу и запускаем фоновую обработку
        task_id = uuid4().hex
        total_files = len(files_data) + len(initial_errors)
        
        # Сохраняем начальное состояние задачи
        initial_data = {
            "user_id": current_user.id,
            "status": "processing" if files_data else "completed",
            "total": total_files,
            "processed": len(initial_errors),
            "results": [],
            "errors": initial_errors,
        }
        key = f"{CAND_UPLOAD_PREFIX}{task_id}"
        await redis.set(
            key,
            json.dumps(initial_data, ensure_ascii=False),
            ex=CAND_UPLOAD_TTL_SECONDS,
        )

        # Запускаем фоновую обработку только если есть файлы для обработки
        if files_data:
            asyncio.create_task(
                process_candidate_files_background(
                    files_data=files_data,
                    user_id=current_user.id,
                    task_id=task_id,
                )
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


@router.post("/add-chat/{candidate_id}")
async def add_chat_to_candidate(
    candidate_id: int,
    request: Request,
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Добавить чат для кандидата (Telegram или Email)
    Извлекает реальный Telegram user_id через Telethon и сохраняет в UserComunication
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Получаем данные из JSON body
    try:
        body = await request.json()
        message_type = body.get("message_type")
    except:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    if not message_type:
        raise HTTPException(status_code=400, detail="message_type обязателен")
    
    if message_type not in ["telegram", "email"]:
        raise HTTPException(status_code=400, detail="message_type должен быть 'telegram' или 'email'")
    
    # Получаем кандидата
    candidate = await candidate_repo.get_candidate_profile_for_candidate_id_and_user_id(
        candidate_id, current_user.id
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Кандидат не найден")
    
    # Формируем полное имя
    name_parts = []
    if candidate.first_name:
        name_parts.append(candidate.first_name)
    if candidate.last_name:
        name_parts.append(candidate.last_name)
    if candidate.middle_name:
        name_parts.append(candidate.middle_name)
    full_name = " ".join(name_parts) if name_parts else "Без имени"
    
    # Проверяем наличие контакта
    if message_type == "telegram" and not candidate.telegram:
        raise HTTPException(status_code=400, detail="У кандидата не указан Telegram")
    if message_type == "email" and not candidate.email:
        raise HTTPException(status_code=400, detail="У кандидата не указан Email")
    
    # Проверяем, есть ли уже чат с этим кандидатом
    from app.database.chat_db import chat_repository, Chat
    from app.database.user_db import UserRepository
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    user_repo = UserRepository()
    
    async with AsyncSession(candidate_repo.engine) as session:
        stmt = select(Chat).where(
            Chat.user_id == current_user.id,
            Chat.candidate_fullname == full_name,
            Chat.message_type == message_type
        ).limit(1)
        result = await session.execute(stmt)
        existing_chat = result.scalar_one_or_none()
    
    if existing_chat:
        return JSONResponse({
            "status": "ok",
            "message": f"Чат {message_type} уже существует для этого кандидата",
            "already_exists": True
        })
    
    # Для Telegram - извлекаем реальный user_id через Telethon
    telegram_user_id = None
    if message_type == "telegram":
        try:
            from app.core.telethon_check import manager
            from telethon import TelegramClient
            from telethon.tl.types import User
            
            client: TelegramClient = await manager.get_client(current_user.id)
            if not client:
                raise HTTPException(status_code=400, detail="Telegram клиент не найден")
            
            if not client.is_connected():
                await client.connect()
            
            if not await client.is_user_authorized():
                raise HTTPException(status_code=401, detail="Необходима авторизация Telegram")
            
            # Получаем Telegram username из профиля кандидата
            telegram_username = candidate.telegram.strip()
            if telegram_username.startswith("@"):
                telegram_username = telegram_username[1:]
            
            print(f"[CANDIDATE_ADD_CHAT] Получение entity для username=@{telegram_username}")
            
            # Получаем entity по username (как в send_message_by_username)
            entity = await client.get_entity(telegram_username)
            
            # Проверяем, что это пользователь (User), а не канал/группа
            if isinstance(entity, User):
                telegram_user_id = entity.id
                print(f"[CANDIDATE_ADD_CHAT] ✅ Получен реальный Telegram user_id={telegram_user_id} для username=@{telegram_username}")
            else:
                raise HTTPException(status_code=400, detail="Это не личный чат с пользователем")
                
        except HTTPException:
            raise
        except Exception as e:
            print(f"[CANDIDATE_ADD_CHAT] ⚠️ Ошибка получения Telegram user_id: {e}")
            import traceback
            print(f"[CANDIDATE_ADD_CHAT] Traceback:\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Не удалось получить Telegram user_id: {str(e)}")
    
    # Сохраняем в UserComunication
    try:
        await user_repo.create_user_comunication(
            user_id=current_user.id,
            email_user=candidate.email if message_type == "email" else None,
            telegram_user_id=telegram_user_id if message_type == "telegram" else None,
            vacancy_id=None,
            candidate_fullname=full_name
        )
        print(f"[CANDIDATE_ADD_CHAT] ✅ Сохранено в UserComunication: message_type={message_type}, telegram_user_id={telegram_user_id}, email={candidate.email if message_type == 'email' else None}")
    except Exception as e:
        print(f"[CANDIDATE_ADD_CHAT] ⚠️ Ошибка сохранения в UserComunication: {e}")
        # Не прерываем выполнение, продолжаем создание чата
    
    # Перезапускаем обработчики входящих сообщений
    try:
        if message_type == "telegram":
            # Перезапускаем Telethon сессию для прослушивания новых чатов
            from app.core.telethon_check import manager
            print(f"[CANDIDATE_ADD_CHAT] Перезапускаем Telethon сессию для user_id={current_user.id}")
            await manager.restart_session(current_user.id)
            print(f"[CANDIDATE_ADD_CHAT] ✅ Telethon сессия перезапущена")
        elif message_type == "email":
            # Перезапускаем Email listener для прослушивания новых email
            from app.core.email_listener import email_listener
            print(f"[CANDIDATE_ADD_CHAT] Перезапускаем Email listener для user_id={current_user.id}")
            await email_listener.restart_for_user(current_user.id)
            print(f"[CANDIDATE_ADD_CHAT] ✅ Email listener перезапущен")
    except Exception as e:
        print(f"[CANDIDATE_ADD_CHAT] ⚠️ Ошибка перезапуска обработчиков: {e}")
        import traceback
        print(f"[CANDIDATE_ADD_CHAT] Traceback:\n{traceback.format_exc()}")
        # Не прерываем выполнение, чат уже создан
    
    # Создаем приветственное сообщение для чата
    try:
        await chat_repository.add_message(
            user_id=current_user.id,
            candidate_id=candidate_id,
            candidate_fullname=full_name,
            vacancy_id=None,
            message_type=message_type,
            sender="user",
            message_text=f"Чат создан для кандидата {full_name}",
            vacancy_title=None,
        )
        print(f"[CANDIDATE_ADD_CHAT] ✅ Создан {message_type} чат для кандидата {full_name} (ID: {candidate_id})")
        return JSONResponse({
            "status": "ok",
            "message": f"Чат {message_type} успешно создан",
            "already_exists": False
        })
    except Exception as e:
        print(f"[CANDIDATE_ADD_CHAT] ⚠️ Ошибка создания {message_type} чата: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка создания чата: {str(e)}")


# ============================================
# ОБНОВЛЕНИЕ РЕЗЮМЕ КАНДИДАТА
# ============================================

@router.post("/update-resume/{candidate_id}", response_class=JSONResponse)
async def update_candidate_resume(
    candidate_id: int,
    file: UploadFile = File(...),
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Обновляет резюме кандидата, объединяя данные из нового резюме со старыми.
    Приоритет: заполняем поля где None, массивы дополняем новыми данными.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Проверяем существование кандидата
    existing_candidate = await candidate_repo.get_candidate_profile_for_candidate_id_and_user_id(
        candidate_id, current_user.id
    )
    if not existing_candidate:
        raise HTTPException(status_code=404, detail="Кандидат не найден")

    # Проверяем формат файла
    original_name = file.filename or "resume"
    ext = Path(original_name).suffix.lower()
    if ext not in (".pdf", ".docx", ".txt", ".rtf"):
        raise HTTPException(
            status_code=400,
            detail=f"Неподдерживаемый формат файла: {ext}. Используйте PDF, DOCX, TXT или RTF"
        )

    try:
        # Сохраняем файл и извлекаем текст
        upload_dir = Path("uploaded_resumes")
        upload_dir.mkdir(parents=True, exist_ok=True)

        safe_name = f"{uuid4().hex}{ext}"
        file_path = upload_dir / safe_name

        file_bytes = await file.read()
        with file_path.open("wb") as f:
            f.write(file_bytes)

        # Извлекаем текст из файла
        if ext == ".pdf":
            text = process_pdf(file_path)
        elif ext == ".docx":
            text = process_docx(file_path)
        elif ext == ".txt":
            text = process_txt(file_path)
        else:  # .rtf
            text = process_rtf(file_path)

        if not text.strip():
            raise HTTPException(
                status_code=400,
                detail="Файл не содержит текста после извлечения"
            )

        # Отправляем в GPT для парсинга
        try:
            gpt_raw = await gpt_generator.create_candidate_profile(text)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Ошибка при вызове GPT: {str(e)}"
            )

        if not gpt_raw:
            raise HTTPException(
                status_code=500,
                detail="GPT не вернул результат"
            )

        # Валидируем ответ GPT
        try:
            if isinstance(gpt_raw, str):
                new_profile = GPTCandidateProfile.model_validate_json(gpt_raw)
            else:
                new_profile = GPTCandidateProfile.model_validate(gpt_raw)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail="Ошибка получения результата от модели GPT. Не удалось корректно разобрать резюме."
            )

        # Объединяем старый и новый профиль
        merged_candidate = await candidate_repo.merge_candidate_profile(
            existing_candidate=existing_candidate,
            new_profile=new_profile,
        )

        return JSONResponse({
            "status": "ok",
            "message": "Резюме успешно обновлено"
        })

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in /candidate/update-resume/{candidate_id}:", e)
        raise HTTPException(
            status_code=500,
            detail="Внутренняя ошибка сервера при обработке резюме"
        )


# ============================================
# ЗАГРУЗКА РЕЗЮМЕ В КАБИНЕТ КАНДИДАТА
# ============================================

@router.post("/upload-resume", response_class=JSONResponse)
async def upload_resume_for_cabinet(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Загружает резюме для кабинета кандидата с детальным логированием для отладки.
    
    Принимает PDF/DOCX файл, парсит его через AI (Gemini 1.5 Flash),
    извлекает данные (grade, stack, bio, experience_years) и сохраняет в CandidateProfile.
    """
    print(f"DEBUG: Начинаем загрузку файла {file.filename}")
    
    try:
        # Проверка авторизации
        if not current_user:
            print("DEBUG: Пользователь не авторизован")
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        print(f"DEBUG: Пользователь авторизован: {current_user.id} ({current_user.email})")
        
        # Проверяем, что пользователь имеет роль CANDIDATE
        if current_user.role != UserRole.CANDIDATE:
            print(f"DEBUG: Неверная роль пользователя: {current_user.role}")
            raise HTTPException(
                status_code=403,
                detail="Только кандидаты могут загружать резюме в свой кабинет"
            )
        
        # Проверяем формат файла
        original_name = file.filename or "resume"
        ext = Path(original_name).suffix.lower()
        print(f"DEBUG: Расширение файла: {ext}")
        
        if ext not in (".pdf", ".docx", ".txt", ".rtf"):
            print(f"DEBUG: Неподдерживаемый формат: {ext}")
            raise HTTPException(
                status_code=400,
                detail=f"Неподдерживаемый формат файла: {ext}. Используйте PDF, DOCX, TXT или RTF"
            )
        
        # 1. Чтение файла
        print("DEBUG: Начинаем чтение файла...")
        file_bytes = await file.read()
        print(f"DEBUG: Файл прочитан, размер {len(file_bytes)} байт")
        
        # Сохраняем файл в статическую директорию
        BASE_DIR = Path(__file__).resolve().parents[1]
        static_dir = BASE_DIR / "static" / "resumes" / "candidate_cabinet"
        static_dir.mkdir(parents=True, exist_ok=True)
        print(f"DEBUG: Директория для сохранения: {static_dir}")
        
        safe_name = f"{current_user.id}_{uuid4().hex}{ext}"
        file_path = static_dir / safe_name
        print(f"DEBUG: Сохраняем файл как: {safe_name}")
        
        with file_path.open("wb") as f:
            f.write(file_bytes)
        print(f"DEBUG: Файл сохранен на диск: {file_path}")
        
        # 2. Извлечение текста из файла
        print("DEBUG: Начинаем извлечение текста из файла...")
        text = ""
        
        try:
            if ext == ".pdf":
                print("DEBUG: Используем process_pdf для извлечения текста")
                text = process_pdf(str(file_path))
            elif ext == ".docx":
                print("DEBUG: Используем process_docx для извлечения текста")
                text = process_docx(str(file_path))
            elif ext == ".txt":
                print("DEBUG: Используем process_txt для извлечения текста")
                text = process_txt(str(file_path))
            else:  # .rtf
                print("DEBUG: Используем process_rtf для извлечения текста")
                text = process_rtf(str(file_path))
            
            print(f"DEBUG: Текст извлечен, длина {len(text)} символов")
            
            if not text.strip():
                print("DEBUG: ВНИМАНИЕ: Файл не содержит текста после извлечения")
                raise HTTPException(
                    status_code=400,
                    detail="Файл не содержит текста после извлечения"
                )
        except Exception as e:
            print(f"DEBUG: ОШИБКА при извлечении текста: {str(e)}")
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Ошибка при извлечении текста из файла: {str(e)}"
            )
        
        # 3. Вызов AI для получения полного GPTCandidateProfile
        print("DEBUG: Отправляем запрос в Gemini для полного парсинга...")
        gpt_profile: Optional[GPTCandidateProfile] = None
        
        try:
            gpt_raw = await gpt_generator.create_candidate_profile(text)
            print("DEBUG: Gemini вернул ответ")
            
            # Парсим JSON в GPTCandidateProfile
            if isinstance(gpt_raw, str):
                gpt_profile = GPTCandidateProfile.model_validate_json(gpt_raw)
            else:
                gpt_profile = GPTCandidateProfile.model_validate(gpt_raw)
            
            print(f"DEBUG: Профиль распарсен: grade={gpt_profile.main.grade}, skills={gpt_profile.main.skills}")
        except Exception as e:
            # ЭТО САМОЕ ВАЖНОЕ: Печатаем полную ошибку в терминал
            error_msg = f"ОШИБКА ПРИ ПАРСИНГЕ ЧЕРЕЗ AI: {str(e)}"
            print(error_msg)
            traceback.print_exc()  # Печатает след ошибки
            
            # Возвращаем ошибку на фронтенд, чтобы увидел пользователь
            return JSONResponse(
                status_code=500,
                content={
                    "detail": error_msg,
                    "traceback": traceback.format_exc()
                }
            )
        
        # 4. Запись в CRM (Общий пул) - Dual Write Strategy
        print("DEBUG: Начинаем запись в CRM (общий пул)...")
        system_user = None
        
        try:
            system_user = await user_repo.get_by_email("cv@omega-solutions.ru")
            if system_user:
                print(f"DEBUG: Системный пользователь найден: ID={system_user.id}")
                
                # Сохраняем кандидата в общую таблицу candidates через candidate_profile_to_db
                db_candidate = await candidate_repo.candidate_profile_to_db(
                    profile=gpt_profile,
                    user_id=system_user.id
                )
                print(f"DEBUG: Кандидат сохранен в CRM: number_for_user={db_candidate.number_for_user}")
            else:
                logger.warning("Системный пользователь cv@omega-solutions.ru не найден. Пропускаем запись в CRM.")
                print("DEBUG: WARNING - Системный пользователь не найден, пропускаем запись в CRM")
        except Exception as e:
            # Логируем ошибку, но не роняем запрос (главное - обновить личный профиль)
            logger.warning(f"Ошибка при сохранении в CRM: {str(e)}")
            print(f"DEBUG: WARNING - Ошибка при сохранении в CRM: {str(e)}")
            traceback.print_exc()
        
        # 5. Извлечение данных для личного профиля из GPTCandidateProfile
        print("DEBUG: Извлекаем данные для личного профиля...")
        
        # Маппинг grade из main.grade
        grade_enum: Optional[Grade] = None
        if gpt_profile.main.grade:
            grade_str = gpt_profile.main.grade.upper()
            print(f"DEBUG: Пытаемся преобразовать grade: {grade_str}")
            try:
                grade_enum = Grade[grade_str]
                print(f"DEBUG: Grade успешно преобразован: {grade_enum}")
            except KeyError:
                print(f"DEBUG: Неизвестный grade: {grade_str}, оставляем None")
                grade_enum = None
        
        # Маппинг stack из main.skills (разбиваем строку на массив, если нужно)
        stack_list = None
        if gpt_profile.main.skills:
            # Если skills - это строка, разбиваем по запятым или переносам строк
            skills_str = gpt_profile.main.skills
            if isinstance(skills_str, str):
                # Разбиваем по запятым, точкам с запятой или переносам строк
                stack_list = [s.strip() for s in skills_str.replace('\n', ',').replace(';', ',').split(',') if s.strip()]
            elif isinstance(skills_str, list):
                stack_list = skills_str
            print(f"DEBUG: Stack извлечен: {stack_list}")
        
        # Маппинг bio из personal.about
        bio = gpt_profile.personal.about if gpt_profile.personal.about else None
        
        # Вычисление experience_years из списка experience
        experience_years = None
        if gpt_profile.experience:
            # Пытаемся извлечь годы из периодов работы
            total_months = 0
            for exp in gpt_profile.experience:
                if exp.period:
                    # Простая эвристика: ищем паттерны типа "2020-2023" или "3 года"
                    period_str = exp.period.lower()
                    # Ищем диапазон годов (например, "2020-2023")
                    year_range = re.findall(r'(\d{4})\s*[-–]\s*(\d{4})', period_str)
                    if year_range:
                        start_year, end_year = map(int, year_range[0])
                        total_months += (end_year - start_year) * 12
                    # Ищем упоминания лет (например, "3 года", "5 лет")
                    years_match = re.search(r'(\d+)\s*(?:лет|год|years?)', period_str)
                    if years_match:
                        total_months += int(years_match.group(1)) * 12
            
            if total_months > 0:
                experience_years = round(total_months / 12)
                print(f"DEBUG: Вычислен опыт работы: {experience_years} лет")
        
        # Формируем URL резюме (путь для доступа через статику)
        resume_url = f"/static/resumes/candidate_cabinet/{safe_name}"
        print(f"DEBUG: URL резюме: {resume_url}")
        
        # 6. Сохранение в личный профиль (CandidateProfile)
        print("DEBUG: Сохраняем данные в личный профиль...")
        try:
            profile = await candidate_profile_repo.create_or_update(
                user_id=current_user.id,
                grade=grade_enum,
                stack=stack_list,
                bio=bio,
                experience_years=experience_years,
                resume_url=resume_url,
            )
            print("DEBUG: Данные сохранены в личный профиль")
            print(f"DEBUG: Профиль ID: {profile.id}")
        except Exception as e:
            error_msg = f"ОШИБКА ПРИ СОХРАНЕНИИ В ЛИЧНЫЙ ПРОФИЛЬ: {str(e)}"
            print(error_msg)
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={
                    "detail": error_msg,
                    "traceback": traceback.format_exc()
                }
            )
        
        # Формируем ответ в формате, ожидаемом фронтендом
        profile_dict = {
            "id": profile.id,
            "user_id": profile.user_id,
            "grade": profile.grade.value if profile.grade else None,
            "stack": profile.stack if profile.stack else None,
            "bio": profile.bio if profile.bio else None,
            "experience_years": profile.experience_years if profile.experience_years else None,
            "resume_url": profile.resume_url if profile.resume_url else None,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        }
        
        print("DEBUG: Успешно завершено! Возвращаем ответ")
        return JSONResponse({
            "status": "success",
            "message": "Профиль обновлен",
            "profile": profile_dict,
        })
        
    except HTTPException:
        # Пробрасываем HTTPException как есть
        raise
    except Exception as e:
        # ЭТО САМОЕ ВАЖНОЕ: Печатаем полную ошибку в терминал
        error_msg = f"ОШИБКА ПРИ ЗАГРУЗКЕ: {str(e)}"
        print(error_msg)
        traceback.print_exc()  # Печатает след ошибки
        
        # Возвращаем ошибку на фронтенд, чтобы увидел пользователь
        return JSONResponse(
            status_code=500,
            content={
                "detail": error_msg,
                "traceback": traceback.format_exc()
            }
        )