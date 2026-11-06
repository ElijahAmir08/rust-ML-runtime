"""Command line entry point.

    python -m workload_sim sweep  --model M --scenario scheduler --rates 2,4,8,16 --duration 180 --warmup 45
    python -m workload_sim replay --model M --start "2024-05-14 06:00" --hours 6 --speedup 6 --rate-scale 0.1
"""
import argparse
import asyncio
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
import pandas as pd

from .client import VLLMClient
from .load_generator import LoadGenerator
from .metrics import RunMetrics
from .server_metrics import ServerMonitor
from .workload import PoissonWorkload, ReplayWorkload, Workload, load_trace, scenario_rows

DEFAULT_TRACE = Path(__file__).parent.parent / "AzureLLMInferenceTrace_conv_1week.csv"


async def run_workload(args, workload: Workload, warmup: float,
                       end: float | None = None) -> tuple[RunMetrics, dict, pd.DataFrame | None]:
    """Run one workload, measuring [warmup, end) (end defaults to the last arrival). Returns client
    metrics, the server-side summary and the server gauge timeseries."""
    requests = workload.requests()
    if end is None:
        end = requests[-1].arrival_time if requests else None
    print(f"  {len(requests)} requests over {requests[-1].arrival_time:.0f} s" if requests else "  no requests")
    gen = None
    async with VLLMClient(args.url, args.model, seed=workload.seed) as client:
        gen = LoadGenerator(client)
        if args.monitor_interval > 0:
            async with ServerMonitor(args.url, args.monitor_interval) as mon:
                results = await gen.run(requests)
            server, series = mon.summary(gen.start, warmup), mon.timeseries(gen.start)
        else:
            results, server, series = await gen.run(requests), {}, None
    return RunMetrics(results, warmup, gen.max_lag, end, gen.start_unix), server, series


def report(metrics: RunMetrics, server: dict, series, csv_path: Path) -> dict:
    metrics.to_csv(csv_path)
    if series is not None:
        series.to_csv(csv_path.with_name(csv_path.stem + "_server.csv"), index=False)
    summary = {**metrics.summary(), **server}
    print(pd.Series(summary).round(2).to_string(), f"\n  per-request results: {csv_path}\n")
    return summary


def run_and_report(args, workload: Workload, warmup: float, csv_path: Path, end: float | None = None) -> dict:
    summary = report(*asyncio.run(run_workload(args, workload, warmup, end)), csv_path)
    if args.cooldown > 0:
        time.sleep(args.cooldown)  # let the server settle (and its gauges return to 0) before the next run
    return summary


def write_run_info(args, name: str) -> None:
    """Record what this run was: arguments, host, GPU, server version/model and code versions."""

    def cmd(*c):
        try:
            return subprocess.run(c, capture_output=True, text=True, timeout=10).stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            return None

    async def server_info():
        out = {}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            for key, path in (("version", "/version"), ("models", "/v1/models")):
                try:
                    async with s.get(args.url.rstrip("/") + path) as r:
                        out[key] = await r.json()
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
                    out[key] = f"unavailable: {e!r}"
        return out

    here = Path(__file__).parent
    try:  # identifies the trace version without hashing 1 GB
        st = args.trace.stat()
        trace = {"path": str(args.trace.resolve()), "bytes": st.st_size,
                 "mtime_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds")}
    except OSError as e:
        trace = {"path": str(args.trace), "error": repr(e)}
    info = {
        "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "argv": sys.argv,
        "args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items() if k != "func"},
        "trace": trace,
        "host": platform.node(),
        "python": platform.python_version(),
        "gpu": cmd("nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"),
        "workload_sim_git": cmd("git", "-C", str(here), "rev-parse", "--short", "HEAD"),
        "workload_sim_dirty": bool(cmd("git", "-C", str(here), "status", "--porcelain", "--", ".")),
        "server": asyncio.run(server_info()),
    }
    path = args.out / f"{name}_run_info.json"
    path.write_text(json.dumps(info, indent=2))
    print(f"run info: {path}")


