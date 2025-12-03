# Модуль «Ставки, валюты и калькулятор курсов»

## Описание

Модуль предназначен для:
- Автоматического получения курсов валют от ЦБ РФ
- Хранения и управления ставками кандидатов в разных валютах
- Автоматического пересчета ставок при изменении курсов
- Предоставления API для работы с валютами

## Архитектура

### Основные компоненты

1. **Модели данных**
   - `ExchangeRate` - хранение курсов валют (USD, EUR, BYN к RUB)
   - Расширенная `CandidateProfileDB` - хранение ставок кандидатов

2. **Сервисы**
   - `exchange_rate_parser.py` - парсинг курсов с сайта ЦБ РФ
   - `currency_service.py` - конвертация валют и расчет ставок

3. **CRUD**
   - `exchange_rate.py` - операции с курсами валют
   - `candidate_rate.py` - операции со ставками кандидатов

4. **API эндпоинты**
   - `/api/currency/*` - работа с валютами и ставками

## Установка и настройка

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

Новые зависимости:
- `requests==2.31.0` - для HTTP запросов к ЦБ РФ
- `beautifulsoup4==4.12.2` - для парсинга HTML

### 2. Миграция базы данных

Запустите миграцию для добавления новых таблиц и полей:

```bash
python scripts/migrate_add_currency_fields.py
```

Миграция создаст:
- Таблицу `exchange_rates` для хранения курсов
- Новые поля в `candidate_profiles` для ставок

### 3. Первый запуск

При первом запуске приложения автоматически:
- Создадутся необходимые таблицы
- Загрузятся актуальные курсы валют от ЦБ РФ

## Использование

### API эндпоинты

#### 1. Получить текущие курсы валют

```http
GET /api/currency/rates/current
```

Ответ:
```json
{
  "id": 1,
  "usd_rate": 95.50,
  "eur_rate": 103.25,
  "byn_rate": 29.80,
  "fetched_at": "2025-12-01T09:00:00",
  "is_active": true,
  "last_update_status": "success",
  "error_message": null
}
```

#### 2. Обновить курсы валют (админ)

```http
POST /api/currency/rates/refresh
```

Принудительно обновляет курсы с сайта ЦБ РФ.

#### 3. Конвертировать валюту

```http
POST /api/currency/convert
Content-Type: application/json

{
  "amount": 1000,
  "from_currency": "USD",
  "to_currency": "RUB"
}
```

Ответ:
```json
{
  "original_amount": 1000,
  "from_currency": "USD",
  "converted_amount": 95500.00,
  "to_currency": "RUB",
  "exchange_rate_used": 95.5,
  "calculated_at": "2025-12-01T10:30:00"
}
```

#### 4. Рассчитать ставку во всех валютах

```http
POST /api/currency/calculate-rates
Content-Type: application/json

{
  "base_amount": 3000,
  "base_currency": "USD",
  "rate_type": "monthly"
}
```

Ответ:
```json
{
  "base_amount": 3000,
  "base_currency": "USD",
  "rate_type": "monthly",
  "is_base": true,
  "rate_rub": 286500.00,
  "rate_usd": 3000.00,
  "rate_eur": 2790.00,
  "rate_byn": 9616.00,
  "rates_calculated_at": "2025-12-01T10:30:00",
  "exchange_rate_snapshot_id": 1,
  "exchange_rate_fetched_at": "2025-12-01T09:00:00"
}
```

#### 5. Получить ставку кандидата

```http
GET /api/currency/candidates/{candidate_id}/rate
```

#### 6. Обновить ставку кандидата

```http
PUT /api/currency/candidates/{candidate_id}/rate
Content-Type: application/json

{
  "base_amount": 250000,
  "base_currency": "RUB",
  "rate_type": "monthly"
}
```

#### 7. Пересчитать ставку кандидата

```http
POST /api/currency/candidates/{candidate_id}/rate/recalculate
```

Пересчитывает ставку с актуальным курсом валют.

#### 8. Пересчитать ставки всех кандидатов (админ)

```http
POST /api/currency/candidates/recalculate-all?user_id=1
```

Параметры:
- `user_id` (опционально) - ID пользователя для фильтрации

## Автоматическое обновление курсов

### Расписание

Курсы валют обновляются автоматически:
- **При старте приложения** - проверка наличия курсов, загрузка при необходимости
- **Каждый день в 09:00** (МСК) - автоматическое обновление через scheduler

### Настройка расписания

Изменить время обновления можно в `app/core/scheduler.py`:

```python
scheduler.add_job(
    update_exchange_rates_job,
    trigger=CronTrigger(hour=9, minute=0),  # Изменить время здесь
    id="daily_exchange_rates_update",
    replace_existing=True,
)
```

## Поддерживаемые валюты

- **RUB** - Российский рубль (базовая валюта системы)
- **USD** - Доллар США
- **EUR** - Евро
- **BYN** - Белорусский рубль

## Логика работы

### Хранение ставок кандидата

Для каждого кандидата хранится:
1. **Основная ставка** (`base_rate_amount`, `base_rate_currency`) - исходная ставка в валюте, указанной кандидатом
2. **Кэшированные значения** (`rate_rub`, `rate_usd`, `rate_eur`, `rate_byn`) - предрассчитанные значения во всех валютах
3. **Метаданные** (`rates_calculated_at`, `exchange_rate_snapshot_id`) - информация о времени и курсе расчета

