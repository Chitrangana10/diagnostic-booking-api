"""add token_version to users

Revision ID: 40791c04c257
Revises: 50ab7eb79b37
Create Date: 2026-10-01 18:59:50.431406

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '40791c04c257'
down_revision: Union[str, Sequence[str], None] = '50ab7eb79b37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('token_version', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'token_version')
