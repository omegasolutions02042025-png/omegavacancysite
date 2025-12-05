-- Добавление полей профиля рекрутера в таблицу users
-- Выполнить вручную в PostgreSQL

-- Добавить новые колонки для профиля рекрутера
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS first_name VARCHAR,
ADD COLUMN IF NOT EXISTS last_name VARCHAR,
ADD COLUMN IF NOT EXISTS middle_name VARCHAR,
ADD COLUMN IF NOT EXISTS phone VARCHAR,
ADD COLUMN IF NOT EXISTS experience TEXT,
ADD COLUMN IF NOT EXISTS specialization VARCHAR,
ADD COLUMN IF NOT EXISTS resume TEXT;

-- Создать индексы для поиска по имени и фамилии
CREATE INDEX IF NOT EXISTS idx_users_first_name ON users(first_name);
CREATE INDEX IF NOT EXISTS idx_users_last_name ON users(last_name);
CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);

-- Проверка
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'users' 
AND column_name IN ('first_name', 'last_name', 'middle_name', 'phone', 'experience', 'specialization', 'resume')
ORDER BY ordinal_position;




