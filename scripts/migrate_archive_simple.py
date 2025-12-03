"""
Простая миграция для добавления полей архивации
"""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

async def main():
    from sqlalchemy import text
    from app.database.database import engine
    
    print("=" * 70)
    print("МИГРАЦИЯ: Добавление полей архивации в таблицу users")
    print("=" * 70)
    print()
    
    commands = [
        ("is_archived", "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_archived BOOLEAN DEFAULT FALSE"),
        ("archived_at", "ALTER TABLE users ADD COLUMN IF NOT EXISTS archived_at VARCHAR"),
        ("archived_by_admin", "ALTER TABLE users ADD COLUMN IF NOT EXISTS archived_by_admin INTEGER"),
    ]
    
    try:
        async with engine.begin() as conn:
            for field_name, sql in commands:
                try:
                    print(f"➤ Добавление поля '{field_name}'...")
                    await conn.execute(text(sql))
                    print(f"  ✅ Поле '{field_name}' добавлено")
                except Exception as e:
                    error_str = str(e).lower()
                    if "already exists" in error_str or "duplicate" in error_str:
                        print(f"  ⏭️  Поле '{field_name}' уже существует")
                    else:
                        print(f"  ❌ Ошибка: {e}")
                        raise
            
            # Проверяем результат
            print()
            print("➤ Проверка результата...")
            result = await conn.execute(text("SELECT COUNT(*) FROM users"))
            count = result.scalar()
            print(f"  📊 Найдено пользователей: {count}")
            
            # Проверяем структуру таблицы
            result = await conn.execute(text("""
                SELECT column_name, data_type, column_default 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                AND column_name IN ('is_archived', 'archived_at', 'archived_by_admin')
                ORDER BY column_name
            """))
            
            print()
            print("➤ Структура новых полей:")
            for row in result:
                print(f"  • {row[0]}: {row[1]} (default: {row[2]})")
        
        print()
        print("=" * 70)
        print("✅ МИГРАЦИЯ УСПЕШНО ЗАВЕРШЕНА")
        print("=" * 70)
        print()
        print("Теперь можно:")
        print("  1. Перезапустить сервер FastAPI")
        print("  2. Войти в админ-панель: /admin/dashboard")
        print("  3. Использовать кнопки 'Архив' и 'Восстановить'")
        print()
        
    except Exception as e:
        print()
        print("=" * 70)
        print("❌ ОШИБКА МИГРАЦИИ")
        print("=" * 70)
        print(f"Ошибка: {e}")
        print()
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())

