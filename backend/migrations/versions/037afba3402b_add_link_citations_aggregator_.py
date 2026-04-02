"""add_link_citations_aggregator_discoveries_domain_blacklist

Revision ID: 037afba3402b
Revises: 
Create Date: 2026-04-01 13:18:04.763797

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '037afba3402b'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- link_citations ---
    op.create_table(
        'link_citations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('source_article_id', sa.String(), nullable=False),
        sa.Column('cited_domain', sa.Text(), nullable=False),
        sa.Column('cited_url', sa.Text(), nullable=False),
        sa.Column('anchor_text', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['source_article_id'], ['articles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_article_id', 'cited_url', name='uq_link_citations_article_url'),
    )
    op.create_index('ix_link_citations_cited_domain', 'link_citations', ['cited_domain'])

    # --- aggregator_discoveries ---
    op.create_table(
        'aggregator_discoveries',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('aggregator', sa.Text(), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('comment_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('discovered_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('url', 'aggregator', name='uq_aggregator_discoveries_url_agg'),
    )
    op.create_index('ix_aggregator_discoveries_agg_date', 'aggregator_discoveries', ['aggregator', 'discovered_at'])

    # --- domain_blacklist ---
    op.create_table(
        'domain_blacklist',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('domain', sa.Text(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('added_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('domain', name='uq_domain_blacklist_domain'),
    )

    # Seed 6 low-quality domains
    import uuid
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    seed_domains = [
        ('medium.com', 'Ad-heavy content farm with paywalls'),
        ('forbes.com', 'Ad-heavy listicle farm'),
        ('buzzfeed.com', 'Clickbait content'),
        ('huffpost.com', 'Low-signal aggregator'),
        ('businessinsider.com', 'Paywalled ad-heavy content'),
        ('mashable.com', 'Clickbait tech coverage'),
    ]
    op.bulk_insert(
        sa.table(
            'domain_blacklist',
            sa.column('id', sa.String()),
            sa.column('domain', sa.Text()),
            sa.column('reason', sa.Text()),
            sa.column('added_at', sa.DateTime()),
        ),
        [
            {'id': str(uuid.uuid4()), 'domain': domain, 'reason': reason, 'added_at': now}
            for domain, reason in seed_domains
        ],
    )


def downgrade() -> None:
    op.drop_table('domain_blacklist')
    op.drop_index('ix_aggregator_discoveries_agg_date', table_name='aggregator_discoveries')
    op.drop_table('aggregator_discoveries')
    op.drop_index('ix_link_citations_cited_domain', table_name='link_citations')
    op.drop_table('link_citations')