### Алгоритм конвертации

Все конвертации проходят через рубль (RUB):

1. Конвертация из исходной валюты в RUB:
   - `amount_rub = amount * rate(currency → RUB)`

2. Конвертация из RUB в целевую валюту:
   - `amount_target = amount_rub / rate(target_currency → RUB)`

### Пример расчета

Исходные данные:
- Ставка: 3000 USD
- Курс USD: 95.50 RUB

Расчет:
1. В RUB: `3000 * 95.50 = 286,500 RUB`
2. В EUR: `286,500 / 103.25 = 2,775.18 EUR`
3. В BYN: `286,500 / 29.80 = 9,614.09 BYN`

## Обработка ошибок

### Недоступность ЦБ РФ

При недоступности сайта ЦБ РФ:
1. Используется последний успешно сохраненный курс
2. Создается запись со статусом `error`
3. Логируется ошибка
4. Работа системы не блокируется

### Отсутствие курсов

При отсутствии курсов в БД:
- API возвращает HTTP 404 с понятным сообщением
- Рекомендуется вызвать `/api/currency/rates/refresh`

## Интеграция с профилем кандидата

### Поля в CandidateProfileDB

```python
# Основная ставка
base_rate_amount: float  # Сумма
base_rate_currency: str  # Валюта (RUB, USD, EUR, BYN)
rate_type: str          # Тип (hourly, monthly, yearly)

# Кэшированные значения
rate_rub: float
rate_usd: float
rate_eur: float
rate_byn: float

# Метаданные
rates_calculated_at: str
exchange_rate_snapshot_id: int
```

### Пример использования в коде

```python
from app.crud.candidate_rate import CandidateRateCRUD

# Обновить ставку кандидата
candidate = await CandidateRateCRUD.update_candidate_rate(
    session,
    candidate_id=123,
    base_amount=250000,
    base_currency="RUB",
    rate_type="monthly"
)

# Получить ставку с конвертацией
candidate = await CandidateRateCRUD.get_candidate_with_rates(
    session,
    candidate_id=123
)

print(f"Ставка в USD: {candidate.rate_usd}")
print(f"Ставка в EUR: {candidate.rate_eur}")
```

## UI интеграция

### Отображение ставок

В личном кабинете кандидата рекомендуется отображать:

```html
<div class="candidate-rates">
  <h3>Ставка кандидата</h3>
  
  <div class="base-rate">
    <span class="amount">{{ base_rate_amount }}</span>
    <span class="currency">{{ base_rate_currency }}</span>
    <span class="badge">✓ Исходная ставка</span>
  </div>
  
  <div class="converted-rates">
    <div class="rate-item">
      <span class="label">RUB:</span>
      <span class="value">{{ rate_rub | number_format(2) }}</span>
    </div>
    <div class="rate-item">
      <span class="label">USD:</span>
      <span class="value">{{ rate_usd | number_format(2) }}</span>
    </div>
    <div class="rate-item">
      <span class="label">EUR:</span>
      <span class="value">{{ rate_eur | number_format(2) }}</span>
    </div>
    <div class="rate-item">
      <span class="label">BYN:</span>
      <span class="value">{{ rate_byn | number_format(2) }}</span>
    </div>
  </div>
  
  <div class="rate-meta">
    <small>Курс от: {{ exchange_rate_fetched_at }}</small>
  </div>
</div>
```

## Мониторинг и логирование

### Логи

Все операции логируются в стандартный logger:

```python
logger.info("Курсы валют успешно обновлены")
logger.error("Ошибка при парсинге курсов ЦБ РФ")
logger.warning("Активный курс не найден в БД")
```

### Проверка статуса

Проверить статус последнего обновления:

```http
GET /api/currency/rates/current
```

Поле `last_update_status` покажет:
- `success` - успешное обновление
- `error` - ошибка при обновлении

## Расширение функционала

### Добавление новой валюты

1. Добавить поле в `ExchangeRate`:
```python
cny_rate: Optional[float] = Field(default=None, description="Курс CNY к RUB")
```

2. Обновить парсер в `exchange_rate_parser.py`

3. Добавить логику конвертации в `currency_service.py`

4. Добавить поле в `CandidateProfileDB`:
```python
rate_cny: Optional[float] = Field(default=None, description="Ставка в юанях")
```

### Смена источника курсов

Заменить функцию `parse_cb_rf()` в `app/core/exchange_rate_parser.py` на другой источник данных (API, файл, другой сайт).

## Troubleshooting

### Проблема: Курсы не обновляются

**Решение:**
1. Проверить доступность сайта ЦБ РФ
2. Проверить логи приложения
3. Вручную вызвать `/api/currency/rates/refresh`

### Проблема: Ошибка при миграции

**Решение:**
1. Проверить права доступа к БД
2. Убедиться, что БД доступна
3. Проверить, не существуют ли уже поля

### Проблема: Неверные курсы

**Решение:**
1. Проверить структуру HTML на сайте ЦБ РФ (могла измениться)
2. Обновить индексы в парсере
3. Добавить логирование для отладки

## Контакты и поддержка

При возникновении проблем:
1. Проверьте логи приложения
2. Проверьте документацию API
3. Обратитесь к разработчикам

