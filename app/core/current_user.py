# app/dependencies/current_user.py
from typing import Optional

import jwt
from fastapi import Request

from app.core.security import config
from app.database.user_db import UserRepository

user_repo = UserRepository()


async def get_current_user_from_cookie(request: Request):
    """
    Возвращает объект пользователя или None, если не залогинен.
    Не кидает 401 — удобно для публичных страниц.
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
    return user
