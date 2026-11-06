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
Each job starts `vllm serve` (fp16, since V100 has no bf16), waits until it is healthy, runs an unmeasured
60 s priming pass for sweeps (the first run on a fresh server showed a one-time ~9 s stall), runs the
workload, and stops the server. Every submission is logged in `experiments/runs.tsv` (time, job id, run,
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
| `sweep_<scenario>_rate<r>_rep<i>.csv` | one row per request: arrival, lengths, ttft, tpot, e2e, mean ITL, error |
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
Client side, over requests that arrived after warmup:
- `offered_rps`: arrival rate actually generated. `steady_requests_per_s` / `steady_output_tokens_per_s`: requests and tokens completed *inside* the measured interval [warmup, warmup + duration) divided by its length; equals the offered rate when the server keeps up, and isn't diluted by the drain after arrivals stop. (`requests_per_s` / `output_tokens_per_s` use first arrival → last completion instead.)
- `ttft`, `tpot`, `itl`, `e2e`: mean, p50, p90, p95, p99 in ms. TTFT and E2E are timed from the request's *scheduled* arrival, so client lag counts (`client_max_lag_ms` reports it; a warning prints over 100 ms). TPOT = (e2e − ttft) / (tokens − 1). ITL is the gap between streamed chunks.

Server side (`srv_*`, from vLLM's `/metrics`):
- `srv_running_*`, `srv_waiting_*`, `srv_kv_cache_usage_*`: mean / p50 / p95 / max of the 1 s samples after warmup.
- `srv_queue_mean_ms`, `srv_queue_frac_over_{0.3,1.0}s`, `srv_preemptions`, `srv_prefix_cache_hit_rate`: differences of vLLM's counters over the whole run, *including* warmup requests (vLLM only exposes them in aggregate). Queue-time percentiles aren't reported because vLLM's smallest histogram bucket is 0.3 s.

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
