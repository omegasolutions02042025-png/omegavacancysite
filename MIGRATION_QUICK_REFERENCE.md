# Быстрая справка по миграциям

## 🚀 Самый простой способ

```bash
apply_migration.bat upgrade head
```

## 📋 Основные команды

### Применить все миграции
```bash
venv\Scripts\alembic.exe upgrade head
```

### Проверить текущую версию
```bash
venv\Scripts\alembic.exe current
```

### Посмотреть историю
```bash
venv\Scripts\alembic.exe history
```

### Откатить последнюю миграцию
```bash
venv\Scripts\alembic.exe downgrade -1
```

## ⚡ Через скрипт (удобнее)

```bash
# Применить все миграции
apply_migration.bat upgrade head

# Проверить версию
apply_migration.bat current

# История
apply_migration.bat history

# Откат
apply_migration.bat downgrade -1
```

## 📝 Текущие миграции

1. **001_archive_status** - Поля архивации
2. **002_password_changed_at** - Дата смены пароля

## ⚠️ После применения миграции

**Обязательно перезапустите сервер:**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

**Полная документация:** `HOW_TO_APPLY_MIGRATIONS.md`


