### Workload_simulator for benchmarking

Below we include our workload simulator for benchmarking. The goal is to provide a thorough description of its capabilities and purpose. This serves as information to any reader and also a place for us to ideate about the workload simulator.

#### Things we need to test
- baseline could be just a completely full queue where order is sampled randomly from our data.
- stress testing kv caching by including many long context prompts...
- stress testing the scheduler by including many high concurrency jobs (low context length that require a lot of parallelism)
- real world simulated env (testing time done as a time variable in seconds)


**open question:** how to track metrics and which metrics to track when benchmarking
- time to completion?
- time to first token
- tokens per second
- avg end to end latency
- request per second
- Inter-Token Latency

#### How it works
The simulator lives in `workload_sim/`. It is open loop: every request is sent at its scheduled time no matter how busy the server is, so queueing happens inside vllm's scheduler (the thing we're testing). Prompts are random token ids of the trace's exact prompt length, and `ignore_eos` makes vllm generate exactly the trace's output length.

Classes: `Workload` (`PoissonWorkload`, `ReplayWorkload`) builds a sorted list of `Request`s →
`LoadGenerator` dispatches them on time → `VLLMClient` streams each one and times it → `RunMetrics` summarizes.
While a run is going, `ServerMonitor` polls vLLM's Prometheus `/metrics` once a second for what the client
can't see: batch size, queue depth, KV-cache usage, preemptions and vLLM's own queue time.
`workload_sim_diagram.png` shows the whole flow.

#### Running an experiment on the cluster
One entry point, `run.sh`, and one job template, `slurms/_job.slurm`. An experiment is a JSON file in
`experiments/`; every entry in its `runs` list becomes one Slurm job with its own GPU and vLLM server,
all submitted in parallel. From `vllm_playground/`:
```
./run.sh --list                          # experiments and their descriptions
./run.sh --dry-run baseline_v1           # the exact server command, workload command and sbatch flags
./run.sh baseline_v1                     # submit every run
./run.sh baseline_v1 --only kv_cache     # just one run (repeatable)
./run.sh smoke --tag after_fix           # a new copy under results/smoke_after_fix/
./run.sh --local smoke --only scheduler  # inline on a GPU node you're already on (e.g. inside srun)
./run.sh --after 12345 baseline_v1       # start only if job 12345 succeeds
```
Each job starts `vllm serve` (fp16, since V100 has no bf16) and waits until it is healthy. For
`"mode": "sweep"` runs only, it then sends 60 s of unmeasured traffic at the run's highest rate, to absorb
a one-time ~9 s stall seen on a fresh server. Finally it runs the workload and stops the server. Every submission is logged in `experiments/runs.tsv` (time, job id, run,
git commit). Results are never overwritten: reusing a results folder, or submitting a changed config into an
existing one, is refused (use `--tag`).

**Config format** (`experiments/baseline_v1.json` is a full example; the `//` comments below are
explanations only, real JSON has none). Unknown keys are rejected, so typos fail at submit time:
```
{
  "description": "one line, shown by --list",
  "notes": "free text: why these settings",
  "seed": 0,                                  // required
  "server": {"model": "Qwen/Qwen2.5-7B-Instruct", "max_model_len": 8192,
             "args": ["--max-num-seqs", "64"], // extra `vllm serve` flags
             "venv": "../vllm/.venv"},          // which vLLM build to serve
  "slurm":  {"partition": "gpu", "gpus": 1, "cpus": 8, "mem": "64G", "time": "8:00:00"},
  "runs": [
    {"name": "kv_cache", "mode": "sweep", "scenario": "kv_cache",   // baseline | scheduler | kv_cache
     "rates": [0.05, 0.1, 0.2], "repeats": 3, "duration": 480, "warmup": 90},
    {"name": "replay_0514", "mode": "replay", "start": "2024-05-14 10:00",
     "hours": 6, "speedup": 6, "rate_scale": 0.0019}
  ]
}
```
Defaults: sweeps `repeats` 3, `duration` 180, `warmup` 45, `prime` true, `short_ctx` 512, `long_ctx` 3072;
replays `repeats` 1; `server` and `slurm` as shown. A run may also set its own `seed` or any `slurm` key
(e.g. a longer `time`). Replay load on the server ≈ trace rate (45-75 req/s) × `speedup` × `rate_scale`.

**Seeding.** Everything is seeded from `seed` (repeat *i* uses `seed + i`): Poisson arrival times, which
trace rows set the request lengths, which rows a replay keeps, every request's prompt tokens (its own RNG,
seeded by seed and request id, so send order doesn't matter), and `vllm serve --seed`. The same config gives
the same requests, at the same times, with the same prompts and lengths. vLLM's generated text can still
vary slightly because batching depends on real timing; output lengths can't, since `ignore_eos` fixes them.

