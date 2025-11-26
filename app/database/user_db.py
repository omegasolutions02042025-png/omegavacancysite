from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import engine, User, UserComunication, UserNotification, Sverka
from ..core.passwords import hash_password, verify_password


class UserRepository:
    def __init__(self):
        self.engine = engine

    async def get_by_email(self, email: str) -> Optional[User]:
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(User).where(User.email == email)
            )
            return result.scalars().first()

    async def create_user(
        self,
        email: str,
        password: str,
    ) -> User:

        async with AsyncSession(self.engine) as session:
            # Проверяем, есть ли пользователь
            result = await session.execute(
                select(User).where(User.email == email)
            )
            existing = result.scalars().first()
            if existing:
                print("User already exists")
                return None

            hashed_password = hash_password(password)

            user = User(
                email=email,
                hashed_password=hashed_password,
                work_telegram="",
                work_email="",
                work_telegram_session_name="",
                work_email_app_pass="",
            )

            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def authenticate(self, email: str, password: str) -> Optional[User]:
        user = await self.get_by_email(email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user


    async def get_by_id(self, user_id: int) -> User | None:
        async with AsyncSession(self.engine) as session:
            res = await session.execute(
                select(User).where(User.id == user_id)
            )
            return res.scalars().first()

    async def update_user_telegram(self, user_id: int, session_name: str, username: str) -> User | None:
        async with AsyncSession(self.engine) as session:
            user = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = user.scalars().first()
            if not user:
                return None
            user.work_telegram = username
            user.work_telegram_session_name = session_name
            await session.commit()
            await session.refresh(user)
            return user

    async def update_user_email(self, user_id: int, email: str, password: str) -> User | None:
        async with AsyncSession(self.engine) as session:
            user = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = user.scalars().first()
            if not user:
                return None
            user.work_email = email
            user.work_email_app_pass = password
            await session.commit()
            await session.refresh(user)
            return user
    

    async def create_user_comunication(self, user_id: int, email_user : str|None, telegram_user_id : str|None, vacancy_id : str|None, candidate_fullname : str|None) -> User | None:
        async with AsyncSession(self.engine) as session:
            user = await session.execute(
                select(UserComunication).where(UserComunication.user_id == user_id, UserComunication.email_user == email_user, UserComunication.telegram_user_id == telegram_user_id, UserComunication.vacancy_id == vacancy_id, UserComunication.candidate_fullname == candidate_fullname)
            )
            user = user.scalars().first()
            if user:
                print("User comunication already exists")
                return user
            user = UserComunication(
                user_id=user_id,
                email_user=email_user,
                telegram_user_id=telegram_user_id,
                vacancy_id=vacancy_id,
                candidate_fullname=candidate_fullname
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user
    
    async def get_user_sessions(self) -> list[tuple[str, int]]:
        async with AsyncSession(self.engine) as session:
            res = await session.execute(
                select(
                    User.work_telegram_session_name,
                    User.id,
                ).where(User.work_telegram_session_name.is_not(None))
            )
            # вернёт список кортежей: [(session_name, user_id), ...]
            rows: list[tuple[str, int]] = res.all()
            return rows
    
    async def get_chat_id_candidates(self, user_id: int) -> list[str]:
        async with AsyncSession(self.engine) as session:
            res = await session.execute(
                select(UserComunication.telegram_user_id).where(UserComunication.user_id == user_id).where(UserComunication.telegram_user_id.is_not(None)) 
            )
            return res.scalars().all()

    async def add_user_notification(self, user_id: int, notification: str, url: str) -> User | None:
        async with AsyncSession(self.engine) as session:
            user = await session.execute(
                select(UserNotification).where(UserNotification.user_id == user_id, UserNotification.notification == notification)
            )
            user = user.scalars().first()
            if user:
                print("User notification already exists")
                return user
            user = UserNotification(
                user_id=user_id,
                notification=notification,
                url=url
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def delete_user_notification(self, user_id: int, notification: str) -> User | None:
        async with AsyncSession(self.engine) as session:
            user = await session.execute(
                select(UserNotification).where(UserNotification.user_id == user_id, UserNotification.notification == notification)
            )
            user = user.scalars().first()
            if not user:
                print("User notification not found")
                return None
            await session.delete(user)
            await session.commit()
            return user
    


    async def get_user_notifications(self, user_id: int) -> list[UserNotification]:
        async with AsyncSession(self.engine) as session:
            res = await session.execute(
                select(UserNotification).where(UserNotification.user_id == user_id)
            )
            return res.scalars().all()
    

    async def get_candidate_by_chat_id(self, chat_id: int) -> User | None:
        async with AsyncSession(self.engine) as session:
            res = await session.execute(
                select(UserComunication).where(UserComunication.telegram_user_id == chat_id)
            )
            return res.scalars().first()



    async def get_users_with_work_email(self) -> list[User]:
        """
        Все пользователи, у кого настроена рабочая почта (email + app_pass).
        Будем по ним запускать e-mail listener.
        """
        async with AsyncSession(self.engine) as session:
            res = await session.execute(
                select(User).where(
                    User.work_email.is_not(None),
                    User.work_email != "",
                    User.work_email_app_pass.is_not(None),
                    User.work_email_app_pass != "",
                )
            )
            return res.scalars().all()

    async def find_candidate_by_email(self, user_id: int, email: str) -> Optional[UserComunication]:
        """
        Ищем кандидата по email отправителя в таблице UserComunication.
        Важно: фильтруем по user_id, чтобы рекрутёр видел только своих кандидатов.
        work_email этого рекрутёра 'слушает' все email_user его кандидатов.
        """
        email = (email or "").strip().lower()
        if not email:
            return None

        async with AsyncSession(self.engine) as session:
            res = await session.execute(
                select(UserComunication).where(
                    UserComunication.user_id == user_id,
                    UserComunication.email_user.is_not(None),
                    UserComunication.email_user != "",
                    UserComunication.email_user.ilike(email),
                )
            )
            return res.scalars().first()



    async def get_sverka_history(self, user_id: int) -> list[dict]:
        async with AsyncSession(self.engine) as session:
            # берём именно объекты Sverka, а не Row
            res = await session.execute(
                select(Sverka).where(Sverka.user_id == user_id)
            )
            rows: list[Sverka] = res.scalars().all()

            unic: dict[str, dict] = {}

            for s in rows:
                # s — это экземпляр модели Sverka
                data = s.sverka_json or {}
                vacancy_block = data.get("vacancy") or {}
                print(vacancy_block)
                title = vacancy_block.get("position_name") or "Вакансия"

                # чтобы по одному разу на странице
                if s.vacancy_id not in unic:
                    unic[s.vacancy_id] = {
                        "vacancy_id": s.vacancy_id,
                        "title": title,
                    }

            return list(unic.values())

    async def get_sverka_by_vac_id_and_slug(self, user_id: int, vacancy_id: str, slug: str) -> Optional[Sverka]:
        async with AsyncSession(self.engine) as session:
            res = await session.execute(
                select(Sverka).where(Sverka.user_id == user_id, Sverka.vacancy_id == vacancy_id, Sverka.slug == slug)
            )
            return res.scalars().first()