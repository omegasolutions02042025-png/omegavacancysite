"""
Скрипт для создания администратора
Запуск: python scripts/create_admin.py
"""
import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.admin_db import admin_repository


async def create_admin():
    """Создать администратора с учетными данными"""
    
    # Учетные данные администратора
    username = "admin"
    password = "OmegaAdmin2025!"
    
    print("=" * 60)
    print("🔐 СОЗДАНИЕ АДМИНИСТРАТОРА")
    print("=" * 60)
    
    # Создаем администратора
    admin = await admin_repository.create_admin(username, password)
    
    if admin:
        print(f"\n✅ Администратор успешно создан!")
        print(f"\n📋 УЧЕТНЫЕ ДАННЫЕ:")
        print(f"   Логин:  {username}")
        print(f"   Пароль: {password}")
        print(f"   ID:     {admin.id}")
        
        # Сохраняем в файл
        credentials_file = Path(__file__).parent / "admin_credentials.txt"
        with open(credentials_file, "w", encoding="utf-8") as f:
            f.write("=" * 60 + "\n")
            f.write("УЧЕТНЫЕ ДАННЫЕ АДМИНИСТРАТОРА\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"Логин:  {username}\n")
            f.write(f"Пароль: {password}\n")
            f.write(f"ID:     {admin.id}\n")
            f.write(f"\nURL для входа: http://localhost:8000/admin/login\n")
            f.write("\n⚠️ ВАЖНО: Храните этот файл в безопасном месте!\n")
        
        print(f"\n💾 Учетные данные сохранены в: {credentials_file}")
        print(f"\n🌐 URL для входа: http://localhost:8000/admin/login")
        print("\n⚠️  ВАЖНО: Сохраните эти данные в безопасном месте!")
        print("=" * 60)
    else:
        print("\n❌ Администратор с таким логином уже существует")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(create_admin())


