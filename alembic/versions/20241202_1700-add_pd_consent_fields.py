"""Add personal data consent fields to users and registration_requests tables

Revision ID: 003_pd_consent
Revises: 002_password_changed_at
Create Date: 2024-12-02 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003_pd_consent'
down_revision: Union[str, None] = '002_password_changed_at'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Добавляет поля согласия на обработку персональных данных:
    - В таблицу users: pd_consent, pd_consent_at, pd_consent_email, pd_consent_ip
    - В таблицу registration_requests: pd_consent, pd_consent_at, pd_consent_email, pd_consent_ip
    """
    from sqlalchemy import inspect
    
    # Получаем информацию о существующих колонках
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # ==========================================
    # Таблица users
    # ==========================================
    existing_columns_users = [col['name'] for col in inspector.get_columns('users')]
    
    # Добавляем колонку pd_consent (если не существует)
    if 'pd_consent' not in existing_columns_users:
        op.add_column('users', sa.Column('pd_consent', sa.Boolean(), nullable=False, server_default='false'))
    
    # Добавляем колонку pd_consent_at (если не существует)
    if 'pd_consent_at' not in existing_columns_users:
        op.add_column('users', sa.Column('pd_consent_at', sa.String(), nullable=True))
    
    # Добавляем колонку pd_consent_email (если не существует)
    if 'pd_consent_email' not in existing_columns_users:
        op.add_column('users', sa.Column('pd_consent_email', sa.String(), nullable=True))
    
    # Добавляем колонку pd_consent_ip (если не существует)
    if 'pd_consent_ip' not in existing_columns_users:
        op.add_column('users', sa.Column('pd_consent_ip', sa.String(), nullable=True))
    
    # ==========================================
    # Таблица registration_requests
    # ==========================================
    try:
        existing_columns_reg = [col['name'] for col in inspector.get_columns('registration_requests')]
    except Exception:
        # Таблица может не существовать, пропускаем
        existing_columns_reg = []
    
    # Добавляем колонку pd_consent (если не существует)
    if 'pd_consent' not in existing_columns_reg:
        op.add_column('registration_requests', sa.Column('pd_consent', sa.Boolean(), nullable=False, server_default='false'))
    
    # Добавляем колонку pd_consent_at (если не существует)
    if 'pd_consent_at' not in existing_columns_reg:
        op.add_column('registration_requests', sa.Column('pd_consent_at', sa.String(), nullable=True))
    
    # Добавляем колонку pd_consent_email (если не существует)
    if 'pd_consent_email' not in existing_columns_reg:
        op.add_column('registration_requests', sa.Column('pd_consent_email', sa.String(), nullable=True))
    
    # Добавляем колонку pd_consent_ip (если не существует)
    if 'pd_consent_ip' not in existing_columns_reg:
        op.add_column('registration_requests', sa.Column('pd_consent_ip', sa.String(), nullable=True))


def downgrade() -> None:
    """
    Откатывает изменения: удаляет добавленные колонки из обеих таблиц.
    """
    # Удаляем колонки из registration_requests
    try:
        op.drop_column('registration_requests', 'pd_consent_ip')
        op.drop_column('registration_requests', 'pd_consent_email')
        op.drop_column('registration_requests', 'pd_consent_at')
        op.drop_column('registration_requests', 'pd_consent')
    except Exception:
        pass  # Таблица может не существовать
    
    # Удаляем колонки из users
    op.drop_column('users', 'pd_consent_ip')
    op.drop_column('users', 'pd_consent_email')
    op.drop_column('users', 'pd_consent_at')
    op.drop_column('users', 'pd_consent')




