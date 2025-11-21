# OmegaVac FastAPI Application

Профессиональное FastAPI приложение с SQLModel, полным CRUD и структурированной архитектурой.

## 📁 Структура проекта

```
omegavacsite/
├── app/                          # Основной пакет приложения
│   ├── __init__.py
│   ├── main.py                   # FastAPI app с lifespan events
│   ├── api/                      # API endpoints
│   │   ├── __init__.py
│   │   └── routes/               # Роутеры
│   │       ├── __init__.py
│   │       ├── items.py          # CRUD для items
│   │       └── upload.py         # Загрузка файлов + API
│   ├── core/                     # Ядро приложения
│   │   ├── __init__.py
│   │   ├── config.py             # Настройки (pydantic-settings)
│   │   └── database.py           # SQLModel engine и session
│   ├── models/                   # SQLModel таблицы
│   │   ├── __init__.py
│   │   ├── item.py               # Item model
│   │   └── upload.py             # UploadedFile model
│   ├── schemas/                  # Pydantic схемы для API
│   │   ├── __init__.py
│   │   ├── item.py               # ItemCreate, ItemUpdate, ItemResponse
│   │   └── upload.py             # UploadCreate, UploadResponse, UploadStats
│   ├── crud/                     # CRUD операции
│   │   ├── __init__.py
│   │   ├── item.py               # Item CRUD
│   │   └── upload.py             # Upload CRUD
│   └── services/                 # Бизнес-логика
│       ├── __init__.py
│       └── upload_service.py     # Сервис загрузки файлов
├── templates/                    # Jinja2 шаблоны
│   └── upload.html
├── static/                       # Статические файлы
├── uploads/                      # Загруженные файлы
├── main.py                       # Entrypoint (импортирует app.main)
├── requirements.txt              # Зависимости
├── .env.example                  # Пример конфигурации
└── omegavac.db                   # SQLite база данных (создается автоматически)
```

## 🚀 Запуск

1. **Установите зависимости:**
```bash
pip install -r requirements.txt
```

2. **Создайте .env файл (опционально):**
```bash
cp .env.example .env
```

3. **Запустите сервер:**
```bash
uvicorn main:app --reload
```

4. **Откройте в браузере:**
- 🏠 Root: http://127.0.0.1:8000/
- 📚 API docs: http://127.0.0.1:8000/docs
- 📤 Upload form: http://127.0.0.1:8000/upload

## 📡 API Endpoints

### Items (CRUD)
- `POST /items/` - Создать item
- `GET /items/` - Список items (с пагинацией)
- `GET /items/{item_id}` - Получить item по ID
- `PATCH /items/{item_id}` - Обновить item
- `DELETE /items/{item_id}` - Удалить item

### Upload (HTML форма)
- `GET /upload` - Форма загрузки с историей
- `POST /upload` - Загрузить файл через форму

### Upload API (REST)
- `POST /api/upload` - Загрузить файл (JSON response)
- `GET /api/uploads` - Список загруженных файлов
- `GET /api/uploads/{id}` - Информация о файле
- `GET /api/uploads/{id}/download` - Скачать файл
- `DELETE /api/uploads/{id}` - Удалить файл
- `GET /api/uploads/stats` - Статистика загрузок

## 🗄️ База данных

Приложение использует **SQLModel** (SQLAlchemy + Pydantic) с SQLite по умолчанию.

- База создается автоматически при первом запуске
- Таблицы: `items`, `uploaded_files`
- Для PostgreSQL/MySQL измените `DATABASE_URL` в `.env`

## ⚙️ Конфигурация

Настройки в `app/core/config.py`. Переопределяются через `.env`:

```env
APP_NAME=OmegaVac API
DEBUG=True
UPLOAD_DIR=uploads
MAX_UPLOAD_SIZE=10485760
DATABASE_URL=sqlite:///./omegavac.db
ECHO_SQL=True
```

## 🏗️ Архитектура

- **Models** - SQLModel таблицы для БД
- **Schemas** - Pydantic модели для валидации API
- **CRUD** - Операции с базой данных
- **Services** - Бизнес-логика (файлы, обработка)
- **Routes** - HTTP endpoints
- **Core** - Конфигурация и database engine

## 📝 Примеры использования

### Создать item
```bash
curl -X POST "http://127.0.0.1:8000/items/" \
  -H "Content-Type: application/json" \
  -d '{"name": "Laptop", "price": 999.99, "tags": ["electronics"]}'
```

### Загрузить файл
```bash
curl -X POST "http://127.0.0.1:8000/api/upload" \
  -F "file=@document.pdf" \
  -F "comment=Important document"
```

### Получить список файлов
```bash
curl "http://127.0.0.1:8000/api/uploads?skip=0&limit=10"
```
