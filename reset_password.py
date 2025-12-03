import asyncio
import sys
import os
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Добавляем пути
sys.path.append(os.getcwd())

from app.database.database import engine, User

TARGET_EMAIL = "test@candidate.com"
NEW_PASSWORD = "123456"  # Минимум 6 символов

async def reset_password():
    print(f"🔄 Подключение к БД...")
    async with AsyncSession(engine) as session:
        # Ищем пользователя
        query = select(User).where(User.email == TARGET_EMAIL)
        result = await session.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"❌ ОШИБКА: Пользователь {TARGET_EMAIL} вообще не найден в базе!")
            print(f"👉 Вам нужно зайти на http://localhost:8000/auth/register и зарегистрироваться заново.")
            return

        # Устанавливаем новый пароль
        # В модели User пароль хранится в открытом виде в поле password
        # (как указано в комментарии в database.py: "Храним в открытом виде для администратора")
        user.password = NEW_PASSWORD
        session.add(user)
        await session.commit()
        
        print(f"✅ УСПЕХ! Пароль для {TARGET_EMAIL} сброшен на: {NEW_PASSWORD}")

if __name__ == "__main__":
    asyncio.run(reset_password())