#!/usr/bin/env python3
"""Analyze completed representation_v1 raw caches and write the thesis artifacts."""
from __future__ import annotations

import csv, json, math, random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "representation_v1"
MODELS = {
    "oss20b": ("openai/gpt-oss-20b", "CoreWeave"),
    "gemma12b": ("google/gemma-3-12b-it", "DeepInfra"),
    "llama31_8b": ("meta-llama/llama-3.1-8b-instruct", "DeepInfra"),
    "gemma4b": ("google/gemma-3-4b-it", "DeepInfra"),
}
ARMS = ("T1500_HTML", "T1500_KV", "T1500_VERB", "R1500_RECURSIVE")
REP_ARMS = ("T1500_HTML", "T1500_KV", "T1500_VERB")
QS = json.loads((ROOT / ".bench_cache" / "gen500.json").read_text())
ORDER = [q["qid"] for q in QS]
QMAP = {q["qid"]: q for q in QS}


def exact_mcnemar(b: int, c: int) -> float:
    n = b + c
    if not n:
        return 1.0
    p = 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / (2 ** n)
    return min(1.0, p)


def holm(pairs):
    out = {}
    ordered = sorted(pairs, key=lambda x: x[1])
    prev = 0.0
    m = len(ordered)
    for i, (key, p) in enumerate(ordered):
        adj = min(1.0, max(prev, (m - i) * p))
        out[key] = adj; prev = adj
    return out


def load_raw(model_key, arm):
    p = OUT / f"raw_{model_key}_{arm}.json"
    d = json.loads(p.read_text())
    byq = {}
    for v in d.values():
        byq[v["query_id"]] = v
    if len(byq) != 500:
        raise SystemExit(f"incomplete raw cache: {p} ({len(byq)}/500)")
    return byq


def bootstrap(values, seed, n=20000):
    rng = random.Random(seed); size = len(values); vals = []
    for _ in range(n):
        vals.append(sum(values[rng.randrange(size)] for _ in range(size)) / size)
    vals.sort()
    return vals[n // 40], vals[n - n // 40 - 1]


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)


