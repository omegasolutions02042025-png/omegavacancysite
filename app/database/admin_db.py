from typing import Optional, List
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import Admin, User, engine, CandidateProfileDB, Sverka, UserCustomerAccess, CustomerDropdown
from ..core.passwords import hash_password, verify_password


class AdminRepository:
    """
    Репозиторий для работы с администраторами.
    
    Управляет созданием, аутентификацией администраторов и созданием рекрутеров.
    """
    
    def __init__(self):
        """Инициализация репозитория с подключением к базе данных."""
        self.engine = engine

    async def create_admin(self, username: str, password: str) -> Optional[Admin]:
        """
        Создать нового администратора.
        
        Проверяет что администратор с таким username не существует.
        Пароль хешируется перед сохранением.
        
        Args:
            username: Имя пользователя администратора
            password: Пароль администратора (будет захеширован)
            
        Returns:
            Admin: Созданный администратор или None если уже существует
        """
        async with AsyncSession(self.engine) as session:
            # Проверяем существует ли админ
            existing = await session.execute(
                select(Admin).where(Admin.username == username)
            )
            if existing.scalars().first():
                return None
            
            admin = Admin(
                username=username,
                hashed_password=hash_password(password),
                created_at=datetime.now().isoformat()
            )
            session.add(admin)
            await session.commit()
            await session.refresh(admin)
            print(f"[ADMIN_DB] ✅ Создан администратор: {username}")
            return admin

    async def authenticate(self, username: str, password: str) -> Optional[Admin]:
        """
        Аутентификация администратора по username и паролю.
        
        Args:
            username: Имя пользователя администратора
            password: Пароль администратора
            
        Returns:
            Admin: Администратор если учетные данные верны, иначе None
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(Admin).where(Admin.username == username)
            )
            admin = result.scalars().first()
            
            if not admin:
                return None
            
            if not verify_password(password, admin.hashed_password):
                return None
            
            return admin

    async def get_by_id(self, admin_id: int) -> Optional[Admin]:
        """
        Получить администратора по ID.
        
        Args:
            admin_id: ID администратора
            
        Returns:
            Admin: Администратор или None если не найден
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(Admin).where(Admin.id == admin_id)
            )
            return result.scalars().first()

    async def create_recruiter(self, email: str, password: str, admin_id: int) -> Optional[User]:
        """
        Создать аккаунт рекрутера.
        
        Пароль хранится в открытом виде для просмотра администратором.
        
        Args:
            email: Email рекрутера
            password: Пароль рекрутера (хранится в открытом виде)
            admin_id: ID администратора, создавшего рекрутера
            
        Returns:
            User: Созданный рекрутер или None если уже существует
        """
        async with AsyncSession(self.engine) as session:
            # Проверяем существует ли пользователь
            existing = await session.execute(
                select(User).where(User.email == email)
            )
            if existing.scalars().first():
                return None
            
            user = User(
                email=email,
                password=password,  # Храним в открытом виде для администратора
                created_by_admin=admin_id,
                created_at=datetime.now().isoformat()
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            print(f"[ADMIN_DB] ✅ Создан рекрутер: {email} (admin_id={admin_id})")
            return user

    async def get_all_recruiters(self) -> List[User]:
        """
        Получить список всех рекрутеров.
        
        Возвращает только пользователей, созданных администратором.
        
        Returns:
            List[User]: Список всех рекрутеров
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(User).where(User.created_by_admin.isnot(None))
            )
            return list(result.scalars().all())

    async def get_all_candidates(self) -> List[CandidateProfileDB]:
        """
        Получить всех кандидатов из всех рекрутеров.
        
        Администратор может видеть всех кандидатов независимо от рекрутера.
        
        Returns:
            List[CandidateProfileDB]: Список всех кандидатов
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(CandidateProfileDB)
            )
            return list(result.scalars().all())

    async def get_all_sverkas(self) -> List[Sverka]:
        """
        Получить все сверки из всех рекрутеров.
        
        Администратор может видеть все сверки независимо от рекрутера.
        
        Returns:
            List[Sverka]: Список всех сверок
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(Sverka)
            )
            return list(result.scalars().all())

    async def grant_customer_access(self, user_id: int, customer_id: int) -> bool:
        """
        Предоставить рекрутеру доступ к заказчику.
        
        Args:
            user_id: ID рекрутера
            customer_id: ID заказчика
            
        Returns:
            bool: True если доступ предоставлен, False если уже существует
        """
        async with AsyncSession(self.engine) as session:
            # Проверяем существует ли уже доступ
            existing = await session.execute(
                select(UserCustomerAccess).where(
                    UserCustomerAccess.user_id == user_id,
                    UserCustomerAccess.customer_id == customer_id
                )
            )
            if existing.scalars().first():
                return False
            
            access = UserCustomerAccess(
                user_id=user_id,
                customer_id=customer_id,
                created_at=datetime.now().isoformat()
            )
            session.add(access)
            await session.commit()
            print(f"[ADMIN_DB] ✅ Предоставлен доступ user_id={user_id} к customer_id={customer_id}")
            return True

    async def revoke_customer_access(self, user_id: int, customer_id: int) -> bool:
        """
        Отозвать доступ рекрутера к заказчику.
        
        Args:
            user_id: ID рекрутера
            customer_id: ID заказчика
            
        Returns:
            bool: True если доступ отозван, False если не найден
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(UserCustomerAccess).where(
                    UserCustomerAccess.user_id == user_id,
                    UserCustomerAccess.customer_id == customer_id
                )
            )
            access = result.scalars().first()
            if not access:
                return False
            
            await session.delete(access)
            await session.commit()
            print(f"[ADMIN_DB] ✅ Отозван доступ user_id={user_id} к customer_id={customer_id}")
            return True

    async def get_user_customer_access(self, user_id: int) -> List[int]:
        """
        Получить список ID заказчиков, к которым у рекрутера есть доступ.
        
        Args:
            user_id: ID рекрутера
            
        Returns:
            List[int]: Список ID заказчиков
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(UserCustomerAccess.customer_id).where(
                    UserCustomerAccess.user_id == user_id
                )
            )
            return list(result.scalars().all())

    async def has_customer_access(self, user_id: int) -> bool:
        """
        Проверить есть ли у рекрутера доступ хотя бы к одному заказчику.
        
        Args:
            user_id: ID рекрутера
            
        Returns:
            bool: True если есть доступ, False если нет
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(UserCustomerAccess).where(
                    UserCustomerAccess.user_id == user_id
                ).limit(1)
            )
            return result.scalars().first() is not None


    async def change_user_password(self, user_id: int, new_password: str) -> Optional[User]:
        """
        Изменить пароль пользователя (рекрутера).
        
        Args:
            user_id: ID пользователя
            new_password: Новый пароль
            
        Returns:
            User: Объект пользователя если успешно, None если пользователь не найден
        """
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalars().first()
            
            if not user:
                return None
            
            user.password = new_password
            user.password_changed_at = datetime.now().isoformat()
            await session.commit()
            await session.refresh(user)
            print(f"[ADMIN_DB] ✅ Пароль изменен для user_id={user_id}")
            return user


# Singleton
admin_repository = AdminRepository()

