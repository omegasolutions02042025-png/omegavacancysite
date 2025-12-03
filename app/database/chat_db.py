from typing import Optional, List
from datetime import datetime
from sqlalchemy import select, and_, or_, desc, delete
from sqlalchemy.ext.asyncio import AsyncSession

from .database import Chat, engine


class ChatRepository:
    def __init__(self):
        self.engine = engine

    async def add_message(
        self,
        user_id: int,
        candidate_fullname: str,
        vacancy_id: Optional[str],
        message_type: str,  # 'telegram' или 'email'
        sender: str,  # 'user' или 'candidate'
        message_text: str,
        vacancy_title: Optional[str] = None,
        candidate_id: Optional[int] = None,  # number_for_user кандидата
        has_media: bool = False,
        media_type: Optional[str] = None,
        media_path: Optional[str] = None,
        media_filename: Optional[str] = None,
    ) -> Chat:
        """
        Добавить сообщение в чат
        """
        async with AsyncSession(self.engine) as session:
            chat_message = Chat(
                user_id=user_id,
                candidate_id=candidate_id,
                candidate_fullname=candidate_fullname,
                vacancy_id=vacancy_id,
                vacancy_title=vacancy_title,
                message_type=message_type,
                sender=sender,
                message_text=message_text,
                timestamp=datetime.now().isoformat(),
                is_read=(sender == "user"),  # Сообщения от пользователя сразу прочитаны
                has_media=has_media,
                media_type=media_type,
                media_path=media_path,
                media_filename=media_filename,
            )
            session.add(chat_message)
            await session.commit()
            await session.refresh(chat_message)
            return chat_message

    async def get_user_chats(self, user_id: int) -> List[dict]:
        """
        Получить список всех чатов пользователя (уникальные кандидаты)
        с последним сообщением и количеством непрочитанных
        """
        async with AsyncSession(self.engine) as session:
            # Получаем все сообщения пользователя
            stmt = (
                select(Chat)
                .where(Chat.user_id == user_id)
                .order_by(desc(Chat.timestamp))
            )
            result = await session.execute(stmt)
            all_messages = result.scalars().all()

            # Группируем по кандидатам
            chats_dict = {}
            for msg in all_messages:
                key = (msg.candidate_fullname, msg.message_type)
                if key not in chats_dict:
                    chats_dict[key] = {
                        "candidate_id": msg.candidate_id,  # Добавлено
                        "candidate_fullname": msg.candidate_fullname,
                        "vacancy_id": msg.vacancy_id,
                        "vacancy_title": msg.vacancy_title,  # Добавлено
                        "message_type": msg.message_type,
                        "last_message": msg.message_text,
                        "last_timestamp": msg.timestamp,
                        "unread_count": 0,
                    }
                
                # Считаем непрочитанные сообщения от кандидата
                if msg.sender == "candidate" and not msg.is_read:
                    chats_dict[key]["unread_count"] += 1

            return list(chats_dict.values())

    async def get_chat_messages(
        self,
        user_id: int,
        candidate_fullname: str,
        message_type: str,
        limit: int = 100,
    ) -> List[Chat]:
        """
        Получить все сообщения в конкретном чате
        """
        async with AsyncSession(self.engine) as session:
            stmt = (
                select(Chat)
                .where(
                    and_(
                        Chat.user_id == user_id,
                        Chat.candidate_fullname == candidate_fullname,
                        Chat.message_type == message_type,
                    )
                )
                .order_by(Chat.timestamp)
                .limit(limit)
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def mark_messages_as_read(
        self,
        user_id: int,
        candidate_fullname: str,
        message_type: str,
    ) -> int:
        """
        Отметить все сообщения от кандидата как прочитанные
        """
        async with AsyncSession(self.engine) as session:
            stmt = (
                select(Chat)
                .where(
                    and_(
                        Chat.user_id == user_id,
                        Chat.candidate_fullname == candidate_fullname,
                        Chat.message_type == message_type,
                        Chat.sender == "candidate",
                        Chat.is_read == False,
                    )
                )
            )
            result = await session.execute(stmt)
            messages = result.scalars().all()

            count = 0
            for msg in messages:
                msg.is_read = True
                count += 1

            if count > 0:
                await session.commit()

            return count

    async def get_unread_count(self, user_id: int) -> int:
        """
        Получить общее количество непрочитанных сообщений пользователя
        """
        async with AsyncSession(self.engine) as session:
            stmt = select(Chat).where(
                and_(
                    Chat.user_id == user_id,
                    Chat.sender == "candidate",
                    Chat.is_read == False,
                )
            )
            result = await session.execute(stmt)
            messages = result.scalars().all()
            return len(messages)

    async def search_messages(
        self,
        user_id: int,
        search_query: str,
        message_type: Optional[str] = None,
    ) -> List[Chat]:
        """
        Поиск сообщений по тексту
        """
        async with AsyncSession(self.engine) as session:
            conditions = [
                Chat.user_id == user_id,
                Chat.message_text.ilike(f"%{search_query}%"),
            ]
            
            if message_type:
                conditions.append(Chat.message_type == message_type)

            stmt = (
                select(Chat)
                .where(and_(*conditions))
                .order_by(desc(Chat.timestamp))
                .limit(50)
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def mark_as_read(
        self,
        user_id: int,
        candidate_fullname: str,
        message_type: str
    ):
        """
        Пометить все сообщения от кандидата как прочитанные
        """
        async with AsyncSession(self.engine) as session:
            # Находим все непрочитанные сообщения от этого кандидата
            stmt = (
                select(Chat)
                .where(
                    Chat.user_id == user_id,
                    Chat.candidate_fullname == candidate_fullname,
                    Chat.message_type == message_type,
                    Chat.sender == "candidate",  # Только сообщения от кандидата
                    Chat.is_read == False
                )
            )
            result = await session.execute(stmt)
            messages = result.scalars().all()
            
            # Помечаем все как прочитанные
            for msg in messages:
                msg.is_read = True
                session.add(msg)
            
            await session.commit()
            print(f"[CHAT_DB] Помечено как прочитанные {len(messages)} сообщений от {candidate_fullname}")

    async def mark_last_message_as_unread(
        self,
        user_id: int,
        candidate_fullname: str,
        message_type: str,
    ) -> int:
        """
        Пометить последнее прочитанное сообщение от кандидата как непрочитанное
        Возвращает количество обновленных сообщений (0 или 1)
        """
        async with AsyncSession(self.engine) as session:
            # Находим последнее прочитанное сообщение от кандидата
            stmt = (
                select(Chat)
                .where(
                    and_(
                        Chat.user_id == user_id,
                        Chat.candidate_fullname == candidate_fullname,
                        Chat.message_type == message_type,
                        Chat.sender == "candidate",  # Только сообщения от кандидата
                        Chat.is_read == True,  # Только прочитанные
                    )
                )
                .order_by(desc(Chat.timestamp))  # Сортируем по времени (новые первые)
                .limit(1)  # Берем только последнее
            )
            result = await session.execute(stmt)
            message = result.scalar_one_or_none()
            
            if message:
                message.is_read = False
                session.add(message)
                await session.commit()
                print(f"[CHAT_DB] Последнее сообщение от {candidate_fullname} помечено как непрочитанное")
                return 1
            else:
                print(f"[CHAT_DB] Нет прочитанных сообщений от {candidate_fullname} для пометки")
                return 0

    async def delete_chat_messages(
        self,
        user_id: int,
        candidate_fullname: str,
        message_type: str
    ) -> int:
        """
        Удалить все сообщения с кандидатом
        Возвращает количество удаленных сообщений
        """
        async with AsyncSession(self.engine) as session:
            # Используем delete() statement для более эффективного удаления
            stmt = delete(Chat).where(
                Chat.user_id == user_id,
                Chat.candidate_fullname == candidate_fullname,
                Chat.message_type == message_type
            )
            
            result = await session.execute(stmt)
            await session.commit()
            
            count = result.rowcount
            print(f"[CHAT_DB] ✅ Удалено {count} сообщений от {candidate_fullname} ({message_type})")
            
            return count

    async def get_all_users_with_chats(self) -> List[dict]:
        """
        Получить всех пользователей, у которых есть чаты (для админки)
        Возвращает список пользователей с информацией о количестве чатов
        """
        from .database import User
        async with AsyncSession(self.engine) as session:
            # Получаем уникальные user_id из чатов
            stmt = select(Chat.user_id).distinct()
            result = await session.execute(stmt)
            user_ids = [row[0] for row in result.all() if row[0] is not None]
            
            # Для каждого пользователя получаем информацию и считаем статистику
            users_with_chats = []
            for user_id in user_ids:
                # Получаем информацию о пользователе
                user_stmt = select(User).where(User.id == user_id)
                user_result = await session.execute(user_stmt)
                user = user_result.scalar_one_or_none()
                
                if not user:
                    continue
                
                # Считаем статистику
                chats = await self.get_user_chats(user_id)
                total_messages = await self.get_total_messages_count(user_id)
                unread_count = await self.get_unread_count(user_id)
                
                users_with_chats.append({
                    "user_id": user_id,
                    "email": user.email,
                    "chats_count": len(chats),
                    "total_messages": total_messages,
                    "unread_count": unread_count,
                })
            
            return users_with_chats

    async def get_total_messages_count(self, user_id: int) -> int:
        """
        Получить общее количество сообщений пользователя
        """
        async with AsyncSession(self.engine) as session:
            stmt = select(Chat).where(Chat.user_id == user_id)
            result = await session.execute(stmt)
            messages = result.scalars().all()
            return len(messages)

    async def get_chat_messages_admin(
        self,
        user_id: int,
        candidate_fullname: str,
        message_type: str,
        limit: int = 1000,  # Для админа больше лимит
    ) -> List[Chat]:
        """
        Получить все сообщения в конкретном чате (для админа, без ограничений)
        """
        async with AsyncSession(self.engine) as session:
            stmt = (
                select(Chat)
                .where(
                    and_(
                        Chat.user_id == user_id,
                        Chat.candidate_fullname == candidate_fullname,
                        Chat.message_type == message_type,
                    )
                )
                .order_by(Chat.timestamp)
                .limit(limit)
            )
            result = await session.execute(stmt)
            return result.scalars().all()


# Singleton instance
chat_repository = ChatRepository()

