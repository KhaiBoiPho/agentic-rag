#!/usr/bin/env python3
"""Print what material_prices actually holds for each benchmark probe.

Run INSIDE the app container:

    PYTHONPATH=/app python scripts/bench_ground.py

Exists so no expected value in bench_questions.py is written from memory.
Every probe below is either a value the benchmark asserts, or an absence the
benchmark asserts — and an absence has to be re-checked whenever the corpus
is re-ingested, because a product appearing later would silently turn a
correct refusal into a scored failure.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text as sql

from app.db.postgres.base import get_session

# (nhãn, vùng hoặc None, mảnh tên cần tìm)
PROBES: list[tuple[str, str | None, str]] = [
    ("Bút Sơn", "HN", "bút sơn"),
    ("Hà Tiên", "HCM", "hà tiên"),
    ("Hạ Long", None, "hạ long"),
    ("CXV-150", None, "cxv-150"),
    ("CXV-500", None, "cxv-500"),
    ("LV-ABC-4x95", None, "lv-abc-4x95"),
    ("đá mi", "DN", "đá mi"),
    ("đá 0,5x1", "DN", "0,5x1"),
    ("Dmax25", "DN", "dmax25"),
    ("Dmax 25", "DN", "dmax 25"),
    ("Dmax37,5", "DN", "dmax37,5"),
    ("Thanh Tâm", None, "thanh tâm"),
    ("đá 1x2", None, "1x2"),
    ("cát san lấp", "HCM", "san lấp"),
    ("thép D10", "HN", "d10"),
    ("thép D12", "HN", "d12"),
    ("Việt Nhật", None, "việt nhật"),
    ("Topal XFAD", "HN", "topal"),
    ("nhựa đường", "HN", "nhựa đường"),
    ("uPVC", "DN", "upvc"),
    ("Điện Quang LEDBUA80", "DN", "ledbua80"),
    ("Nối trơn phi 16", "DN", "nối trơn phi 16"),
    ("Sông Gianh", None, "sông gianh"),
    ("Nghi Sơn", None, "nghi sơn"),
    ("Hoa Sen", None, "hoa sen"),
    ("PCB50", None, "pcb50"),
    ("Hoàng Thạch", None, "hoàng thạch"),
    ("gạch không nung", None, "không nung"),
]


async def main() -> int:
    only = sys.argv[1].lower() if len(sys.argv) > 1 else None
    async with get_session() as s:
        for label, region, needle in PROBES:
            if only and only not in label.lower():
                continue
            where = "material_name ilike :n"
            params = {"n": f"%{needle}%"}
            if region:
                where += " and region = :r"
                params["r"] = region
            rows = (
                await s.execute(
                    sql(
                        "select region, material_name, unit, price_ex_vat, "
                        "coalesce(manufacturer,'') from material_prices "
                        f"where {where} order by price_ex_vat"
                    ),
                    params,
                )
            ).fetchall()
            head = f"── {label}  [{region or 'mọi vùng'}]  {len(rows)} dòng"
            print(head)
            if not rows:
                print("     (KHÔNG CÓ — dùng được cho câu hỏi phải từ chối)")
            seen: set[tuple] = set()
            for r in rows:
                key = (r[0], r[1], r[3])
                if key in seen:
                    continue
                seen.add(key)
                if len(seen) > 12:
                    print(f"     … còn {len(rows) - 12} dòng nữa")
                    break
                print(f"     {r[0]:4} {r[1][:52]:54} {r[2] or '-':8} {r[3]:>12,.0f}  {r[4][:26]}")
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
