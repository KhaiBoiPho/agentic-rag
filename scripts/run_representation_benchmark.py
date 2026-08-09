#!/usr/bin/env python3
"""Run the fixed-retrieval table representation benchmark."""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import os
import random
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts.eval_chunking_strategy import chunks_recursive
# Importing eval_tier4_nim keeps the scoring and system prompt identical to the
# already validated generation benchmark.
from scripts.eval_tier4_nim import SYS, grade
from scripts.eval_final_500 import table_chunks_at_cap

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "representation_v1"
IDENTITY = ROOT / "results" / "benchmark_identity_v1"
TOPK = 5
MODELS = {
    "oss20b": ("openai/gpt-oss-20b", "coreweave"),
    "gemma12b": ("google/gemma-3-12b-it", "deepinfra"),
    "llama31_8b": ("meta-llama/llama-3.1-8b-instruct", "deepinfra"),
    "gemma4b": ("google/gemma-3-4b-it", "deepinfra"),
}
ARMS = ("T1500_HTML", "T1500_KV", "T1500_VERB", "R1500_RECURSIVE")
ARM_TO_BASE = {a: ("T1500" if a.startswith("T1500") else "R1500") for a in ARMS}

_ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
_CELL = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.S)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def clean(s: str) -> str:
    return _WS.sub(" ", _TAG.sub("", s)).strip()


def parse_table(html: str):
    rows = [[clean(c) or "<EMPTY>" for c in _CELL.findall(r)] for r in _ROW.findall(html)]
    rows = [r for r in rows if r]
    return (rows[0], rows[1:]) if rows else (None, [])


def kv_table(html: str) -> str:
    hdr, body = parse_table(html)
    if not hdr or not body:
        return clean(html)
    out = []
    for row in body:
        vals = row + ["<EMPTY>"] * max(0, len(hdr) - len(row))
        out.append(" | ".join(f"{hdr[i]}: {vals[i]}" for i in range(len(hdr))))
    return "\n".join(out)


def verb_table(html: str) -> str:
    hdr, body = parse_table(html)
    if not hdr or not body:
        return clean(html)
    out = []
    for row in body:
        vals = row + ["<EMPTY>"] * max(0, len(hdr) - len(row))
        parts = [f"{hdr[i]} là {vals[i] if vals[i] != '<EMPTY>' else 'không có giá trị'}" for i in range(len(hdr))]
        out.append("Trong hàng này, " + "; ".join(parts) + ".")
    return "\n".join(out)


def rewrite(text: str, mode: str) -> str:
    if mode == "HTML":
        return text
    fn = kv_table if mode == "KV" else verb_table
    return re.sub(r"<table.*?</table>", lambda m: fn(m.group(0)), text, flags=re.S)


def atomic_write(path: Path, data: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(data)
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def token_count(text: str) -> int:
    try:
        import tiktoken
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return len(text.split())


def load_inputs():
    manifest = {r["config_id"]: r for r in csv.DictReader((IDENTITY / "run_manifest.csv").open())}
    stats = json.loads((IDENTITY / "run_identity_stats.json").read_text())
    checks = [
        manifest.get("T1500", {}).get("chunk_count") == "2252",
        manifest.get("R1500", {}).get("chunk_count") == "790",
        stats["T1500"]["cache_digest_matches"],
        stats["R1500"]["cache_digest_matches"],
    ]
    if not all(checks):
        raise SystemExit("identity_v2 fingerprint mismatch; benchmark stopped")
    qs = json.loads((ROOT / ".bench_cache" / "gen500.json").read_text())
    if len(qs) != 500 or len({q["qid"] for q in qs}) != 500:
        raise SystemExit("gen500 query_id mismatch")
    if sum("expect_values" in q for q in qs) != 252 or sum("expect_text" in q for q in qs) != 248:
        raise SystemExit("question group count mismatch")
    retrieval = {}
    for base, fn, expected in [("T1500", "retrieval_T1500_dense.csv", 343), ("R1500", "retrieval_R1500_dense.csv", 354)]:
        rows = list(csv.DictReader((IDENTITY / fn).open()))
        if len(rows) != 500 or sum(int(r["hit_at_5"]) for r in rows) != expected:
            raise SystemExit(f"retrieval fingerprint mismatch: {base}")
        retrieval[base] = {r["query_id"]: r for r in rows}
    return qs, retrieval


def build_contexts(qs, retrieval):
    chunks = {"T1500": table_chunks_at_cap(1500), "R1500": chunks_recursive(1500)}
    if len(chunks["T1500"]) != 2252 or len(chunks["R1500"]) != 790:
        raise SystemExit("rebuilt chunk count mismatch")
    out = {}
    for q in qs:
        qid = q["qid"]
        for arm in ARMS:
            base = ARM_TO_BASE[arm]
            ids = retrieval[base][qid]["retrieved_chunk_ids"].split(";")
            originals = [chunks[base][int(x.rsplit("-", 1)[1])] for x in ids]
            mode = "HTML" if arm.endswith("HTML") else "KV" if arm.endswith("KV") else "VERB" if arm.endswith("VERB") else "HTML"
            rendered = [rewrite(x, mode) for x in originals]
            fp = hashlib.sha256(json.dumps({"ids": ids, "chunks": originals}, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
            out[(qid, arm)] = {"ids": ids, "originals": originals, "rendered": rendered, "data_fingerprint": fp}
    return out


def write_samples(qs, contexts):
    price = [q for q in qs if "expect_values" in q][:5]
    attr = [q for q in qs if "expect_text" in q][:5]
    lines = ["# Representation samples", "", "Các arm T1500 dùng cùng retrieved_chunk_ids và data fingerprint.", ""]
    for q in price + attr:
        lines += [f"## {q['qid']} — {q['question']}", ""]
        for arm in ("T1500_HTML", "T1500_KV", "T1500_VERB"):
            c = contexts[(q["qid"], arm)]
            lines += [f"### {arm}", f"- chunk_ids: `{', '.join(c['ids'])}`", f"- data_fingerprint: `{c['data_fingerprint']}`", f"- context_tokens: {token_count(chr(10).join(c['rendered']))}", "```text", "\n\n---\n\n".join(c["rendered"]), "```", ""]
    atomic_write(OUT / "representation_samples.md", "\n".join(lines))


async def request(client, sem, model, provider, prompt):
    key = os.environ["OPENROUTER_API_KEY"]
    base = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    for attempt in range(6):
        started = time.perf_counter()
        try:
            async with sem:
                r = await client.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {key}"}, json={
                    "model": model, "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": prompt}],
                    "temperature": 0, "max_tokens": 2000,
                    "provider": {"order": [provider], "allow_fallbacks": False, "require_parameters": True},
                })
            latency = (time.perf_counter() - started) * 1000
            if r.status_code == 200:
                body = r.json(); choice = body["choices"][0]; msg = choice.get("message", {})
                text = (msg.get("content") or "").strip()
                actual = body.get("provider")
                if actual != ("CoreWeave" if provider == "coreweave" else "DeepInfra"):
                    return {"error": f"provider_mismatch:{actual}", "latency_ms": latency, "retry_count": attempt}
                cut = choice.get("finish_reason") == "length" or not text
                return {"raw_answer": text, "provider_actual": actual, "finish_reason": choice.get("finish_reason"), "empty_output": not bool(text), "cut": cut, "input_tokens": (body.get("usage") or {}).get("prompt_tokens"), "output_tokens": (body.get("usage") or {}).get("completion_tokens"), "latency_ms": latency, "retry_count": attempt, "estimated_cost": body.get("usage", {}).get("cost")}
            if r.status_code not in (429, 500, 502, 503, 504):
                return {"error": f"http_{r.status_code}", "latency_ms": latency, "retry_count": attempt}
        except Exception as exc:
            error = type(exc).__name__
        await asyncio.sleep(min(2 ** attempt, 30) + random.random())
    return {"error": "retry_exhausted", "latency_ms": 0, "retry_count": 6}


