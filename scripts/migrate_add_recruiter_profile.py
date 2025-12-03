"""
Миграция: Добавление полей профиля рекрутера
Запуск: python scripts/migrate_add_recruiter_profile.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.database import engine


async def run_migration():
    """Применить миграцию для добавления полей профиля рекрутера"""
    
    print("=" * 60)
    print("🔄 МИГРАЦИЯ: Добавление полей профиля рекрутера")
    print("=" * 60)
    
    async with AsyncSession(engine) as session:
        try:
            # 1. Проверить существующие колонки
            print("\n1️⃣ Проверка существующих колонок в users...")
            result = await session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users'
            """))
            existing_columns = [row[0] for row in result.fetchall()]
            print(f"   Существующие колонки: {', '.join(existing_columns)}")
            
            # 2. Добавить новые колонки
            print("\n2️⃣ Добавление новых колонок...")
            new_columns = [
                ("first_name", "VARCHAR", "Имя рекрутера"),
                ("last_name", "VARCHAR", "Фамилия рекрутера"),
                ("middle_name", "VARCHAR", "Отчество рекрутера"),
                ("phone", "VARCHAR", "Телефон рекрутера"),
                ("experience", "TEXT", "Опыт работы"),
                ("specialization", "VARCHAR", "Специализация"),
                ("resume", "TEXT", "Резюме"),
            ]
            
            for col_name, col_type, description in new_columns:
                if col_name in existing_columns:
                    print(f"   ⏭️  Колонка {col_name} уже существует, пропускаем")
                else:
                    try:
                        await session.execute(text(f"""
                            ALTER TABLE users 
                            ADD COLUMN {col_name} {col_type}
                        """))
                        await session.commit()
                        print(f"   ✅ Добавлена колонка {col_name} ({description})")
                    except Exception as e:
                        error_msg = str(e)
                        if "already exists" in error_msg.lower() or "duplicate" in error_msg.lower():
                            print(f"   ⏭️  Колонка {col_name} уже существует")
                        else:
                            print(f"   ❌ Ошибка при добавлении {col_name}: {error_msg}")
                            raise
            
            # 3. Создать индексы
            print("\n3️⃣ Создание индексов...")
            indexes = [
                ("idx_users_first_name", "first_name"),
                ("idx_users_last_name", "last_name"),
                ("idx_users_phone", "phone"),
            ]
            
            for idx_name, col_name in indexes:
                try:
                    await session.execute(text(f"""
                        CREATE INDEX IF NOT EXISTS {idx_name} ON users({col_name})
                    """))
                    await session.commit()
                    print(f"   ✅ Создан индекс {idx_name}")
                except Exception as e:
                    error_msg = str(e)
                    if "already exists" in error_msg.lower() or "duplicate" in error_msg.lower():
                        print(f"   ⏭️  Индекс {idx_name} уже существует")
                    else:
                        print(f"   ⚠️  Предупреждение при создании индекса {idx_name}: {error_msg}")
            
            # 4. Проверка результата
            print("\n4️⃣ Проверка результата...")
            result = await session.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                AND column_name IN ('first_name', 'last_name', 'middle_name', 'phone', 'experience', 'specialization', 'resume')
                ORDER BY column_name
            """))
            new_cols = result.fetchall()
            
            if new_cols:
                print(f"   ✅ Найдено {len(new_cols)} новых полей:")
                for col_name, col_type in new_cols:
                    print(f"      - {col_name} ({col_type})")
            else:
                print("   ⚠️  Новые поля не найдены")
            
            print("\n" + "=" * 60)
            print("✅ МИГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!")
            print("=" * 60)
            
        except Exception as e:
            await session.rollback()
            print(f"\n❌ ОШИБКА МИГРАЦИИ: {e}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_migration())
