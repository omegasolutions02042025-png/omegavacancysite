# app/routers/telegram_link.py
from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.responses import JSONResponse

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

from app.core.config import settings          # TG_API_ID, TG_API_HASH
from app.core.current_user import get_current_user_from_cookie
from app.database.user_db import UserRepository
from app.core.telethon_check import manager
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    AuthRestartError,
)

import os
from pathlib import Path

router = APIRouter(prefix="/telegram", tags=["Telegram"])

user_repo = UserRepository()
PHONE_HASH : dict[int, str] = {}
SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)

async def create_client_for_user(user_id: int) -> TelegramClient:
    """
    Создаём клиента Telethon с именованной сессией.
    Telethon сам будет сохранять/читать сессию из файла tg_user_{id}.session.
    """
    api_id = settings.api_id
    api_hash = settings.api_hash
    session_name = f"tg_user_{user_id}"
    session_path = SESSIONS_DIR / f"{session_name}.session"   # один файл сессии на пользователя

    client = TelegramClient(session_path, api_id, api_hash)
    await manager.add_client(user_id, client)
    



@router.post("/send-code")
async def send_telegram_code(
    phone: str = Form(...),
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Шаг 1 — отправляем код на номер.
    """
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Необходима авторизация")

    phone = phone.strip()
    if not phone:
        raise HTTPException(status_code=400, detail="Номер телефона не указан")

    await create_client_for_user(current_user.id)
    client = await manager.get_client(current_user.id)
    await client.disconnect()

    try:
        await client.connect()
        sent = await client.send_code_request(phone)
        if sent:
            PHONE_HASH[current_user.id] = sent.phone_code_hash

        return JSONResponse(
            {
                "ok": True,
                "message": "Код отправлен. Введите код из Telegram.",
            }
        )

    except AuthRestartError:
        raise HTTPException(status_code=500, detail="Нажмите еще раз на кнопку")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при отправке кода: {e}")

    
        
    finally:
        await client.disconnect()


@router.post("/confirm-code")
async def confirm_telegram_code(
    phone: str = Form(...),
    code: str = Form(...),
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Шаг 2 — подтверждаем код.
    Если включён облачный пароль — отдаем флаг need_password=True.
    Если 2FA нет — сразу делаем get_me() и сохраняем в БД.
    """
    if current_user is None:
        return JSONResponse(
            {
                "ok": False,
                "error": "Необходима авторизация",
            }
        )

    phone = phone.strip()
    code = code.strip()
    if not phone or not code:
        return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "Номер телефона и код обязательны"},
            )

    client : TelegramClient = await manager.get_client(current_user.id)



    try:
        await client.connect()

        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=PHONE_HASH[current_user.id])
        except PhoneCodeInvalidError:
            raise HTTPException(status_code=400, detail="Неверный код из Telegram")
        except SessionPasswordNeededError:
            # Нужен облачный пароль => идём на шаг 3
            return JSONResponse(
                {
                    "ok": True,
                    "need_password": True,
                    "message": "Для этого аккаунта включён облачный пароль. Введите пароль.",
                }
            )

        # Если сюда дошли — 2FA нет, авторизация прошла
        me = await client.get_me()
        if not me:
            del PHONE_HASH[current_user.id]
            return JSONResponse(
                {
                    "ok": False,
                    "error": "Не удалось получить данные Telegram-профиля",
                }
            )
            
        
        session_name = f"tg_user_{current_user.id}"

        await user_repo.update_user_telegram(current_user.id, session_name, me.username)
        
        del PHONE_HASH[current_user.id]
        return JSONResponse(
            {
                "ok": True,
                "need_password": False,
                "message": "Telegram успешно привязан",
                "telegram_username": me.username,
            }
        )

    finally:
        await client.disconnect()
        await manager.restart_session(current_user.id)


@router.post("/password")
async def confirm_telegram_password(
    phone: str = Form(...),
    password: str = Form(...),
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Шаг 3 — ввод облачного пароля (2FA).
    Тут уже не нужен код, мы продолжаем авторизацию.
    """
    print(phone, password)
    if current_user is None:
        return JSONResponse(
            {
                "ok": False,
                "error": "Необходима авторизация",
            }
        )

    phone = phone.strip()
    password = password.strip()
    if not phone or not password:
        return JSONResponse(
            {
                "ok": False,
                "error": "Номер телефона и облачный пароль обязательны",
            }
        )

    client = await manager.get_client(current_user.id)

    try:
        await client.connect()

        # После шага с кодом Telethon уже знает phone/phone_code_hash через сессию
        await client.sign_in(password=password)

        me = await client.get_me()
        if not me:
            return JSONResponse(
                {
                    "ok": False,
                    "error": "Не удалось получить данные Telegram-профиля",
                }
            )

        # 👉 Сохранить данные в БД
        session_name = f"tg_user_{current_user.id}"
        await client.disconnect()
        await user_repo.update_user_telegram(current_user.id, session_name, me.username)
        
        del PHONE_HASH[current_user.id]
        

        return JSONResponse(
            {
                "ok": True,
                "message": "Telegram успешно привязан",
                "telegram_username": me.username,
            }
        )

    finally:
        await client.disconnect()
        await manager.restart_session(current_user.id)

@router.post("/unlink")
async def unlink_telegram(current_user=Depends(get_current_user_from_cookie)):
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Необходима авторизация")
    
    await manager.stop_solo_session(f"tg_user_{current_user.id}", for_unlink=True)
    
    success = await user_repo.update_user_telegram(current_user.id, None, None)
    if not success:
        raise HTTPException(status_code=500, detail="Не удалось отвязать Telegram")
    
    return JSONResponse(
        {
            "ok": True,
            "message": "Telegram успешно отвязан",
        }
    )
