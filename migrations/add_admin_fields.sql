-- Добавление полей для администратора в таблицу users
-- Выполнить вручную в PostgreSQL

-- 1. Создать таблицу admins если её нет
CREATE TABLE IF NOT EXISTS admins (
    id SERIAL PRIMARY KEY,
    username VARCHAR NOT NULL UNIQUE,
    hashed_password VARCHAR NOT NULL,
    created_at VARCHAR
);

-- 2. Добавить новые колонки в таблицу users
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS created_by_admin INTEGER,
ADD COLUMN IF NOT EXISTS created_at VARCHAR;

-- 3. Добавить внешний ключ (опционально)
ALTER TABLE users 
ADD CONSTRAINT fk_users_created_by_admin 
FOREIGN KEY (created_by_admin) REFERENCES admins(id) 
ON DELETE SET NULL;

-- 4. Создать индексы для производительности
CREATE INDEX IF NOT EXISTS idx_users_created_by_admin ON users(created_by_admin);
CREATE INDEX IF NOT EXISTS idx_admins_username ON admins(username);

-- Проверка
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'users' 
ORDER BY ordinal_position;


