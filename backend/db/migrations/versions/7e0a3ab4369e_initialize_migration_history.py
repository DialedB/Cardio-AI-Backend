"""initialize migration history

Revision ID: 7e0a3ab4369e
Revises: 
Create Date: 2026-10-20 07:54:00.141846

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '7e0a3ab4369e'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
