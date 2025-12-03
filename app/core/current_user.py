# app/dependencies/current_user.py
from typing import Optional

import jwt
from fastapi import Request

from app.core.security import config
from app.database.user_db import UserRepository

user_repo = UserRepository()


async def get_current_user_from_cookie(request: Request):
    """
    Получить текущего пользователя из cookie с JWT токеном.
    
    Декодирует JWT токен из cookie и загружает пользователя из базы данных.
    Не выбрасывает исключения, возвращает None если пользователь не авторизован.
    Удобно для публичных страниц где авторизация опциональна.
    
    Args:
        request: FastAPI Request объект
        
    Returns:
        User: Объект пользователя или None если не авторизован/токен невалиден
    """
    token = request.cookies.get(config.JWT_ACCESS_COOKIE_NAME)  # "access_token"

    if not token:
        return None

    try:
        payload = jwt.decode(
            token,
            config.JWT_SECRET_KEY,
            algorithms=[config.JWT_ALGORITHM],
        )
    except jwt.PyJWTError:
        # битый/протухший токен — ведём себя как гость
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return None

    user = await user_repo.get_by_id(user_id)

    if user and getattr(user, "is_archived", False):
        # Помечаем запрос, чтобы middleware удалил cookie
        request.state.force_logout = True
        return None

    return user