Everything lands in `results/<experiment>[_<tag>]/<run>/`:

| file | contents |
|---|---|
| `sweep_<scenario>_rate<r>_rep<i>.csv` | one row per request: arrival, lengths, ttft, tpot, e2e, norm_latency, mean ITL, error |
| `..._server.csv` | vLLM gauges every second: running (batch), waiting (queue), KV-cache usage |
| `sweep_<scenario>_summary.csv` | one row per run (rate × repeat): every summary metric below |
| `replay_<start>_rep<i>.csv`, `replay_<start>_summary.csv` | the same for a replay |
| `*_run_info.json` | simulator arguments, trace file (size, mtime), host, GPU, vLLM version, served model |
| `server_cmd.txt`, `server.log`, `server_config_lines.txt` | exact `vllm serve` command, full server log, and the lines that show its config (attention backend, KV-cache size, chunked prefill) |
| `env.txt`, `git.txt`, `slurm-<job>.out` | node, GPU (and anything else already on it), venv, versions; commits at submit time; the job log |
| `../experiment.json` | the config as submitted |

#### Looking at the results
`grafana/` has a local Grafana setup (Docker) with two dashboards: per-scenario rate sweeps, and a per-run view of
load, batch size, queue depth, KV cache and latency over time (select several runs to overlay them). It reads
`baselines/` by default, the results committed to the repo. To share an experiment:
`cp -r results/<NAME> baselines/` and commit it. See `grafana/README.md`.

#### Summary metrics
Each run (one rate × one repeat, or one replay repeat) writes one row to `*_summary.csv`. The row starts
with identifying columns: `scenario`, `rate`, `rep`, `seed` for sweeps, or `start`, `rep`, `seed` for
replays. The metrics that follow are described below. All times are measured from t = 0, the moment the run
starts dispatching.

**Which requests count.** A request is *measured* if it arrived at or after `warmup` (sweeps use the
`warmup` from the config; replays use 0). Measured requests stay in the per-request CSV either way. A request
*succeeds* if it streamed at least one chunk without an HTTP or connection error. Only successful measured
requests go into the latency stats. Failures are dropped from them silently, so always check
`requests` against `successes`.

**Bookkeeping**
| column | meaning |
|---|---|
| `start_unix` | wall-clock time of t = 0, used to line runs up with server logs and dashboards |
| `requests` / `successes` | measured requests sent / measured requests that succeeded |
| `client_max_lag_ms` | worst gap between a request's scheduled send time and its actual send time, over the whole run (warmup included). A warning prints above 100 ms. If this is large, the client was the bottleneck and the latencies are suspect. |

**Throughput.** There are two windows, and they answer different questions:
| column | meaning |
|---|---|
| `offered_rps` | load actually generated: measured requests ÷ (last measured arrival − first measured arrival). Because arrivals are Poisson, this is close to `rate` but not equal to it. |
| `steady_window_s` | length of the measured interval [warmup, warmup + duration). For a replay it runs from 0 to the last arrival. |
| `steady_requests_per_s` | requests that *finished* inside the steady window ÷ its length. Any request counts, including warmup arrivals that finish inside the window. While the server keeps up, this ≈ `offered_rps`. Once it saturates, this levels off at the server's capacity while `offered_rps` keeps rising. **This is the number to use for throughput.** |
| `steady_output_tokens_per_s` | output tokens streamed inside the steady window ÷ its length. Chunks are counted by when they arrived, and each chunk is worth `received_tokens / chunks` tokens. |
| `window_s` | first measured arrival → last measured completion. This window includes the drain after arrivals stop. |
| `requests_per_s`, `output_tokens_per_s`, `prompt_tokens_per_s` | successful measured requests, their output tokens, and their prompt tokens, each ÷ `window_s`. The drain makes these lower than the steady numbers when the server is overloaded. |

