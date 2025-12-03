from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from .database import engine, User, UserComunication, UserNotification, Sverka, PasswordResetToken, TelegramDialogStatus


class UserRepository:
    """
    Репозиторий для работы с пользователями (рекрутерами).
    
    Управляет созданием, аутентификацией и обновлением данных пользователей.
    Пароли хранятся в открытом виде для просмотра администратором.
    """
    
    def __init__(self):
        """Инициализация репозитория с подключением к базе данных."""
        self.engine = engine

    async def get_by_email(self, email: str) -> Optional[User]:
        """
        Получить пользователя по email.
        
        Args:
            email: Email пользователя
            
        Returns:
            User: Пользователь или None если не найден
        """
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
        """
        Создать нового пользователя.
        
        Проверяет что пользователь с таким email не существует.
        Пароль хранится в открытом виде.
        
        Args:
            email: Email пользователя
            password: Пароль пользователя (хранится в открытом виде)
            
        Returns:
            User: Созданный пользователь или None если уже существует
        """

        async with AsyncSession(self.engine) as session:
            # Проверяем, есть ли пользователь
            result = await session.execute(
                select(User).where(User.email == email)
            )
            existing = result.scalars().first()
            if existing:
                print("User already exists")
                return None

            user = User(
                email=email,
                password=password,  # Храним в открытом виде
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
        """
        Аутентификация пользователя по email и паролю.
        
        Сравнивает пароли напрямую (без хеширования).
        
        Args:
            email: Email пользователя
            password: Пароль пользователя
            
        Returns:
            User: Пользователь если учетные данные верны, иначе None
        """
        user = await self.get_by_email(email)
        if not user:
            return None
        # Сравниваем пароли напрямую (без хеширования)
        if password != user.password:
            return None
        return user


    async def get_by_id(self, user_id: int) -> User | None:
        """
        Получить пользователя по ID.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            User: Пользователь или None если не найден
        """
        async with AsyncSession(self.engine) as session:
            res = await session.execute(
                select(User).where(User.id == user_id)
            )
            return res.scalars().first()

    async def update_user_telegram(self, user_id: int, session_name: str, username: str) -> User | None:
        """
        Обновить данные Telegram пользователя.
        
        Args:
            user_id: ID пользователя
            session_name: Имя сессии Telegram
            username: Username в Telegram
            
        Returns:
            User: Обновленный пользователь или None если не найден
        """
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
        """
        Обновить рабочую почту пользователя.
        
        Args:
            user_id: ID пользователя
            email: Email адрес
            password: Пароль приложения для email
            
        Returns:
            User: Обновленный пользователь или None если не найден
        """
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

    async def update_profile(
        self,
        user_id: int,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        middle_name: Optional[str] = None,
        phone: Optional[str] = None,
        experience: Optional[str] = None,
        specialization: Optional[str] = None,
        resume: Optional[str] = None,
    ) -> User | None:
        """
        Обновить профиль рекрутера.
        
        Args:
            user_id: ID пользователя
            first_name: Имя рекрутера
            last_name: Фамилия рекрутера
            middle_name: Отчество рекрутера
            phone: Телефон рекрутера
            experience: Опыт работы
            specialization: Специализация
            resume: Резюме (текст или путь к файлу)
            
        Returns:
            User: Обновленный пользователь или None если не найден
        """
        async with AsyncSession(self.engine) as session:
            user = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = user.scalars().first()
            if not user:
                return None
            
            # Обновляем только переданные поля
            if first_name is not None:
                user.first_name = first_name
            if last_name is not None:
                user.last_name = last_name
            if middle_name is not None:
                user.middle_name = middle_name
            if phone is not None:
                user.phone = phone
            if experience is not None:
                user.experience = experience
            if specialization is not None:
                user.specialization = specialization
            if resume is not None:
                user.resume = resume
            
            await session.commit()
            await session.refresh(user)
            return user

    async def reset_password(self, email: str, new_password: str) -> bool:
        """
        Сброс пароля пользователя по email.
        Возвращает True если пароль успешно обновлен, False если пользователь не найден.
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(User).where(User.email == email)
            )
            user = result.scalars().first()
            if not user:
                return False
            
            user.password = new_password  # Храним в открытом виде
            await session.commit()
            return True

    async def create_password_reset_token(self, email: str) -> Optional[str]:
        """
        Создает токен для восстановления пароля.
        
        Args:
            email: Email пользователя
            
        Returns:
            Optional[str]: Токен восстановления или None, если пользователь не найден
        """
        from datetime import datetime, timedelta
        import secrets
        
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(User).where(User.email == email)
            )
            user = result.scalars().first()
            if not user:
                return None
            
            # Генерируем токен
            token = secrets.token_urlsafe(32)
            
            # Устанавливаем время истечения (24 часа)
            expires_at = (datetime.now() + timedelta(hours=24)).isoformat()
            created_at = datetime.now().isoformat()
            
            # Создаем запись токена
            reset_token = PasswordResetToken(
                user_id=user.id,
                token=token,
                created_at=created_at,
                expires_at=expires_at,
                used=False
            )
            
            session.add(reset_token)
            await session.commit()
            
            return token

    async def verify_password_reset_token(self, token: str) -> Optional[User]:
        """
        Проверяет токен восстановления пароля и возвращает пользователя.
        
        Args:
            token: Токен восстановления
            
        Returns:
            Optional[User]: Пользователь, если токен валиден, иначе None
        """
        from datetime import datetime
        
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(PasswordResetToken).where(
                    PasswordResetToken.token == token,
                    PasswordResetToken.used == False
                )
            )
            reset_token = result.scalars().first()
            
            if not reset_token:
                return None
            
            # Проверяем срок действия
            if reset_token.expires_at:
                expires_at = datetime.fromisoformat(reset_token.expires_at)
                if datetime.now() > expires_at:
                    return None
            
            # Получаем пользователя
            user_result = await session.execute(
                select(User).where(User.id == reset_token.user_id)
            )
            user = user_result.scalars().first()
            
            return user

    async def reset_password_by_token(self, token: str, new_password: str) -> bool:
        """
        Сбрасывает пароль по токену восстановления.
        
        Args:
            token: Токен восстановления
            new_password: Новый пароль
            
        Returns:
            bool: True если пароль успешно обновлен, False в противном случае
        """
        from datetime import datetime
        
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(PasswordResetToken).where(
                    PasswordResetToken.token == token,
                    PasswordResetToken.used == False
                )
            )
            reset_token = result.scalars().first()
            
            if not reset_token:
                return False
            
            # Проверяем срок действия
            if reset_token.expires_at:
                expires_at = datetime.fromisoformat(reset_token.expires_at)
                if datetime.now() > expires_at:
                    return False
            
            # Получаем пользователя
            user_result = await session.execute(
                select(User).where(User.id == reset_token.user_id)
            )
            user = user_result.scalars().first()
            
            if not user:
                return False
            
            # Обновляем пароль
            user.password = new_password  # Храним в открытом виде
            
            # Помечаем токен как использованный
            reset_token.used = True
            
            await session.commit()
            return True
    

    async def create_user_comunication(self, user_id: int, email_user : str|None, telegram_user_id : str|None, vacancy_id : str|None, candidate_fullname : str|None) -> User | None:
        """
        Создать запись о связи пользователя с кандидатом.
        
        Хранит информацию о способах связи с кандидатом (email, telegram).
        
        Args:
            user_id: ID пользователя (рекрутера)
            email_user: Email кандидата
            telegram_user_id: Telegram ID кандидата
            vacancy_id: ID вакансии
            candidate_fullname: Полное имя кандидата
            
        Returns:
            UserComunication: Созданная или существующая запись связи
        """
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
        """
        Получить список всех активных Telegram сессий пользователей.
        
        Returns:
            list[tuple[str, int]]: Список кортежей (session_name, user_id)
        """
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
        """
        Получить список Telegram ID всех кандидатов пользователя.
        
        Args:
            user_id: ID пользователя (рекрутера)
            
        Returns:
            list[str]: Список Telegram ID кандидатов
        """
        async with AsyncSession(self.engine) as session:
            res = await session.execute(
                select(UserComunication.telegram_user_id).where(UserComunication.user_id == user_id).where(UserComunication.telegram_user_id.is_not(None)) 
            )
            return res.scalars().all()

    async def add_user_notification(self, user_id: int, notification: str, url: str) -> User | None:
        """
        Добавить уведомление пользователю.
        
        Args:
            user_id: ID пользователя
            notification: Текст уведомления
            url: URL для перехода при клике на уведомление
            
        Returns:
            UserNotification: Созданное или существующее уведомление
        """
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
        """
        Удалить уведомление пользователя.
        
        Args:
            user_id: ID пользователя
            notification: Текст уведомления для удаления
            
        Returns:
            UserNotification: Удаленное уведомление или None если не найдено
        """
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
        """
        Получить все уведомления пользователя.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            list[UserNotification]: Список всех уведомлений пользователя
        """
        async with AsyncSession(self.engine) as session:
            res = await session.execute(
                select(UserNotification).where(UserNotification.user_id == user_id)
            )
            return res.scalars().all()
    

    async def get_candidate_by_chat_id(self, chat_id: int) -> User | None:
        """
        Получить запись связи по Telegram chat ID кандидата.
        
        Args:
            chat_id: Telegram chat ID кандидата
            
        Returns:
            UserComunication: Запись связи или None если не найдена
        """
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
        """
        Получить историю сверок пользователя.
        
        Возвращает уникальный список вакансий с которыми были сделаны сверки.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            list[dict]: Список словарей с vacancy_id и title вакансий
        """
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
        """
        Получить сверку по ID вакансии и slug.
        
        Args:
            user_id: ID пользователя
            vacancy_id: ID вакансии
            slug: Slug сверки
            
        Returns:
            Sverka: Сверка или None если не найдена
        """
        async with AsyncSession(self.engine) as session:
            res = await session.execute(
                select(Sverka).where(Sverka.user_id == user_id, Sverka.vacancy_id == vacancy_id, Sverka.slug == slug)
            )
            return res.scalars().first()

    async def get_telegram_user_id_by_candidate_fullname_and_user_id_and_vacancy_id(self, user_id: int, candidate_fullname: str, vacancy_id: Optional[str]) -> Optional[int]:
        """
        Получить Telegram ID кандидата по его имени, user_id и vacancy_id.
        
        Args:
            user_id: ID пользователя (рекрутера)
            candidate_fullname: Полное имя кандидата
            vacancy_id: ID вакансии (может быть None)
            
        Returns:
            int: Telegram ID кандидата или None если не найден
        """
        async with AsyncSession(self.engine) as session:
            # Если vacancy_id указан - ищем с ним
            if vacancy_id:
                res = await session.execute(
                    select(UserComunication).where(
                        UserComunication.user_id == user_id,
                        UserComunication.candidate_fullname == candidate_fullname,
                        UserComunication.vacancy_id == vacancy_id
                    )
                )
                user = res.scalars().first()
                if user and user.telegram_user_id:
                    return user.telegram_user_id
            
            # Если не нашли с vacancy_id или vacancy_id=None - ищем любую запись для этого кандидата
            res = await session.execute(
                select(UserComunication).where(
                    UserComunication.user_id == user_id,
                    UserComunication.candidate_fullname == candidate_fullname,
                    UserComunication.telegram_user_id.is_not(None)
                ).order_by(UserComunication.id.desc())  # Берем последнюю запись
            )
            user = res.scalars().first()
            if not user:
                return None
            return user.telegram_user_id

    async def get_email_by_candidate_fullname_and_user_id_and_vacancy_id(self, user_id: int, candidate_fullname: str, vacancy_id: str) -> str:
        """
        Получить email кандидата по его имени, user_id и vacancy_id
        """
        async with AsyncSession(self.engine) as session:
            res = await session.execute(
                select(UserComunication).where(
                    UserComunication.user_id == user_id,
                    UserComunication.candidate_fullname == candidate_fullname,
                    UserComunication.vacancy_id == vacancy_id
                )
            )
            user = res.scalars().first()
            if not user:
                return None
            return user.email_user

    async def delete_user_comunication_by_candidate(
        self, user_id: int, candidate_fullname: str
    ) -> int:
        """
        Удалить все записи UserComunication для кандидата
        Возвращает количество удаленных записей
        """
        async with AsyncSession(self.engine) as session:
            # Используем delete() statement для более эффективного удаления
            stmt = delete(UserComunication).where(
                UserComunication.user_id == user_id,
                UserComunication.candidate_fullname == candidate_fullname
            )
            
            result = await session.execute(stmt)
            await session.commit()
            
            count = result.rowcount
            print(f"[USER_DB] ✅ Удалено {count} записей UserComunication для {candidate_fullname}")
            
            return count

    async def get_telegram_dialog_status(self, user_id: int, telegram_chat_id: int) -> Optional[TelegramDialogStatus]:
        """
        Получить статус диалога (добавлен/скрыт)
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(TelegramDialogStatus).where(
                    TelegramDialogStatus.user_id == user_id,
                    TelegramDialogStatus.telegram_chat_id == telegram_chat_id
                )
            )
            return result.scalars().first()

    async def set_telegram_dialog_status(
        self, user_id: int, telegram_chat_id: int, status: str
    ) -> TelegramDialogStatus:
        """
        Установить статус диалога ('added' или 'hidden')
        """
        from datetime import datetime
        async with AsyncSession(self.engine) as session:
            # Проверяем существующую запись в той же сессии
            result = await session.execute(
                select(TelegramDialogStatus).where(
                    TelegramDialogStatus.user_id == user_id,
                    TelegramDialogStatus.telegram_chat_id == telegram_chat_id
                )
            )
            existing = result.scalars().first()
            
            if existing:
                existing.status = status
                await session.commit()
                await session.refresh(existing)
                return existing
            
            # Создаем новую запись
            dialog_status = TelegramDialogStatus(
                user_id=user_id,
                telegram_chat_id=telegram_chat_id,
                status=status,
                created_at=datetime.now().isoformat()
            )
            session.add(dialog_status)
            await session.commit()
            await session.refresh(dialog_status)
            return dialog_status

    async def get_added_telegram_chat_ids(self, user_id: int) -> list[int]:
        """
        Получить список ID уже добавленных Telegram чатов
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(TelegramDialogStatus.telegram_chat_id).where(
                    TelegramDialogStatus.user_id == user_id,
                    TelegramDialogStatus.status == "added"
                )
            )
            return [int(chat_id) for chat_id in result.scalars().all()]

    async def get_hidden_telegram_chat_ids(self, user_id: int) -> list[int]:
        """
        Получить список ID скрытых Telegram чатов
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(TelegramDialogStatus.telegram_chat_id).where(
                    TelegramDialogStatus.user_id == user_id,
                    TelegramDialogStatus.status == "hidden"
                )
            )
            return [int(chat_id) for chat_id in result.scalars().all()]

    async def delete_telegram_dialog_status(
        self, user_id: int, telegram_chat_id: int
    ) -> bool:
        """
        Удалить статус диалога (чтобы диалог снова стал доступен для добавления)
        """
        async with AsyncSession(self.engine) as session:
            stmt = delete(TelegramDialogStatus).where(
                TelegramDialogStatus.user_id == user_id,
                TelegramDialogStatus.telegram_chat_id == telegram_chat_id
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def archive_user(self, user_id: int, admin_id: int) -> Optional[User]:
        """
        Перевести пользователя в архив.
        
        Пользователи в архиве не могут входить в систему.
        
        Args:
            user_id: ID пользователя для архивации
            admin_id: ID администратора, выполняющего действие
            
        Returns:
            User: Обновленный пользователь или None если не найден
        """
        from datetime import datetime
        
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalars().first()
            
            if not user:
                return None
            
            user.is_archived = True
            user.archived_at = datetime.now().isoformat()
            user.archived_by_admin = admin_id
            
            await session.commit()
            await session.refresh(user)
            
            print(f"[USER_DB] ✅ Пользователь {user.email} (ID: {user_id}) переведен в архив")
            return user

    async def unarchive_user(self, user_id: int) -> Optional[User]:
        """
        Восстановить пользователя из архива.
        
        Args:
            user_id: ID пользователя для восстановления
            
        Returns:
            User: Обновленный пользователь или None если не найден
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalars().first()
            
            if not user:
                return None
            
            user.is_archived = False
            user.archived_at = None
            user.archived_by_admin = None
            
            await session.commit()
            await session.refresh(user)
            
            print(f"[USER_DB] ✅ Пользователь {user.email} (ID: {user_id}) восстановлен из архива")
            return user