import asyncio
import sys
import os
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Добавляем пути
sys.path.append(os.getcwd())

from app.database.database import engine, User, UserRole

# Введите email вашего админа
ADMIN_EMAIL = "admin@omega.tech" 

async def disable_2fa_for_admin():
    print(f"🔧 Подключение к базе данных...")
    
    async with AsyncSession(engine) as session:
        # 1. Ищем админа
        query = select(User).where(User.email == ADMIN_EMAIL)
        result = await session.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"❌ Админ с почтой {ADMIN_EMAIL} не найден!")
            print("Проверьте email или создайте админа через предыдущий скрипт.")
            return

        print(f"✅ Админ найден (ID: {user.id})")
        print("🔍 Анализирую поля безопасности...")

        changes_made = False

        # === СПИСОК ВОЗМОЖНЫХ ПОЛЕЙ 2FA ===
        # Скрипт проверит, есть ли такие поля в вашей базе, и отключит их
        fields_to_disable = [
            "is_2fa_enabled", 
            "two_factor_enabled", 
            "otp_enabled", 
            "mfa_enabled",
            "is_totp_enabled"
        ]
        
        # Поля, которые нужно ВКЛЮЧИТЬ (чтобы пустило без подтверждения почты)
        fields_to_enable = [
            "is_active",
            "is_verified", 
            "email_verified",
            "is_approved"
        ]

        # 2. Отключаем 2FA
        for field in fields_to_disable:
            if hasattr(user, field):
                current_val = getattr(user, field)
                if current_val:
                    setattr(user, field, False)
                    print(f"   🔓 Отключено поле: {field}")
                    changes_made = True

        # 3. Включаем верификацию (чтобы не просило подтвердить email)
        for field in fields_to_enable:
            if hasattr(user, field):
                current_val = getattr(user, field)
                if not current_val:
                    setattr(user, field, True)
                    print(f"   🟢 Включено поле: {field}")
                    changes_made = True

        if changes_made:
            session.add(user)
            await session.commit()
            print("🚀 УСПЕХ! Настройки безопасности обновлены.")
            print("Теперь попробуйте войти с паролем.")
        else:
            print("ℹ️ Изменений не требовалось (2FA уже выключена или поля не найдены).")

if __name__ == "__main__":
    asyncio.run(disable_2fa_for_admin())
    