**Latency.** Each of these has `_mean_ms`, `_p50_ms`, `_p90_ms`, `_p95_ms` and `_p99_ms` (numpy linear-interpolated percentiles).
`pXX` is the value XX% of requests (or, for `itl`, of chunk gaps) came in under: p50 is the median, a typical
request; p95/p99 are the tail, the slowest 1 in 20 / 1 in 100. The mean is pulled up by a few very slow
requests, so mean ≫ p50 signals a heavy tail. Saturation shows up first in p99, then in p50.
| metric | definition | what it reflects |
|---|---|---|
| `ttft` | scheduled arrival → first streamed chunk | client lag + HTTP + vLLM queue time + prefill (with chunked prefill, a long prompt is split over several engine steps). This is where scheduler queueing shows up. |
| `e2e` | scheduled arrival → last streamed chunk | the whole request. It is dominated by output length, so compare it only within one scenario. |
| `norm_latency` | per request: e2e / output tokens (ms per token) | "normalized latency" from the vLLM (PagedAttention) paper: e2e with output length divided out, so it can be compared across scenarios. It mixes TTFT and TPOT: ≈ TPOT for long outputs, ≈ TTFT / tokens for short ones. Its mean against rate is the paper's headline curve. |
| `tpot` | per request: (e2e − ttft) / (output tokens − 1); requests with fewer than 2 tokens are skipped | decode speed as one user sees it. It rises with batch size and with prefill chunks interleaved into the decode steps. Each request counts once. |
| `itl` | time between two consecutive output tokens of the same request, as the client sees them (the gap between two chunks, since a chunk is one token here). A request with n output tokens gives n − 1 gaps, and the stats pool every gap of every request. | roughly how long one engine step took. Each step produces one token for every running request, so a gap is the step time: it grows with batch size, and it jumps when the step also prefills a prompt chunk or after a preemption. `tpot` is the *average* of one request's gaps, while `itl` keeps every gap, so its p99 catches individual stalls that `tpot` averages away. |

Timing from the *scheduled* arrival, not from when the client actually sent the request, means client lag is
counted against the server rather than hidden (this avoids coordinated omission).

**Server side** (`srv_*`, scraped from vLLM's Prometheus `/metrics` every `--monitor-interval`, 1 s by default).
The full 1 s timeseries is in `..._server.csv`.
| column | meaning |
|---|---|
| `srv_running_{mean,p50,p95,max}` | requests in vLLM's current batch (`num_requests_running`) |
| `srv_waiting_{mean,p50,p95,max}` | requests queued in vLLM's scheduler and not yet started (`num_requests_waiting`). If this stays above 0, the server is saturated. |
| `srv_kv_cache_usage_{mean,p50,p95,max}` | fraction (0 to 1) of KV-cache blocks in use. A value near 1 means the batch is memory-bound. |
| `srv_queue_requests` | number of requests vLLM recorded a queue time for |
| `srv_queue_mean_ms` | mean time a request waited in vLLM's queue before it was first scheduled |
| `srv_queue_frac_over_0.3s`, `srv_queue_frac_over_1.0s` | fraction of requests that waited longer than 0.3 s and longer than 1 s |
| `srv_preemptions` | times vLLM evicted a running request because it ran out of KV blocks; that request's work is recomputed later. Any value above 0 means real KV-cache pressure. |
| `srv_prefix_cache_hit_rate` | prefix-cache hits ÷ lookups, counted in tokens. It should be ≈ 0, because prompts are random token ids. |

The gauges (`running`, `waiting`, `kv_cache_usage`) use only the samples taken after warmup, and that
includes the drain until the last request finishes. The queue, preemption and prefix-cache columns are
differences of vLLM's counters between the start and the end of the run. They therefore *include warmup
requests*, because vLLM only exposes these counters in aggregate. Queue-time percentiles aren't reported
because vLLM's smallest histogram bucket is 0.3 s, so the two bucket fractions are exact and an interpolated
p50 would be a guess.

#### Running the simulator by hand
Start vllm, then from `vllm_playground/` (inside the vllm venv, needs `aiohttp pandas numpy`):
```
# sweep: Poisson arrivals at several rates; scenario picks lengths from the trace
#   baseline = all rows, scheduler = prompt <= --short-ctx, kv_cache = prompt >= --long-ctx
python -m workload_sim sweep --model <model> --scenario scheduler --rates 2,4,8,16 --duration 180 --warmup 45 --repeats 3

# replay: real trace timestamps, compressed by --speedup and thinned by --rate-scale
python -m workload_sim replay --model <model> --start "2024-05-14 10:00" --hours 6 --speedup 6 --rate-scale 0.0019
```
Set `--max-model-len` to the server's context length; longer requests are clipped. The experiments use 8192:
with 4096, 9.7% of trace requests are clipped, and most `kv_cache` prompts become 4095 tokens with 1 output token.
`--repeats N` reruns everything with seeds `seed … seed+N-1` (repeat is the outer loop).
`--monitor-interval 0` turns off `/metrics` polling; `--cooldown` idles between runs.

#### Notes on the cluster setup
- GPU nodes have no internet (`HF_HUB_OFFLINE=1`) and no `git`; download models on the login node
  (`../vllm/.venv/bin/hf download <model>`). `run.sh` records git state at submit time.
- On V100 (sm70) vLLM uses the `TRITON_ATTN` attention backend; FlashAttention needs sm80+.
- Defaults otherwise: chunked prefill with `max_num_batched_tokens=2048`, `gpu_memory_utilization=0.9`
  (≈13 GiB / 246k tokens of KV cache for Qwen2.5-7B at 8192 context).
