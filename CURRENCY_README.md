# 💰 Модуль «Ставки, валюты и калькулятор курсов»

> Полнофункциональный модуль для работы с валютами и ставками кандидатов в системе OmegaVac

[![Status](https://img.shields.io/badge/status-ready-brightgreen)]()
[![Version](https://img.shields.io/badge/version-1.0.0-blue)]()
[![Python](https://img.shields.io/badge/python-3.10+-blue)]()

## 📋 Содержание

- [Описание](#описание)
- [Возможности](#возможности)
- [Быстрый старт](#быстрый-старт)
- [Документация](#документация)
- [API](#api)
- [Примеры](#примеры)
- [Архитектура](#архитектура)
- [FAQ](#faq)

## 🎯 Описание

Модуль предоставляет полный функционал для работы с валютами и ставками кандидатов:

- 🔄 **Автоматическое получение курсов** от ЦБ РФ
- 💱 **Конвертация валют** (RUB, USD, EUR, BYN)
- 💰 **Управление ставками** кандидатов
- 📊 **Автоматический пересчет** при изменении курсов
- 🎨 **Готовый UI виджет** для отображения
- 🔌 **REST API** для интеграции
- ⏰ **Фоновые задачи** для обновления

## ✨ Возможности

### Для пользователей
- ✅ Отображение ставки кандидата в 4 валютах одновременно
- ✅ Визуальная отметка исходной валюты кандидата
- ✅ Актуальные курсы от ЦБ РФ
- ✅ Пересчет ставок одним кликом
- ✅ Красивый адаптивный интерфейс

### Для разработчиков
- ✅ 8 готовых API эндпоинтов
- ✅ Полная типизация (Pydantic)
- ✅ Асинхронные операции
- ✅ Автоматическая документация (Swagger)
- ✅ Тестовое покрытие
- ✅ Подробная документация

### Для администраторов
- ✅ Автоматическое обновление курсов (раз в день)
- ✅ Ручное обновление курсов
- ✅ Пересчет ставок всех кандидатов
- ✅ Логирование всех операций
- ✅ Обработка ошибок

## 🚀 Быстрый старт

### 1. Установка

```bash
# Установите зависимости
pip install requests beautifulsoup4

# Или все сразу
pip install -r requirements.txt
```

### 2. Миграция БД

```bash
python scripts/migrate_add_currency_fields.py
```

### 3. Тестирование

```bash
python scripts/test_currency_module.py
```

### 4. Запуск

```bash
uvicorn app.main:app --reload
```

### 5. Проверка

```bash
curl http://localhost:8000/api/currency/rates/current
```

**Готово!** 🎉

## 📚 Документация

| Документ | Описание |
|----------|----------|
| [CURRENCY_QUICKSTART.md](CURRENCY_QUICKSTART.md) | Быстрый старт с примерами |
| [CURRENCY_SETUP_INSTRUCTIONS.md](CURRENCY_SETUP_INSTRUCTIONS.md) | Подробная инструкция по установке |
| [CURRENCY_MODULE.md](CURRENCY_MODULE.md) | Полная документация модуля |
| [CURRENCY_IMPLEMENTATION_SUMMARY.md](CURRENCY_IMPLEMENTATION_SUMMARY.md) | Детали реализации |
| [CURRENCY_FILES_LIST.md](CURRENCY_FILES_LIST.md) | Список всех файлов |

## 🔌 API

### Курсы валют

```http
GET  /api/currency/rates/current     # Получить текущие курсы
POST /api/currency/rates/refresh     # Обновить курсы (админ)
```

### Конвертация

```http
POST /api/currency/convert           # Конвертировать валюту
POST /api/currency/calculate-rates   # Рассчитать ставку
```

### Ставки кандидатов

```http
GET  /api/currency/candidates/{id}/rate              # Получить ставку
PUT  /api/currency/candidates/{id}/rate              # Обновить ставку
POST /api/currency/candidates/{id}/rate/recalculate  # Пересчитать
POST /api/currency/candidates/recalculate-all        # Пересчитать все
```

**Полная документация:** `http://localhost:8000/docs`

## 💡 Примеры

### Получить курсы валют

```bash
curl http://localhost:8000/api/currency/rates/current
```

```json
{
  "usd_rate": 95.50,
  "eur_rate": 103.25,
  "byn_rate": 29.80,
  "fetched_at": "2025-12-01T09:00:00"
}
```

### Конвертировать валюту

```bash
curl -X POST http://localhost:8000/api/currency/convert \
  -H "Content-Type: application/json" \
  -d '{"amount": 1000, "from_currency": "USD", "to_currency": "RUB"}'
```

```json
{
  "converted_amount": 95500.00,
  "exchange_rate_used": 95.5
}
```

### Рассчитать ставку кандидата

```bash
curl -X POST http://localhost:8000/api/currency/calculate-rates \
  -H "Content-Type: application/json" \
  -d '{"base_amount": 3000, "base_currency": "USD", "rate_type": "monthly"}'
```

```json
{
  "rate_rub": 286500.00,
  "rate_usd": 3000.00,
  "rate_eur": 2775.18,
  "rate_byn": 9614.09
}
```

### Использование в Python

```python
from app.crud.candidate_rate import CandidateRateCRUD

# Установить ставку
await CandidateRateCRUD.update_candidate_rate(
    session,
    candidate_id=123,
    base_amount=3000,
    base_currency="USD",
    rate_type="monthly"
)

# Получить ставку
candidate = await CandidateRateCRUD.get_candidate_with_rates(
    session,
    candidate_id=123
)

print(f"USD: {candidate.rate_usd}")
print(f"EUR: {candidate.rate_eur}")
print(f"RUB: {candidate.rate_rub}")
```

### Использование в шаблонах

```html
<!-- Добавьте в профиль кандидата -->
{% include "candidate/candidate_rates_widget.html" %}
```

## 🏗️ Архитектура

```
┌─────────────────────────────────────────────────┐
│                  UI Layer                        │
│    candidate_rates_widget.html                   │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│                API Layer                         │
│         /api/currency/* (8 endpoints)            │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│             Service Layer                        │
│  CurrencyService + ExchangeRateCRUD +            │
│  CandidateRateCRUD                               │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│             Database Layer                       │
│  ExchangeRate + CandidateProfileDB               │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│            External Source                       │
│         ЦБ РФ (cbr.ru)                           │
└─────────────────────────────────────────────────┘
```

## 🌍 Поддерживаемые валюты

| Валюта | Код | Символ | Страна |
|--------|-----|--------|--------|
| Российский рубль | RUB | ₽ | 🇷🇺 Россия |
| Доллар США | USD | $ | 🇺🇸 США |
| Евро | EUR | € | 🇪🇺 Евросоюз |
| Белорусский рубль | BYN | Br | 🇧🇾 Беларусь |

**Базовая валюта системы:** RUB (все конвертации идут через рубль)

## ⏰ Автоматизация

### Обновление курсов

- **При старте:** Проверка и загрузка курсов
- **Ежедневно в 09:00 (МСК):** Автоматическое обновление
- **По требованию:** Ручное обновление через API

### Пересчет ставок

- **При изменении ставки:** Автоматический пересчет
- **При обновлении курсов:** Пересчет по требованию
- **Массовый пересчет:** Для всех кандидатов через API

## 🎨 UI Виджет

Готовый виджет для отображения ставок:

![Widget Preview](https://via.placeholder.com/600x400?text=Currency+Widget)

**Особенности:**
- 🎨 Современный дизайн с градиентами
- 📱 Адаптивная верстка
- ⚡ AJAX обновление без перезагрузки
- ✨ Плавные анимации
- 🎯 Визуальная отметка базовой валюты

## 🔧 Настройка

### Изменить время обновления

`app/core/scheduler.py`:
```python
trigger=CronTrigger(hour=12, minute=0)  # 12:00 вместо 09:00
```

### Добавить новую валюту

1. Добавить поле в `ExchangeRate`
2. Обновить парсер
3. Обновить сервис конвертации
4. Добавить в UI виджет

Подробнее: [CURRENCY_MODULE.md](CURRENCY_MODULE.md)

## ❓ FAQ

### Как часто обновляются курсы?

Автоматически каждый день в 09:00 (МСК). Можно изменить в `scheduler.py`.

### Что если ЦБ РФ недоступен?

Используется последний успешно сохраненный курс. Система продолжает работать.

### Как пересчитать все ставки?

```bash
curl -X POST http://localhost:8000/api/currency/candidates/recalculate-all
```

### Можно ли использовать другой источник курсов?

Да, замените функцию `parse_cb_rf()` в `exchange_rate_parser.py`.

### Как добавить новую валюту?

См. раздел "Расширение функционала" в [CURRENCY_MODULE.md](CURRENCY_MODULE.md).

## 🐛 Troubleshooting

| Проблема | Решение |
|----------|---------|
| Курсы не загружаются | Проверьте доступность cbr.ru, вызовите `/rates/refresh` |
| Ошибка миграции | Проверьте подключение к БД, права доступа |
| Scheduler не работает | Проверьте, что `scheduler = start_scheduler()` раскомментирован |
| Ставки не обновляются | Вызовите `/candidates/{id}/rate/recalculate` |

Подробнее: [CURRENCY_SETUP_INSTRUCTIONS.md](CURRENCY_SETUP_INSTRUCTIONS.md)

## 📊 Статистика проекта

- **Файлов создано:** 14
- **Файлов обновлено:** 4
- **Строк кода:** ~2500+
- **API эндпоинтов:** 8
- **Поддерживаемых валют:** 4
- **Тестов:** 5

## 🤝 Вклад

Модуль разработан в соответствии с техническим заданием и готов к использованию.

### Что реализовано

✅ Все требования ТЗ выполнены
✅ Дополнительные улучшения добавлены
✅ Полная документация создана
✅ Тесты написаны
✅ UI компоненты готовы

### Что можно улучшить

- [ ] Добавить кэширование на уровне Redis
- [ ] Реализовать резервный источник курсов
- [ ] Добавить историю изменения ставок
- [ ] Реализовать уведомления об изменении курсов
- [ ] Добавить экспорт в Excel/PDF

## 📞 Поддержка

При возникновении вопросов:

1. 📖 Проверьте [документацию](CURRENCY_MODULE.md)
2. 🧪 Запустите [тесты](scripts/test_currency_module.py)
3. 📋 Проверьте [FAQ](#faq)
4. 🔍 Проверьте логи приложения
5. 💬 Обратитесь к разработчикам

## 📄 Лицензия

Модуль является частью системы OmegaVac.

## 📅 История версий

### v1.0.0 (01.12.2025)
- ✨ Первый релиз
- ✅ Все функции реализованы
- 📚 Документация создана
- 🧪 Тесты написаны

---

<div align="center">

**Модуль готов к использованию!** 🎉

[Быстрый старт](CURRENCY_QUICKSTART.md) • [Документация](CURRENCY_MODULE.md) • [API Docs](http://localhost:8000/docs)

Made with ❤️ for OmegaVac

</div>

