# Grafana dashboards for workload_sim results

Explore benchmark results interactively on your own machine: rate sweeps per scenario, and how
load, vLLM's batch size, queue depth, KV-cache usage and latency change **during** each run.
Everything runs locally from the repo; nothing connects to the cluster.

## Start

Needs Docker (Docker Desktop on a Mac). From this folder:

```bash
docker compose up        # first start downloads Grafana and the SQLite plugin
```

Open <http://localhost:3000>. It opens on **vLLM baseline: overview**; the other dashboard is
**vLLM run detail** (both are in the *vLLM benchmarks* folder). Stop with `Ctrl-C`, or
`docker compose down` to remove the containers (`-v` also removes the stored database).

By default it reads `../baselines/`, the committed results. To look at another folder of results:

```bash
RESULTS_DIR=../results docker compose up
```

After adding or changing results, rebuild the database and refresh the browser:

```bash
docker compose run --rm loader
```

## What's where

| Dashboard | Shows |
|---|---|
| **overview** | One row per scenario: throughput (offered vs completed), TTFT, TPOT and vLLM's batch/queue at each offered rate, as the median over repeats. A table of every run at the bottom; click a run's name to open it in *run detail*. |
| **run detail** | Selected runs over time: arrivals and completions per second, `num_requests_running` (batch), `num_requests_waiting` (queue), KV-cache usage, TTFT/TPOT percentiles per 10 s window, and one dot per request for TTFT and end-to-end latency. Select several runs in *Run* to overlay them. |

**Time axis.** Sweep runs are placed at 2000-01-01 00:00 UTC, so the axis reads as elapsed time
(`00:01:30` = 90 s after the first request) and runs line up when overlaid. The first `warmup`
seconds are not in the summary numbers. A trace replay is placed at the trace's own time of day
(e.g. 2024-05-14 10:00-16:00), with run time stretched back by the replay's `--speedup`.

## Files

| File | Purpose |
|---|---|
| `docker-compose.yml` | `loader` builds `results.db` from the CSVs, then `grafana` starts with it. Grafana listens on `127.0.0.1` only, with anonymous admin access (no login). |
| `load_results.py` | CSV → SQLite (standard library only). Tables: `runs`, `requests`, `server`, `windows`, `sweep_agg`. |
| `build_dashboards.py` | Generates `dashboards/*.json`. Edit it and rerun `python3 build_dashboards.py` to change the dashboards. |
| `provisioning/` | Grafana datasource (SQLite plugin `frser-sqlite-datasource`) and dashboard provider. |

Dashboard edits made in the Grafana UI work but are lost when the container is recreated; to keep
one, export its JSON (*Share → Export*) into `dashboards/`, or make the change in `build_dashboards.py`.

## Without Docker

`python3 load_results.py ../baselines results.db` works with any Python ≥ 3.9. Point a local
Grafana's SQLite datasource at that file and import the two JSON files from `dashboards/`.
