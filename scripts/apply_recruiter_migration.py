"""Применить миграцию для добавления полей профиля рекрутера"""
import asyncio
import sys
from pathlib import Path

# Добавляем путь к проекту
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

async def apply_migration():
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.database.database import engine
        
        print("Подключение к базе данных...")
        
        async with AsyncSession(engine) as session:
            # Список команд для выполнения
            commands = [
                ("ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name VARCHAR", "first_name"),
                ("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name VARCHAR", "last_name"),
                ("ALTER TABLE users ADD COLUMN IF NOT EXISTS middle_name VARCHAR", "middle_name"),
                ("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR", "phone"),
                ("ALTER TABLE users ADD COLUMN IF NOT EXISTS experience TEXT", "experience"),
                ("ALTER TABLE users ADD COLUMN IF NOT EXISTS specialization VARCHAR", "specialization"),
                ("ALTER TABLE users ADD COLUMN IF NOT EXISTS resume TEXT", "resume"),
            ]
            
            indexes = [
                ("CREATE INDEX IF NOT EXISTS idx_users_first_name ON users(first_name)", "idx_users_first_name"),
                ("CREATE INDEX IF NOT EXISTS idx_users_last_name ON users(last_name)", "idx_users_last_name"),
                ("CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone)", "idx_users_phone"),
            ]
            
            # Выполняем команды
            for cmd, name in commands:
                try:
                    await session.execute(text(cmd))
                    await session.commit()
                    print(f"OK: {name}")
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" in error_str or "duplicate" in error_str:
                        print(f"SKIP: {name} (уже существует)")
                    else:
                        print(f"ERROR: {name} - {e}")
                        raise
            
            # Создаем индексы
            for cmd, name in indexes:
                try:
                    await session.execute(text(cmd))
                    await session.commit()
                    print(f"OK: индекс {name}")
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" in error_str:
                        print(f"SKIP: индекс {name} (уже существует)")
                    else:
                        print(f"WARNING: индекс {name} - {e}")
            
            # Проверка
            result = await session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                AND column_name IN ('first_name', 'last_name', 'middle_name', 'phone', 'experience', 'specialization', 'resume')
            """))
            found = [row[0] for row in result.fetchall()]
            print(f"\nПроверка: найдено {len(found)} полей: {', '.join(found)}")
            
        await engine.dispose()
        print("\nМиграция завершена!")
        
    except Exception as e:
        print(f"ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(apply_migration())


