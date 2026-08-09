# Representation benchmark report

## Protocol

16 combinations: 4 OpenRouter models × 4 arms × 500 queries. Retrieval is fixed dense identity_v2 top-5; only the generation context representation changes for T1500 HTML/KV/VERB. R1500_RECURSIVE is the exploratory pipeline baseline. Temperature=0, max_tokens=2000, no tools. CUT and empty output are scored 0 and remain in n=500.

## Main results

| Model | Arm | EM | Price | Attribute | Empty | CUT | Input avg | Output avg | Cost |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| oss20b | T1500_HTML | 240/500 (48.0%) | 156/252 (61.9%) | 84/248 (33.87%) | 15 | 15 | 5065.23 | 374.24 | 0.10030424 |
| oss20b | T1500_KV | 243/500 (48.6%) | 149/252 (59.13%) | 94/248 (37.9%) | 21 | 21 | 7818.74 | 416.77 | 0.14437099 |
| oss20b | T1500_VERB | 231/500 (46.2%) | 144/252 (57.14%) | 87/248 (35.08%) | 38 | 38 | 8220.23 | 504.28 | 0.15608197 |
| oss20b | R1500_RECURSIVE | 214/500 (42.8%) | 150/252 (59.52%) | 64/248 (25.81%) | 33 | 33 | 4790.12 | 470.48 | 0.10243307 |
| gemma12b | T1500_HTML | 293/500 (58.6%) | 159/252 (63.1%) | 134/248 (54.03%) | 0 | 0 | 4136.46 | 9.36 | 0.1041133 |
| gemma12b | T1500_KV | 285/500 (57.0%) | 153/252 (60.71%) | 132/248 (53.23%) | 0 | 0 | 8035.52 | 9.59 | 0.20160685 |
| gemma12b | T1500_VERB | 288/500 (57.6%) | 157/252 (62.3%) | 131/248 (52.82%) | 0 | 0 | 8480.48 | 9.59 | 0.212731 |
| gemma12b | R1500_RECURSIVE | 251/500 (50.2%) | 158/252 (62.7%) | 93/248 (37.5%) | 0 | 0 | 5784.65 | 9.39 | 0.1453206 |
| llama31_8b | T1500_HTML | 210/500 (42.0%) | 91/252 (36.11%) | 119/248 (47.98%) | 0 | 0 | 4930.42 | 7.82 | 0.04946056 |
| llama31_8b | T1500_KV | 231/500 (46.2%) | 110/252 (43.65%) | 121/248 (48.79%) | 0 | 0 | 7784.32 | 8.94 | 0.0780219 |
| llama31_8b | T1500_VERB | 226/500 (45.2%) | 107/252 (42.46%) | 119/248 (47.98%) | 0 | 1 | 8185.78 | 13.07 | 0.08211924 |
| llama31_8b | R1500_RECURSIVE | 204/500 (40.8%) | 112/252 (44.44%) | 92/248 (37.1%) | 0 | 0 | 4657.07 | 8.66 | 0.04674386 |
| gemma4b | T1500_HTML | 235/500 (47.0%) | 119/252 (47.22%) | 116/248 (46.77%) | 0 | 0 | 4136.46 | 9.8 | 0.1039018 |
| gemma4b | T1500_KV | 174/500 (34.8%) | 78/252 (30.95%) | 96/248 (38.71%) | 0 | 0 | 8035.52 | 8.9 | 0.2013328 |
| gemma4b | T1500_VERB | 165/500 (33.0%) | 85/252 (33.73%) | 80/248 (32.26%) | 0 | 0 | 8480.48 | 8.43 | 0.2124335 |
| gemma4b | R1500_RECURSIVE | 183/500 (36.6%) | 102/252 (40.48%) | 81/248 (32.66%) | 0 | 0 | 5784.65 | 9.76 | 0.14510445 |

## Statistical tests

Full McNemar and Holm results are in `representation_mcnemar.csv`. Bootstrap deltas and model interactions are in `representation_bootstrap_interactions.csv`. Recursive comparisons are exploratory because recursive uses a different chunking pipeline.

## Data integrity

HTML/KV/VERB use the same query IDs, dense retrieved chunk IDs, ranks and data fingerprints. See `representation_samples.md` and `representation_manifest.json`.

## Limitations

Provider is pinned within each model but differs across model families: GPT-OSS uses CoreWeave; Gemma and Llama use DeepInfra. Results therefore support within-model representation comparisons and exploratory cross-model interactions, not a provider-controlled model ranking.