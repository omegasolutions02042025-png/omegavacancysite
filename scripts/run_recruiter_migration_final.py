"""
Финальный скрипт миграции для добавления полей профиля рекрутера
Использует тот же подход, что и migrate_add_admin.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.database import engine

async def run_migration():
    log_file = Path(__file__).parent.parent / "migration_result.txt"
    
    def log(msg):
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
        print(msg, flush=True)
    
    log("=" * 60)
    log("МИГРАЦИЯ: Добавление полей профиля рекрутера")
    log("=" * 60)
    
    async with AsyncSession(engine) as session:
        try:
            # Проверяем существующие колонки
            log("\n1. Проверка существующих колонок...")
            result = await session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users'
            """))
            existing = set(row[0] for row in result.fetchall())
            log(f"   Найдено {len(existing)} колонок")
            
            # Добавляем новые колонки
            log("\n2. Добавление новых колонок...")
            columns_to_add = [
                ("first_name", "VARCHAR"),
                ("last_name", "VARCHAR"),
                ("middle_name", "VARCHAR"),
                ("phone", "VARCHAR"),
                ("experience", "TEXT"),
                ("specialization", "VARCHAR"),
                ("resume", "TEXT"),
            ]
            
            added_count = 0
            for col_name, col_type in columns_to_add:
                if col_name in existing:
                    log(f"   - {col_name}: уже существует")
                else:
                    try:
                        await session.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))
                        await session.commit()
                        log(f"   + {col_name}: добавлена")
                        added_count += 1
                    except Exception as e:
                        if "already exists" in str(e).lower():
                            log(f"   - {col_name}: уже существует")
                        else:
                            log(f"   ! {col_name}: ошибка - {e}")
                            raise
            
            # Создаем индексы
            log("\n3. Создание индексов...")
            indexes = [
                ("idx_users_first_name", "first_name"),
                ("idx_users_last_name", "last_name"),
                ("idx_users_phone", "phone"),
            ]
            
            for idx_name, col_name in indexes:
                try:
                    await session.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON users({col_name})"))
                    await session.commit()
                    log(f"   + {idx_name}: создан")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        log(f"   - {idx_name}: уже существует")
                    else:
                        log(f"   ! {idx_name}: предупреждение - {e}")
            
            # Финальная проверка
            log("\n4. Финальная проверка...")
            result = await session.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                AND column_name IN ('first_name', 'last_name', 'middle_name', 'phone', 'experience', 'specialization', 'resume')
                ORDER BY column_name
            """))
            final_cols = result.fetchall()
            
            if final_cols:
                log(f"   Найдено {len(final_cols)} полей профиля:")
                for col_name, col_type in final_cols:
                    log(f"      - {col_name} ({col_type})")
            else:
                log("   ВНИМАНИЕ: Поля не найдены!")
            
            log("\n" + "=" * 60)
            if added_count > 0:
                log(f"УСПЕХ: Добавлено {added_count} новых полей")
            else:
                log("УСПЕХ: Все поля уже существуют")
            log("=" * 60)
            
        except Exception as e:
            await session.rollback()
            log(f"\nОШИБКА: {e}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            await engine.dispose()

if __name__ == "__main__":
    log_file = Path(__file__).parent.parent / "migration_result.txt"
    if log_file.exists():
        log_file.unlink()
    
    try:
        asyncio.run(run_migration())
        print(f"\nРезультат сохранен в: {log_file}")
    except KeyboardInterrupt:
        print("\nПрервано пользователем")
    except Exception as e:
        print(f"\nКритическая ошибка: {e}")
        sys.exit(1)

