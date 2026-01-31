"""Create oauth_credential table

Revision ID: 0002_create_oauthcredential
Revises: 0001_add_unique_constraint_appointment
Create Date: 2025-11-24
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_create_oauthcredential'
down_revision = '0001_add_unique_constraint_appointment'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'oauth_credential',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client_id', sa.String(length=200), nullable=True),
        sa.Column('token', sa.Text(), nullable=False),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('token_uri', sa.String(length=200), nullable=True),
        sa.Column('scopes', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('user_id', sa.Integer(), nullable=True),
    )
    # Note: foreign key to user table can be added if desired


def downgrade():
    op.drop_table('oauth_credential')
