#!/usr/bin/env python3
"""Verify benchmark run identity without calling any model/API.

Writes results/benchmark_identity_v1/run_manifest.csv,
retrieval_T1500_dense.csv, retrieval_R1500_dense.csv, and run_fingerprint.csv.
Retrieval evidence IDs are explicitly marked as
unavailable when the question cache contains only expect_values/expect_text.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import tiktoken

from scripts.eval_chunking_strategy import PDF_DOCS, OVERLAP_PCT, chunks_recursive, fold, digits
from scripts.eval_final_500 import _MONEY_RE, hit

ROOT = Path(__file__).resolve().parents[1]
IDENTITY_OUT = ROOT / "results" / "benchmark_identity_v1"
CACHE = ROOT / ".bench_cache"
EMB = "text-embedding-3-small"


def table_chunks_at_cap(cap: int):
    from app.core.chunking.base import split_oversized_table_chunk
    from app.core.chunking.dispatcher import ChunkDispatcher

    out = []
    for rel, _, _ in PDF_DOCS:
        p = ROOT / "kb_docx" / rel
        raw = ChunkDispatcher(
            chunk_token_num=512,
            overlap_percent=OVERLAP_PCT,
            table_context_size=128,
        ).chunk(filename=p.name, content=p.read_bytes(), document_id="d", kb_id="k")
        for c in raw:
            out.extend(split_oversized_table_chunk(c, cap))
    return out


def token_count(enc, text: str) -> int:
    return len(enc.encode(text, disallowed_special=()))


def iso_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def newest(pattern: str) -> Path | None:
    paths = [p for p in CACHE.glob(pattern) if not p.name.endswith(".manifest.json")]
    return max(paths, key=lambda p: p.stat().st_mtime) if paths else None


def vector_path(config: str) -> Path:
    patterns = {
        "T1500": "emb_openai_text-embedding-3-small_identity_v2_f500_T1500_2252_*.json",
        "T3000": "emb_openai_text-embedding-3-small_f500_T_1476_*.json",
        "R1500": "emb_openai_text-embedding-3-small_identity_v2_f500_R1500_790_*.json",
    }
    p = newest(patterns[config])
    if p is None:
        raise FileNotFoundError(patterns[config])
    return p


def text_digest(texts: list[str]) -> str:
    return hashlib.sha256("\x00".join(texts).encode()).hexdigest()[:12]


def write_manifest(stats: dict[str, dict], paths: dict[str, Path]) -> None:
    fields = ["config_id", "index_name", "chunk_limit", "chunk_count", "avg_chunk_tokens",
              "embedding_model", "source_count", "created_at"]
    IDENTITY_OUT.mkdir(parents=True, exist_ok=True)
    with (IDENTITY_OUT / "run_manifest.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for k in ("T1500", "T3000", "R1500"):
            s = stats[k]
            w.writerow({
                "config_id": k,
                "index_name": s["index_name"],
                "chunk_limit": s["chunk_limit"],
                "chunk_count": s["chunk_count"],
                "avg_chunk_tokens": f'{s["mean_chunk_tokens"]:.3f}',
                "embedding_model": EMB,
                "source_count": 11,
                "created_at": iso_mtime(paths[k]),
            })


def write_stats(stats: dict[str, dict]) -> None:
    IDENTITY_OUT.mkdir(parents=True, exist_ok=True)
    (IDENTITY_OUT / "run_identity_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_vectors(path: Path):
    return np.asarray(json.loads(path.read_text()), dtype=np.float32)


def write_retrieval(config: str, chunks: list[str], vectors: np.ndarray, qs: list[dict]) -> int:
    qpath = newest("emb_openai_text-embedding-3-small_identity_v2_q500_500_*.json") or newest("emb_openai_text-embedding-3-small_q500_500_*.json")
    if qpath is None:
        raise FileNotFoundError("q500 embedding cache")
    qvectors = load_vectors(qpath)
    vectors = vectors / (np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-9)
    qvectors = qvectors / (np.linalg.norm(qvectors, axis=1, keepdims=True) + 1e-9)
    folded, money = [fold(c) for c in chunks], [{digits(m) for m in _MONEY_RE.findall(fold(c))} for c in chunks]
    IDENTITY_OUT.mkdir(parents=True, exist_ok=True)
    out = IDENTITY_OUT / f"retrieval_{config}_dense.csv"
    fields = ["query_id", "question_group", "hit_at_5", "retrieved_chunk_ids",
              "gold_evidence_id", "index_name", "config_id"]
    total = 0
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for q, qv in zip(qs, qvectors):
            top = np.argsort(-(vectors @ qv))[:5].tolist()
            ok = any(hit(q, int(i), folded, money) for i in top)
            total += int(ok)
            gold = "UNAVAILABLE_EXPECT_VALUES" if q.get("expect_values") else "UNAVAILABLE_EXPECT_TEXT"
            w.writerow({
                "query_id": q["qid"],
                "question_group": q["tier"],
                "hit_at_5": int(ok),
                "retrieved_chunk_ids": ";".join(f"{config}-{i:04d}" for i in top),
                "gold_evidence_id": gold,
                "index_name": config,
                "config_id": config,
            })
    return total


def write_fingerprint():
    # This is the exact prompt construction in eval_tier4_nim.py.  Raw answer
    # caches were overwritten by --out at completion, so output-status counts
    # are intentionally unavailable rather than reconstructed.
    sys = (
        "Bạn trả lời câu hỏi về vật liệu xây dựng, CHỈ dựa vào phần ngữ cảnh được "
        "cung cấp. Nếu ngữ cảnh không có thông tin, trả lời đúng hai chữ: KHÔNG CÓ. "
        "Trả lời thật ngắn — chỉ nêu con số hoặc cụm từ được hỏi, không giải thích."
    )
    user_template = "NGỮ CẢNH:\n{ctx}\n\nCÂU HỎI: {question}\nTRẢ LỜI:"
    prompt_hash = hashlib.sha256((sys + "\n" + user_template).encode()).hexdigest()
    fields = ["config_id", "model", "prompt_hash", "max_tokens", "temperature", "top_k",
              "retriever", "cache_version", "total_queries", "empty_outputs", "length_outputs", "em"]
    rows = [
        # The prior commands passed --arms T, whose implementation is the
        # 3,000-token table arm. Do not relabel these as T1500.
        ("T3000_dense", "openai/gpt-oss-20b", "dense", 241),
        ("T3000_bm25", "openai/gpt-oss-20b", "dense_bm25_rrf", 271),
    ]
    IDENTITY_OUT.mkdir(parents=True, exist_ok=True)
    with (IDENTITY_OUT / "run_fingerprint.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for cid, model, retriever, em in rows:
            w.writerow({"config_id": cid, "model": model, "prompt_hash": prompt_hash,
                        "max_tokens": 2000, "temperature": 0, "top_k": 5,
                        "retriever": retriever, "cache_version": "finalrerun",
                        "total_queries": 500, "empty_outputs": "UNAVAILABLE_CACHE_OVERWRITTEN",
                        "length_outputs": "UNAVAILABLE_CACHE_OVERWRITTEN", "em": em})


def main():
    enc = tiktoken.get_encoding("cl100k_base")
    t1500 = table_chunks_at_cap(1500)
    t3000 = table_chunks_at_cap(3000)
    r1500 = chunks_recursive(1500)
    arms = {"T1500": t1500, "T3000": t3000, "R1500": r1500}
    paths = {k: vector_path(k) for k in arms}
    stats = {}
    for k, chunks in arms.items():
        texts = [c.content for c in chunks] if k.startswith("T") else chunks
        toks = np.asarray([token_count(enc, x) for x in texts], dtype=np.int64)
        table_count = sum(1 for c in chunks if getattr(c, "chunk_type", None).value == "table") if k.startswith("T") else 0
        samples = []
        sample_pool = [i for i, c in enumerate(chunks)
                       if getattr(c, "chunk_type", None) is not None
                       and getattr(c, "chunk_type", None).value == "table"]
        if not sample_pool:
            sample_pool = list(range(len(chunks)))
        for pos in np.linspace(0, len(sample_pool) - 1, min(5, len(sample_pool)), dtype=int):
            i = sample_pool[int(pos)]
            c = chunks[int(i)]
            text = c.content if hasattr(c, "content") else c
            metadata = getattr(c, "metadata", {})
            samples.append({"chunk_id": f"{k}-{int(i):04d}", "has_header": bool(re.search(r"<th\b", text)),
                            "token_count": int(toks[int(i)]), "over_1500": bool(toks[int(i)] > 1500),
                            "metadata": metadata,
                            "metadata_chunk_limit": metadata.get("chunk_limit"),
                            "metadata_has_chunk_limit": "chunk_limit" in metadata,
                            "filename": getattr(c, "filename", "")})
        stats[k] = {"index_name": k, "chunk_limit": 1500 if k != "T3000" else 3000,
                    "chunk_count": len(chunks), "min_chunk_tokens": int(toks.min()),
                    "median_chunk_tokens": float(np.median(toks)), "mean_chunk_tokens": float(toks.mean()),
                    "p90_chunk_tokens": float(np.percentile(toks, 90)), "max_chunk_tokens": int(toks.max()),
                    "number_of_table_chunks": table_count, "number_of_source_documents": 11,
                    "vector_cache": str(paths[k].relative_to(ROOT)),
                    "input_text_digest": text_digest(texts),
                    "cache_digest": paths[k].stem.rsplit("_", 1)[-1],
                    "cache_digest_matches": text_digest(texts) == paths[k].stem.rsplit("_", 1)[-1],
                    "samples": samples}
    write_manifest(stats, paths)
    write_stats(stats)
    qs = json.loads((CACHE / "gen500.json").read_text())
    totals = {}
    for k in ("T1500", "T3000", "R1500"):
        totals[k] = write_retrieval(
            k,
            [c.content for c in arms[k]] if k.startswith("T") else arms[k],
            load_vectors(paths[k]),
            qs,
        )
    write_fingerprint()
    print(json.dumps({"manifest": "results/benchmark_identity_v1/run_manifest.csv", "retrieval_totals": totals,
                      "stats": {k: {x: v[x] for x in ("chunk_count", "mean_chunk_tokens", "median_chunk_tokens", "p90_chunk_tokens", "max_chunk_tokens", "number_of_table_chunks")} for k, v in stats.items()}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
