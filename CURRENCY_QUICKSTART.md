# Быстрый старт модуля валют

## Шаг 1: Установка зависимостей

```bash
pip install requests==2.31.0 beautifulsoup4==4.12.2
```

Или установите все зависимости:

```bash
pip install -r requirements.txt
```

## Шаг 2: Миграция базы данных

```bash
python scripts/migrate_add_currency_fields.py
```

Эта команда:
- Создаст таблицу `exchange_rates`
- Добавит поля валют в `candidate_profiles`

## Шаг 3: Запуск приложения

```bash
uvicorn app.main:app --reload
```

При первом запуске автоматически:
- Загрузятся курсы валют от ЦБ РФ
- Настроится автоматическое обновление (каждый день в 09:00)

## Шаг 4: Проверка работы

### Проверить курсы валют

```bash
curl http://localhost:8000/api/currency/rates/current
```

### Конвертировать валюту

```bash
curl -X POST http://localhost:8000/api/currency/convert \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 1000,
    "from_currency": "USD",
    "to_currency": "RUB"
  }'
```

### Рассчитать ставку кандидата

```bash
curl -X POST http://localhost:8000/api/currency/calculate-rates \
  -H "Content-Type: application/json" \
  -d '{
    "base_amount": 3000,
    "base_currency": "USD",
    "rate_type": "monthly"
  }'
```

## Шаг 5: Интеграция в профиль кандидата

### В Python коде

```python
from app.crud.candidate_rate import CandidateRateCRUD

# Установить ставку кандидата
await CandidateRateCRUD.update_candidate_rate(
    session,
    candidate_id=123,
    base_amount=250000,
    base_currency="RUB",
    rate_type="monthly"
)

# Получить ставку кандидата
candidate = await CandidateRateCRUD.get_candidate_with_rates(
    session,
    candidate_id=123
)

print(f"Ставка в USD: {candidate.rate_usd}")
print(f"Ставка в EUR: {candidate.rate_eur}")
```

### В HTML шаблоне

Добавьте виджет в профиль кандидата:

```html
{% include "candidate/candidate_rates_widget.html" %}
```

Передайте переменные:

```python
return templates.TemplateResponse("candidate/candidate_profile.html", {
    "request": request,
    "candidate_id": candidate.id,
    "base_rate_amount": candidate.base_rate_amount,
    "base_rate_currency": candidate.base_rate_currency,
    "rate_type": candidate.rate_type,
    "rate_rub": candidate.rate_rub,
    "rate_usd": candidate.rate_usd,
    "rate_eur": candidate.rate_eur,
    "rate_byn": candidate.rate_byn,
    "rates_calculated_at": candidate.rates_calculated_at,
})
```

## Основные API эндпоинты

| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/currency/rates/current` | Получить текущие курсы |
| POST | `/api/currency/rates/refresh` | Обновить курсы (админ) |
| POST | `/api/currency/convert` | Конвертировать валюту |
| POST | `/api/currency/calculate-rates` | Рассчитать ставку |
| GET | `/api/currency/candidates/{id}/rate` | Получить ставку кандидата |
| PUT | `/api/currency/candidates/{id}/rate` | Обновить ставку кандидата |
| POST | `/api/currency/candidates/{id}/rate/recalculate` | Пересчитать ставку |
| POST | `/api/currency/candidates/recalculate-all` | Пересчитать все ставки |

## Автоматическое обновление

Курсы обновляются автоматически:
- ✅ При старте приложения
- ✅ Каждый день в 09:00 (МСК)

Изменить расписание: `app/core/scheduler.py`

## Поддерживаемые валюты

- 🇷🇺 **RUB** - Российский рубль (базовая)
- 🇺🇸 **USD** - Доллар США
- 🇪🇺 **EUR** - Евро
- 🇧🇾 **BYN** - Белорусский рубль

## Troubleshooting

### Курсы не загружаются

```bash
# Проверить доступность ЦБ РФ
curl https://www.cbr.ru/currency_base/daily/

# Принудительно обновить курсы
curl -X POST http://localhost:8000/api/currency/rates/refresh
```

### Ошибка миграции

```bash
# Проверить подключение к БД
python -c "from app.core.config import settings; print(settings.database_url)"

# Запустить миграцию с логами
python scripts/migrate_add_currency_fields.py
```

### Ставки не пересчитываются

```bash
# Пересчитать ставки всех кандидатов
curl -X POST http://localhost:8000/api/currency/candidates/recalculate-all
```

## Полная документация

См. [CURRENCY_MODULE.md](CURRENCY_MODULE.md) для подробной документации.

## Примеры использования

### Пример 1: Установка ставки при создании кандидата

```python
# При парсинге резюме
candidate = CandidateProfileDB(
    first_name="Иван",
    last_name="Иванов",
    # ... другие поля ...
    base_rate_amount=3000,
    base_rate_currency="USD",
    rate_type="monthly"
)

session.add(candidate)
await session.commit()

# Рассчитать ставки во всех валютах
await CandidateRateCRUD.update_candidate_rate(
    session,
    candidate.id,
    3000,
    "USD",
    "monthly"
)
```

### Пример 2: Обновление ставки через API

```javascript
// JavaScript на фронтенде
async function updateCandidateRate(candidateId, amount, currency) {
    const response = await fetch(`/api/currency/candidates/${candidateId}/rate`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            base_amount: amount,
            base_currency: currency,
            rate_type: 'monthly'
        })
    });
    
    const data = await response.json();
    console.log('Обновленные ставки:', data);
}
```

### Пример 3: Пересчет всех ставок после обновления курсов

```python
# В фоновой задаче или админ-панели
from app.services.currency_service import CurrencyService
from app.crud.candidate_rate import CandidateRateCRUD

# Обновить курсы
await CurrencyService.update_exchange_rates(session)

# Пересчитать ставки всех кандидатов
updated_count = await CandidateRateCRUD.recalculate_all_candidates_rates(session)
print(f"Обновлено ставок: {updated_count}")
```

## Что дальше?

1. ✅ Интегрируйте виджет в профиль кандидата
2. ✅ Настройте отображение ставок в списке кандидатов
3. ✅ Добавьте фильтрацию по ставкам
4. ✅ Настройте уведомления об изменении курсов
5. ✅ Добавьте экспорт ставок в отчеты

## Поддержка

При возникновении проблем:
1. Проверьте логи: `tail -f app.log`
2. Проверьте статус курсов: `GET /api/currency/rates/current`
3. Обратитесь к документации: [CURRENCY_MODULE.md](CURRENCY_MODULE.md)

