"""Скрипт миграции с выводом в файл"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

log_file = project_root / "migrations" / "migration_log.txt"

def log(msg):
    """Записать сообщение в файл и вывести на экран"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] {msg}\n"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(log_msg)
    print(msg, flush=True)

async def main():
    try:
        log("=" * 60)
        log("Начало выполнения миграции")
        log("=" * 60)
        
        from sqlalchemy import text
        from app.database.database import engine
        
        log("Подключение к базе данных...")
        
        commands = [
            ("first_name", "VARCHAR"),
            ("last_name", "VARCHAR"),
            ("middle_name", "VARCHAR"),
            ("phone", "VARCHAR"),
            ("experience", "TEXT"),
            ("specialization", "VARCHAR"),
            ("resume", "TEXT"),
        ]
        
        async with engine.begin() as conn:
            # Добавляем колонки
            for col_name, col_type in commands:
                cmd = f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                try:
                    await conn.execute(text(cmd))
                    log(f"OK: Добавлена колонка {col_name} ({col_type})")
                except Exception as e:
                    error_msg = str(e)
                    if "already exists" in error_msg.lower() or "duplicate" in error_msg.lower():
                        log(f"SKIP: Колонка {col_name} уже существует")
                    else:
                        log(f"ERROR: {error_msg}")
                        raise
            
            # Создаем индексы
            indexes = [
                ("idx_users_first_name", "first_name"),
                ("idx_users_last_name", "last_name"),
                ("idx_users_phone", "phone"),
            ]
            
            for idx_name, col_name in indexes:
                cmd = f"CREATE INDEX IF NOT EXISTS {idx_name} ON users({col_name})"
                try:
                    await conn.execute(text(cmd))
                    log(f"OK: Создан индекс {idx_name}")
                except Exception as e:
                    error_msg = str(e)
                    if "already exists" in error_msg.lower() or "duplicate" in error_msg.lower():
                        log(f"SKIP: Индекс {idx_name} уже существует")
                    else:
                        log(f"WARNING: {error_msg}")
        
        # Проверка
        async with engine.connect() as conn:
            result = await conn.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                AND column_name IN ('first_name', 'last_name', 'middle_name', 'phone', 'experience', 'specialization', 'resume')
                ORDER BY column_name
            """))
            cols = result.fetchall()
            
            if cols:
                log(f"\nПроверка: найдено {len(cols)} полей:")
                for col_name, col_type in cols:
                    log(f"  - {col_name} ({col_type})")
            else:
                log("WARNING: Поля не найдены в таблице users")
        
        await engine.dispose()
        log("\n" + "=" * 60)
        log("Миграция завершена успешно!")
        log("=" * 60)
        
    except Exception as e:
        log(f"\nОШИБКА: {e}")
        import traceback
        error_trace = traceback.format_exc()
        log(error_trace)
        sys.exit(1)

if __name__ == "__main__":
    # Очищаем лог файл
    if log_file.exists():
        log_file.unlink()
    
    asyncio.run(main())
    print(f"\nЛог сохранен в: {log_file}")


