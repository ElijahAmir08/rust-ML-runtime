#!/usr/bin/env python3
"""Load workload_sim results (CSV files) into one SQLite database for Grafana.

    python3 load_results.py <results-dir> <out.db>

Standard library only, so it runs in a stock python container. Every *_summary.csv under
<results-dir> becomes runs; the experiment name is the first folder below <results-dir>
(e.g. baselines/qwen7b_v100/kv_cache/... -> "qwen7b_v100").

Time axis. Grafana plots against wall-clock time, so each run gets one:
  * sweep runs start at 2000-01-01 00:00:00 UTC, so with the dashboard in UTC the axis reads as
    elapsed time (00:01:30 = 90 s into the run) and runs overlay when you select several;
  * replay runs use the trace's own time of day: trace start + t * speedup.

Tables: runs (one row per run, all summary metrics), requests (one row per request),
server (vLLM gauge samples), windows (per-time-bucket latency percentiles and load),
sweep_agg (median/min/max over repeats for each scenario and rate).
"""
import csv
import json
import math
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SWEEP_ORIGIN = 946684800.0  # 2000-01-01 00:00:00 UTC: midnight, so the time axis reads as elapsed time.
# (Timestamps near the 1970 epoch make Grafana report "Invalid date" for the time range.)
AGG_METRICS = [
    "offered_rps", "steady_requests_per_s", "steady_output_tokens_per_s",
    "ttft_p50_ms", "ttft_p90_ms", "ttft_p99_ms", "tpot_p50_ms", "tpot_p99_ms", "itl_p50_ms", "itl_p99_ms",
    "e2e_p50_ms", "e2e_p99_ms", "srv_running_mean", "srv_waiting_mean", "srv_kv_cache_usage_mean",
    "srv_queue_mean_ms", "srv_preemptions",
]


def num(v):
    """CSV text -> float, bool -> 0/1, '' -> None; anything else stays text."""
    if v is None or v == "":
        return None
    if v in ("True", "False"):
        return float(v == "True")
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except ValueError:
        return v


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return [{k: num(v) for k, v in row.items()} for row in csv.DictReader(f)]


def pct(values, q):
    """q-th percentile with linear interpolation (numpy's default)."""
    v = sorted(values)
    if not v:
        return None
    k = (len(v) - 1) * q / 100
    lo, hi = math.floor(k), math.ceil(k)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def run_info(folder: Path, prefix: str) -> dict:
    p = folder / f"{prefix}_run_info.json"
    return json.loads(p.read_text())["args"] if p.exists() else {}


