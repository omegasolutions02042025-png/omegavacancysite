from fastapi import APIRouter, Request, Depends, HTTPException, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from typing import Optional
import asyncio
import json
import jwt

from app.core.current_user import get_current_user_from_cookie
from app.core.security import config
from app.database.chat_db import chat_repository
from app.database.user_db import UserRepository
from app.database.candidate_db import CandidateRepository
from app.core.telethon_check import manager
from app.core.chat_websocket import chat_ws_manager
from telethon import TelegramClient
from app.core.email_send import send_email_smtp

router = APIRouter(prefix="/chat", tags=["chat"])
templates_dir = str(Path(__file__).resolve().parent.parent / "templates")
templates = Jinja2Templates(directory=templates_dir)

user_repo = UserRepository()
candidate_repo = CandidateRepository()



@router.get("", response_class=HTMLResponse)
async def chat_page(
    request: Request,
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Главная страница чата со списком всех переписок
    """
    if not current_user:
        return RedirectResponse("/auth/login", status_code=303)

    # Получаем список всех чатов пользователя
    chats = await chat_repository.get_user_chats(current_user.id)

    # Разделяем на Telegram и Email
    telegram_chats = [c for c in chats if c["message_type"] == "telegram"]
    email_chats = [c for c in chats if c["message_type"] == "email"]

    return templates.TemplateResponse(
        "chat/chat.html",
        {
            "request": request,
            "user_email": current_user.email,
            "user_id": current_user.id,
            "telegram_chats": telegram_chats,
            "email_chats": email_chats,
        },
    )


@router.get("/chats-list")
async def get_chats_list(
    current_user=Depends(get_current_user_from_cookie),
):
    """
    API для получения обновленного списка чатов (для динамического обновления)
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Получаем список всех чатов пользователя
    chats = await chat_repository.get_user_chats(current_user.id)

    # Разделяем на Telegram и Email
    telegram_chats = [c for c in chats if c["message_type"] == "telegram"]
    email_chats = [c for c in chats if c["message_type"] == "email"]

    return JSONResponse(content={
        "telegram_chats": telegram_chats,
        "email_chats": email_chats,
    })


@router.get("/messages/{message_type}/{candidate_fullname}")
async def get_chat_messages(
    message_type: str,
    candidate_fullname: str,
    mark_read: bool = True,  # Новый параметр
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Получить все сообщения конкретного чата (API для AJAX)
    mark_read: если False, не помечать сообщения как прочитанные
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Получаем сообщения
    messages = await chat_repository.get_chat_messages(
        user_id=current_user.id,
        candidate_fullname=candidate_fullname,
        message_type=message_type,
    )

    # Отмечаем как прочитанные только если mark_read=True
    if mark_read:
        await chat_repository.mark_messages_as_read(
            user_id=current_user.id,
            candidate_fullname=candidate_fullname,
            message_type=message_type,
        )

    # Преобразуем в JSON
    messages_data = [
        {
            "id": msg.id,
            "sender": msg.sender,
            "message_text": msg.message_text,
            "timestamp": msg.timestamp,
            "is_read": msg.is_read,
            "vacancy_id": msg.vacancy_id,
            "vacancy_title": msg.vacancy_title,
            "has_media": msg.has_media,
            "media_type": msg.media_type,
            "media_path": msg.media_path,
            "media_filename": msg.media_filename,
        }
        for msg in messages
    ]

    return JSONResponse(content={"messages": messages_data, "vacancy_id": messages[0].vacancy_id if messages else None, "vacancy_title": messages[0].vacancy_title if messages else None})


@router.post("/send")
async def send_message(
    candidate_fullname: str = Form(...),
    message_type: str = Form(...),
    message_text: str = Form(...),
    vacancy_id: Optional[str] = Form(None),
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Отправить сообщение кандидату
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Получаем название вакансии
    from app.database.vacancy_db import VacancyRepository
    vacancy_repo = VacancyRepository()
    vacancy_title = None
    if vacancy_id:
        vacancy = await vacancy_repo.get_vacancy_by_id(vacancy_id)
        if vacancy:
            vacancy_title = vacancy.title

    # Получаем ID кандидата по его полному имени
    candidate_id = await candidate_repo.get_candidate_id_by_fullname(
        user_id=current_user.id,
        candidate_fullname=candidate_fullname
    )

    # Сохраняем сообщение в БД
    message = await chat_repository.add_message(
        user_id=current_user.id,
        candidate_id=candidate_id,
        candidate_fullname=candidate_fullname,
        vacancy_id=vacancy_id,
        message_type=message_type,
        sender="user",
        message_text=message_text,
        vacancy_title=vacancy_title,
    )

    success = False  # Инициализируем переменную
    
    # Реальная отправка через Telegram или Email
    if message_type == "telegram":
        try:
            client : TelegramClient = await manager.get_client(current_user.id)
            if not client.is_connected():
                await client.connect()
            if not await client.is_user_authorized():
                raise HTTPException(status_code=401, detail="Необходима авторизация Telegram")
            
            telegram_user_id = await user_repo.get_telegram_user_id_by_candidate_fullname_and_user_id_and_vacancy_id(
                current_user.id, candidate_fullname, vacancy_id
            )
            
            entity = None
            
            # Если нашли telegram_user_id в UserComunication - используем его
            if telegram_user_id:
                print(f"[CHAT] Отправка сообщения в Telegram user_id={telegram_user_id} ({candidate_fullname})")
                try:
                    entity = await client.get_entity(telegram_user_id)
                    print(f"[CHAT] ✅ Entity получен по user_id={telegram_user_id} (entity.id={entity.id})")
                except Exception as entity_error:
                    print(f"[CHAT] ⚠️ Не удалось получить entity по user_id={telegram_user_id}: {entity_error}")
                    # Продолжаем попытку через username
                    entity = None
            
            # Если не удалось получить entity по user_id - пробуем через username из профиля кандидата
            if not entity:
                # Получаем профиль кандидата для получения Telegram username
                candidate = await candidate_repo.get_candidate_profile_for_candidate_id_and_user_id(
                    candidate_id, current_user.id
                )
                
                if not candidate or not candidate.telegram:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Telegram контакт для кандидата {candidate_fullname} не найден. Добавьте чат через кнопку '+ Чат' в карточке кандидата."
                    )
                
                # Используем Telegram username (как в send_message_by_username)
                telegram_username = candidate.telegram.strip()
                if telegram_username.startswith("@"):
                    telegram_username = telegram_username[1:]
                
                print(f"[CHAT] Попытка отправки через Telegram username=@{telegram_username} ({candidate_fullname})")
                try:
                    entity = await client.get_entity(telegram_username)
                    print(f"[CHAT] ✅ Entity получен по username=@{telegram_username} (entity.id={entity.id})")
                    
                    # Сохраняем полученный user_id в UserComunication для будущих использований
                    if entity.id:
                        try:
                            await user_repo.create_user_comunication(
                                user_id=current_user.id,
                                email_user=None,
                                telegram_user_id=entity.id,
                                vacancy_id=vacancy_id,
                                candidate_fullname=candidate_fullname
                            )
                            print(f"[CHAT] ✅ Сохранен telegram_user_id={entity.id} в UserComunication")
                        except Exception as save_error:
                            print(f"[CHAT] ⚠️ Не удалось сохранить telegram_user_id: {save_error}")
                            # Не критично, продолжаем отправку
                except Exception as username_error:
                    print(f"[CHAT] ⚠️ Не удалось получить entity по username=@{telegram_username}: {username_error}")
                    raise HTTPException(
                        status_code=404,
                        detail=f"Не удалось найти пользователя Telegram @{telegram_username}. Проверьте правильность username в профиле кандидата."
                    )
            
            # Отправляем сообщение
            if entity:
                await client.send_message(entity, message_text)
                success = True
                print(f"[CHAT] ✅ Telegram сообщение отправлено {candidate_fullname} (entity.id={entity.id})")
            else:
                raise HTTPException(
                    status_code=500,
                    detail="Не удалось определить получателя сообщения"
                )
                
        except HTTPException:
            raise
        except Exception as e:
            print(f"[CHAT] Ошибка отправки Telegram: {e}")
            import traceback
            print(f"[CHAT] Traceback:\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Не удалось отправить Telegram сообщение: {str(e)}")

    elif message_type == "email":
        try:
            # Получаем email кандидата
            candidate_email = await user_repo.get_email_by_candidate_fullname_and_user_id_and_vacancy_id(
                current_user.id, candidate_fullname, vacancy_id
            )
            
            if not candidate_email:
                raise HTTPException(status_code=404, detail="Email кандидата не найден")
            
            # Формируем тему письма
            subject = f"Сообщение от {current_user.email}"
            
            success = await send_email_smtp(
                sender_email=current_user.work_email,
                recipient_email='artursimoncik@gmail.com',
                subject=subject,
                body=message_text,
                html=True,
                smtp_host='mailbe07.hoster.by',
                smtp_port=465,
                smtp_username=current_user.work_email,
                smtp_password=current_user.work_email_app_pass,
                use_tls=True,
                use_starttls=False,
            )
            
            if success:
                print(f"[CHAT] Email отправлен на {candidate_email}")
            else:
                print(f"[CHAT] Не удалось отправить email на {candidate_email}")
                raise HTTPException(status_code=500, detail="Не удалось отправить email")
                
        except HTTPException:
            raise
        except Exception as e:
            print(f"[CHAT] Ошибка отправки Email: {e}")
            raise HTTPException(status_code=500, detail=f"Не удалось отправить Email: {str(e)}")
    
    else:
        raise HTTPException(status_code=400, detail=f"Неизвестный тип сообщения: {message_type}")

    # Возвращаем успешный ответ
    return JSONResponse(
        content={
            "success": True,
            "message": {
                "id": message.id,
                "sender": message.sender,
                "message_text": message.message_text,
                "timestamp": message.timestamp,
            },
        }
    )

@router.get("/unread-count")
async def get_unread_count(
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Получить количество непрочитанных сообщений (для бейджа)
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    count = await chat_repository.get_unread_count(current_user.id)
    return JSONResponse(content={"unread_count": count})


@router.get("/candidate-id/{candidate_fullname}")
async def get_candidate_id(
    candidate_fullname: str,
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Получить ID кандидата (number_for_user) по его полному имени
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    candidate_id = await candidate_repo.get_candidate_id_by_fullname(
        user_id=current_user.id,
        candidate_fullname=candidate_fullname
    )
    
    return JSONResponse(content={"candidate_id": candidate_id})


@router.get("/last-sverka/{candidate_fullname}/{vacancy_id}")
async def get_last_sverka(
    candidate_fullname: str,
    vacancy_id: str,
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Получить последнюю сверку для кандидата и вакансии
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    from app.database.vacancy_db import VacancyRepository
    from app.core.utils import norm_tg
    
    vacancy_repo = VacancyRepository()
    
    # Получаем последнюю сверку
    sverka = await vacancy_repo.get_last_sverka_by_vacancy_and_candidate_and_user_id(
        vacancy_id=vacancy_id,
        candidate_fullname=candidate_fullname,
        user_id=current_user.id
    )
    
    if not sverka:
        return JSONResponse(content={"found": False})
    
    # Формируем ссылку на сверку
    tg_username = norm_tg(current_user.work_telegram or "")
    sverka_url = f"/sverka/history/result-{vacancy_id}/{sverka.slug}?tg_username={tg_username}"
    
    return JSONResponse(content={
        "found": True,
        "slug": sverka.slug,
        "url": sverka_url,
        "vacancy_id": vacancy_id
    })


@router.post("/mark-read/{message_type}/{candidate_fullname}")
async def mark_messages_as_read(
    message_type: str,
    candidate_fullname: str,
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Пометить все сообщения от кандидата как прочитанные
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        await chat_repository.mark_as_read(
            user_id=current_user.id,
            candidate_fullname=candidate_fullname,
            message_type=message_type
        )
        print(f"[CHAT] Сообщения от {candidate_fullname} ({message_type}) помечены как прочитанные для user_id={current_user.id}")
        return JSONResponse(content={"success": True})
    except Exception as e:
        print(f"[CHAT] Ошибка при пометке сообщений как прочитанных: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mark-unread/{message_type}/{candidate_fullname}")
async def mark_chat_as_unread(
    message_type: str,
    candidate_fullname: str,
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Пометить последнее сообщение от кандидата как непрочитанное
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # Помечаем последнее прочитанное сообщение от кандидата как непрочитанное
        count = await chat_repository.mark_last_message_as_unread(
            user_id=current_user.id,
            candidate_fullname=candidate_fullname,
            message_type=message_type
        )
        
        if count > 0:
            print(f"[CHAT] Последнее сообщение от {candidate_fullname} ({message_type}) помечено как непрочитанное для user_id={current_user.id}")
        else:
            print(f"[CHAT] Нет прочитанных сообщений от {candidate_fullname} ({message_type}) для пометки")
        
        return JSONResponse(content={
            "success": True,
            "count": count
        })
    except Exception as e:
        print(f"[CHAT] Ошибка при пометке сообщения как непрочитанного: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/telegram-dialogs")
async def get_telegram_dialogs(
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Получить список всех диалогов из Telegram пользователя
    Фильтрует уже добавленные и скрытые диалоги
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        client: TelegramClient = await manager.get_client(current_user.id)
        
        if not client:
            raise HTTPException(status_code=400, detail="Telegram не подключен")
        
        if not client.is_connected():
            await client.connect()
        
        if not await client.is_user_authorized():
            raise HTTPException(status_code=401, detail="Необходима авторизация Telegram")
        
        # Получаем уже добавленные и скрытые диалоги
        added_chat_ids = await user_repo.get_added_telegram_chat_ids(current_user.id)
        hidden_chat_ids = await user_repo.get_hidden_telegram_chat_ids(current_user.id)
        
        # Получаем все диалоги
        dialogs = await client.get_dialogs()
        
        # Форматируем для фронтенда
        dialog_list = []
        for dialog in dialogs:
            if dialog.is_user:  # Только личные чаты
                entity = dialog.entity
                chat_id = entity.id
                
                # Пропускаем уже добавленные и скрытые
                if chat_id in added_chat_ids or chat_id in hidden_chat_ids:
                    continue
                
                # Формируем инициалы
                initials = ""
                if hasattr(entity, 'first_name') and entity.first_name:
                    initials += entity.first_name[0].upper()
                if hasattr(entity, 'last_name') and entity.last_name:
                    initials += entity.last_name[0].upper()
                
                # Формируем полное имя
                name_parts = []
                if hasattr(entity, 'first_name') and entity.first_name:
                    name_parts.append(entity.first_name)
                if hasattr(entity, 'last_name') and entity.last_name:
                    name_parts.append(entity.last_name)
                
                name = " ".join(name_parts) if name_parts else f"User {entity.id}"
                
                dialog_list.append({
                    "id": entity.id,
                    "name": name,
                    "username": getattr(entity, 'username', None),
                    "initials": initials or "👤",
                })
        
        print(f"[CHAT] Загружено {len(dialog_list)} диалогов для user_id={current_user.id} (исключено добавленных: {len(added_chat_ids)}, скрытых: {len(hidden_chat_ids)})")
        
        return JSONResponse(content={"dialogs": dialog_list})
        
    except Exception as e:
        print(f"[CHAT] Ошибка получения диалогов: {e}")
        import traceback
        print(f"[CHAT] Traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения диалогов: {str(e)}")


@router.post("/add-telegram-dialogs")
async def add_telegram_dialogs(
    request: Request,
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Добавить несколько Telegram диалогов в чаты (множественное добавление)
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        data = await request.json()
        dialogs = data.get("dialogs", [])  # Список {telegram_chat_id, candidate_fullname}
        
        if not dialogs or len(dialogs) == 0:
            raise HTTPException(status_code=400, detail="Список диалогов пуст")
        
        added_count = 0
        errors = []
        
        for dialog_data in dialogs:
            telegram_chat_id = dialog_data.get("telegram_chat_id")
            candidate_fullname = dialog_data.get("candidate_fullname", "").strip()
            
            if not telegram_chat_id:
                errors.append({"chat_id": telegram_chat_id, "error": "telegram_chat_id обязателен"})
                continue
            
            if not candidate_fullname:
                errors.append({"chat_id": telegram_chat_id, "error": "candidate_fullname обязателен"})
                continue
            
            # Преобразуем в int, если это строка
            if isinstance(telegram_chat_id, str):
                telegram_chat_id = int(telegram_chat_id)
            
            try:
                # Получаем реальный Telegram user_id через Telethon
                telegram_user_id = None
                try:
                    client: TelegramClient = await manager.get_client(current_user.id)
                    if client and client.is_connected() and await client.is_user_authorized():
                        # Получаем entity по chat_id
                        from telethon.tl.types import User
                        entity = await client.get_entity(telegram_chat_id)
                        
                        # Проверяем, что это пользователь (User), а не канал/группа
                        if isinstance(entity, User):
                            telegram_user_id = entity.id
                            print(f"[ADD_DIALOG] ✅ Получен реальный Telegram user_id={telegram_user_id} для chat_id={telegram_chat_id}")
                        else:
                            errors.append({"chat_id": telegram_chat_id, "error": "Это не личный чат с пользователем"})
                            continue
                    else:
                        errors.append({"chat_id": telegram_chat_id, "error": "Telegram клиент не подключен или не авторизован"})
                        continue
                except Exception as e:
                    print(f"[ADD_DIALOG] ⚠️ Ошибка получения user_id через Telethon: {e}")
                    errors.append({"chat_id": telegram_chat_id, "error": f"Не удалось получить user_id: {str(e)}"})
                    continue
                
                if not telegram_user_id:
                    errors.append({"chat_id": telegram_chat_id, "error": "Не удалось получить Telegram user_id"})
                    continue
                
                # Сохраняем в UserComunication с реальным user_id
                await user_repo.create_user_comunication(
                    user_id=current_user.id,
                    email_user=None,
                    telegram_user_id=telegram_user_id,  # Используем реальный user_id
                    vacancy_id=None,
                    candidate_fullname=candidate_fullname
                )
                
                # Помечаем как добавленный (используем реальный user_id)
                await user_repo.set_telegram_dialog_status(
                    user_id=current_user.id,
                    telegram_chat_id=telegram_user_id,  # Используем реальный user_id
                    status="added"
                )
                
                # Загружаем последние 50 сообщений из Telegram диалога
                try:
                    client: TelegramClient = await manager.get_client(current_user.id)
                    if client and client.is_connected() and await client.is_user_authorized():
                        messages = await client.get_messages(telegram_user_id, limit=50)  # Используем реальный user_id
                        saved_count = 0
                        for msg in reversed(messages):
                            message_text = msg.text or msg.message or ""
                            if not message_text and not msg.media:
                                continue
                            
                            sender = "user"
                            if msg.from_id:
                                if hasattr(msg.from_id, 'user_id'):
                                    sender = "candidate" if msg.from_id.user_id == telegram_user_id else "user"
                                elif hasattr(msg.from_id, 'channel_id') or hasattr(msg.from_id, 'chat_id'):
                                    sender = "candidate"
                            else:
                                if hasattr(msg, 'out') and msg.out:
                                    sender = "user"
                                else:
                                    sender = "candidate"
                            
                            has_media = bool(msg.media)
                            media_type = None
                            if msg.photo:
                                media_type = "photo"
                            elif msg.document:
                                media_type = "document"
                            elif msg.video:
                                media_type = "video"
                            elif msg.audio or msg.voice:
                                media_type = "audio"
                            
                            display_text = message_text
                            if not display_text and has_media:
                                display_text = f"[{media_type.upper() if media_type else 'MEDIA'}]"
                            
                            if not display_text:
                                continue
                            
                            try:
                                # Получаем ID кандидата
                                candidate_id = await candidate_repo.get_candidate_id_by_fullname(
                                    user_id=current_user.id,
                                    candidate_fullname=candidate_fullname
                                )
                                
                                await chat_repository.add_message(
                                    user_id=current_user.id,
                                    candidate_id=candidate_id,
                                    candidate_fullname=candidate_fullname,
                                    vacancy_id=None,
                                    message_type="telegram",
                                    sender=sender,
                                    message_text=display_text,
                                    vacancy_title=None,
                                    has_media=has_media,
                                    media_type=media_type,
                                    media_path=None,
                                    media_filename=None,
                                )
                                saved_count += 1
                            except Exception as e:
                                print(f"[ADD_DIALOG] ⚠️ Ошибка сохранения сообщения: {e}")
                                continue
                        
                        print(f"[ADD_DIALOG] ✅ Сохранено {saved_count} сообщений из истории для {candidate_fullname}")
                except Exception as e:
                    print(f"[ADD_DIALOG] ⚠️ Ошибка загрузки истории сообщений: {e}")
                
                added_count += 1
                print(f"[ADD_DIALOG] ✅ Добавлен диалог chat_id={telegram_chat_id} -> user_id={telegram_user_id} ({candidate_fullname})")
                
            except Exception as e:
                errors.append({"chat_id": telegram_chat_id, "error": str(e)})
                print(f"[ADD_DIALOG] ❌ Ошибка добавления диалога {telegram_chat_id}: {e}")
                continue
        
        # Перезапускаем Telethon сессию
        try:
            await manager.restart_session(current_user.id)
            print(f"[CHAT] ✅ Telethon сессия перезапущена")
        except Exception as e:
            print(f"[CHAT] ⚠️ Ошибка перезапуска Telethon сессии: {e}")
        
        return JSONResponse(content={
            "success": True,
            "added_count": added_count,
            "errors": errors,
            "message": f"Добавлено {added_count} диалогов"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[CHAT] Ошибка добавления диалогов: {e}")
        import traceback
        print(f"[CHAT] Traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Ошибка добавления диалогов: {str(e)}")


@router.post("/add-telegram-dialog")
async def add_telegram_dialog(
    request: Request,
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Добавить Telegram диалог в чаты (старый метод для обратной совместимости)
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        data = await request.json()
        telegram_chat_id = data.get("telegram_chat_id")
        candidate_fullname = data.get("candidate_fullname", "").strip()
        
        print(f"[ADD_DIALOG] Получены данные: telegram_chat_id={telegram_chat_id} (type={type(telegram_chat_id)}), candidate={candidate_fullname}")
        
        if not telegram_chat_id:
            raise HTTPException(status_code=400, detail="telegram_chat_id обязателен")
        
        if not candidate_fullname:
            raise HTTPException(status_code=400, detail="candidate_fullname обязателен")
        
        # Преобразуем в int, если это строка
        if isinstance(telegram_chat_id, str):
            telegram_chat_id = int(telegram_chat_id)
        
        # Получаем реальный Telegram user_id через Telethon
        telegram_user_id = None
        try:
            client: TelegramClient = await manager.get_client(current_user.id)
            
            if not client:
                raise HTTPException(status_code=400, detail="Telegram клиент не найден")
            
            if not client.is_connected():
                await client.connect()
            
            if not await client.is_user_authorized():
                raise HTTPException(status_code=401, detail="Необходима авторизация Telegram")
            
            # Получаем entity по chat_id
            from telethon.tl.types import User
            entity = await client.get_entity(telegram_chat_id)
            
            # Проверяем, что это пользователь (User), а не канал/группа
            if isinstance(entity, User):
                telegram_user_id = entity.id
                print(f"[ADD_DIALOG] ✅ Получен реальный Telegram user_id={telegram_user_id} для chat_id={telegram_chat_id}")
            else:
                raise HTTPException(status_code=400, detail="Это не личный чат с пользователем")
        except HTTPException:
            raise
        except Exception as e:
            print(f"[ADD_DIALOG] ⚠️ Ошибка получения user_id через Telethon: {e}")
            raise HTTPException(status_code=500, detail=f"Не удалось получить Telegram user_id: {str(e)}")
        
        if not telegram_user_id:
            raise HTTPException(status_code=500, detail="Не удалось получить Telegram user_id")
        
        print(f"[ADD_DIALOG] Сохраняем в БД: user_id={current_user.id}, telegram_user_id={telegram_user_id} (chat_id={telegram_chat_id}), candidate={candidate_fullname}")
        
        # Сохраняем в UserComunication с реальным user_id
        await user_repo.create_user_comunication(
            user_id=current_user.id,
            email_user=None,
            telegram_user_id=telegram_user_id,  # Используем реальный user_id
            vacancy_id=None,  # Можно добавить выбор вакансии позже
            candidate_fullname=candidate_fullname
        )
        
        # Помечаем как добавленный (используем реальный user_id)
        await user_repo.set_telegram_dialog_status(
            user_id=current_user.id,
            telegram_chat_id=telegram_user_id,  # Используем реальный user_id
            status="added"
        )
        
        print(f"[ADD_DIALOG] ✅ Сохранено в UserComunication")
        
        # Загружаем последние 50 сообщений из Telegram диалога
        try:
            if await client.is_user_authorized():
                print(f"[ADD_DIALOG] Загружаем последние 50 сообщений из диалога user_id={telegram_user_id}")
                
                # Получаем последние 50 сообщений (используем реальный user_id)
                messages = await client.get_messages(telegram_user_id, limit=50)
                
                print(f"[ADD_DIALOG] Получено {len(messages)} сообщений")
                
                # Сохраняем сообщения в обратном порядке (от старых к новым)
                saved_count = 0
                for msg in reversed(messages):
                    # Извлекаем текст сообщения
                    message_text = msg.text or msg.message or ""
                    
                    # Пропускаем пустые сообщения без медиа
                    if not message_text and not msg.media:
                        continue
                    
                    # Определяем отправителя
                    # Проверяем from_id (может быть None для системных сообщений)
                    sender = "user"  # По умолчанию считаем что это пользователь
                    
                    if msg.from_id:
                        # from_id может быть PeerUser, PeerChannel, PeerChat
                        if hasattr(msg.from_id, 'user_id'):
                            # Это PeerUser
                            sender = "candidate" if msg.from_id.user_id == telegram_user_id else "user"
                        elif hasattr(msg.from_id, 'channel_id'):
                            # Это сообщение из канала - считаем как от кандидата
                            sender = "candidate"
                        elif hasattr(msg.from_id, 'chat_id'):
                            # Это сообщение из группы - считаем как от кандидата
                            sender = "candidate"
                    else:
                        # Если from_id None - это может быть системное сообщение или исходящее
                        # Проверяем по sender_id или out
                        if hasattr(msg, 'out') and msg.out:
                            sender = "user"  # Исходящее сообщение
                        else:
                            sender = "candidate"  # Входящее
                    
                    # Обрабатываем медиа (если есть)
                    has_media = False
                    media_type = None
                    media_path = None
                    media_filename = None
                    
                    if msg.media:
                        # Здесь можно добавить обработку медиа, если нужно
                        has_media = True
                        if msg.photo:
                            media_type = "photo"
                        elif msg.document:
                            media_type = "document"
                        elif msg.video:
                            media_type = "video"
                        elif msg.audio or msg.voice:
                            media_type = "audio"
                    
                    # Формируем текст для отображения
                    display_text = message_text
                    if not display_text and has_media:
                        display_text = f"[{media_type.upper() if media_type else 'MEDIA'}]"
                    
                    # Пропускаем если нет ни текста ни медиа
                    if not display_text:
                        continue
                    
                    # Сохраняем сообщение
                    try:
                        # Получаем ID кандидата
                        candidate_id = await candidate_repo.get_candidate_id_by_fullname(
                            user_id=current_user.id,
                            candidate_fullname=candidate_fullname
                        )
                        
                        await chat_repository.add_message(
                            user_id=current_user.id,
                            candidate_id=candidate_id,
                            candidate_fullname=candidate_fullname,
                            vacancy_id=None,
                            message_type="telegram",
                            sender=sender,
                            message_text=display_text,
                            vacancy_title=None,
                            has_media=has_media,
                            media_type=media_type,
                            media_path=media_path,
                            media_filename=media_filename,
                        )
                        saved_count += 1
                    except Exception as e:
                        print(f"[ADD_DIALOG] ⚠️ Ошибка сохранения сообщения: {e}")
                        continue
                
                print(f"[ADD_DIALOG] ✅ Сохранено {saved_count} из {len(messages)} сообщений из истории")
            else:
                print(f"[ADD_DIALOG] ⚠️ Telegram клиент не авторизован")
        except Exception as e:
            print(f"[ADD_DIALOG] ⚠️ Ошибка загрузки истории сообщений: {e}")
            import traceback
            print(f"[ADD_DIALOG] Traceback:\n{traceback.format_exc()}")
            # Не прерываем выполнение, диалог уже добавлен
        
        print(f"[CHAT] Добавлен диалог chat_id={telegram_chat_id} -> user_id={telegram_user_id} ({candidate_fullname}) для user_id={current_user.id}")
        
        # ✅ ВАЖНО: Перезапускаем Telethon сессию, чтобы начать слушать новый чат
        try:
            print(f"[CHAT] Перезапускаем Telethon сессию для user_id={current_user.id}")
            await manager.restart_session(current_user.id)
            print(f"[CHAT] ✅ Telethon сессия перезапущена, теперь слушаем telegram_chat_id={telegram_chat_id}")
        except Exception as e:
            print(f"[CHAT] ⚠️ Ошибка перезапуска Telethon сессии: {e}")
            # Не прерываем выполнение, диалог уже добавлен в БД
        
        return JSONResponse(content={"success": True, "message": "Диалог добавлен"})
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[CHAT] Ошибка добавления диалога: {e}")
        import traceback
        print(f"[CHAT] Traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Ошибка добавления диалога: {str(e)}")


@router.post("/hide-telegram-dialogs")
async def hide_telegram_dialogs(
    request: Request,
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Скрыть выбранные Telegram диалоги из списка
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        data = await request.json()
        chat_ids = data.get("chat_ids", [])  # Список telegram_chat_id
        
        if not chat_ids:
            raise HTTPException(status_code=400, detail="Список chat_ids пуст")
        
        hidden_count = 0
        for chat_id in chat_ids:
            if isinstance(chat_id, str):
                chat_id = int(chat_id)
            
            await user_repo.set_telegram_dialog_status(
                user_id=current_user.id,
                telegram_chat_id=chat_id,
                status="hidden"
            )
            hidden_count += 1
        
        return JSONResponse(content={
            "success": True,
            "hidden_count": hidden_count,
            "message": f"Скрыто {hidden_count} диалогов"
        })
        
    except Exception as e:
        print(f"[CHAT] Ошибка скрытия диалогов: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка скрытия диалогов: {str(e)}")


@router.delete("/delete-dialog/{message_type}/{candidate_fullname}")
async def delete_dialog(
    message_type: str,
    candidate_fullname: str,
    current_user=Depends(get_current_user_from_cookie),
):
    """
    Удалить диалог (все сообщения с кандидатом)
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        print(f"[DELETE_DIALOG] Удаление диалога: type={message_type}, candidate={candidate_fullname}, user_id={current_user.id}")
        
        # Удаляем все сообщения с этим кандидатом
        deleted_messages = await chat_repository.delete_chat_messages(
            user_id=current_user.id,
            candidate_fullname=candidate_fullname,
            message_type=message_type
        )
        
        # Удаляем из UserComunication
        if message_type == "telegram":
            # Получаем telegram_chat_id перед удалением
            from sqlalchemy import select
            from app.database.database import UserComunication
            from sqlalchemy.ext.asyncio import AsyncSession
            async with AsyncSession(user_repo.engine) as session:
                result = await session.execute(
                    select(UserComunication.telegram_user_id).where(
                        UserComunication.user_id == current_user.id,
                        UserComunication.candidate_fullname == candidate_fullname
                    ).limit(1)
                )
                telegram_chat_id = result.scalar_one_or_none()
            
            await user_repo.delete_user_comunication_by_candidate(
                user_id=current_user.id,
                candidate_fullname=candidate_fullname
            )
            
            # Удаляем статус диалога, чтобы он снова появился в списке доступных диалогов
            if telegram_chat_id:
                await user_repo.delete_telegram_dialog_status(
                    user_id=current_user.id,
                    telegram_chat_id=telegram_chat_id
                )
            
            # Перезапускаем Telethon сессию чтобы перестать слушать этот чат
            try:
                await manager.restart_session(current_user.id)
                print(f"[DELETE_DIALOG] ✅ Telethon сессия перезапущена")
            except Exception as e:
                print(f"[DELETE_DIALOG] ⚠️ Ошибка перезапуска Telethon: {e}")
        
        print(f"[DELETE_DIALOG] ✅ Удалено {deleted_messages} сообщений")
        
        return JSONResponse(content={
            "success": True,
            "message": f"Диалог удален ({deleted_messages} сообщений)"
        })
        
    except Exception as e:
        print(f"[DELETE_DIALOG] ❌ Ошибка удаления диалога: {e}")
        import traceback
        print(f"[DELETE_DIALOG] Traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Ошибка удаления диалога: {str(e)}")


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    """
    WebSocket endpoint для получения сообщений в реальном времени
    """
    print(f"[CHAT_WS] Попытка подключения WebSocket для user_id={user_id}")
    print(f"[CHAT_WS] Cookies: {websocket.cookies}")
    
    # Проверяем авторизацию через JWT cookie
    try:
        # Получаем JWT токен из cookie (такой же как в get_current_user_from_cookie)
        token = websocket.cookies.get(config.JWT_ACCESS_COOKIE_NAME)  # "access_token"
        
        print(f"[CHAT_WS] JWT_ACCESS_COOKIE_NAME: {config.JWT_ACCESS_COOKIE_NAME}")
        print(f"[CHAT_WS] Token найден: {bool(token)}")
        
        if not token:
            print(f"[CHAT_WS] ❌ Нет cookie {config.JWT_ACCESS_COOKIE_NAME} для user_id={user_id}")
            await websocket.close(code=1008, reason="Not authenticated")
            return
        
        # Декодируем JWT токен
        try:
            payload = jwt.decode(
                token,
                config.JWT_SECRET_KEY,
                algorithms=[config.JWT_ALGORITHM],
            )
            print(f"[CHAT_WS] JWT payload: {payload}")
        except jwt.PyJWTError as e:
            print(f"[CHAT_WS] ❌ Ошибка декодирования JWT: {e}")
            await websocket.close(code=1008, reason="Invalid token")
            return
        
        # Получаем user_id из токена
        token_user_id = payload.get("sub")
        if not token_user_id:
            print(f"[CHAT_WS] ❌ Нет 'sub' в JWT payload")
            await websocket.close(code=1008, reason="Invalid token payload")
            return
        
        try:
            token_user_id = int(token_user_id)
        except (TypeError, ValueError):
            print(f"[CHAT_WS] ❌ Невалидный user_id в токене: {token_user_id}")
            await websocket.close(code=1008, reason="Invalid user ID in token")
            return
        
        # Проверяем что user_id из URL совпадает с user_id из токена
        if token_user_id != user_id:
            print(f"[CHAT_WS] ❌ user_id не совпадает: запрошен {user_id}, но в токене {token_user_id}")
            await websocket.close(code=1008, reason="User ID mismatch")
            return
        
        # Получаем пользователя из БД
        current_user = await user_repo.get_by_id(token_user_id)
        if not current_user:
            print(f"[CHAT_WS] ❌ Пользователь с ID {token_user_id} не найден в БД")
            await websocket.close(code=1008, reason="User not found")
            return
        
        print(f"[CHAT_WS] ✅ Авторизация успешна для user_id={user_id} ({current_user.email})")
        
    except Exception as e:
        print(f"[CHAT_WS] ❌ Ошибка авторизации для user_id={user_id}: {e}")
        import traceback
        print(f"[CHAT_WS] Traceback:\n{traceback.format_exc()}")
        await websocket.close(code=1011, reason="Authentication error")
        return
    
    # Подключаем WebSocket
    await chat_ws_manager.connect(websocket, user_id)
    
    try:
        while True:
            # Ожидаем сообщения от клиента (ping для поддержания соединения)
            data = await websocket.receive_text()
            
            # Можно обрабатывать команды от клиента, например:
            if data == "ping":
                await websocket.send_json({"type": "pong"})
            
    except WebSocketDisconnect:
        print(f"[CHAT_WS] WebSocket отключен для user_id={user_id}")
        chat_ws_manager.disconnect(websocket, user_id)
    except Exception as e:
        print(f"[CHAT_WS] Ошибка WebSocket для user_id={user_id}: {e}")
        chat_ws_manager.disconnect(websocket, user_id)

