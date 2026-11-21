# Runs in this folder replaced by reruns

The replaced files are in git history; the rerun's own folder was moved to results_archive/.

## 2026-11-20 23:49 UTC: replaced 6 runs from results/baseline_v1_rerun/kv_cache/ (Slurm job 560187)

Rerun because the original runs had false prefix-cache hits: with the same seed, request i of every rate starts with the same prompt tokens, and the previous rate's KV blocks were still cached. The rerun resets vLLM's prefix cache before every run (workload_sim reset_prefix_cache).

| rate (req/s) | rep | seed | prefix-cache hit rate before -> after | TTFT p50 before -> after (ms) |
|---|---|---|---|---|
| 0.1 | 0 | 0 | 36.7% -> 0.0% | 1934 -> 2740 |
| 0.15 | 0 | 0 | 52.3% -> 0.0% | 1816 -> 3146 |
| 0.1 | 1 | 1 | 47.3% -> 0.0% | 1496 -> 2524 |
| 0.15 | 1 | 1 | 51.7% -> 0.0% | 1963 -> 3223 |
| 0.1 | 2 | 2 | 45.1% -> 0.0% | 1586 -> 2545 |
| 0.15 | 2 | 2 | 0.0% -> 0.0% | 2561 -> 2541 |