def discover(root: Path):
    """Yield (experiment, run dict, per-request csv, server csv) for every run under root."""
    for summ in sorted(root.rglob("*_summary.csv")):
        rel = summ.relative_to(root).parts
        experiment = rel[0] if len(rel) > 1 else root.name
        folder = summ.parent
        for row in read_csv(summ):
            if summ.name.startswith("sweep_"):
                scenario = row["scenario"]
                args = run_info(folder, f"sweep_{scenario}")
                stem = f"sweep_{scenario}_rate{float(row['rate'])}_rep{int(row['rep'])}"
                run = {"mode": "sweep", "scenario": scenario, "rate": row["rate"],
                       "warmup_s": args.get("warmup", 0.0), "duration_s": args.get("duration"),
                       "time_origin": SWEEP_ORIGIN, "time_scale": 1.0,
                       "label": f"{scenario} @{row['rate']:g}/s rep{int(row['rep'])}"}
            elif summ.name.startswith("replay_"):
                stamp = summ.name[len("replay_"):-len("_summary.csv")]
                args = run_info(folder, f"replay_{stamp}")
                start = datetime.strptime(str(row["start"]), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
                stem = f"replay_{stamp}_rep{int(row['rep'])}"
                run = {"mode": "replay", "scenario": "replay", "rate": None, "warmup_s": 0.0,
                       "duration_s": args.get("hours", 0) * 3600 / args.get("speedup", 1) if args else None,
                       "time_origin": start.timestamp(), "time_scale": float(args.get("speedup", 1.0)),
                       "label": f"replay {row['start']} x{args.get('speedup', 1):g} rep{int(row['rep'])}"}
            else:
                continue
            run |= {"experiment": experiment, "rep": row["rep"], "seed": row.get("seed"),
                    "run_id": f"{experiment}/{stem}", "label": f"{experiment}: {run['label']}"}
            run |= {k: v for k, v in row.items() if k not in run and k not in ("start",)}
            yield run, folder / f"{stem}.csv", folder / f"{stem}_server.csv"


def windows(reqs: list[dict], bucket: float) -> list[dict]:
    """Per time bucket (by arrival): offered load, completions and latency percentiles."""
    by_arrival, done = defaultdict(list), defaultdict(int)
    for r in reqs:
        by_arrival[int(r["arrival_time"] // bucket)].append(r)
        if r["success"] and r["e2e"] is not None:
            done[int((r["arrival_time"] + r["e2e"]) // bucket)] += 1
    out = []
    for b in sorted(set(by_arrival) | set(done)):
        rs = [r for r in by_arrival.get(b, []) if r["success"]]
        ttft = [r["ttft"] * 1000 for r in rs if r["ttft"] is not None]
        tpot = [r["tpot"] * 1000 for r in rs if r.get("tpot") is not None]
        e2e = [r["e2e"] * 1000 for r in rs if r["e2e"] is not None]
        out.append({"t_s": b * bucket, "bucket_s": bucket,
                    "arrivals_per_s": len(by_arrival.get(b, [])) / bucket, "completions_per_s": done.get(b, 0) / bucket,
                    "ttft_p50_ms": pct(ttft, 50), "ttft_p99_ms": pct(ttft, 99),
                    "tpot_p50_ms": pct(tpot, 50), "tpot_p99_ms": pct(tpot, 99), "e2e_p50_ms": pct(e2e, 50)})
    return out


def create(db: sqlite3.Connection, table: str, rows: list[dict], first: list[str]):
    cols = list(dict.fromkeys(first + [k for r in rows for k in r]))
    db.execute(f"DROP TABLE IF EXISTS {table}")
    db.execute(f"CREATE TABLE {table} ({', '.join(f'[{c}]' for c in cols)})")
    db.executemany(f"INSERT INTO {table} VALUES ({', '.join('?' * len(cols))})",
                   [[r.get(c) for c in cols] for r in rows])


def main():
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    runs, requests, server, wins = [], [], [], []
    for run, req_csv, srv_csv in discover(root):
        if not req_csv.exists():
            print(f"skip {run['run_id']}: {req_csv.name} missing")
            continue
        o, s, rid = run["time_origin"], run["time_scale"], run["run_id"]
        reqs = read_csv(req_csv)
        last = max((r["arrival_time"] + (r["e2e"] or 0) for r in reqs), default=0)
        run |= {"last_completion_s": last, "from_ms": int((o - 5) * 1000), "to_ms": int((o + (last + 10) * s) * 1000)}
        runs.append(run)
        for r in reqs:
            requests.append({"run_id": rid, "time": o + r["arrival_time"] * s,
                             "measured": float(r["arrival_time"] >= (run["warmup_s"] or 0)),
                             **{k: r.get(k) for k in ("id", "arrival_time", "prompt_tokens", "output_tokens",
                                                      "received_tokens", "success", "error")},
                             **{f"{k}_ms": (r[k] * 1000 if r.get(k) is not None else None)
                                for k in ("ttft", "tpot", "e2e", "mean_itl")}})
        if srv_csv.exists():
            for g in read_csv(srv_csv):
                server.append({"run_id": rid, "time": o + g["t"] * s, **g})
        bucket = 10.0 if run["mode"] == "sweep" else max(10.0, round(last / 120 / 10) * 10)
        for w in windows(reqs, bucket):
            wins.append({"run_id": rid, "time": o + w["t_s"] * s, **w})
        print(f"{rid}: {len(reqs)} requests")

    agg = []
    groups = defaultdict(list)
    for r in runs:
        if r["mode"] == "sweep":
            groups[(r["experiment"], r["scenario"], r["rate"])].append(r)
    for (exp, sc, rate), rs in sorted(groups.items()):
        row = {"experiment": exp, "scenario": sc, "rate": rate, "reps": len(rs)}
        for m in AGG_METRICS:
            v = [r[m] for r in rs if isinstance(r.get(m), float)]
            if v:
                row |= {f"{m}_med": statistics.median(v), f"{m}_min": min(v), f"{m}_max": max(v)}
        agg.append(row)

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    # fixed leading columns, so dashboards work even on runs recorded before a metric existed
    create(db, "runs", runs, ["run_id", "experiment", "mode", "scenario", "rate", "rep", "label"] + AGG_METRICS)
    create(db, "requests", requests, ["run_id", "time"])
    create(db, "server", server, ["run_id", "time", "t", "running", "waiting", "kv_cache_usage"])
    create(db, "windows", wins, ["run_id", "time"])
    create(db, "sweep_agg", agg, ["experiment", "scenario", "rate", "reps"]
           + [f"{m}_{s}" for m in AGG_METRICS for s in ("med", "min", "max")])
    for t in ("requests", "server", "windows"):
        db.execute(f"CREATE INDEX {t}_run ON {t} (run_id, time)")
    db.commit()
    db.close()
    tmp.replace(out)  # atomic, so Grafana never reads a half-written file
    print(f"wrote {out}: {len(runs)} runs, {len(requests)} requests, {len(server)} server samples")


if __name__ == "__main__":
    main()
