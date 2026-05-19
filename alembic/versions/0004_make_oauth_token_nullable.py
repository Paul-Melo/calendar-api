"""Make oauth_credential.token nullable

Revision ID: 0004_make_oauth_token_nullable
Revises: 0003_add_encrypted_token_columns
Create Date: 2026-05-19
"""
from alembic import op
import sqlalchemy as sa


revision = '0004_make_oauth_token_nullable'
down_revision = '0003_add_encrypted_token_columns'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        'oauth_credential',
        'token',
        existing_type=sa.Text(),
        nullable=True,
        existing_nullable=False,
    )


def downgrade():
    op.execute("UPDATE oauth_credential SET token = '' WHERE token IS NULL")
    op.alter_column(
        'oauth_credential',
        'token',
        existing_type=sa.Text(),
        nullable=False,
        existing_nullable=True,
    )
