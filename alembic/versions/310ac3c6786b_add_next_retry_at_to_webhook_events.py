"""add next_retry_at to webhook events

Revision ID: 310ac3c6786b
Revises: 40791c04c257
Create Date: 2026-10-01 19:01:08.910813

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '310ac3c6786b'
down_revision: Union[str, Sequence[str], None] = '40791c04c257'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('webhook_events', sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('webhook_events', 'next_retry_at')
