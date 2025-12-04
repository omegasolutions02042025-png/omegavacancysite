# Миграция системы ролей пользователей

## Обзор изменений

Расширена схема базы данных для поддержки системы ролей пользователей с сохранением полной обратной совместимости.

## Изменения в моделях

### 1. Расширена модель `User` (`app/database/database.py`)

**Добавлено:**
- Поле `role: Optional[UserRole]` (nullable, default=RECRUITER)
- Enum `UserRole` с значениями: CANDIDATE, RECRUITER, CONTRACTOR, ADMIN
- Relationships для профилей ролей (One-to-One)

**Важно:** Все существующие поля сохранены без изменений. Новое поле `role` является опциональным, что гарантирует работоспособность существующего кода.

### 2. Созданы модели профилей (`app/models/users.py`)

**Новые модели:**
- `CandidateProfile` - профиль кандидата (One-to-One с User)
- `RecruiterProfile` - профиль рекрутера (One-to-One с User)
- `ContractorProfile` - профиль контрактора (One-to-One с User)

**Особенности:**
- Все модели наследуют `TimestampMixin` (created_at, updated_at в ISO формате)
- JSON поля для стека технологий
- Enum `Grade` для уровня (JUNIOR, MIDDLE, SENIOR, LEAD)
- Связаны с существующей таблицей `users` через `user_id`

## Миграция базы данных

### Файл миграции
`alembic/versions/20241202_1900-add_user_roles_system.py`

### Что делает миграция:

1. **Добавляет поле `role` в таблицу `users`**
   - Тип: VARCHAR(20) для SQLite, ENUM для PostgreSQL
   - Nullable: True
   - Default: 'RECRUITER'

2. **Устанавливает роль для существующих пользователей**
   - Все существующие пользователи получают роль `RECRUITER`

3. **Создает таблицы профилей:**
   - `candidate_profiles_roles`
   - `recruiter_profiles_roles`
   - `contractor_profiles_roles`

4. **Создает индексы и внешние ключи:**
   - Индексы на `user_id` для быстрого поиска
   - Уникальные ограничения на `user_id` (One-to-One)
   - Внешние ключи на `users.id`

## Применение миграции

```bash
# Применить миграцию
alembic upgrade head

# Откатить миграцию (если нужно)
alembic downgrade -1
```

## Обратная совместимость

✅ **Все существующие пользователи сохраняют работоспособность:**
- Поле `role` nullable, поэтому старые записи не ломаются
- По умолчанию все пользователи получают роль `RECRUITER`
- Все существующие поля модели `User` сохранены

✅ **Существующий код продолжает работать:**
- Все импорты `from app.database.database import User` работают как прежде
- Репозитории и сервисы не требуют изменений
- API endpoints продолжают функционировать

## Использование новых моделей

### Импорт моделей

```python
from app.database.database import User, UserRole
from app.models.users import (
    CandidateProfile,
    RecruiterProfile,
    ContractorProfile,
    Grade
)
```

### Пример создания пользователя с профилем

```python
# Создание пользователя-кандидата
user = User(
    email="candidate@example.com",
    password="password",
    role=UserRole.CANDIDATE
)

# Создание профиля кандидата
profile = CandidateProfile(
    user_id=user.id,
    grade=Grade.SENIOR,
    experience_years=5,
    stack=["Python", "FastAPI", "PostgreSQL"],
    bio="Опытный разработчик"
)
```

### Пример получения профиля

```python
# Получить профиль рекрутера
user = await user_repo.get_by_id(user_id)
if user.recruiter_profile:
    profile = user.recruiter_profile
    print(f"Специализация: {profile.specialization}")
```

## Структура таблиц

### Таблица `users` (расширена)
- `role` VARCHAR(20) / ENUM - роль пользователя (nullable)

### Таблица `candidate_profiles_roles`
- `id` INTEGER PRIMARY KEY
- `user_id` INTEGER UNIQUE FK -> users.id
- `grade` VARCHAR(20) / ENUM (JUNIOR, MIDDLE, SENIOR, LEAD)
- `experience_years` INTEGER
- `stack` JSON (массив строк)
- `resume_url` VARCHAR
- `bio` TEXT
- `created_at` VARCHAR (ISO format)
- `updated_at` VARCHAR (ISO format)

### Таблица `recruiter_profiles_roles`
- `id` INTEGER PRIMARY KEY
- `user_id` INTEGER UNIQUE FK -> users.id
- `specialization` VARCHAR
- `experience_years` INTEGER
- `company` VARCHAR
- `phone` VARCHAR
- `telegram` VARCHAR
- `linkedin` VARCHAR
- `created_at` VARCHAR (ISO format)
- `updated_at` VARCHAR (ISO format)

### Таблица `contractor_profiles_roles`
- `id` INTEGER PRIMARY KEY
- `user_id` INTEGER UNIQUE FK -> users.id
- `grade` VARCHAR(20) / ENUM
- `experience_years` INTEGER
- `stack` JSON (массив строк)
- `hourly_rate_usd` FLOAT
- `is_available` BOOLEAN (default: true)
- `portfolio_url` VARCHAR
- `bio` TEXT
- `created_at` VARCHAR (ISO format)
- `updated_at` VARCHAR (ISO format)

## Безопасность

✅ **Все изменения безопасны:**
- Новые поля nullable
- Существующие данные не изменяются
- Миграция идемпотентна (можно запускать несколько раз)
- Откат миграции полностью восстанавливает исходное состояние

## Следующие шаги

После применения миграции можно:
1. Создавать пользователей с разными ролями
2. Создавать профили для пользователей
3. Использовать роли для разграничения доступа в API
4. Расширять функционал для каждой роли

## Примечания

- Модели профилей импортируются в `app/database/database.py` для регистрации в SQLModel.metadata (нужно для Alembic autogenerate)
- Используется `TYPE_CHECKING` для избежания циклических импортов
- Все временные метки хранятся в формате ISO строк для совместимости с существующим кодом


