"""Add candidate status fields

Revision ID: 006_candidate_status
Revises: 005_user_roles
Create Date: 2024-12-02 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '006_candidate_status'
down_revision: Union[str, None] = '005_user_roles'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Добавляет поля статуса кандидата:
    1. Удаляет существующий enum тип candidatestatus, если он есть (для PostgreSQL)
    2. Добавляет поле status в таблицу candidate_profiles (VARCHAR)
    3. Добавляет поле status_until в таблицу candidate_profiles
    4. Устанавливает значение по умолчанию 'В активном поиске' для всех существующих кандидатов
    """
    from sqlalchemy import inspect, text
    
    conn = op.get_bind()
    inspector = inspect(conn)
    is_postgresql = conn.dialect.name == 'postgresql'
    
    # Проверяем существующие колонки
    existing_columns = [col['name'] for col in inspector.get_columns('candidate_profiles')]
    
    # Удаляем существующий enum тип, если он есть (для PostgreSQL)
    if is_postgresql:
        try:
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_type WHERE typname = 'candidatestatus'
                )
            """))
            enum_exists = result.scalar()
            if enum_exists:
                # Удаляем enum тип, если он существует
                op.execute(text('DROP TYPE IF EXISTS candidatestatus CASCADE'))
        except Exception as e:
            # Игнорируем ошибки при проверке/удалении enum
            pass
    
    # ========================================================================
    # 1. Добавляем поле status (используем VARCHAR для совместимости)
    # ========================================================================
    if 'status' not in existing_columns:
        # Используем VARCHAR вместо enum для совместимости с SQLAlchemy
        op.add_column(
            'candidate_profiles',
            sa.Column(
                'status',
                sa.String(length=50),
                nullable=True,
                server_default='В активном поиске'
            )
        )
        
        # Устанавливаем значение по умолчанию для всех существующих кандидатов
        op.execute(text("""
            UPDATE candidate_profiles 
            SET status = 'В активном поиске' 
            WHERE status IS NULL
        """))
    
    # ========================================================================
    # 2. Добавляем поле status_until
    # ========================================================================
    if 'status_until' not in existing_columns:
        op.add_column(
            'candidate_profiles',
            sa.Column('status_until', sa.String(), nullable=True)
        )


def downgrade() -> None:
    """
    Откатывает изменения:
    1. Удаляет поле status_until
    2. Удаляет поле status
    """
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    
    existing_columns = [col['name'] for col in inspector.get_columns('candidate_profiles')]
    
    # Удаляем поле status_until
    if 'status_until' in existing_columns:
        op.drop_column('candidate_profiles', 'status_until')
    
    # Удаляем поле status
    if 'status' in existing_columns:
        op.drop_column('candidate_profiles', 'status')

