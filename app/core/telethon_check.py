from app.core.config import settings
from telethon import TelegramClient, events
from app.database.user_db import UserRepository
from app.core.websocket_notif import ws_manager
import os
import asyncio


class Norifications:
    def __init__(self):
        self.api_hash = settings.api_hash
        self.api_id = settings.api_id
        self.user_repo = UserRepository()
        self.clients : dict[int, TelegramClient] = {}

    
    async def start_solo_session(self, watch_users: list[int], user_id: int):
        session_path = f'sessions/tg_user_{user_id}'
        print(watch_users)
        client : TelegramClient = TelegramClient(session_path, self.api_id, self.api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            print("User not authorized")
            await client.disconnect()
            return
        self._create_handler(client, watch_users, user_id)
        asyncio.create_task(client.run_until_disconnected())
       
               
    def _create_handler(self, client: TelegramClient,watch_users: list[int],user_id: int):
        print("Handler created")
        self.clients[user_id] = client
        @client.on(events.NewMessage(chats=watch_users))
        async def handler(event):
            sendler = await event.get_sender()
            username = sendler.username
            url = f"https://t.me/{username}"
            chat_id = sendler.id
            
            candidate = await self.user_repo.get_candidate_by_chat_id(chat_id)
            if not candidate:
                return
            

            notification = {
                "type": "telegram_message",
                "vacancy_id": candidate.vacancy_id,
                "candidate_fullname": candidate.candidate_fullname,
                "message": f"Пришло сообщение в Telegram от {candidate.candidate_fullname} по вакансии {candidate.vacancy_id}",
                "url": url,
            }

            await ws_manager.send_to_user(user_id, notification)
            await self.user_repo.add_user_notification(user_id, notification["message"], url)




    async def start_all_sessions(self):
        sessions = await self.user_repo.get_user_sessions()
        for session in sessions:
            user_id = session[1]
            session_name = f"tg_user_{user_id}"
            watch_users = await self.user_repo.get_chat_id_candidates(user_id)
            await self.start_solo_session(watch_users, user_id)
            

    async def stop_solo_session(self, user_id: int, for_unlink: bool = False):
        session_path = f'sessions/tg_user_{user_id}'
        client : TelegramClient = TelegramClient(session_path, self.api_id, self.api_hash)
        if client and client.is_connected():
            await client.disconnect()
        if for_unlink:
            del self.clients[user_id]
            try:
                os.remove(session_path)
            except:
                pass
        

    async def get_client(self, user_id: int):
        return self.clients.get(user_id)

    async def restart_session(self, user_id: int):
        watch_users = await self.user_repo.get_chat_id_candidates(user_id)
        await self.stop_solo_session(user_id)
        await self.start_solo_session(watch_users, user_id)

manager = Norifications()
