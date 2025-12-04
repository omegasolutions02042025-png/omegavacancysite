from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from pathlib import Path
from uuid import uuid4
import os

from app.core.current_user import get_current_user_from_cookie
from app.database.user_db import UserRepository
from app.database.candidate_db import CandidateRepository
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.database import engine, User, RecruiterCandidates, Admin

router = APIRouter(prefix="/photo", tags=["photo"])

user_repo = UserRepository()
candidate_repo = CandidateRepository()

# Папка для хранения фото
PHOTOS_DIR = Path("media/photos")
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


async def save_photo_file(file: UploadFile, user_id: int, entity_type: str) -> str:
    """
    Сохранить фото файл и вернуть относительный путь
    """
    # Проверяем расширение
    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Неподдерживаемый формат. Разрешены: {', '.join(ALLOWED_EXTENSIONS)}")
    
    # Генерируем уникальное имя файла
    filename = f"{entity_type}_{user_id}_{uuid4().hex}{file_ext}"
    file_path = PHOTOS_DIR / filename
    
    # Сохраняем файл (используем стандартный подход FastAPI)
    content = await file.read()
    with open(file_path, 'wb') as f:
        f.write(content)
    
    # Возвращаем относительный путь для сохранения в БД
    return f"/media/photos/{filename}"


@router.post("/upload/user")
async def upload_user_photo(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Загрузить фото для текущего пользователя (рекрутера)
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        photo_path = await save_photo_file(file, current_user.id, "user")
        
        # Обновляем photo_path в БД
        async with AsyncSession(engine) as session:
            from sqlalchemy import update
            await session.execute(
                update(User)
                .where(User.id == current_user.id)
                .values(photo_path=photo_path)
            )
            await session.commit()
        
        return JSONResponse(content={
            "success": True,
            "photo_path": photo_path,
            "message": "Фото загружено"
        })
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PHOTO] Ошибка загрузки фото пользователя: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки фото: {str(e)}")


@router.post("/upload/candidate/{candidate_id}")
async def upload_candidate_photo(
    candidate_id: int,
    file: UploadFile = File(...),
    current_user=Depends(get_current_user_from_cookie),
):

    """
    Загрузить фото для кандидата
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Проверяем что кандидат принадлежит пользователю
    candidate = await candidate_repo.get_candidate_profile_for_candidate_id_and_user_id(
        candidate_id, current_user.id
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Кандидат не найден")
    
    try:
        photo_path = await save_photo_file(file, candidate_id, "candidate")
        
        # Обновляем photo_path в БД
        async with AsyncSession(engine) as session:
            from sqlalchemy import update
            await session.execute(
                update(RecruiterCandidates)
                .where(RecruiterCandidates.id == candidate.id)
                .values(photo_path=photo_path)
            )
            await session.commit()
        
        return JSONResponse(content={
            "success": True,
            "photo_path": photo_path,
            "message": "Фото загружено"
        })
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PHOTO] Ошибка загрузки фото кандидата: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки фото: {str(e)}")


@router.post("/upload/admin/{admin_id}")
async def upload_admin_photo(
    admin_id: int,
    file: UploadFile = File(...),
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Загрузить фото для администратора (только для админов)
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # TODO: Проверка что current_user - админ
    # Пока разрешаем всем авторизованным пользователям
    
    try:
        photo_path = await save_photo_file(file, admin_id, "admin")
        
        # Обновляем photo_path в БД
        async with AsyncSession(engine) as session:
            from sqlalchemy import update
            await session.execute(
                update(Admin)
                .where(Admin.id == admin_id)
                .values(photo_path=photo_path)
            )
            await session.commit()
        
        return JSONResponse(content={
            "success": True,
            "photo_path": photo_path,
            "message": "Фото загружено"
        })
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PHOTO] Ошибка загрузки фото администратора: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки фото: {str(e)}")

