# Руководство по работе с Alembic

## Что такое Alembic?

Alembic - это инструмент для управления миграциями базы данных для SQLAlchemy. Он позволяет:
- Версионировать схему базы данных
- Автоматически генерировать миграции
- Откатывать изменения
- Работать в команде без конфликтов

## Структура проекта

```
omegavacsite/
├── alembic/                    # Директория Alembic
│   ├── versions/               # Файлы миграций
│   │   └── 20241202_1530-add_archive_status_fields.py
│   ├── env.py                  # Конфигурация окружения
│   ├── script.py.mako          # Шаблон для миграций
│   └── README
├── alembic.ini                 # Главный конфиг Alembic
└── app/
    └── database/
        └── database.py         # Модели SQLModel
```

## Основные команды

### 1. Создание новой миграции

**Автоматическая генерация (рекомендуется):**
```bash
alembic revision --autogenerate -m "Описание изменений"
```

Alembic сравнит модели в `app/database/database.py` с текущей схемой БД и создаст миграцию автоматически.

**Ручное создание:**
```bash
alembic revision -m "Описание изменений"
```

Создаст пустой файл миграции, который нужно заполнить вручную.

### 2. Применение миграций

**Применить все миграции:**
```bash
alembic upgrade head
```

**Применить конкретную миграцию:**
```bash
alembic upgrade <revision_id>
```

**Применить следующую миграцию:**
```bash
alembic upgrade +1
```

### 3. Откат миграций

**Откатить последнюю миграцию:**
```bash
alembic downgrade -1
```

**Откатить до конкретной версии:**
```bash
alembic downgrade <revision_id>
```

**Откатить все миграции:**
```bash
alembic downgrade base
```

### 4. Информация о миграциях

**Текущая версия БД:**
```bash
alembic current
```

**История миграций:**
```bash
alembic history
```

**Подробная история:**
```bash
alembic history --verbose
```

**Показать SQL без выполнения:**
```bash
alembic upgrade head --sql
```

## Примеры использования

### Пример 1: Добавление нового поля

1. Добавьте поле в модель (`app/database/database.py`):
```python
class User(SQLModel, table=True):
    # ... существующие поля ...
    new_field: Optional[str] = Field(default=None)
```

2. Создайте миграцию:
```bash
alembic revision --autogenerate -m "Add new_field to users"
```

3. Проверьте созданный файл в `alembic/versions/`

4. Примените миграцию:
```bash
alembic upgrade head
```

### Пример 2: Изменение типа поля

1. Измените тип в модели
2. Создайте миграцию вручную:
```bash
alembic revision -m "Change field type"
```

3. Отредактируйте файл миграции:
```python
def upgrade() -> None:
    op.alter_column('users', 'field_name',
                    type_=sa.Integer(),
                    existing_type=sa.String())

def downgrade() -> None:
    op.alter_column('users', 'field_name',
                    type_=sa.String(),
                    existing_type=sa.Integer())
```

4. Примените:
```bash
alembic upgrade head
```

### Пример 3: Добавление индекса

```python
def upgrade() -> None:
    op.create_index('idx_users_email', 'users', ['email'])

def downgrade() -> None:
    op.drop_index('idx_users_email', 'users')
```

## Текущая миграция: Archive Status

### Что добавлено

Файл: `alembic/versions/20241202_1530-add_archive_status_fields.py`

**Добавленные поля:**
- `is_archived` (BOOLEAN, default: false) - статус архива
- `archived_at` (VARCHAR, nullable) - дата архивации
- `archived_by_admin` (INTEGER, nullable, FK -> admins.id) - ID администратора

**Применение:**
```bash
alembic upgrade head
```

**Откат:**
```bash
alembic downgrade -1
```

## Работа в команде

### При получении новых миграций из Git:

1. Получите изменения:
```bash
git pull
```

2. Примените новые миграции:
```bash
alembic upgrade head
```

### При создании новой миграции:

1. Убедитесь, что ваша БД актуальна:
```bash
alembic upgrade head
```

2. Внесите изменения в модели

3. Создайте миграцию:
```bash
alembic revision --autogenerate -m "Описание"
```

4. Проверьте созданный файл

5. Закоммитьте изменения:
```bash
git add alembic/versions/*.py
git commit -m "Add migration: описание"
git push
```

## Конфигурация

### alembic.ini

Основные настройки:
- `script_location` - путь к миграциям
- `sqlalchemy.url` - строка подключения к БД
- `file_template` - формат имени файлов миграций

### alembic/env.py

Настройки окружения:
- Импорт моделей
- Настройка async/sync режима
- Дополнительные параметры миграций

## Лучшие практики

### ✅ Рекомендуется

1. **Всегда проверяйте автогенерированные миграции**
   - Alembic может не распознать все изменения
   - Проверьте upgrade() и downgrade()

2. **Пишите описательные сообщения**
   ```bash
   alembic revision -m "Add user_role field with default value"
   ```

3. **Тестируйте миграции**
   ```bash
   # Применить
   alembic upgrade head
   # Откатить
   alembic downgrade -1
   # Применить снова
   alembic upgrade head
   ```

4. **Используйте транзакции**
   - По умолчанию включены
   - Откат при ошибке автоматический

5. **Коммитьте миграции в Git**
   - Миграции - часть кода
   - Версионируйте вместе с моделями

### ❌ Не рекомендуется

1. **Не редактируйте примененные миграции**
   - Создавайте новую миграцию для исправлений

2. **Не удаляйте файлы миграций**
   - Это нарушит историю
   - Используйте downgrade

3. **Не применяйте миграции вручную через SQL**
   - Alembic не узнает об изменениях
   - Используйте только команды alembic

4. **Не храните пароли в alembic.ini**
   - Используйте переменные окружения
   - Или .env файлы (не коммитьте!)

## Устранение проблем

### Проблема: "Target database is not up to date"

**Решение:**
```bash
alembic upgrade head
```

### Проблема: "Can't locate revision identified by 'xxx'"

**Решение:**
```bash
# Проверьте текущую версию
alembic current

# Проверьте историю
alembic history

# Синхронизируйте с БД
alembic stamp head
```

### Проблема: Конфликт миграций

**Решение:**
```bash
# Откатите до общей версии
alembic downgrade <common_revision>

# Примените миграции по порядку
alembic upgrade head
```

### Проблема: Миграция не применяется

**Решение:**
1. Проверьте логи:
```bash
alembic upgrade head --verbose
```

2. Проверьте SQL:
```bash
alembic upgrade head --sql
```

3. Проверьте подключение к БД

## Дополнительные возможности

### Ветвление миграций

Для параллельной разработки:
```bash
alembic revision -m "Feature A" --branch-label=feature_a
alembic revision -m "Feature B" --branch-label=feature_b
```

### Метки (Labels)

```bash
alembic revision -m "Release 1.0" --rev-id=1.0
```

### Автозагрузка таблиц

В `env.py` можно настроить автозагрузку существующих таблиц.

## Полезные ссылки

- [Официальная документация Alembic](https://alembic.sqlalchemy.org/)
- [Tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Auto Generating Migrations](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)

## Чек-лист перед продакшеном

- [ ] Все миграции применены: `alembic current`
- [ ] Миграции протестированы (upgrade/downgrade)
- [ ] Созданы бэкапы базы данных
- [ ] Настроены права доступа к БД
- [ ] Документированы изменения схемы
- [ ] Команда проинформирована о миграциях

---

**Версия:** 1.0.0  
**Дата:** 2024-12-02  
**Автор:** OmegaSolutions Team

