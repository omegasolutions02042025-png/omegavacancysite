from app.core.config import settings
from telethon import TelegramClient, events
from app.database.user_db import UserRepository
from app.core.websocket_notif import ws_manager
from pathlib import Path
import os
import asyncio


SESSIONS_DIR = Path("sessions")
SESSIONS_DIR.mkdir(exist_ok=True)


class Notifications:
    def __init__(self):
        self.api_hash = settings.api_hash
        self.api_id = settings.api_id
        self.user_repo = UserRepository()
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
        print(f"[tg] user_id={user_id}: создаём handler для чатов {watch_users}")

        @client.on(events.NewMessage(chats=watch_users))
        async def handler(event):
            sender = await event.get_sender()
            username = sender.username
            url = f"https://t.me/{username}" if username else None
            chat_id = sender.id

            candidate = await self.user_repo.get_candidate_by_chat_id(chat_id)
            if not candidate:
                return

            notification = {
                "type": "telegram_message",
                "vacancy_id": candidate.vacancy_id,
                "candidate_fullname": candidate.candidate_fullname,
                "message": (
                    f"Пришло сообщение в Telegram от "
                    f"{candidate.candidate_fullname} по вакансии {candidate.vacancy_id}"
                ),
                "url": url,
            }

            await ws_manager.send_to_user(user_id, notification)
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
        await self.stop_solo_session(user_id, for_unlink=False)

        watch_users = await self.user_repo.get_chat_id_candidates(user_id)
        await self.start_solo_session(watch_users, user_id)
    
    async def add_client(self, user_id: int, client: TelegramClient):
        self.clients[user_id] = client

manager = Notifications()
