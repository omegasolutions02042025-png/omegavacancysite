"""
Скрипт для создания системного пользователя для сбора резюме.

Проверяет существование пользователя с email cv@omega-solutions.ru.
Если не существует - создает его с ролью RECRUITER.
"""

import asyncio
import secrets
from app.database.user_db import UserRepository
from app.database.database import UserRole

SYSTEM_EMAIL = "cv@omega-solutions.ru"
SYSTEM_PASSWORD = secrets.token_urlsafe(16)  # Генерируем случайный пароль


async def ensure_system_user():
    """
    Проверяет и создает системного пользователя для сбора резюме.
    """
    user_repo = UserRepository()
    
    print(f"🔍 Проверяем существование пользователя: {SYSTEM_EMAIL}")
    
    # Проверяем, существует ли пользователь
    existing_user = await user_repo.get_by_email(SYSTEM_EMAIL)
    
    if existing_user:
        print(f"✅ Пользователь уже существует!")
        print(f"   ID: {existing_user.id}")
        print(f"   Email: {existing_user.email}")
        print(f"   Role: {existing_user.role}")
        return existing_user.id
    else:
        print(f"❌ Пользователь не найден. Создаем нового...")
        
        # Создаем пользователя
        # Пароль генерируется случайный, так как вход под ним не требуется
        new_user = await user_repo.create_user(
            email=SYSTEM_EMAIL,
            password=SYSTEM_PASSWORD
        )
        
        if new_user:
            # Убеждаемся, что роль установлена как RECRUITER
            # (по умолчанию должно быть RECRUITER, но проверим)
            if new_user.role != UserRole.RECRUITER:
                from sqlalchemy.ext.asyncio import AsyncSession
                from app.database.database import engine
                
                async with AsyncSession(engine) as session:
                    new_user.role = UserRole.RECRUITER
                    session.add(new_user)
                    await session.commit()
                    await session.refresh(new_user)
            
            print(f"✅ Пользователь успешно создан!")
            print(f"   ID: {new_user.id}")
            print(f"   Email: {new_user.email}")
            print(f"   Role: {new_user.role}")
            print(f"   Password: {SYSTEM_PASSWORD} (случайный, для входа не требуется)")
            return new_user.id
        else:
            print(f"❌ Ошибка при создании пользователя")
            return None


if __name__ == "__main__":
    print("=" * 60)
    print("Инициализация системного пользователя для сбора резюме")
    print("=" * 60)
    print()
    
    user_id = asyncio.run(ensure_system_user())
    
    print()
    print("=" * 60)
    if user_id:
        print(f"✅ Готово! ID системного пользователя: {user_id}")
    else:
        print("❌ Ошибка при инициализации")
    print("=" * 60)

