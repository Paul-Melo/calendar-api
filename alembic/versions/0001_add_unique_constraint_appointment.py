"""Add unique constraint to appointment (appointment_date, service_type)

Revision ID: 0001_add_unique_constraint_appointment
Revises: 
Create Date: 2025-11-24
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_add_unique_constraint_appointment'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # For databases supporting ALTER TABLE ADD CONSTRAINT
    try:
        op.create_unique_constraint('uq_appointment_date_service', 'appointment', ['appointment_date', 'service_type'])
    except Exception:
        # If DB (e.g., SQLite) does not support adding constraint, leave note for manual process
        print('Warning: Could not add unique constraint automatically. For SQLite, recreate table with constraint.')


def downgrade():
    try:
        op.drop_constraint('uq_appointment_date_service', 'appointment', type_='unique')
    except Exception:
        print('Warning: Could not drop unique constraint automatically.')
