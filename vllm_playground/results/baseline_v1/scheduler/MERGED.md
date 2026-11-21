# Runs in this folder replaced by reruns

The replaced files are in git history; the rerun's own folder was moved to results_archive/.

## 2026-11-20 23:49 UTC: replaced 3 runs from results/baseline_v1_rerun/scheduler/ (Slurm job 560185)

Rerun because the original runs had false prefix-cache hits: with the same seed, request i of every rate starts with the same prompt tokens, and the previous rate's KV blocks were still cached. The rerun resets vLLM's prefix cache before every run (workload_sim reset_prefix_cache).

| rate (req/s) | rep | seed | prefix-cache hit rate before -> after | TTFT p50 before -> after (ms) |
|---|---|---|---|---|
| 4 | 0 | 0 | 35.2% -> 0.0% | 124 -> 144 |
| 4 | 1 | 1 | 39.5% -> 0.0% | 120 -> 148 |
| 4 | 2 | 2 | 39.6% -> 0.0% | 122 -> 150 |

