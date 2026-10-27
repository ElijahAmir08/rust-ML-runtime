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

#### How to run
The simulator lives in `workload_sim/`. It is open loop: every request is sent at its scheduled time no matter how busy the server is, so queueing happens inside vllm's scheduler (the thing we're testing). Prompts are random token ids of the trace's exact prompt length, and `ignore_eos` makes vllm generate exactly the trace's output length.

Start vllm, then from `vllm_playground/` (inside the vllm venv, needs `aiohttp pandas numpy`):
```
# sweep: Poisson arrivals at several rates; scenario picks lengths from the trace
#   baseline = all rows, scheduler = prompt <= --short-ctx, kv_cache = prompt >= --long-ctx
python -m workload_sim sweep --model <model> --scenario scheduler --rates 2,4,8,16 --duration 180 --warmup 45

# replay: real trace timestamps, compressed by --speedup and thinned by --rate-scale
python -m workload_sim replay --model <model> --start "2024-05-14 06:00" --hours 6 --speedup 6 --rate-scale 0.1
```
Set `--max-model-len` to the server's context length (default 4096); longer requests are clipped.
Results go to `results/`: one CSV per run (one row per request: ttft, e2e, mean_itl, ...) and a summary CSV
(requests/s, output tokens/s, mean/p50/p90/p99 of TTFT, ITL, E2E). Requests arriving during warmup are
excluded from the summary. A warning is printed if the client itself falls behind schedule.

Classes: `Workload` (`PoissonWorkload`, `ReplayWorkload`) builds a sorted list of `Request`s →
`LoadGenerator` dispatches them on time → `VLLMClient` streams each one and times it → `RunMetrics` summarizes.
