"""
Миграция для добавления статуса архива к пользователям.

Добавляет поля:
- is_archived: bool - статус архива
- archived_at: str - дата перевода в архив
- archived_by_admin: int - ID администратора, который перевел в архив

Запуск:
    python scripts/migrate_add_archive_status.py
"""

import asyncio
import sys
from pathlib import Path

# Добавляем корневую директорию в путь для импорта
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from app.database.database import engine


async def run_migration():
    """Выполнить миграцию."""
    print("=" * 60, flush=True)
    print("МИГРАЦИЯ: Добавление статуса архива для пользователей", flush=True)
    print("=" * 60, flush=True)
    
    try:
        async with engine.begin() as conn:
            # Добавляем колонки одной командой
            print("\n📝 Добавление колонок архивации...", flush=True)
            
            await conn.execute(text("""
                ALTER TABLE users 
                ADD COLUMN IF NOT EXISTS is_archived BOOLEAN DEFAULT FALSE,
                ADD COLUMN IF NOT EXISTS archived_at VARCHAR,
                ADD COLUMN IF NOT EXISTS archived_by_admin INTEGER
            """))
            
            print("✅ Колонки добавлены", flush=True)
            
            # Добавляем внешний ключ отдельно (если база поддерживает)
            try:
                await conn.execute(text("""
                    DO $$ 
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint 
                            WHERE conname = 'fk_archived_by_admin'
                        ) THEN
                            ALTER TABLE users 
                            ADD CONSTRAINT fk_archived_by_admin 
                            FOREIGN KEY (archived_by_admin) REFERENCES admins(id);
                        END IF;
                    END $$;
                """))
                print("✅ Внешний ключ добавлен", flush=True)
            except Exception as e:
                print(f"⚠️  Внешний ключ не добавлен (возможно, не PostgreSQL): {e}", flush=True)
            
            # Проверяем количество пользователей
            result = await conn.execute(text("SELECT COUNT(*) FROM users"))
            user_count = result.scalar()
            
            print("\n" + "=" * 60, flush=True)
            print("✅ МИГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО", flush=True)
            print("=" * 60, flush=True)
            print(f"📊 Всего пользователей в системе: {user_count}", flush=True)
            print(f"📊 Все пользователи по умолчанию имеют статус 'Активен'", flush=True)
            print("\nТеперь администраторы могут:", flush=True)
            print("  • Переводить пользователей в архив (блокировка входа)", flush=True)
            print("  • Восстанавливать пользователей из архива", flush=True)
            print("=" * 60, flush=True)
            
    except Exception as e:
        print(f"\n❌ ОШИБКА МИГРАЦИИ: {e}", flush=True)
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    print("\n🚀 Запуск миграции...\n", flush=True)
    asyncio.run(run_migration())
    print("\n✅ Готово!\n", flush=True)

