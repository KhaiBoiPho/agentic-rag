#!/usr/bin/env python3
"""Retrieval-only benchmark for top-k and embedding representation variants."""
from __future__ import annotations

import asyncio, csv, hashlib, json, math, os, random, time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from scripts.bench_retrieval import BM25Index, rrf_fuse
from scripts.eval_chunking_strategy import chunks_recursive
from scripts.eval_final_500 import hit, table_chunks_at_cap
from scripts.run_representation_benchmark import kv_table, verb_table, rewrite

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "retrieval_representation_v1"
IDENTITY = ROOT / "results" / "benchmark_identity_v1"
CACHE = ROOT / ".bench_cache"
EMB = "openai/text-embedding-3-small"
QFILE = CACHE / "gen500.json"
ARMS = ("T1500_HTML", "T1500_KV", "T1500_VERB", "R1500_RECURSIVE")


def digest(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def text_digest(xs):
    return hashlib.sha256(json.dumps(xs, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def load_vec(pattern):
    paths = [p for p in CACHE.glob(pattern) if not p.name.endswith(".manifest.json") and not p.name.endswith(".partial")]
    if not paths:
        raise SystemExit(f"missing vector cache: {pattern}")
    return json.loads(max(paths, key=lambda p: p.stat().st_mtime).read_text()), max(paths, key=lambda p: p.stat().st_mtime)


def validate_identity(qs):
    manifest = {r["config_id"]: r for r in csv.DictReader((IDENTITY / "run_manifest.csv").open())}
    stats = json.loads((IDENTITY / "run_identity_stats.json").read_text())
    if manifest["T1500"]["chunk_count"] != "2252" or manifest["R1500"]["chunk_count"] != "790":
        raise SystemExit("identity mismatch: chunk count")
    if not stats["T1500"]["cache_digest_matches"] or not stats["R1500"]["cache_digest_matches"]:
        raise SystemExit("identity mismatch: vector cache digest")
    if len(qs) != 500 or len({q["qid"] for q in qs}) != 500:
        raise SystemExit("query identity mismatch")
    if sum("expect_values" in q for q in qs) != 252 or sum("expect_text" in q for q in qs) != 248:
        raise SystemExit("question group identity mismatch")
    for fn, expected in [("retrieval_T1500_dense.csv", 343), ("retrieval_R1500_dense.csv", 354)]:
        rows = list(csv.DictReader((IDENTITY / fn).open()))
        if len(rows) != 500 or sum(int(r["hit_at_5"]) for r in rows) != expected:
            raise SystemExit(f"locked retrieval mismatch: {fn}")
    return stats


def metric_rows(records, qs):
    by = {q["qid"]: q for q in qs}
    groups = {"all": list(records), "price": [r for r in records if "expect_values" in by[r["query_id"]]], "attribute": [r for r in records if "expect_text" in by[r["query_id"]]]}
    out=[]
    for scope, rs in groups.items():
        n=len(rs); first=[r["first_hit_rank"] for r in rs if r["first_hit_rank"]]
        out.append({"scope":scope,"n":n,"recall_at_1":sum(r["hit_at_1"] for r in rs),"recall_at_3":sum(r["hit_at_3"] for r in rs),"recall_at_5":sum(r["hit_at_5"] for r in rs),"recall_at_10":sum(r["hit_at_10"] for r in rs),"mrr":round(sum((1/r["first_hit_rank"] if r["first_hit_rank"] else 0) for r in rs)/n,6),"median_first_hit_rank":(float(np.median(first)) if first else None),"no_hit_at_10":sum(not r["first_hit_rank"] for r in rs)})
    return out


def retrieve(qs, chunks, vecs, qvecs, index_name, representation, hybrid=False):
    V=np.asarray(vecs,dtype=np.float32); V/=np.linalg.norm(V,axis=1,keepdims=True)+1e-9
    Q=np.asarray(qvecs,dtype=np.float32); Q/=np.linalg.norm(Q,axis=1,keepdims=True)+1e-9
    bm=BM25Index.build(chunks) if hybrid else None
    folded=["" for _ in chunks]; money=[set() for _ in chunks]
    from scripts.eval_chunking_strategy import fold, digits, _MONEY_RE
    folded=[fold(x) for x in chunks]; money=[{digits(m) for m in _MONEY_RE.findall(f)} for f in folded]
    idx_digest=text_digest(chunks)
    records=[]
    for q,v in zip(qs,Q):
        dense=list(np.argsort(-(V@v))[:50])
        ranks=dense if not hybrid else rrf_fuse([dense,bm.top(q["question"],50)],10)
        if not hybrid: ranks=list(np.argsort(-(V@v))[:10])
        scores=[float(V[i]@v) for i in ranks]
        hitr=[rank+1 for rank,i in enumerate(ranks) if hit(q,i,folded,money)]
        first=hitr[0] if hitr else None
        records.append({"query_id":q["qid"],"question_group":"price" if "expect_values" in q else "attribute","index_name":index_name,"representation":representation,"retrieved_chunk_ids_top10":[f"{index_name}-{i:04d}" for i in ranks],"scores_top10":[round(s,8) for s in scores],"first_hit_rank":first,"hit_at_1":int(first is not None and first<=1),"hit_at_3":int(first is not None and first<=3),"hit_at_5":int(first is not None and first<=5),"hit_at_10":int(first is not None and first<=10),"question_digest":digest(q),"index_digest":idx_digest,"created_at":datetime.now(timezone.utc).isoformat()})
    return records


async def embed_rep(rep, chunks):
    from scripts.bench_agentic import embed_texts
    import scripts.bench_agentic as ba
    d=OUT / "embedding_cache" / rep.lower(); d.mkdir(parents=True,exist_ok=True)
    old=ba.CACHE_DIR; ba.CACHE_DIR=str(d)
    try:
        return await embed_texts(EMB,chunks,f"retrieval_repr_v1_{rep.lower()}",{"config_id":f"T1500_EMBED_{rep}"})
    finally: ba.CACHE_DIR=old


def write_csv(path, rows):
    if not rows:return
    fields=list(rows[0]);
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)


def exact(b,c):
    n=b+c
    return 1.0 if not n else min(1.0,2*sum(math.comb(n,i) for i in range(min(b,c)+1))/2**n)


def holm(pairs):
    out={};prev=0
    for i,(k,p) in enumerate(sorted(pairs,key=lambda x:x[1])):
        out[k]=min(1,max(prev,(len(pairs)-i)*p));prev=out[k]
    return out


def bootstrap(vals, seed, n=100000):
    # Vectorized in batches: identical resampling definition, but practical
    # for the required 100,000 paired resamples.
    rng=np.random.default_rng(seed); a=np.asarray(vals,dtype=np.float64); L=len(a); z=[]
    for start in range(0,n,1000):
        count=min(1000,n-start)
        z.extend(a[rng.integers(0,L,size=(count,L))].mean(axis=1).tolist())
    z.sort();return z[n//40],z[n-n//40-1]


def interaction_rows(allrecs, qs, pairs):
    byid={name:{r["query_id"]:r for r in recs} for name,recs in allrecs.items()}
    out=[]
    for label,ha,da,hb,db in pairs:
        vals=[]
        for q in qs:
            i=q["qid"]
            vals.append((byid[ha][i]["hit_at_5"]-byid[da][i]["hit_at_5"])-(byid[hb][i]["hit_at_5"]-byid[db][i]["hit_at_5"]))
        lo,hi=bootstrap(vals,20260807+len(out))
        out.append({"comparison":label,"estimate":round(sum(vals)/len(vals),6),"ci95_low":round(lo,6),"ci95_high":round(hi,6),"bootstrap_n":100000,"seed":20260807,"n":len(vals)})
    return out


def analyze_stats(allrecs, qs):
    order=[q["qid"] for q in qs]; qmap={q["qid"]:q for q in qs}
    byid={name:{r["query_id"]:r for r in recs} for name,recs in allrecs.items()}
    # Per-query and aggregate metrics.
    qrows=[]; summaries=[]
    for name,recs in allrecs.items():
        for r in recs:qrows.append(r)
        summaries += [{"index_name":name,**m} for m in metric_rows(recs,qs)]
    write_csv(OUT/"representation_top10_by_query.csv",qrows)
    write_csv(OUT/"representation_recall_at_k.csv",summaries)
    write_csv(OUT/"representation_recall_by_group.csv",[r for r in summaries if r["scope"]!="all"])
    # McNemar R@5 among T representations.
    m=[]
    for scope in ("all","price","attribute"):
        ids=order if scope=="all" else [i for i in order if ("expect_values" in qmap[i])==(scope=="price")]
        raw=[]
        for a,b in [("T1500_HTML","T1500_KV"),("T1500_HTML","T1500_VERB"),("T1500_KV","T1500_VERB")]:
            x=sum(byid[a][i]["hit_at_5"] and not byid[b][i]["hit_at_5"] for i in ids);y=sum(not byid[a][i]["hit_at_5"] and byid[b][i]["hit_at_5"] for i in ids);p=exact(x,y);key=(scope,a,b);raw.append((key,p));m.append({"scope":scope,"comparison":f"{a} vs {b}","a_hit_b_miss":x,"a_miss_b_hit":y,"difference":y-x,"p_raw":p,"p_holm":""})
        adj=holm(raw)
        for row in m:
            k=(row["scope"],row["comparison"].split(" vs ")[0],row["comparison"].split(" vs ")[1]);
            if k in adj:row["p_holm"]=adj[k]
    write_csv(OUT/"representation_mcnemar_r5.csv",m)
    # Retrieval bootstrap: R@5 and MRR for three pairs and scopes.
    b=[]
    for scope in ("all","price","attribute"):
        ids=order if scope=="all" else [i for i in order if ("expect_values" in qmap[i])==(scope=="price")]
        for a,c in [("T1500_HTML","T1500_KV"),("T1500_HTML","T1500_VERB"),("T1500_KV","T1500_VERB")]:
            for metric in ("r5","mrr"):
                vals=[]
                for i in ids:
                    av=byid[a][i]["hit_at_5"] if metric=="r5" else (1/byid[a][i]["first_hit_rank"] if byid[a][i]["first_hit_rank"] else 0)
                    cv=byid[c][i]["hit_at_5"] if metric=="r5" else (1/byid[c][i]["first_hit_rank"] if byid[c][i]["first_hit_rank"] else 0)
                    vals.append(cv-av)
                lo,hi=bootstrap(vals,20260807+len(b));b.append({"scope":scope,"comparison":f"{a} vs {c}","metric":metric,"difference":round(sum(vals)/len(vals),6),"ci95_low":round(lo,6),"ci95_high":round(hi,6),"bootstrap_n":100000,"seed":20260807})
    write_csv(OUT/"representation_bootstrap.csv",b)
    return summaries


async def main():
    OUT.mkdir(parents=True,exist_ok=True)
    qs=json.loads(QFILE.read_text()); stats=validate_identity(qs); order=[q["qid"] for q in qs]
    qvec,qpath=load_vec("emb_openai_text-embedding-3-small_identity_v2_q500_500_*.json")
    chunks={"T1500":table_chunks_at_cap(1500),"R1500":chunks_recursive(1500)}
    if len(chunks["T1500"])!=2252 or len(chunks["R1500"])!=790: raise SystemExit("rebuilt chunk count mismatch")
    vecT,_=load_vec("emb_openai_text-embedding-3-small_identity_v2_f500_T1500_2252_*.json");vecR,_=load_vec("emb_openai_text-embedding-3-small_identity_v2_f500_R1500_790_*.json")
    allrecs={"T1500_DENSE":retrieve(qs,chunks["T1500"],vecT,qvec,"T1500","DENSE"),"R1500_DENSE":retrieve(qs,chunks["R1500"],vecR,qvec,"R1500","DENSE")}
    bmT=BM25Index.build(chunks["T1500"]);bmR=BM25Index.build(chunks["R1500"])
    allrecs["T1500_HYBRID"]=retrieve(qs,chunks["T1500"],vecT,qvec,"T1500","DENSE_BM25_RRF",True)
    allrecs["R1500_HYBRID"]=retrieve(qs,chunks["R1500"],vecR,qvec,"R1500","DENSE_BM25_RRF",True)
    locked={k:sum(r["hit_at_5"] for r in v) for k,v in allrecs.items()}; expected={"T1500_DENSE":343,"R1500_DENSE":354,"T1500_HYBRID":410,"R1500_HYBRID":403}
    if locked!=expected: raise SystemExit(f"locked Recall@5 mismatch: {locked} != {expected}")
    # Existing retrieval artifacts.
    existing=[r for name in ("T1500_DENSE","R1500_DENSE","T1500_HYBRID","R1500_HYBRID") for r in allrecs[name]]
    write_csv(OUT/"existing_retrieval_top10_by_query.csv",existing)
    write_csv(OUT/"existing_retrieval_recall_at_k.csv",[{"index_name":name,**m} for name in allrecs for m in metric_rows(allrecs[name],qs)])
    write_csv(OUT/"existing_retrieval_recall_by_group.csv",[{"index_name":name,**m} for name in allrecs for m in metric_rows(allrecs[name],qs) if m["scope"]!="all"])
    # Three new embedding representations.
    rep_chunks={"HTML":chunks["T1500"],"KV":[rewrite(x,"KV") for x in chunks["T1500"]],"VERB":[rewrite(x,"VERB") for x in chunks["T1500"]]}
    canonical=[hashlib.sha256(x.encode()).hexdigest() for x in chunks["T1500"]]
    if len(canonical) != 2252: raise SystemExit("canonical fingerprint entry count mismatch")
    rep_vec={}
    for rep,chs in rep_chunks.items():
        if [hashlib.sha256(x.encode()).hexdigest() for x in chunks["T1500"]]!=canonical: raise SystemExit("representation fingerprint mismatch")
        rep_vec[rep]=await embed_rep(rep,chs)
    for rep,chs in rep_chunks.items(): allrecs[f"T1500_{rep}"]=retrieve(qs,chs,rep_vec[rep],qvec,"T1500",rep)
    analyze_stats({k:allrecs[k] for k in ("T1500_HTML","T1500_KV","T1500_VERB")},qs)
    # Additional hybrid: HTML, dense winner, and recursive baseline. HTML is
    # always included; winner is selected by R@5 then MRR.
    scores={r:sum(x["hit_at_5"] for x in allrecs[f"T1500_{r}"]) for r in ("HTML","KV","VERB")}
    winner=max(("HTML","KV","VERB"),key=lambda r:(scores[r],sum((1/x["first_hit_rank"] if x["first_hit_rank"] else 0) for x in allrecs[f"T1500_{r}"])))
    hybrid_names={"T1500_HTML","R1500_RECURSIVE",f"T1500_{winner}"}
    for name in list(hybrid_names):
        if name=="T1500_HTML": allrecs["T1500_HTML_HYBRID"]=retrieve(qs,rep_chunks["HTML"],rep_vec["HTML"],qvec,"T1500","HTML_DENSE_BM25_RRF",True)
        elif name==f"T1500_{winner}": allrecs[f"T1500_{winner}_HYBRID"]=retrieve(qs,rep_chunks[winner],rep_vec[winner],qvec,"T1500",f"{winner}_DENSE_BM25_RRF",True)
        else: allrecs["R1500_RECURSIVE_HYBRID"]=retrieve(qs,chunks["R1500"],vecR,qvec,"R1500","RECURSIVE_DENSE_BM25_RRF",True)
    write_csv(OUT/"representation_hybrid_summary.csv",[{"index_name":n,**m} for n in allrecs if n.endswith("HYBRID") for m in metric_rows(allrecs[n],qs)])
    # Paired interaction: the difference in hybrid gain between two arms.
    interaction_pairs=[
        ("T1500_HTML_HYBRID gain vs R1500_RECURSIVE_HYBRID gain",
         "T1500_HTML_HYBRID","T1500_HTML","R1500_RECURSIVE_HYBRID","R1500_DENSE"),
    ]
    if winner != "HTML":
        interaction_pairs.append((f"T1500_{winner}_HYBRID gain vs T1500_HTML_HYBRID gain",
                                  f"T1500_{winner}_HYBRID",f"T1500_{winner}",
                                  "T1500_HTML_HYBRID","T1500_HTML"))
    write_csv(OUT/"representation_hybrid_interaction.csv",interaction_rows(allrecs,qs,interaction_pairs))
    # This experiment does not call generation; copy the already completed,
    # per-query generation comparison produced by representation_v1.
    gen_src=ROOT/"results"/"representation_v1"/"representation_mcnemar.csv"
    if gen_src.exists(): (OUT/"generation_representation_mcnemar.csv").write_bytes(gen_src.read_bytes())
    # Index manifests.
    manifests={}
    for name,chs in [("T1500_DENSE",chunks["T1500"]),("R1500_DENSE",chunks["R1500"]),("T1500_EMBED_HTML",rep_chunks["HTML"]),("T1500_EMBED_KV",rep_chunks["KV"]),("T1500_EMBED_VERB",rep_chunks["VERB"])]:
        manifests[name]={"experiment_version":"retrieval_repr_v1","index_name":name,"representation":name.split("_")[-1],"chunk_count":len(chs),"chunk_digest":text_digest(chs),"canonical_fingerprint_digest":text_digest(canonical if name.startswith("T1500_EMBED") else [hashlib.sha256(x.encode()).hexdigest() for x in chs]),"question_digest":digest(qs),"embedding_model":EMB,"retrieval_type":"dense cosine top10","retrieval_parameters":{"top_k":10,"metric":"cosine"},"created_at":datetime.now(timezone.utc).isoformat()}
    (OUT/"index_manifests.json").write_text(json.dumps(manifests,ensure_ascii=False,indent=2))
    # Compact report.
    lines=["# Retrieval representation benchmark report","","## Identity","","T1500=2,252 chunks (mean 831 tokens), R1500=790 chunks (mean 1,102 tokens). Query set: 500 unique IDs, 252 price and 248 attribute. Existing dense/hybrid Recall@5 was verified as 343, 354, 410 and 403 respectively before writing results.","","## Existing retrieval","","| Index | Scope | R@1 | R@3 | R@5 | R@10 | MRR | Median rank | No-hit@10 |","|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name in ("T1500_DENSE","R1500_DENSE","T1500_HYBRID","R1500_HYBRID"):
        for m in metric_rows(allrecs[name],qs):lines.append(f"| {name} | {m['scope']} | {m['recall_at_1']}/{m['n']} | {m['recall_at_3']}/{m['n']} | {m['recall_at_5']}/{m['n']} | {m['recall_at_10']}/{m['n']} | {m['mrr']} | {m['median_first_hit_rank']} | {m['no_hit_at_10']} |")
    lines += ["","## Representation dense retrieval","",f"Dense Recall@5 winner: T1500_{winner} (HTML={scores['HTML']}, KV={scores['KV']}, VERB={scores['VERB']}). Full metrics, McNemar, Holm and bootstrap are in the CSV outputs.","","## Hybrid interaction","", "The interaction CSV reports paired-bootstrap differences in hybrid gain; the bootstrap uses seed 20260807 and 100,000 resamples.","","## Proxy limitation","","These are proxy evidence hits based on expect_values/expect_text at chunk level, not gold row/cell recall. Generation was not called by this experiment.","","## Generation analysis","","Generation McNemar is copied from the completed per-query raw-cache analysis in representation_v1 and is written separately as generation_representation_mcnemar.csv."]
    (OUT/"retrieval_representation_report.md").write_text("\n".join(lines),encoding="utf-8")


if __name__ == "__main__": asyncio.run(main())
