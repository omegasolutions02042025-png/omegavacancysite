-- Миграция для добавления полей архивации пользователей
-- Дата: 2024-12-02

-- Добавляем поле is_archived (статус архива)
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_archived BOOLEAN DEFAULT FALSE;

-- Добавляем поле archived_at (дата архивации)
ALTER TABLE users ADD COLUMN IF NOT EXISTS archived_at VARCHAR;

-- Добавляем поле archived_by_admin (ID администратора)
ALTER TABLE users ADD COLUMN IF NOT EXISTS archived_by_admin INTEGER;

-- Выводим результат
SELECT 'Migration completed successfully!' AS status;

-- Проверяем структуру
SELECT column_name, data_type, column_default 
FROM information_schema.columns 
WHERE table_name = 'users' 
AND column_name IN ('is_archived', 'archived_at', 'archived_by_admin')
ORDER BY column_name;

