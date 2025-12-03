"""Add user roles system

Revision ID: 005_user_roles
Revises: 004_candidate_id_chat
Create Date: 2024-12-02 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '005_user_roles'
down_revision: Union[str, None] = '004_candidate_id_chat'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Добавляет систему ролей пользователей:
    1. Добавляет поле role в таблицу users (nullable, default='RECRUITER')
    2. Устанавливает role='RECRUITER' для всех существующих пользователей
    3. Создает таблицы для профилей ролей (candidate_profiles_roles, recruiter_profiles_roles, contractor_profiles_roles)
    """
    from sqlalchemy import inspect, text
    
    conn = op.get_bind()
    inspector = inspect(conn)
    is_postgresql = conn.dialect.name == 'postgresql'
    
    # ========================================================================
    # 1. Добавляем поле role в таблицу users
    # ========================================================================
    existing_columns = [col['name'] for col in inspector.get_columns('users')]
    
    if 'role' not in existing_columns:
        # Определяем тип колонки в зависимости от БД
        if is_postgresql:
            # Для PostgreSQL создаем enum тип
            user_role_enum = postgresql.ENUM(
                'CANDIDATE', 'RECRUITER', 'CONTRACTOR', 'ADMIN',
                name='userrole',
                create_type=True
            )
            op.add_column('users', sa.Column('role', user_role_enum, nullable=True))
        else:
            # Для SQLite и других БД используем VARCHAR
            op.add_column('users', sa.Column('role', sa.String(length=20), nullable=True))
    
    # Устанавливаем role='RECRUITER' для всех существующих пользователей, у которых role IS NULL
    op.execute(text("UPDATE users SET role = 'RECRUITER' WHERE role IS NULL"))
    
    # ========================================================================
    # 2. Создаем enum тип для Grade (только для PostgreSQL)
    # ========================================================================
    if is_postgresql:
        grade_enum = postgresql.ENUM(
            'JUNIOR', 'MIDDLE', 'SENIOR', 'LEAD',
            name='grade',
            create_type=True
        )
    else:
        grade_enum = sa.String(length=20)
    
    # ========================================================================
    # 3. Создаем таблицу candidate_profiles_roles
    # ========================================================================
    op.create_table(
        'candidate_profiles_roles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('grade', grade_enum, nullable=True),
        sa.Column('experience_years', sa.Integer(), nullable=True),
        sa.Column('stack', sa.JSON(), nullable=True),
        sa.Column('resume_url', sa.String(), nullable=True),
        sa.Column('bio', sa.Text(), nullable=True),
        sa.Column('created_at', sa.String(), nullable=True),
        sa.Column('updated_at', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_candidate_profiles_roles_user_id'), 'candidate_profiles_roles', ['user_id'], unique=False)
    
    # ========================================================================
    # 4. Создаем таблицу recruiter_profiles_roles
    # ========================================================================
    op.create_table(
        'recruiter_profiles_roles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('specialization', sa.String(), nullable=True),
        sa.Column('experience_years', sa.Integer(), nullable=True),
        sa.Column('company', sa.String(), nullable=True),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('telegram', sa.String(), nullable=True),
        sa.Column('linkedin', sa.String(), nullable=True),
        sa.Column('created_at', sa.String(), nullable=True),
        sa.Column('updated_at', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_recruiter_profiles_roles_user_id'), 'recruiter_profiles_roles', ['user_id'], unique=False)
    
    # ========================================================================
    # 5. Создаем таблицу contractor_profiles_roles
    # ========================================================================
    op.create_table(
        'contractor_profiles_roles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('grade', grade_enum, nullable=True),
        sa.Column('experience_years', sa.Integer(), nullable=True),
        sa.Column('stack', sa.JSON(), nullable=True),
        sa.Column('hourly_rate_usd', sa.Float(), nullable=True),
        sa.Column('is_available', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('portfolio_url', sa.String(), nullable=True),
        sa.Column('bio', sa.Text(), nullable=True),
        sa.Column('created_at', sa.String(), nullable=True),
        sa.Column('updated_at', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_contractor_profiles_roles_user_id'), 'contractor_profiles_roles', ['user_id'], unique=False)


def downgrade() -> None:
    """
    Откатывает изменения:
    1. Удаляет таблицы профилей
    2. Удаляет поле role из таблицы users
    3. Удаляет enum типы (для PostgreSQL)
    """
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    is_postgresql = conn.dialect.name == 'postgresql'
    
    # Удаляем таблицы профилей
    op.drop_index(op.f('ix_contractor_profiles_roles_user_id'), table_name='contractor_profiles_roles')
    op.drop_table('contractor_profiles_roles')
    
    op.drop_index(op.f('ix_recruiter_profiles_roles_user_id'), table_name='recruiter_profiles_roles')
    op.drop_table('recruiter_profiles_roles')
    
    op.drop_index(op.f('ix_candidate_profiles_roles_user_id'), table_name='candidate_profiles_roles')
    op.drop_table('candidate_profiles_roles')
    
    # Удаляем поле role из таблицы users
    op.drop_column('users', 'role')
    
    # Удаляем enum типы (только для PostgreSQL)
    if is_postgresql:
        op.execute('DROP TYPE IF EXISTS grade')
        op.execute('DROP TYPE IF EXISTS userrole')

