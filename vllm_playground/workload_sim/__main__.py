"""Command line entry point.

    python -m workload_sim sweep  --model M --scenario scheduler --rates 2,4,8,16 --duration 180 --warmup 45
    python -m workload_sim replay --model M --start "2024-05-14 06:00" --hours 6 --speedup 6 --rate-scale 0.1
"""
import argparse
import asyncio
from pathlib import Path

import pandas as pd

from .client import VLLMClient
from .load_generator import LoadGenerator
from .metrics import RunMetrics
from .workload import PoissonWorkload, ReplayWorkload, Workload, load_trace, scenario_rows

DEFAULT_TRACE = Path(__file__).parent.parent / "AzureLLMInferenceTrace_conv_1week.csv"


async def run_workload(args, workload: Workload, warmup: float) -> RunMetrics:
    requests = workload.requests()
    print(f"  {len(requests)} requests over {requests[-1].arrival_time:.0f} s" if requests else "  no requests")
    async with VLLMClient(args.url, args.model, seed=args.seed) as client:
        results = await LoadGenerator(client).run(requests)
    return RunMetrics(results, warmup)


def report(metrics: RunMetrics, csv_path: Path) -> dict:
    metrics.to_csv(csv_path)
    summary = metrics.summary()
    print(pd.Series(summary).round(2).to_string(), f"\n  per-request results: {csv_path}\n")
    return summary


def sweep(args) -> None:
    rows = scenario_rows(load_trace(args.trace), args.scenario, args.short_ctx, args.long_ctx)
    print(f"{args.scenario}: sampling lengths from {len(rows):,} trace rows")
    summaries = []
    for rate in args.rates:
        print(f"rate {rate} req/s")
        workload = PoissonWorkload(rows, rate, args.warmup + args.duration, args.max_model_len, args.seed)
        metrics = asyncio.run(run_workload(args, workload, args.warmup))
        summaries.append({"rate": rate, **report(metrics, args.out / f"sweep_{args.scenario}_rate{rate}.csv")})
    pd.DataFrame(summaries).to_csv(args.out / f"sweep_{args.scenario}_summary.csv", index=False)


def replay(args) -> None:
    end = (pd.Timestamp(args.start) + pd.Timedelta(hours=args.hours)).strftime("%Y-%m-%d %H:%M:%S")
    window = load_trace(args.trace, args.start, end)
    print(f"replaying {len(window):,} trace rows from {args.start} to {end} UTC")
    workload = ReplayWorkload(window, args.start, args.speedup, args.rate_scale, args.max_model_len, args.seed)
    metrics = asyncio.run(run_workload(args, workload, warmup=0.0))
    stamp = args.start.replace(" ", "_").replace(":", "")
    pd.DataFrame([report(metrics, args.out / f"replay_{stamp}.csv")]).to_csv(
        args.out / f"replay_{stamp}_summary.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(prog="workload_sim", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--model", required=True, help="model name as served by vllm")
    common.add_argument("--url", default="http://localhost:8000")
    common.add_argument("--trace", type=Path, default=DEFAULT_TRACE)
    common.add_argument("--out", type=Path, default=Path("results"))
    common.add_argument("--max-model-len", type=int, default=4096, help="clip request lengths to this")
    common.add_argument("--seed", type=int, default=0)
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
