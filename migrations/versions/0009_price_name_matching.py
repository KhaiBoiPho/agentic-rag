"""Diacritic- and word-order-insensitive matching for material_prices.

`lookup_material_price` matched with a single `material_name ILIKE '%…%'`,
which requires the user's words to appear **contiguously and in order**. Real
questions do not: asked "giá xi măng Bút Sơn PCB40", the row that holds the
answer is named "Xi măng bao Bút Sơn Xanh đa dụng PCB40" — the same words with
"bao" and "Xanh đa dụng" interleaved — so the lookup returned nothing while
the data sat right there. Typing without diacritics ("xi mang But Son") also
returned nothing.

Both are fixed at the query layer (see MaterialPriceRepository.lookup); this
migration only installs what that query needs:

  unaccent  — so "but son" matches "Bút Sơn".
  pg_trgm   — similarity() is used to RANK the survivors, so the closest name
              comes first instead of whichever row was inserted last.

The GIN index is on the unaccented, lower-cased name. unaccent() is declared
STABLE, not IMMUTABLE, so it cannot be indexed directly; the wrapper below is
the standard workaround and is safe here because the unaccent dictionary is
fixed for this database.

Revision ID: 0009_price_name_matching
Revises: 0008_kb_price_extraction
Create Date: 2026-08-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_price_name_matching"
down_revision = "0008_kb_price_extraction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS unaccent"))
    conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    conn.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION immutable_unaccent(text)
            RETURNS text AS $$
              SELECT public.unaccent('public.unaccent'::regdictionary, $1)
            $$ LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
            """
        )
    )
    conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_material_prices_name_trgm "
            "ON material_prices USING gin (lower(immutable_unaccent(material_name)) "
            "gin_trgm_ops)"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_material_prices_name_trgm"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS immutable_unaccent(text)"))
