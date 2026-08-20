"""Repair `material_prices.unit` values corrupted by the wrong-unit-column
ingestion bug (see app/core/ingestion/price_extractor.py's unit
self-correction, added same session as this script).

A handful of company-block sub-tables (measured: the Nishu section of
HaNoi_PhuLuc.pdf) had their header detected correctly overall but `unit_col`
pointed at the WRONG physical column ("Vận chuyển" instead of "Đơn vị tính"),
so every row in that block stored unit="Bao gồm" instead of "kg"/"lít". The
extractor now self-corrects this at ingest time — but the rows already in the
database were written before that fix existed, and re-ingesting requires the
original PDF bytes, which this system does not retain after upload.

The fix here needs no re-ingestion: `raw_row_text` is the full, unmodified,
pipe-joined row exactly as parsed ("bột bả nội thất | BT- 01 | kg | ... |
Bao gồm | ... | 5.625") — the CORRECT unit ("kg") is sitting right there,
just not at the position that got written to the `unit` column. This finds
every row whose stored `unit` is not a recognized unit token, and whose
raw_row_text DOES contain one, and rewrites `unit` to that recovered value.

Conservative by construction: a row is only ever touched when a real unit
token is found verbatim in its own raw_row_text — nothing is invented, and a
row with no recognizable unit anywhere in its raw text is left alone and
reported so it can be looked at by hand.

Usage:
    python -m scripts.repair_unit_column            # dry run: report only
    python -m scripts.repair_unit_column --apply     # write the fixes

    # Against Railway (or any other DB) instead of the local one:
    DATABASE_URL=postgresql+asyncpg://... python -m scripts.repair_unit_column --apply
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.core.ingestion.price_extractor import _UNIT_TOKENS
from app.db.postgres.base import get_session
from app.db.postgres.models import MaterialPrice


def _recover_unit(raw_row_text: str) -> str | None:
    for cell in raw_row_text.split("|"):
        token = cell.strip()
        if token.lower() in _UNIT_TOKENS:
            return token
    return None


async def main(apply: bool) -> None:
    async with get_session() as s:
        rows = (
            (await s.execute(select(MaterialPrice))).scalars().all()
        )

        fixable: list[tuple[MaterialPrice, str]] = []
        unfixable: list[MaterialPrice] = []
        for row in rows:
            if row.unit and row.unit.strip().lower() in _UNIT_TOKENS:
                continue  # already a recognized unit — nothing to do
            recovered = _recover_unit(row.raw_row_text or "")
            if recovered:
                fixable.append((row, recovered))
            else:
                unfixable.append(row)

        print(f"Scanned {len(rows)} rows.")
        print(f"  {len(fixable)} have a wrong unit AND a recoverable one in raw_row_text.")
        print(f"  {len(unfixable)} have a wrong-looking unit but nothing recoverable — left as-is.")

        by_old_unit: dict[str, int] = {}
        for row, _ in fixable:
            by_old_unit[row.unit or "(rỗng)"] = by_old_unit.get(row.unit or "(rỗng)", 0) + 1
        for old, count in sorted(by_old_unit.items(), key=lambda kv: -kv[1]):
            print(f"    {count:>5}  {old!r} -> recovered")

        if unfixable:
            print("\n  Sample of unfixable rows (first 5):")
            for row in unfixable[:5]:
                print(f"    id={row.id} unit={row.unit!r} raw={row.raw_row_text[:100]!r}")

        if not apply:
            print("\nDry run only — pass --apply to write these fixes.")
            return

        for row, recovered in fixable:
            row.unit = recovered
        await s.commit()
        print(f"\nApplied: {len(fixable)} rows updated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write the fixes (default: dry run)")
    args = parser.parse_args()
    asyncio.run(main(args.apply))
