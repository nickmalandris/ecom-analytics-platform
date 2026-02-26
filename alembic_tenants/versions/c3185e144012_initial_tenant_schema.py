"""Initial tenant schema

Revision ID: c3185e144012
Revises: 
Create Date: 2026-02-26 12:12:23.046065

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3185e144012'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from src.ingestion.db_utils import (
        SHOPIFY_PRODUCTS_DDL,
        SHOPIFY_PRODUCT_VARIANTS_DDL,
        SHOPIFY_CUSTOMERS_DDL,
        SHOPIFY_ORDERS_DDL,
        SHOPIFY_ORDER_REFUNDS_DDL,
        META_CAMPAIGNS_DDL,
        META_AD_SETS_DDL,
        META_ADS_DDL,
        META_ADS_INSIGHTS_DDL,
    )
    
    statements = [
        SHOPIFY_PRODUCTS_DDL,
        SHOPIFY_PRODUCT_VARIANTS_DDL,
        SHOPIFY_CUSTOMERS_DDL,
        SHOPIFY_ORDERS_DDL,
        SHOPIFY_ORDER_REFUNDS_DDL,
        META_CAMPAIGNS_DDL,
        META_AD_SETS_DDL,
        META_ADS_DDL,
        META_ADS_INSIGHTS_DDL,
    ]

    for stmt in statements:
        # Since the connection already has search_path set to the tenant's schema,
        # we can just drop the {schema}. prefix and run the command.
        op.execute(sa.text(stmt.replace("{schema}.", "")))


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(sa.text("DROP TABLE IF EXISTS products CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS product_variants CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS customers CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS orders CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS order_refunds CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS campaigns CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS ad_sets CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS ads CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS ads_insights CASCADE;"))
