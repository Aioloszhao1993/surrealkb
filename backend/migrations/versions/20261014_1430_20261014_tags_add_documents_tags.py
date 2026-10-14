"""add documents.tags

Revision ID: 20261014_tags
Revises: 4bea7672db9d
Create Date: 2026-10-14

P3 新增的 documents.tags 列未包含在 baseline 中，新环境执行
`alembic upgrade head` 会缺少该列导致标签相关查询报错。此迁移补齐。
"""
from alembic import op
import sqlalchemy as sa

revision = "20261014_tags"
down_revision = "4bea7672db9d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("tags", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "tags")
