"""add_created_at_to_candidates

Revision ID: add_created_at_candidates
Revises: 53d7c93b736d
Create Date: 2025-12-05 00:56:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


# revision identifiers, used by Alembic.
revision: str = 'add_created_at_candidates'
down_revision: Union[str, None] = '53d7c93b736d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Добавляет поле created_at в таблицу candidate_profiles.
    
    1. Добавляет поле created_at (nullable, String)
    2. Добавляет индекс для быстрой сортировки
    3. Устанавливает текущую дату для существующих записей (опционально)
    """
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Проверяем существующие колонки
    existing_columns = [col['name'] for col in inspector.get_columns('candidate_profiles')]
    
    if 'created_at' not in existing_columns:
        # Добавляем поле created_at
        op.add_column(
            'candidate_profiles',
            sa.Column('created_at', sa.String(), nullable=True)
        )
        
        # Добавляем индекс для быстрой сортировки
        op.create_index(
            'ix_candidate_profiles_created_at',
            'candidate_profiles',
            ['created_at']
        )
        
        # Опционально: устанавливаем текущую дату для существующих записей
        # Можно оставить NULL, если не нужно заполнять исторические данные
        # from datetime import datetime
        # current_date = datetime.now().isoformat()
        # op.execute(text(f"UPDATE candidate_profiles SET created_at = '{current_date}' WHERE created_at IS NULL"))


def downgrade() -> None:
    """
    Откатывает изменения:
    1. Удаляет индекс created_at
    2. Удаляет поле created_at из таблицы candidate_profiles
    """
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    
    existing_columns = [col['name'] for col in inspector.get_columns('candidate_profiles')]
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('candidate_profiles')]
    
    # Удаляем индекс
    if 'ix_candidate_profiles_created_at' in existing_indexes:
        op.drop_index('ix_candidate_profiles_created_at', table_name='candidate_profiles')
    
    # Удаляем поле created_at
    if 'created_at' in existing_columns:
        op.drop_column('candidate_profiles', 'created_at')