async def run_arm(client, sem, model_key, model, provider, arm, qs, contexts, smoke=False):
    path = OUT / (f"smoke_{model_key}_{arm}.json" if smoke else f"raw_{model_key}_{arm}.json")
    cache = json.loads(path.read_text()) if path.exists() else {}
    selected = qs[:3] if smoke else qs
    async def one(q):
        qid = q["qid"]; c = contexts[(qid, arm)]
        context_text = "\n\n---\n\n".join(c["rendered"])
        prompt = f"NGỮ CẢNH:\n{context_text}\n\nCÂU HỎI: {q['question']}\nTRẢ LỜI:"
        prompt_hash = hashlib.sha256((SYS + "\n" + prompt).encode()).hexdigest()
        key = f"{model}|{provider}|{arm}|{qid}|{c['data_fingerprint']}|{prompt_hash}|0|2000"
        if key in cache and not cache[key].get("error"):
            return None
        result = await request(client, sem, model, provider, prompt)
        ans = result.get("raw_answer", "")
        result.update({"query_id": qid, "question_group": "price" if "expect_values" in q else "attribute", "question": q["question"], "model_id": model, "provider_requested": provider, "arm": arm, "representation": arm.rsplit("_", 1)[-1], "retrieved_chunk_ids": c["ids"], "retrieval_ranks": list(range(1, 6)), "source_document_ids": c["ids"], "context_hash": hashlib.sha256(context_text.encode()).hexdigest(), "data_fingerprint": c["data_fingerprint"], "context_tokens": token_count(context_text), "prompt_hash": prompt_hash, "gold_values": q.get("expect_values", []), "gold_text": q.get("expect_text", []), "normalized_answer": ans, "is_correct": bool(ans) and not result.get("cut") and grade(q, ans), "created_at": datetime.now(timezone.utc).isoformat()})
        return key, result

    todo = [q for q in selected if not (next((v for k, v in cache.items() if k.split("|")[2:4] == [arm, q["qid"]]), {}).get("error") is False)]
    # Resume by checking the exact key inside one() and issue up to three
    # requests concurrently; checkpoint after every batch.
    for i in range(0, len(todo), 8):
        results = await asyncio.gather(*(one(q) for q in todo[i : i + 8]))
        for item in results:
            if item:
                key, result = item
                cache[key] = result
        atomic_write(path, json.dumps(cache, ensure_ascii=False, indent=2))
    return path


async def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--smoke", action="store_true"); ap.add_argument("--models", default=",")
    a = ap.parse_args(); OUT.mkdir(parents=True, exist_ok=True)
    qs, retrieval = load_inputs(); contexts = build_contexts(qs, retrieval); write_samples(qs, contexts)
    print("fingerprint OK; representation_samples.md written", flush=True)
    import httpx
    selected = list(MODELS) if a.models == "," else [x for x in a.models.split(",") if x in MODELS]
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient(timeout=180) as client:
        for mk in selected:
            model, provider = MODELS[mk]
            for arm in ARMS:
                await run_arm(client, sem, mk, model, provider, arm, qs, contexts, a.smoke)
                print(f"done {mk} {arm} {'smoke' if a.smoke else 'full'}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