def sweep(args) -> None:
    write_run_info(args, f"sweep_{args.scenario}")
    rows = scenario_rows(load_trace(args.trace), args.scenario, args.short_ctx, args.long_ctx)
    print(f"{args.scenario}: sampling lengths from {len(rows):,} trace rows")
    summaries = []
    # repeats are the outer loop, so slow drift on the server affects every rate equally
    for rep in range(args.repeats):
        seed = args.seed + rep
        for rate in args.rates:
            print(f"rep {rep} (seed {seed}), rate {rate} req/s")
            workload = PoissonWorkload(rows, rate, args.warmup + args.duration, args.max_model_len, seed)
            csv = args.out / f"sweep_{args.scenario}_rate{rate}_rep{rep}.csv"
            summaries.append({"scenario": args.scenario, "rate": rate, "rep": rep, "seed": seed,
                              **run_and_report(args, workload, args.warmup, csv, args.warmup + args.duration)})
            # rewrite after every run so a crash or time limit keeps what finished
            pd.DataFrame(summaries).to_csv(args.out / f"sweep_{args.scenario}_summary.csv", index=False)


def replay(args) -> None:
    stamp = args.start.replace(" ", "_").replace(":", "")
    write_run_info(args, f"replay_{stamp}")
    end = (pd.Timestamp(args.start) + pd.Timedelta(hours=args.hours)).strftime("%Y-%m-%d %H:%M:%S")
    window = load_trace(args.trace, args.start, end)
    print(f"replaying {len(window):,} trace rows from {args.start} to {end} UTC")
    summaries = []
    for rep in range(args.repeats):
        seed = args.seed + rep
        print(f"rep {rep} (seed {seed})")
        workload = ReplayWorkload(window, args.start, args.speedup, args.rate_scale, args.max_model_len, seed)
        csv = args.out / f"replay_{stamp}_rep{rep}.csv"
        summaries.append({"start": args.start, "rep": rep, "seed": seed,
                          **run_and_report(args, workload, 0.0, csv)})
        pd.DataFrame(summaries).to_csv(args.out / f"replay_{stamp}_summary.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(prog="workload_sim", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--model", required=True, help="model name as served by vllm")
    common.add_argument("--url", default="http://localhost:8000")
    common.add_argument("--trace", type=Path, default=DEFAULT_TRACE)
    common.add_argument("--out", type=Path, default=Path("results"))
    common.add_argument("--max-model-len", type=int, default=4096, help="clip request lengths to this")
    common.add_argument("--seed", type=int, default=0, help="seed of the first repeat; repeat i uses seed + i")
    common.add_argument("--repeats", type=int, default=1, help="run everything this many times")
    common.add_argument("--monitor-interval", type=float, default=1.0,
                        help="seconds between scrapes of the server's /metrics (0 disables)")
    common.add_argument("--cooldown", type=float, default=5.0, help="idle seconds after each run")
    sub = parser.add_subparsers(dest="mode", required=True)

    s = sub.add_parser("sweep", parents=[common], help="Poisson arrivals at each of several rates")
    s.add_argument("--scenario", choices=["baseline", "kv_cache", "scheduler"], default="baseline")
    s.add_argument("--rates", type=lambda v: [float(x) for x in v.split(",")], default=[1, 2, 4, 8])
    s.add_argument("--duration", type=float, default=180, help="measured seconds per rate")
    s.add_argument("--warmup", type=float, default=45, help="unmeasured seconds before each run")
    s.add_argument("--short-ctx", type=int, default=512, help="scheduler scenario: max prompt tokens")
    s.add_argument("--long-ctx", type=int, default=3072, help="kv_cache scenario: min prompt tokens")

    r = sub.add_parser("replay", parents=[common], help="replay a window of the trace")
    r.add_argument("--start", required=True, help='UTC, e.g. "2024-05-14 06:00"')
    r.add_argument("--hours", type=float, default=1.0)
    r.add_argument("--speedup", type=float, default=1.0, help="compress time by this factor")
    r.add_argument("--rate-scale", type=float, default=1.0, help="fraction of trace requests to keep")

    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    sweep(args) if args.mode == "sweep" else replay(args)


if __name__ == "__main__":
    main()
