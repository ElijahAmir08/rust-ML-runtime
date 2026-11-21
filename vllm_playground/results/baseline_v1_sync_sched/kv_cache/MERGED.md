# Runs in this folder replaced by reruns

The replaced files are in git history; the rerun's own folder was moved to results_archive/.

## 2026-11-20 23:54 UTC: replaced 6 runs from results/baseline_v1_sync_sched_rerun/kv_cache/ (Slurm job 560190)

Rerun because the original runs had false prefix-cache hits: with the same seed, request i of every rate starts with the same prompt tokens, and the previous rate's KV blocks were still cached. The rerun resets vLLM's prefix cache before every run (workload_sim reset_prefix_cache).

| rate (req/s) | rep | seed | prefix-cache hit rate before -> after | TTFT p50 before -> after (ms) |
|---|---|---|---|---|
| 0.1 | 0 | 0 | 36.7% -> 0.0% | 1938 -> 2835 |
| 0.15 | 0 | 0 | 52.3% -> 0.0% | 1808 -> 3179 |
| 0.1 | 1 | 1 | 47.3% -> 0.0% | 1536 -> 2540 |
| 0.15 | 1 | 1 | 51.7% -> 0.0% | 1926 -> 3297 |
| 0.1 | 2 | 2 | 45.1% -> 0.0% | 1591 -> 2679 |
| 0.15 | 2 | 2 | 0.0% -> 0.0% | 2540 -> 2528 |

