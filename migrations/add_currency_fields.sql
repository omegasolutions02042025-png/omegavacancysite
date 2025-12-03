-- Миграция: Добавление полей валют

-- 1. Создание таблицы exchange_rates
CREATE TABLE IF NOT EXISTS exchange_rates (
    id SERIAL PRIMARY KEY,
    usd_rate FLOAT,
    eur_rate FLOAT,
    byn_rate FLOAT,
    fetched_at VARCHAR NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    last_update_status VARCHAR DEFAULT 'success',
    error_message VARCHAR
);

-- Индексы для exchange_rates
CREATE INDEX IF NOT EXISTS idx_exchange_rates_fetched_at ON exchange_rates(fetched_at);
CREATE INDEX IF NOT EXISTS idx_exchange_rates_is_active ON exchange_rates(is_active);

-- 2. Добавление полей в candidate_profiles
ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS base_rate_amount FLOAT;
ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS base_rate_currency VARCHAR DEFAULT 'RUB';
ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS rate_type VARCHAR DEFAULT 'monthly';
ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS rate_rub FLOAT;
ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS rate_usd FLOAT;
ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS rate_eur FLOAT;
ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS rate_byn FLOAT;
ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS rates_calculated_at VARCHAR;
ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS exchange_rate_snapshot_id INTEGER;

