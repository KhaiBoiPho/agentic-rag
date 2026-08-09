# Retrieval representation benchmark report

## Identity

T1500=2,252 chunks (mean 831 tokens), R1500=790 chunks (mean 1,102 tokens). Query set: 500 unique IDs, 252 price and 248 attribute. Existing dense/hybrid Recall@5 was verified as 343, 354, 410 and 403 respectively before writing results.

## Existing retrieval

| Index | Scope | R@1 | R@3 | R@5 | R@10 | MRR | Median rank | No-hit@10 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| T1500_DENSE | all | 207/500 | 307/500 | 343/500 | 394/500 | 0.534467 | 1.0 | 106 |
| T1500_DENSE | price | 108/252 | 166/252 | 189/252 | 210/252 | 0.566134 | 1.0 | 42 |
| T1500_DENSE | attribute | 99/248 | 141/248 | 154/248 | 184/248 | 0.502288 | 1.0 | 64 |
| R1500_DENSE | all | 228/500 | 327/500 | 354/500 | 389/500 | 0.565908 | 1.0 | 111 |
| R1500_DENSE | price | 113/252 | 179/252 | 196/252 | 214/252 | 0.588654 | 1.0 | 38 |
| R1500_DENSE | attribute | 115/248 | 148/248 | 158/248 | 175/248 | 0.542795 | 1.0 | 73 |
| T1500_HYBRID | all | 272/500 | 373/500 | 410/500 | 435/500 | 0.65969 | 1.0 | 65 |
| T1500_HYBRID | price | 156/252 | 219/252 | 238/252 | 243/252 | 0.757209 | 1.0 | 9 |
| T1500_HYBRID | attribute | 116/248 | 154/248 | 172/248 | 192/248 | 0.560599 | 1.0 | 56 |
| R1500_HYBRID | all | 294/500 | 381/500 | 403/500 | 438/500 | 0.684374 | 1.0 | 62 |
| R1500_HYBRID | price | 171/252 | 219/252 | 228/252 | 241/252 | 0.779781 | 1.0 | 11 |
| R1500_HYBRID | attribute | 123/248 | 162/248 | 175/248 | 197/248 | 0.587428 | 1.0 | 51 |

## Representation dense retrieval

Dense Recall@5 winner: T1500_HTML (HTML=343, KV=306, VERB=218). Full metrics, McNemar, Holm and bootstrap are in the CSV outputs.

## Hybrid interaction

The interaction CSV reports paired-bootstrap differences in hybrid gain; the bootstrap uses seed 20260807 and 100,000 resamples.

## Proxy limitation

These are proxy evidence hits based on expect_values/expect_text at chunk level, not gold row/cell recall. Generation was not called by this experiment.

## Generation analysis

Generation McNemar is copied from the completed per-query raw-cache analysis in representation_v1 and is written separately as generation_representation_mcnemar.csv.