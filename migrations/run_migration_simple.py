"""Простой скрипт для выполнения миграции"""
import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

async def main():
    try:
        from sqlalchemy import text
        from app.database.database import engine
        
        print("Подключение к базе данных...")
        
        commands = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name VARCHAR",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name VARCHAR",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS middle_name VARCHAR",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS experience TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS specialization VARCHAR",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS resume TEXT",
            "CREATE INDEX IF NOT EXISTS idx_users_first_name ON users(first_name)",
            "CREATE INDEX IF NOT EXISTS idx_users_last_name ON users(last_name)",
            "CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone)",
        ]
        
        async with engine.begin() as conn:
            for i, cmd in enumerate(commands, 1):
                try:
                    await conn.execute(text(cmd))
                    print(f"{i}. OK: {cmd[:60]}")
                except Exception as e:
                    error_msg = str(e)
                    if "already exists" in error_msg.lower() or "duplicate" in error_msg.lower():
                        print(f"{i}. SKIP (уже существует): {cmd[:60]}")
                    else:
                        print(f"{i}. ERROR: {error_msg}")
                        raise
        
        # Проверка
        async with engine.connect() as conn:
            result = await conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                AND column_name IN ('first_name', 'last_name', 'middle_name', 'phone', 'experience', 'specialization', 'resume')
                ORDER BY column_name
            """))
            cols = [row[0] for row in result.fetchall()]
            print(f"\nПроверка: найдено {len(cols)} полей: {', '.join(cols) if cols else 'нет'}")
        
        await engine.dispose()
        print("\nМиграция завершена!")
        
    except Exception as e:
        print(f"ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())



