"""Add candidate_id field to chat

Revision ID: 004_candidate_id_chat
Revises: 003_pd_consent
Create Date: 2024-12-02 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004_candidate_id_chat'
down_revision: Union[str, None] = '003_pd_consent'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Добавляет поле candidate_id в таблицу chat.
    """
    from sqlalchemy import inspect
    
    # Получаем информацию о существующих колонках
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('chat')]
    
    # Добавляем колонку candidate_id (если не существует)
    if 'candidate_id' not in existing_columns:
        op.add_column('chat', sa.Column('candidate_id', sa.Integer(), nullable=True, index=True))


def downgrade() -> None:
    """
    Откатывает изменения: удаляет колонку candidate_id.
    """
    op.drop_column('chat', 'candidate_id')

