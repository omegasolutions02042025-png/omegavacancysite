"""add_role_to_registration_requests

Revision ID: 53d7c93b736d
Revises: 006_candidate_status
Create Date: 2025-12-04 19:27:28.200253

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '53d7c93b736d'
down_revision: Union[str, None] = '006_candidate_status'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Добавляет поле role в таблицу registration_requests.
    
    1. Добавляет поле role (nullable, default='RECRUITER')
    2. Устанавливает role='RECRUITER' для всех существующих заявок
    """
    from sqlalchemy import inspect, text
    
    conn = op.get_bind()
    inspector = inspect(conn)
    is_postgresql = conn.dialect.name == 'postgresql'
    
    # Проверяем существующие колонки
    existing_columns = [col['name'] for col in inspector.get_columns('registration_requests')]
    
    if 'role' not in existing_columns:
        # Определяем тип колонки в зависимости от БД
        if is_postgresql:
            # Для PostgreSQL используем существующий enum тип userrole, если он есть
            # Иначе создаем новый или используем VARCHAR
            try:
                # Проверяем существование enum типа userrole
                result = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_type WHERE typname = 'userrole'
                    )
                """))
                enum_exists = result.scalar()
                
                if enum_exists:
                    # Используем существующий enum тип
                    user_role_enum = postgresql.ENUM(
                        'CANDIDATE', 'RECRUITER', 'CONTRACTOR', 'ADMIN',
                        name='userrole',
                        create_type=False
                    )
                    op.add_column(
                        'registration_requests',
                        sa.Column('role', user_role_enum, nullable=True, server_default='RECRUITER')
                    )
                else:
                    # Создаем enum тип
                    user_role_enum = postgresql.ENUM(
                        'CANDIDATE', 'RECRUITER', 'CONTRACTOR', 'ADMIN',
                        name='userrole',
                        create_type=True
                    )
                    op.add_column(
                        'registration_requests',
                        sa.Column('role', user_role_enum, nullable=True, server_default='RECRUITER')
                    )
            except Exception:
                # В случае ошибки используем VARCHAR
                op.add_column(
                    'registration_requests',
                    sa.Column('role', sa.String(length=20), nullable=True, server_default='RECRUITER')
                )
        else:
            # Для SQLite и других БД используем VARCHAR
            op.add_column(
                'registration_requests',
                sa.Column('role', sa.String(length=20), nullable=True, server_default='RECRUITER')
            )
        
        # Устанавливаем role='RECRUITER' для всех существующих заявок, у которых role IS NULL
        op.execute(text("UPDATE registration_requests SET role = 'RECRUITER' WHERE role IS NULL"))


def downgrade() -> None:
    """
    Откатывает изменения:
    1. Удаляет поле role из таблицы registration_requests
    """
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    
    existing_columns = [col['name'] for col in inspector.get_columns('registration_requests')]
    
    # Удаляем поле role
    if 'role' in existing_columns:
        op.drop_column('registration_requests', 'role')

