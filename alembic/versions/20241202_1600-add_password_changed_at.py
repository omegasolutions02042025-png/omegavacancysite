"""Add password_changed_at field to users

Revision ID: 002_password_changed_at
Revises: 001_archive_status
Create Date: 2024-12-02 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_password_changed_at'
down_revision: Union[str, None] = '001_archive_status'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Добавляет поле password_changed_at в таблицу users.
    """
    from sqlalchemy import inspect
    
    # Получаем информацию о существующих колонках
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('users')]
    
    # Добавляем колонку password_changed_at (если не существует)
    if 'password_changed_at' not in existing_columns:
        op.add_column('users', sa.Column('password_changed_at', sa.String(), nullable=True))


def downgrade() -> None:
    """
    Откатывает изменения: удаляет колонку password_changed_at.
    """
    op.drop_column('users', 'password_changed_at')

