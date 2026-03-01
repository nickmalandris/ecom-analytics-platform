"""Initial public schema

Revision ID: e2b0c4d130c8
Revises: 
Create Date: 2026-02-26 12:06:51.920587

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2b0c4d130c8'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create auth tables used by FastAPI Users."""

    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('hashed_password', sa.String(length=1024), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    op.create_table(
        'oauth_account',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('oauth_name', sa.String(length=100), nullable=False),
        sa.Column('access_token', sa.String(length=1024), nullable=False),
        sa.Column('expires_at', sa.Integer(), nullable=True),
        sa.Column('refresh_token', sa.String(length=1024), nullable=True),
        sa.Column('account_id', sa.String(length=320), nullable=False),
        sa.Column('account_email', sa.String(length=320), nullable=False),
    )
    op.create_index('ix_oauth_account_oauth_name', 'oauth_account', ['oauth_name'])
    op.create_index('ix_oauth_account_account_id', 'oauth_account', ['account_id'])


def downgrade() -> None:
    """Drop auth tables."""

    op.drop_index('ix_oauth_account_account_id', table_name='oauth_account')
    op.drop_index('ix_oauth_account_oauth_name', table_name='oauth_account')
    op.drop_table('oauth_account')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')
