from app.core.config import settings
from telethon import TelegramClient, events
from app.database.user_db import UserRepository
from app.database.chat_db import chat_repository
from app.database.vacancy_db import VacancyRepository
from app.database.candidate_db import CandidateRepository
from app.core.websocket_notif import ws_manager
from app.core.chat_websocket import chat_ws_manager
from pathlib import Path
import os
import asyncio
from datetime import datetime
import uuid


SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)

MEDIA_DIR = Path("media/chat")
MEDIA_DIR.mkdir(parents=True, exist_ok=True)


class Notifications:
    def __init__(self):
        self.api_hash = settings.api_hash
        self.api_id = settings.api_id
        self.user_repo = UserRepository()
        self.vacancy_repo = VacancyRepository()
        self.candidate_repo = CandidateRepository()
        # user_id -> TelegramClient
        self.clients: dict[int, TelegramClient] = {}
        # опционально: user_id -> handler, если захочешь потом снимать хендлеры
        # self.handlers: dict[int, callable] = {}

    async def start_solo_session(self, watch_users: list[int], user_id: int):
        """
        Запускаем (или поднимаем) одну сессию для конкретного user_id.
        Если клиент уже есть и подключен — второй раз не создаём.
        """
        # Если клиент уже создан — просто убеждаемся, что он подключен
        client = self.clients.get(user_id)
        if client:
            if not client.is_connected():
                await client.connect()
            print(f"[tg] user_id={user_id}: клиент уже существует и подключен")
            return  # ✅ ВАЖНО: выходим, чтобы не создавать дубликат!

        session_path = SESSIONS_DIR / f"tg_user_{user_id}.session"
        print(f"[tg] user_id={user_id}: создаём нового клиента, session={session_path}")

        client = TelegramClient(str(session_path), self.api_id, self.api_hash)
        await client.connect()

        if not await client.is_user_authorized():
            print(f"[tg] user_id={user_id}: User not authorized")
            await client.disconnect()
            return

        # регистрируем клиента и хендлеры
        self._create_handler(client, watch_users, user_id)

        # сохраняем в словарь только после успешного коннекта
        self.clients[user_id] = client

        # запускаем клиента в фоне
        asyncio.create_task(client.run_until_disconnected())

    def _create_handler(self, client: TelegramClient, watch_users: list[int], user_id: int):
        print(f"[TELETHON_HANDLER] user_id={user_id}: создаём handler для чатов {watch_users}")
        print(f"[TELETHON_HANDLER] Количество чатов для прослушивания: {len(watch_users)}")

        @client.on(events.NewMessage(chats=watch_users))
        async def handler(event):
            sender = await event.get_sender()
            username = sender.username
            url = f"https://t.me/{username}" if username else None
            chat_id = sender.id
            
            print(f"[TELETHON_HANDLER] 📨 Получено сообщение от chat_id={chat_id} для user_id={user_id}")

            candidate = await self.user_repo.get_candidate_by_chat_id(chat_id)
            if not candidate:
                print(f"[TELETHON_HANDLER] ⚠️ Кандидат с chat_id={chat_id} не найден в БД")
                return
            
            print(f"[TELETHON_HANDLER] ✅ Найден кандидат: {candidate.candidate_fullname}")

            message_text = event.message.text or event.message.message or ""
            
            # Проверяем наличие медиа
            has_media = False
            media_type = None
            media_path = None
            media_filename = None
            
            if event.message.media:
                try:
                    # Определяем тип медиа
                    if event.message.photo:
                        media_type = "photo"
                        extension = "jpg"
                    elif event.message.document:
                        media_type = "document"
                        # Получаем расширение из mime_type или имени файла
                        if hasattr(event.message.document, 'attributes'):
                            for attr in event.message.document.attributes:
                                if hasattr(attr, 'file_name'):
                                    media_filename = attr.file_name
                                    extension = media_filename.split('.')[-1] if '.' in media_filename else 'bin'
                                    break
                        if not extension:
                            extension = "bin"
                    elif event.message.video:
                        media_type = "video"
                        extension = "mp4"
                    elif event.message.audio or event.message.voice:
                        media_type = "audio"
                        extension = "mp3"
                    else:
                        media_type = "other"
                        extension = "bin"
                    
                    # Генерируем уникальное имя файла
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    safe_candidate_name = "".join(c for c in candidate.candidate_fullname if c.isalnum() or c in (' ', '-', '_')).strip()
                    filename = f"{safe_candidate_name}_{timestamp}.{extension}"
                    if not media_filename:
                        media_filename = filename
                    
                    # Скачиваем файл
                    file_path = MEDIA_DIR / filename
                    await event.message.download_media(file=str(file_path))
                    
                    has_media = True
                    media_path = f"/media/chat/{filename}"
                    
                    print(f"[TELEGRAM] Скачан файл: {filename} ({media_type})")
                    
                    # Если нет текста, добавляем описание медиа
                    if not message_text:
                        message_text = f"[{media_type.upper()}] {media_filename}"
                    
                except Exception as e:
                    print(f"[TELEGRAM] Ошибка скачивания медиа: {e}")
            
            notification = {
                "type": "telegram_message",
                "vacancy_id": candidate.vacancy_id,
                "candidate_fullname": candidate.candidate_fullname,
                "message": (
                    f"Пришло сообщение в Telegram от "
                    f"{candidate.candidate_fullname} по вакансии {candidate.vacancy_id}"
                ),
                "message_text": message_text,
                "has_media": has_media,
                "media_type": media_type,
                "media_path": media_path,
                "media_filename": media_filename,
                "url": url,
            }

            # Получаем название вакансии
            vacancy_title = None
            if candidate.vacancy_id:
                vacancy = await self.vacancy_repo.get_vacancy_by_id(candidate.vacancy_id)
                if vacancy:
                    vacancy_title = vacancy.title
            
            # Получаем ID кандидата по его полному имени
            candidate_id = None
            if candidate.candidate_fullname:
                candidate_id = await self.candidate_repo.get_candidate_id_by_fullname(
                    user_id=user_id,
                    candidate_fullname=candidate.candidate_fullname
                )
            
            # Сохраняем сообщение в чат
            saved_message = None
            try:
                saved_message = await chat_repository.add_message(
                    user_id=user_id,
                    candidate_id=candidate_id,
                    candidate_fullname=candidate.candidate_fullname,
                    vacancy_id=candidate.vacancy_id,
                    message_type="telegram",
                    sender="candidate",
                    message_text=message_text,
                    vacancy_title=vacancy_title,
                    has_media=has_media,
                    media_type=media_type,
                    media_path=media_path,
                    media_filename=media_filename,
                )
                print(f"[TELEGRAM] Сообщение сохранено в БД с ID: {saved_message.id}")
            except Exception as e:
                print(f"[TELEGRAM] Ошибка сохранения в чат: {e}")

            # Отправляем уведомление через основной WebSocket
            await ws_manager.send_to_user(user_id, notification)
            
            # Отправляем обновление в чат через WebSocket
            if saved_message:
                chat_update = {
                    "type": "new_message",
                    "message": {
                        "id": saved_message.id,
                        "sender": "candidate",
                        "message_text": message_text,
                        "timestamp": saved_message.timestamp,
                        "candidate_fullname": candidate.candidate_fullname,
                        "vacancy_id": candidate.vacancy_id,
                        "vacancy_title": vacancy_title,
                        "message_type": "telegram",
                        "has_media": has_media,
                        "media_type": media_type,
                        "media_path": media_path,
                        "media_filename": media_filename,
                    }
                }
                await chat_ws_manager.send_personal_message(chat_update, user_id)
                print(f"[TELEGRAM] Отправлено обновление чата через WebSocket для user_id={user_id}")
            await self.user_repo.add_user_notification(
                user_id, notification["message"], url
            )

        # если хочешь потом уметь удалить handler:
        # self.handlers[user_id] = handler

    async def start_all_sessions(self):
        """
        Поднимаем сессии для всех пользователей, у кого есть сохранённая сессия,
        но не создаём дубликаты, если клиент уже есть.
        """
        sessions = await self.user_repo.get_user_sessions()
        for session in sessions:
            user_id = session[1]
            if user_id in self.clients:
                print(f"[tg] user_id={user_id}: сессия уже запущена, пропускаем")
                continue


            watch_users = await self.user_repo.get_chat_id_candidates(user_id)
            await self.start_solo_session(watch_users, user_id)

    async def stop_solo_session(self, user_id: int, for_unlink: bool = False):
        """
        Корректно выключаем существующий клиент.
        Если for_unlink=True — ещё и удаляем session-файл.
        """
        client = self.clients.get(user_id)
        if client:
            if client.is_connected():
                await client.disconnect()
            # если нужно полностью отвязать — удаляем из словаря
            if for_unlink:
                del self.clients[user_id]

        if for_unlink:
            # удаляем .session файл
            session_file = SESSIONS_DIR / f"tg_user_{user_id}.session"
            try:
                if session_file.exists():
                    os.remove(session_file)
                    print(f"[tg] user_id={user_id}: session file удалён")
            except Exception as e:
                print(f"[tg] user_id={user_id}: ошибка при удалении session file: {e}")

    async def get_client(self, user_id: int) -> TelegramClient | None:
        return self.clients.get(user_id)


    async def restart_session(self, user_id: int):
        """
        Корректный рестарт: выключаем существующий клиент и создаём новый.
        """
        print(f"[RESTART_SESSION] Начало restart_session для user_id={user_id}")
        print(f"[RESTART_SESSION] Текущие клиенты: {list(self.clients.keys())}")
        
        # Полностью удаляем старый клиент из словаря
        client = self.clients.get(user_id)
        if client:
            print(f"[RESTART_SESSION] Найден существующий клиент для user_id={user_id}")
            if client.is_connected():
                print(f"[RESTART_SESSION] Клиент подключен, отключаем...")
                await client.disconnect()
                print(f"[RESTART_SESSION] ✅ Клиент отключен")
            else:
                print(f"[RESTART_SESSION] Клиент уже отключен")
            # Удаляем из словаря, чтобы start_solo_session создал новый
            del self.clients[user_id]
            print(f"[RESTART_SESSION] ✅ Старый клиент удален из словаря")
        else:
            print(f"[RESTART_SESSION] Клиент для user_id={user_id} не найден в словаре")

        print(f"[RESTART_SESSION] Получаем watch_users для user_id={user_id}...")
        watch_users = await self.user_repo.get_chat_id_candidates(user_id)
        print(f"[RESTART_SESSION] watch_users: {watch_users}")
        
        print(f"[RESTART_SESSION] Запускаем start_solo_session...")
        await self.start_solo_session(watch_users, user_id)
        print(f"[RESTART_SESSION] ✅ restart_session завершен для user_id={user_id}")
        print(f"[RESTART_SESSION] Клиенты после рестарта: {list(self.clients.keys())}")
    
    async def add_client(self, user_id: int, client: TelegramClient):
        print(f"[ADD_CLIENT] Добавляем клиент для user_id={user_id}")
        self.clients[user_id] = client
        print(f"[ADD_CLIENT] ✅ Клиент добавлен. Текущие клиенты: {list(self.clients.keys())}")

manager = Notifications()
