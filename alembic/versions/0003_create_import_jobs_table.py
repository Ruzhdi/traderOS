"""create import jobs table

Revision ID: 0003_create_import_jobs_table
Revises: 0002_create_trades_table
Create Date: 2026-08-02 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_create_import_jobs_table"
down_revision: str | None = "0002_create_trades_table"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "processing",
                "completed",
                "failed",
                name="import_job_status",
                native_enum=False,
                create_constraint=True,
                validate_strings=True,
                length=20,
            ),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=True),
        sa.Column(
            "imported_rows",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "rejected_rows",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
            "total_rows IS NULL OR total_rows >= 0",
            name="ck_import_jobs_total_rows_non_negative",
        ),
        sa.CheckConstraint(
            "imported_rows >= 0",
            name="ck_import_jobs_imported_rows_non_negative",
        ),
        sa.CheckConstraint(
            "rejected_rows >= 0",
            name="ck_import_jobs_rejected_rows_non_negative",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        op.f("ix_import_jobs_user_id"),
        "import_jobs",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_import_jobs_user_id"), table_name="import_jobs")
    op.drop_table("import_jobs")