def main():
    raw = {mk: {a: load_raw(mk, a) for a in ARMS} for mk in MODELS}
    # Per-query long table.
    by_rows=[]
    for mk,(model,_) in MODELS.items():
        for arm in ARMS:
            for qid in ORDER:
                v=raw[mk][arm][qid]; q=QMAP[qid]
                by_rows.append({"query_id":qid,"question_group":"price" if "expect_values" in q else "attribute","model_key":mk,"model_id":model,"arm":arm,"representation":arm.rsplit("_",1)[-1],"retrieved_chunk_ids":";".join(v.get("retrieved_chunk_ids",[])),"context_hash":v.get("context_hash",""),"context_tokens":v.get("context_tokens",""),"prompt_hash":v.get("prompt_hash",""),"provider_requested":v.get("provider_requested",""),"provider_actual":v.get("provider_actual",""),"raw_answer":v.get("raw_answer",""),"normalized_answer":v.get("normalized_answer",""),"is_correct":int(bool(v.get("is_correct"))),"finish_reason":v.get("finish_reason",""),"empty_output":int(bool(v.get("empty_output"))),"cut":int(bool(v.get("cut"))),"input_tokens":v.get("input_tokens",""),"output_tokens":v.get("output_tokens",""),"latency_ms":v.get("latency_ms",""),"retry_count":v.get("retry_count",""),"estimated_cost":v.get("estimated_cost","")})
    fields=list(by_rows[0]); write_csv(OUT/"representation_results_by_query.csv",by_rows,fields)

    summaries=[]
    for mk,(model,provider) in MODELS.items():
        for arm in ARMS:
            vals=list(raw[mk][arm].values()); price=[v for q,v in raw[mk][arm].items() if "expect_values" in QMAP[q]]; attr=[v for q,v in raw[mk][arm].items() if "expect_text" in QMAP[q]]
            num=lambda xs,k: sum(bool(x.get(k)) for x in xs)
            avg=lambda xs,k: round(sum(float(x[k]) for x in xs if x.get(k) is not None)/max(1,sum(x.get(k) is not None for x in xs)),2)
            summaries.append({"model_key":mk,"model_id":model,"provider":provider,"arm":arm,"em":num(vals,"is_correct"),"em_pct":round(100*num(vals,"is_correct")/500,2),"price_correct":num(price,"is_correct"),"price_pct":round(100*num(price,"is_correct")/252,2),"attribute_correct":num(attr,"is_correct"),"attribute_pct":round(100*num(attr,"is_correct")/248,2),"empty":num(vals,"empty_output"),"cut":num(vals,"cut"),"input_tokens_avg":avg(vals,"input_tokens"),"output_tokens_avg":avg(vals,"output_tokens"),"latency_ms_avg":avg(vals,"latency_ms"),"estimated_cost_total":round(sum(float(x.get("estimated_cost") or 0) for x in vals),8)})
    write_csv(OUT/"representation_summary.csv",summaries,list(summaries[0]))

    # McNemar within each model: 3 pairs x 3 scopes, then Holm within model.
    mrows=[]
    for mk in MODELS:
        rawp=[]
        for a,b in [("T1500_HTML","T1500_KV"),("T1500_HTML","T1500_VERB"),("T1500_KV","T1500_VERB")]:
            for scope in ("all","price","attribute"):
                ids=ORDER if scope=="all" else [i for i in ORDER if ("expect_values" in QMAP[i])==(scope=="price")]
                x=sum(raw[mk][a][i].get("is_correct",False) and not raw[mk][b][i].get("is_correct",False) for i in ids)
                y=sum(not raw[mk][a][i].get("is_correct",False) and raw[mk][b][i].get("is_correct",False) for i in ids)
                p=exact_mcnemar(x,y); key=(mk,a,b,scope); rawp.append((key,p)); mrows.append({"model_key":mk,"comparison":f"{a} vs {b}","scope":scope,"a_correct_b_wrong":x,"a_wrong_b_correct":y,"delta_b_minus_a":y-x,"p_raw":p,"p_holm":""})
        adj=holm(rawp)
        for row in mrows:
            key=(row["model_key"],row["comparison"].split(" vs ")[0],row["comparison"].split(" vs ")[1],row["scope"])
            if key in adj: row["p_holm"]=adj[key]
    write_csv(OUT/"representation_mcnemar.csv",mrows,list(mrows[0]))

    # Pipeline comparison: best T representation selected by EM, exploratory.
    prow=[]
    for mk in MODELS:
        scores={a:sum(raw[mk][a][i].get("is_correct",False) for i in ORDER) for a in REP_ARMS}; best=max(scores,key=scores.get); b="R1500_RECURSIVE"
        for scope in ("all","price","attribute"):
            ids=ORDER if scope=="all" else [i for i in ORDER if ("expect_values" in QMAP[i])==(scope=="price")]
            x=sum(raw[mk][best][i].get("is_correct",False) and not raw[mk][b][i].get("is_correct",False) for i in ids); y=sum(not raw[mk][best][i].get("is_correct",False) and raw[mk][b][i].get("is_correct",False) for i in ids)
            prow.append({"model_key":mk,"best_representation":best,"recursive":"R1500_RECURSIVE","scope":scope,"best_correct_recursive_wrong":x,"best_wrong_recursive_correct":y,"p_exact":exact_mcnemar(x,y),"exploratory":True})
    # Paired deltas and interactions.
    brows=[]; oss={}
    for mk in MODELS:
        for rep in ("T1500_KV","T1500_VERB"):
            for scope in ("all","price","attribute"):
                ids=ORDER if scope=="all" else [i for i in ORDER if ("expect_values" in QMAP[i])==(scope=="price")]
                vals=[int(raw[mk][rep][i].get("is_correct"))-int(raw[mk]["T1500_HTML"][i].get("is_correct")) for i in ids]
                lo,hi=bootstrap(vals,1000+len(brows)); delta=sum(vals)/len(vals)
                brows.append({"type":"delta","model_key":mk,"representation":rep,"scope":scope,"estimate_pp":round(100*delta,2),"ci95_low_pp":round(100*lo,2),"ci95_high_pp":round(100*hi,2),"p_value":""})
                if mk!="oss20b":
                    baseids=ids; inter=[(int(raw[mk][rep][i].get("is_correct"))-int(raw[mk]["T1500_HTML"][i].get("is_correct")))-(int(raw["oss20b"][rep][i].get("is_correct"))-int(raw["oss20b"]["T1500_HTML"][i].get("is_correct"))) for i in baseids]
                    ilo,ihi=bootstrap(inter,9000+len(brows)); est=sum(inter)/len(inter); rng=random.Random(19000+len(brows)); boots=[sum(inter[rng.randrange(len(inter))] for _ in inter)/len(inter) for _ in range(10000)]; p=sum(abs(x-est)>=abs(est) for x in boots)/len(boots)
                    brows.append({"type":"interaction_vs_oss","model_key":mk,"representation":rep,"scope":scope,"estimate_pp":round(100*est,2),"ci95_low_pp":round(100*ilo,2),"ci95_high_pp":round(100*ihi,2),"p_value":round(p,6)})
    write_csv(OUT/"representation_bootstrap_interactions.csv",brows,list(brows[0]))

    manifest={"experiment_version":"representation_v1","models":{k:{"model_id":v[0],"provider":v[1]} for k,v in MODELS.items()},"arms":list(ARMS),"query_count":500,"price_count":252,"attribute_count":248,"temperature":0,"max_tokens":2000,"top_k":5,"tools":[],"retrieval":"dense identity_v2 fixed top-5","cut_policy":"is_correct=0; included in denominator","raw_cache_count":len(by_rows),"representation_samples":"representation_samples.md","created_at":"2026-08-07T00:00:00Z"}
    (OUT/"representation_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2))

    lines=["# Representation benchmark report","","## Protocol","","16 combinations: 4 OpenRouter models × 4 arms × 500 queries. Retrieval is fixed dense identity_v2 top-5; only the generation context representation changes for T1500 HTML/KV/VERB. R1500_RECURSIVE is the exploratory pipeline baseline. Temperature=0, max_tokens=2000, no tools. CUT and empty output are scored 0 and remain in n=500.","","## Main results","","| Model | Arm | EM | Price | Attribute | Empty | CUT | Input avg | Output avg | Cost |","|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for s in summaries: lines.append(f"| {s['model_key']} | {s['arm']} | {s['em']}/500 ({s['em_pct']}%) | {s['price_correct']}/252 ({s['price_pct']}%) | {s['attribute_correct']}/248 ({s['attribute_pct']}%) | {s['empty']} | {s['cut']} | {s['input_tokens_avg']} | {s['output_tokens_avg']} | {s['estimated_cost_total']} |")
    lines += ["","## Statistical tests","","Full McNemar and Holm results are in `representation_mcnemar.csv`. Bootstrap deltas and model interactions are in `representation_bootstrap_interactions.csv`. Recursive comparisons are exploratory because recursive uses a different chunking pipeline.","","## Data integrity","","HTML/KV/VERB use the same query IDs, dense retrieved chunk IDs, ranks and data fingerprints. See `representation_samples.md` and `representation_manifest.json`.","","## Limitations","","Provider is pinned within each model but differs across model families: GPT-OSS uses CoreWeave; Gemma and Llama use DeepInfra. Results therefore support within-model representation comparisons and exploratory cross-model interactions, not a provider-controlled model ranking."]
    (OUT/"representation_benchmark_report.md").write_text("\n".join(lines),encoding="utf-8")


if __name__ == "__main__": main()
