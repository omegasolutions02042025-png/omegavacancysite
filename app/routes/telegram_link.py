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

    client = TelegramClient(str(session_path), api_id, api_hash)
    await manager.add_client(user_id, client)
    return client  # ✅ Возвращаем клиент!
    



@router.post("/send-code")
async def send_telegram_code(
    phone: str = Form(...),
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Шаг 1 — отправляем код на номер.
    """
    print("=" * 80)
    print("[SEND_CODE] Начало функции send_telegram_code")
    print(f"[SEND_CODE] Phone: {phone}")
    print(f"[SEND_CODE] User ID: {current_user.id if current_user else None}")
    
    if current_user is None:
        print("[SEND_CODE] ❌ Пользователь не авторизован")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Необходима авторизация")

    phone = phone.strip()
    if not phone:
        print("[SEND_CODE] ❌ Пустой номер телефона")
        raise HTTPException(status_code=400, detail="Номер телефона не указан")

    print(f"[SEND_CODE] Создаем клиент для user_id={current_user.id}")
    client = await create_client_for_user(current_user.id)
    print(f"[SEND_CODE] ✅ Клиент создан: {client}")
    
    try:
        print("[SEND_CODE] Подключаем клиент...")
        await client.connect()
        print("[SEND_CODE] ✅ Клиент подключен")
        
        print(f"[SEND_CODE] Отправляем код на номер {phone}...")
        sent = await client.send_code_request(phone)
        
        if sent:
            PHONE_HASH[current_user.id] = sent.phone_code_hash
            print(f"[SEND_CODE] ✅ Код отправлен, phone_code_hash сохранен")
            print(f"[SEND_CODE] phone_code_hash: {sent.phone_code_hash[:20]}...")
        else:
            print("[SEND_CODE] ⚠️ send_code_request вернул None")

        # НЕ отключаем клиент - он нужен для следующего шага (confirm_code)
        print("[SEND_CODE] ✅ Код успешно отправлен")
        print(f"[SEND_CODE] Клиент сохранен в manager для user_id={current_user.id}")
        print("=" * 80)
        
        return JSONResponse(
            {
                "ok": True,
                "message": "Код отправлен. Введите код из Telegram.",
            }
        )

    except AuthRestartError as e:
        print(f"[SEND_CODE] ❌ AuthRestartError: {e}")
        raise HTTPException(status_code=500, detail="Нажмите еще раз на кнопку")
    except Exception as e:
        print(f"[SEND_CODE] ❌ ОШИБКА: {type(e).__name__}: {e}")
        import traceback
        print(f"[SEND_CODE] Traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Ошибка при отправке кода: {e}")
    
    finally:
        print("[SEND_CODE] Выполняется finally блок")
        print("[SEND_CODE] Отключаем клиент...")
        await client.disconnect()
        print("[SEND_CODE] ✅ Клиент отключен")
        print("=" * 80)


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
    print("=" * 80)
    print("[CODE] Начало функции confirm_telegram_code")
    print(f"[CODE] Phone: {phone}")
    print(f"[CODE] Code: {code}")
    print(f"[CODE] User ID: {current_user.id if current_user else None}")
    
    if current_user is None:
        print("[CODE] ❌ Пользователь не авторизован")
        return JSONResponse(
            {
                "ok": False,
                "error": "Необходима авторизация",
            }
        )

    phone = phone.strip()
    code = code.strip()
    if not phone or not code:
        print("[CODE] ❌ Пустой телефон или код")
        return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "Номер телефона и код обязательны"},
            )

    print(f"[CODE] Получаем клиент для user_id={current_user.id}")
    client : TelegramClient = await manager.get_client(current_user.id)
    
    if not client:
        print("[CODE] ❌ Клиент не найден")
        print(f"[CODE] Доступные клиенты: {list(manager.clients.keys())}")
        return JSONResponse(
            {
                "ok": False,
                "error": "Сессия истекла. Начните привязку заново (отправьте код снова).",
            }
        )
    
    print(f"[CODE] ✅ Клиент найден: {client}")
    print(f"[CODE] Клиент подключен: {client.is_connected()}")
    print(f"[CODE] PHONE_HASH содержит user_id: {current_user.id in PHONE_HASH}")

    need_password = False  # Флаг для finally блока
    
    try:
        if not client.is_connected():
            print("[CODE] Подключаем клиент...")
            await client.connect()
            print("[CODE] ✅ Клиент подключен")
        else:
            print("[CODE] Клиент уже подключен")

        try:
            print("[CODE] Вызываем client.sign_in с кодом...")
            await client.sign_in(phone=phone, code=code, phone_code_hash=PHONE_HASH[current_user.id])
            print("[CODE] ✅ sign_in успешно выполнен (без 2FA)")
        except PhoneCodeInvalidError:
            print("[CODE] ❌ Неверный код")
            raise HTTPException(status_code=400, detail="Неверный код из Telegram")
        except SessionPasswordNeededError:
            print("[CODE] ⚠️ Требуется облачный пароль (2FA)")
            # Нужен облачный пароль => идём на шаг 3
            # НЕ отключаем клиент - он нужен для следующего шага!
            print("[CODE] Клиент остается подключенным для шага с паролем")
            need_password = True  # Устанавливаем флаг
            return JSONResponse(
                {
                    "ok": True,
                    "need_password": True,
                    "message": "Для этого аккаунта включён облачный пароль. Введите пароль.",
                }
            )

        # Если сюда дошли — 2FA нет, авторизация прошла
        print("[CODE] Получаем данные профиля (без 2FA)...")
        me = await client.get_me()
        if not me:
            print("[CODE] ❌ get_me вернул None")
            del PHONE_HASH[current_user.id]
            return JSONResponse(
                {
                    "ok": False,
                    "error": "Не удалось получить данные Telegram-профиля",
                }
            )
        
        print(f"[CODE] ✅ Профиль получен: @{me.username}, ID: {me.id}")
        
        session_name = f"tg_user_{current_user.id}"
        print(f"[CODE] Сохраняем в БД: session_name={session_name}")

        await user_repo.update_user_telegram(current_user.id, session_name, me.username)
        print("[CODE] ✅ Данные сохранены в БД")
        
        del PHONE_HASH[current_user.id]
        print("[CODE] ✅ PHONE_HASH очищен")
        print("[CODE] ✅ Привязка успешно завершена (без 2FA)")
        
        return JSONResponse(
            {
                "ok": True,
                "need_password": False,
                "message": "Telegram успешно привязан",
                "telegram_username": me.username,
            }
        )

    finally:
        print("[CODE] Выполняется finally блок")
        print(f"[CODE] need_password флаг: {need_password}")
        print(f"[CODE] Клиент в manager.clients для user_id={current_user.id}: {current_user.id in manager.clients}")
        
        # Если требуется пароль - НЕ отключаем клиент и НЕ перезапускаем сессию!
        if need_password:
            print("[CODE] ⚠️ Требуется пароль - клиент остается активным, restart_session НЕ вызывается")
            # Убеждаемся, что клиент сохранен в manager
            if current_user.id not in manager.clients:
                print("[CODE] ⚠️ Клиент не в manager.clients, добавляем...")
                await manager.add_client(current_user.id, client)
            print("[CODE] Клиент сохранен в manager для следующего шага")
            print(f"[CODE] Текущие клиенты в manager: {list(manager.clients.keys())}")
        else:
            # Если пароль НЕ нужен - делаем обычную очистку
            if client and client.is_connected():
                print("[CODE] Отключаем клиент...")
                await client.disconnect()
                print("[CODE] ✅ Клиент отключен")
            
            print(f"[CODE] Перезапускаем сессию для user_id={current_user.id}")
            await manager.restart_session(current_user.id)
            print("[CODE] ✅ Сессия перезапущена")
        
        print("=" * 80)


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
    print("=" * 80)
    print("[PASSWORD] Начало функции confirm_telegram_password")
    print(f"[PASSWORD] Phone: {phone}")
    print(f"[PASSWORD] Password length: {len(password) if password else 0}")
    print(f"[PASSWORD] User ID: {current_user.id if current_user else None}")
    
    if current_user is None:
        print("[PASSWORD] ❌ Пользователь не авторизован")
        return JSONResponse(
            {
                "ok": False,
                "error": "Необходима авторизация",
            }
        )

    phone = phone.strip()
    password = password.strip()
    if not phone or not password:
        print("[PASSWORD] ❌ Пустой телефон или пароль")
        return JSONResponse(
            {
                "ok": False,
                "error": "Номер телефона и облачный пароль обязательны",
            }
        )

    print(f"[PASSWORD] Получаем клиент для user_id={current_user.id}")
    client = await manager.get_client(current_user.id)
    
    if not client:
        print("[PASSWORD] ❌ Клиент не найден в manager.clients")
        print(f"[PASSWORD] Доступные клиенты: {list(manager.clients.keys())}")
        print("[PASSWORD] Пытаемся пересоздать клиент из сессии...")
        
        # Пытаемся пересоздать клиент из файла сессии
        try:
            client = await create_client_for_user(current_user.id)
            print(f"[PASSWORD] ✅ Клиент пересоздан: {client}")
        except Exception as e:
            print(f"[PASSWORD] ❌ Не удалось пересоздать клиент: {e}")
            return JSONResponse(
                {
                    "ok": False,
                    "error": "Сессия истекла или не найдена. Попробуйте начать привязку сначала.",
                }
            )
    
    print(f"[PASSWORD] ✅ Клиент найден: {client}")
    print(f"[PASSWORD] Клиент подключен: {client.is_connected()}")

    try:
        if not client.is_connected():
            print("[PASSWORD] Подключаем клиент...")
            await client.connect()
            print("[PASSWORD] ✅ Клиент подключен")
        else:
            print("[PASSWORD] Клиент уже подключен")

        print("[PASSWORD] Вызываем client.sign_in с паролем...")
        # После шага с кодом Telethon уже знает phone/phone_code_hash через сессию
        await client.sign_in(password=password)
        print("[PASSWORD] ✅ sign_in успешно выполнен")

        print("[PASSWORD] Получаем данные профиля...")
        me = await client.get_me()
        
        if not me:
            print("[PASSWORD] ❌ get_me вернул None")
            return JSONResponse(
                {
                    "ok": False,
                    "error": "Не удалось получить данные Telegram-профиля",
                }
            )
        
        print(f"[PASSWORD] ✅ Профиль получен: @{me.username}, ID: {me.id}")

        # 👉 Сохранить данные в БД
        session_name = f"tg_user_{current_user.id}"
        print(f"[PASSWORD] Сохраняем в БД: session_name={session_name}, username={me.username}")
        
        await user_repo.update_user_telegram(current_user.id, session_name, me.username)
        print("[PASSWORD] ✅ Данные сохранены в БД")
        
        if current_user.id in PHONE_HASH:
            del PHONE_HASH[current_user.id]
            print("[PASSWORD] ✅ PHONE_HASH очищен")
        else:
            print("[PASSWORD] ⚠️ PHONE_HASH не содержал user_id")

        print("[PASSWORD] ✅ Привязка успешно завершена")
        return JSONResponse(
            {
                "ok": True,
                "message": "Telegram успешно привязан",
                "telegram_username": me.username,
            }
        )

    except Exception as e:
        print(f"[PASSWORD] ❌ ОШИБКА: {type(e).__name__}: {e}")
        import traceback
        print(f"[PASSWORD] Traceback:\n{traceback.format_exc()}")
        return JSONResponse(
            {
                "ok": False,
                "error": f"Ошибка авторизации: {str(e)}",
            }
        )

    finally:
        print("[PASSWORD] Выполняется finally блок")
        if client:
            if client.is_connected():
                print("[PASSWORD] Отключаем клиент...")
                await client.disconnect()
                print("[PASSWORD] ✅ Клиент отключен")
            else:
                print("[PASSWORD] Клиент уже отключен")
        else:
            print("[PASSWORD] Клиент None в finally")
        
        print(f"[PASSWORD] Перезапускаем сессию для user_id={current_user.id}")
        await manager.restart_session(current_user.id)
        print("[PASSWORD] ✅ Сессия перезапущена")
        print("=" * 80)

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
