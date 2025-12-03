"""Add archive status fields to users table

Revision ID: 001_archive_status
Revises: 
Create Date: 2024-12-02 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_archive_status'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Добавляет поля архивации в таблицу users:
    - is_archived: статус архива (boolean, default false)
    - archived_at: дата архивации (varchar, nullable)
    - archived_by_admin: ID администратора (integer, nullable, FK)
    """
    from sqlalchemy import inspect, text
    
    # Получаем информацию о существующих колонках
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('users')]
    
    # Добавляем колонку is_archived (если не существует)
    if 'is_archived' not in existing_columns:
        op.add_column('users', sa.Column('is_archived', sa.Boolean(), nullable=False, server_default='false'))
    
    # Добавляем колонку archived_at (если не существует)
    if 'archived_at' not in existing_columns:
        op.add_column('users', sa.Column('archived_at', sa.String(), nullable=True))
    
    # Добавляем колонку archived_by_admin (если не существует)
    if 'archived_by_admin' not in existing_columns:
        op.add_column('users', sa.Column('archived_by_admin', sa.Integer(), nullable=True))
    
    # Проверяем существование внешнего ключа
    existing_fks = [fk['name'] for fk in inspector.get_foreign_keys('users')]
    if 'fk_users_archived_by_admin' not in existing_fks:
        # Добавляем внешний ключ для archived_by_admin
        op.create_foreign_key(
            'fk_users_archived_by_admin',  # constraint name
            'users',  # source table
            'admins',  # target table
            ['archived_by_admin'],  # source columns
            ['id']  # target columns
        )


def downgrade() -> None:
    """
    Откатывает изменения:
    - Удаляет внешний ключ
    - Удаляет добавленные колонки
    """
    # Удаляем внешний ключ
    op.drop_constraint('fk_users_archived_by_admin', 'users', type_='foreignkey')
    
    # Удаляем колонки
    op.drop_column('users', 'archived_by_admin')
    op.drop_column('users', 'archived_at')
    op.drop_column('users', 'is_archived')

