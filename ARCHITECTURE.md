# Архитектура приложения OmegaVac

## Слои приложения

```
┌─────────────────────────────────────────────────────────┐
│                    HTTP Requests                         │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                  API Routes Layer                        │
│  app/api/routes/                                         │
│  - items.py      (Items CRUD endpoints)                  │
│  - upload.py     (Upload endpoints + HTML)               │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                  Schemas Layer                           │
│  app/schemas/                                            │
│  - item.py       (ItemCreate, ItemUpdate, ItemResponse)  │
│  - upload.py     (UploadCreate, UploadResponse, Stats)   │
│                                                          │
│  Валидация входных/выходных данных                       │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│              Services Layer (Business Logic)             │
│  app/services/                                           │
│  - upload_service.py  (Сохранение файлов, генерация     │
│                        уникальных имен)                  │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                  CRUD Layer                              │
│  app/crud/                                               │
│  - item.py       (Item CRUD операции)                    │
│  - upload.py     (Upload CRUD операции)                  │
│                                                          │
│  Абстракция работы с БД                                  │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                  Models Layer                            │
│  app/models/                                             │
│  - item.py       (SQLModel Item table)                   │
│  - upload.py     (SQLModel UploadedFile table)           │
│                                                          │
│  Определение структуры таблиц БД                         │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                    Database                              │
│  SQLite / PostgreSQL / MySQL                             │
└─────────────────────────────────────────────────────────┘
```

## Поток данных

### Создание Item (POST /items/)

```
1. Client → POST /items/ + JSON body
2. Routes → Валидация через ItemCreate schema
3. Routes → item_crud.create(session, item_in)
4. CRUD → Создание Item model
5. CRUD → session.add() + commit()
6. CRUD → return Item
7. Routes → Конвертация в ItemResponse
8. Routes → JSON response to client
```

### Загрузка файла (POST /api/upload)

```
1. Client → POST /api/upload + multipart/form-data
2. Routes → Получение UploadFile
3. Routes → upload_service.save_file(file, session, comment)
4. Service → Генерация уникального имени
5. Service → Сохранение на диск
6. Service → upload_crud.create() с метаданными
7. CRUD → Создание UploadedFile record
8. Service → return UploadedFile
9. Routes → Конвертация в UploadResponse
10. Routes → JSON response to client
```

## Ключевые компоненты

### Core (app/core/)
- **config.py** - Настройки приложения через pydantic-settings
- **database.py** - SQLModel engine, создание таблиц, session dependency

### Models (app/models/)
- SQLModel классы с `table=True`
- Определяют структуру БД
- Используются CRUD слоем

### Schemas (app/schemas/)
- Pydantic модели для API
- Валидация входных данных
- Сериализация выходных данных
- Разделение: Create, Update, Response

### CRUD (app/crud/)
- Инкапсуляция операций с БД
- Методы: create, get, get_multi, update, delete, count
- Работают с SQLModel session

### Services (app/services/)
- Бизнес-логика
- Координация между CRUD и внешними ресурсами (файловая система)
- Обработка сложных операций

### Routes (app/api/routes/)
- HTTP endpoints
- Dependency injection (session, services)
- Обработка запросов/ответов
- Документация OpenAPI

## Dependency Injection

```python
# Database session
session: Session = Depends(get_session)

# Используется в каждом endpoint для доступа к БД
# Автоматически закрывается после обработки запроса
```

## Преимущества архитектуры

1. **Разделение ответственности** - каждый слой имеет четкую роль
2. **Тестируемость** - легко мокировать CRUD/Services
3. **Масштабируемость** - просто добавлять новые роуты/модели
4. **Переиспользование** - CRUD методы используются разными роутами
5. **Типобезопасность** - Pydantic + SQLModel + type hints
6. **Документация** - автогенерация OpenAPI из schemas

## Расширение приложения

### Добавить новую сущность (например, User)

1. Создать `app/models/user.py` (SQLModel table)
2. Создать `app/schemas/user.py` (UserCreate, UserUpdate, UserResponse)
3. Создать `app/crud/user.py` (UserCRUD class)
4. Создать `app/api/routes/user.py` (endpoints)
5. Подключить роутер в `app/main.py`

### Добавить аутентификацию

1. Создать `app/core/security.py` (JWT, password hashing)
2. Создать `app/api/dependencies.py` (get_current_user)
3. Добавить `Depends(get_current_user)` в защищенные endpoints

### Добавить фоновые задачи

1. Установить `celery` или использовать `BackgroundTasks`
2. Создать `app/tasks/` для задач
3. Вызывать из services или routes
