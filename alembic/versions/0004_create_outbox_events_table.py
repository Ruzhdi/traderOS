"""create outbox events table

Revision ID: 0004_create_outbox_events_table
Revises: 0003_create_import_jobs_table
Create Date: 2026-08-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_create_outbox_events_table"
down_revision: str | None = "0003_create_import_jobs_table"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

status_values = ("pending", "processing", "published", "failed")
outbox_event_status = postgresql.ENUM(
    *status_values,
    name="outbox_event_status",
)


def upgrade() -> None:
    outbox_event_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                *status_values,
                name="outbox_event_status",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_outbox_events_attempt_count_non_negative",
        ),
        sa.CheckConstraint(
            "length(trim(event_type)) > 0",
            name="ck_outbox_events_event_type_not_empty",
        ),
        sa.CheckConstraint(
            "status != 'published' OR published_at IS NOT NULL",
            name="ck_outbox_events_published_at_required",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_outbox_events_pending_available_at_id",
        "outbox_events",
        ["available_at", "id"],
        unique=False,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outbox_events_pending_available_at_id",
        table_name="outbox_events",
    )
    op.drop_table("outbox_events")
    outbox_event_status.drop(op.get_bind(), checkfirst=True)
