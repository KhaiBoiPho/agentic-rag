#!/usr/bin/env python3
"""Before/after for material-name matching in lookup_material_price.

Run INSIDE the app container:

    python scripts/eval_price_lookup.py

OLD is a single `material_name ILIKE '%<whole phrase>%'` — the behaviour
before migration 0009. NEW is the word-by-word, accent-insensitive match that
replaced it. Both run against the same live table, so the comparison is on
identical data.

A case counts as CORRECT only if the top hit's name contains `expect` — a
lookup that returns rows but the wrong product is a wrong construction cost,
which is worse than returning nothing.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db.postgres.base import get_session
from app.db.postgres.models import MaterialPrice
from app.db.postgres.repositories.material_price_repo import MaterialPriceRepository

# (vùng, câu tra như model thường truyền vào, chuỗi PHẢI có trong tên tìm được)
CASES: list[tuple[str, str, str]] = [
    ("HN", "xi măng Bút Sơn PCB40", "Bút Sơn"),
    ("HN", "xi măng Bút Sơn PCB30", "Bút Sơn"),
    ("HN", "xi mang But Son PCB40", "Bút Sơn"),  # không dấu
    ("HCM", "xi măng Vicem Hà Tiên Xây tô", "Xây tô"),
    ("HCM", "XM Vicem Hà Tiên đa dụng PCB40", "Đa dụng"),
    ("HCM", "xi mang Vicem Ha Tien PCB40", "Hà Tiên"),  # không dấu
    ("DN", "cáp điện CXV-150", "CXV-150"),
    ("DN", "cáp vặn xoắn LV-ABC-4x95", "LV-ABC-4x95"),
    ("DN", "đèn led CDE-CM30W", "CDE-CM30W"),
    ("HN", "cửa sổ nhôm Topal XFAD", "Topal XFAD"),
    # FAF 2500 chỉ có trong chunk, không vào material_prices (ô giá trống ở
    # bản gốc) — dùng dòng có thật để phép đo không chấm sai.
    ("HN", "van cổng gang ty chìm FAF 6000 DN65", "FAF 6000"),
    ("HCM", "đá 1x2", "Đá 1x2"),
    ("HCM", "cát san lấp", "san lấp"),
    ("HN", "thép thanh vằn D10", "D10"),
    ("HN", "nhựa đường 60/70", "nhựa đường"),
    ("DN", "ống nhựa uPVC", "uPVC"),
    # Đơn vị đo model tự thêm vào. "mm2" có chữ số nên từng bị ghim vĩnh viễn
    # bởi luật "không bao giờ bỏ token có số" (vốn để giữ "d12"), mà nó lại
    # khớp 0 dòng — nên mọi ứng viên đều bị loại và một sản phẩm CÓ THẬT bị
    # báo là không tìm thấy.
    ("DN", "cáp vặn xoắn LV-ABC-4x95 mm2", "LV-ABC-4x95"),
    ("DN", "cáp điện CXV-150 mm2", "CXV-150"),
    ("HN", "thép thanh vằn D10 kg", "D10"),
]


async def old_lookup(region: str, name: str, limit: int = 5) -> list[MaterialPrice]:
    """The pre-0009 behaviour: one substring match on the whole phrase."""
    async with get_session() as s:
        q = (
            select(MaterialPrice)
            .where(MaterialPrice.region == region, MaterialPrice.material_name.ilike(f"%{name}%"))
            .order_by(
                MaterialPrice.price_period.desc().nulls_last(),
                MaterialPrice.created_at.desc(),
            )
            .limit(limit)
        )
        return list((await s.execute(q)).scalars().all())


async def main() -> int:
    repo = MaterialPriceRepository()
    print(f"{'vùng':5} {'câu tra':34} {'CŨ':>22}  {'MỚI':>22}")
    old_ok = new_ok = 0
    for region, query, expect in CASES:
        o = await old_lookup(region, query)
        n = await repo.lookup(region=region, material_name=query, limit=5)

        def verdict(rows: list[MaterialPrice]) -> tuple[str, bool]:
            if not rows:
                return "0 dòng", False
            ok = expect.lower() in rows[0].material_name.lower()
            return (f"{len(rows)} dòng {'ĐÚNG' if ok else 'SAI SP'}", ok)

        ov, oo = verdict(o)
        nv, no = verdict(n)
        old_ok += oo
        new_ok += no
        mark = "" if oo == no else ("  <<< MỚI TÌM ĐƯỢC" if no else "  <<< MẤT")
        print(f"{region:5} {query[:32]:34} {ov:>22}  {nv:>22}{mark}")
        if no and not oo:
            print(f"{'':41} -> {n[0].material_name[:64]}")

    print()
    print(f"CŨ  đúng {old_ok}/{len(CASES)}")
    print(f"MỚI đúng {new_ok}/{len(CASES)}   ({new_ok - old_ok:+d})")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
