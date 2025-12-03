# Как применить миграции Alembic

## ✅ Быстрый способ

### Вариант 1: Через скрипт (самый простой)
```bash
apply_migration.bat upgrade head
```

### Вариант 2: Прямой путь к alembic.exe
```bash
venv\Scripts\alembic.exe upgrade head
```

### Вариант 3: Если alembic в PATH
```bash
alembic upgrade head
```

Эта команда применяет все миграции до последней версии.

## 📋 Пошаговая инструкция

### 1. Проверить текущую версию

```bash
venv\Scripts\alembic.exe current
# или через скрипт
apply_migration.bat current
```

Показывает, какая миграция применена в данный момент.

### 2. Посмотреть историю миграций

```bash
venv\Scripts\alembic.exe history
# или через скрипт
apply_migration.bat history
```

Показывает все доступные миграции с их ID и описаниями.

### 3. Применить все миграции

```bash
venv\Scripts\alembic.exe upgrade head
# или через скрипт
apply_migration.bat upgrade head
```

Применяет все миграции до последней версии (`head`).

### 4. Применить конкретную миграцию

```bash
venv\Scripts\alembic.exe upgrade <revision_id>
# или через скрипт
apply_migration.bat upgrade <revision_id>
```

Например:
```bash
venv\Scripts\alembic.exe upgrade 002_password_changed_at
```

### 5. Применить следующую миграцию

```bash
venv\Scripts\alembic.exe upgrade +1
# или через скрипт
apply_migration.bat upgrade +1
```

## 🔍 Проверка результата

### Проверить, что миграция применена:

```bash
venv\Scripts\alembic.exe current
# или через скрипт
apply_migration.bat current
```

Должно показать что-то вроде:
```
002_password_changed_at (head)
```

### Проверить структуру таблицы в БД:

```sql
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'users' 
AND column_name = 'password_changed_at';
```

Если колонка существует - миграция применена успешно!

## ⚠️ Откат миграции (если нужно)

### Откатить последнюю миграцию:

```bash
venv\Scripts\alembic.exe downgrade -1
# или через скрипт
apply_migration.bat downgrade -1
```

### Откатить до конкретной версии:

```bash
venv\Scripts\alembic.exe downgrade <revision_id>
# или через скрипт
apply_migration.bat downgrade <revision_id>
```

### Откатить все миграции:

```bash
venv\Scripts\alembic.exe downgrade base
# или через скрипт
apply_migration.bat downgrade base
```

## 📝 Текущие миграции в проекте

1. **001_archive_status** - Добавление полей архивации (`is_archived`, `archived_at`, `archived_by_admin`)
2. **002_password_changed_at** - Добавление поля `password_changed_at`

## 🚀 После применения миграции

**ВАЖНО:** Перезапустите сервер FastAPI, чтобы изменения вступили в силу:

```bash
# Остановите сервер (Ctrl+C)
# Запустите заново
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## ❓ Частые проблемы

### Проблема: "alembic: command not found" или "No module named alembic.__main__"

**Решение:**
Используйте прямой путь к alembic.exe:
```bash
venv\Scripts\alembic.exe upgrade head
```

Или используйте скрипт:
```bash
apply_migration.bat upgrade head
```

Если alembic не установлен:
```bash
pip install alembic
```

### Проблема: "Target database is not up to date"

**Решение:**
```bash
venv\Scripts\alembic.exe upgrade head
# или через скрипт
apply_migration.bat upgrade head
```

### Проблема: "Can't locate revision identified by 'xxx'"

**Решение:**
```bash
# Проверьте историю
venv\Scripts\alembic.exe history

# Синхронизируйте с БД
venv\Scripts\alembic.exe stamp head
```

### Проблема: Миграция не применяется

**Решение:**
1. Проверьте подключение к БД в `alembic.ini`
2. Проверьте логи:
   ```bash
   venv\Scripts\alembic.exe upgrade head --verbose
   ```
3. Посмотрите SQL без выполнения:
   ```bash
   venv\Scripts\alembic.exe upgrade head --sql
   ```

## 📚 Дополнительная информация

- Полное руководство: `ALEMBIC_GUIDE.md`
- Быстрый старт: `ALEMBIC_QUICKSTART.md`

---

**Текущий статус:** ✅ Миграции применены  
**Последняя миграция:** `002_password_changed_at`

