# Runs in this folder replaced by reruns

The replaced files are in git history; the rerun's own folder was moved to results_archive/.

## 2026-11-20 23:54 UTC: replaced 3 runs from results/baseline_v1_sync_sched_rerun/baseline/ (Slurm job 560189)

Rerun because the original runs had false prefix-cache hits: with the same seed, request i of every rate starts with the same prompt tokens, and the previous rate's KV blocks were still cached. The rerun resets vLLM's prefix cache before every run (workload_sim reset_prefix_cache).

| rate (req/s) | rep | seed | prefix-cache hit rate before -> after | TTFT p50 before -> after (ms) |
|---|---|---|---|---|
| 0.5 | 0 | 0 | 22.6% -> 0.0% | 763 -> 931 |
| 0.5 | 1 | 1 | 22.8% -> 0.0% | 325 -> 586 |
| 0.5 | 2 | 2 | 25.1% -> 0.0% | 363 -> 501 |

