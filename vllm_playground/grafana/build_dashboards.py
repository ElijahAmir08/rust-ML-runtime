#!/usr/bin/env python3
"""Generate the Grafana dashboard JSON in dashboards/ (the files Grafana provisions).

    python3 build_dashboards.py

Edit this script and rerun it to change the dashboards. Edits made in the Grafana UI also work
(the provider allows them) but are lost when the container is recreated unless you export the JSON.
"""
import json
from pathlib import Path

OUT = Path(__file__).parent / "dashboards"
DS = {"type": "frser-sqlite-datasource", "uid": "workload-sim"}
SCENARIO_COLORS = {"scheduler": "#0f766e", "baseline": "#2563eb", "kv_cache": "#c2410c", "replay": "#7c3aed"}
RUNS = "run_id IN (${run:sqlstring})"  # multi-value run variable, quoted for SQL


def target(sql, ref="A", fmt="time series"):
    return {"refId": ref, "datasource": DS, "queryType": fmt, "queryText": sql, "rawQueryText": sql,
            "timeColumns": ["time"]}


def timeseries(title, sql, gp, axis, unit=None, display="${__field.labels.label}", desc="", points=False,
               min_=None, max_=None, log=False):
    """Line/point chart against time. `axis` labels the y-axis; the x-axis is always time."""
    custom = {"drawStyle": "points" if points else "line", "lineWidth": 1, "spanNulls": True,
              "showPoints": "never" if not points else "always", "pointSize": 3 if points else 4,
              "fillOpacity": 0, "lineInterpolation": "linear", "axisLabel": axis}
    if log:
        custom["scaleDistribution"] = {"type": "log", "log": 10}
    defaults = {"displayName": display, "custom": custom}
    if unit:
        defaults["unit"] = unit
    if min_ is not None:
        defaults["min"] = min_
    if max_ is not None:
        defaults["max"] = max_
    return {"type": "timeseries", "title": title, "description": desc, "gridPos": gp, "datasource": DS,
            "targets": [target(sql)], "fieldConfig": {"defaults": defaults, "overrides": []},
            "options": {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                        "tooltip": {"mode": "multi", "sort": "desc"}}}


def barchart(title, sql, gp, axis, unit=None, desc="", log=False, colors=None):
    """Bars per offered rate. `axis` labels the y-axis; the x-axis is the offered load."""
    custom = {"fillOpacity": 85, "lineWidth": 0, "axisLabel": axis}
    if log:
        custom["scaleDistribution"] = {"type": "log", "log": 10}
    overrides = [{"matcher": {"id": "byName", "options": name},
                  "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": c}}]}
                 for name, c in (colors or {}).items()]
    overrides.append({"matcher": {"id": "byName", "options": "rate"},
                      "properties": [{"id": "custom.axisLabel", "value": "offered load (requests per second)"}]})
    defaults = {"custom": custom}
    if unit:
        defaults["unit"] = unit
    return {"type": "barchart", "title": title, "description": desc, "gridPos": gp, "datasource": DS,
            "targets": [target(sql, fmt="table")],
            "fieldConfig": {"defaults": defaults, "overrides": overrides},
            "options": {"xField": "rate", "orientation": "vertical", "groupWidth": 0.75, "barWidth": 0.9,
                        "showValue": "never", "stacking": "none", "xTickLabelRotation": 0,
                        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                        "tooltip": {"mode": "multi", "sort": "none"}}}


def table(title, sql, gp, link=True, desc=""):
    overrides = []
    # the unit is in each header, so cells are plain numbers (no mixing of "596 ms" and "3 mins")
    for col, dec in TABLE_DECIMALS.items():
        overrides.append({"matcher": {"id": "byName", "options": col},
                          "properties": [{"id": "unit", "value": "none"}, {"id": "decimals", "value": dec},
                                         # wide enough for the whole header; the table scrolls sideways
                                         {"id": "custom.minWidth", "value": max(110, 8 * len(col) + 34)}]})
    overrides.append({"matcher": {"id": "byName", "options": "run"},
                      "properties": [{"id": "custom.width", "value": 300}]})
    for col in ("run_id", "experiment", "from_ms", "to_ms"):
        overrides.append({"matcher": {"id": "byName", "options": col},
                          "properties": [{"id": "custom.hidden", "value": True}]})
    if link:
        overrides.append({"matcher": {"id": "byName", "options": "run"}, "properties": [{"id": "links", "value": [{
            "title": "Open this run over time",
            "url": "/d/vllm-run/vllm-run-detail?var-experiment=${__data.fields.experiment}"
                   "&var-run=${__data.fields.run_id}&from=${__data.fields.from_ms}&to=${__data.fields.to_ms}"}]}]})
    for col, steps in (("queue: mean waiting (requests)", [("green", None), ("orange", 1), ("red", 5)]),
                       ("KV cache used, mean (%)", [("green", None), ("orange", 70), ("red", 90)])):
        overrides.append({"matcher": {"id": "byName", "options": col}, "properties": [
            {"id": "custom.cellOptions", "value": {"type": "color-text"}},
            {"id": "thresholds", "value": {"mode": "absolute",
                                           "steps": [{"color": c, "value": v} for c, v in steps]}}]})
    return {"type": "table", "title": title, "description": desc, "gridPos": gp, "datasource": DS,
            "targets": [target(sql, fmt="table")],
            "fieldConfig": {"defaults": {"custom": {"align": "auto", "filterable": True}}, "overrides": overrides},
            "options": {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}}}


def text(content, gp, title=""):
    return {"type": "text", "title": title, "gridPos": gp, "options": {"mode": "markdown", "content": content}}


def row(title, y, repeat=None, collapsed=False):
    r = {"type": "row", "title": title, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "collapsed": collapsed,
         "panels": []}
    if repeat:
        r["repeat"] = repeat
    return r


def var(name, label, sql, multi=False, include_all=False, hide=0):
    return {"type": "query", "name": name, "label": label, "datasource": DS, "query": sql,
            "definition": sql, "refresh": 1, "multi": multi, "includeAll": include_all, "hide": hide,
            "sort": 0, "current": {}, "options": []}


def dashboard(uid, title, panels, variables, time_from, time_to, desc):
    for i, p in enumerate(panels, 1):
        p["id"] = i
    return {"uid": uid, "title": title, "description": desc, "tags": ["vllm", "workload_sim"],
            "timezone": "utc", "schemaVersion": 39, "editable": True, "graphTooltip": 1,
            "time": {"from": time_from, "to": time_to}, "timepicker": {}, "refresh": "",
            "templating": {"list": variables}, "panels": panels, "annotations": {"list": []}}


LATENCY_COLS = [  # (summary metric, table label, unit, decimals)
    ("ttft", "TTFT", "ms", 0), ("tpot", "TPOT", "ms/token", 1), ("itl", "ITL", "ms", 1),
    ("e2e", "E2E", "ms", 0), ("norm_latency", "norm. latency", "ms/token", 1),
]
STATS = ("mean", "p50", "p90", "p95", "p99")
RUN_TABLE_SQL = """SELECT label AS run, scenario, rate AS [rate (req/s)], rep AS repeat,
  offered_rps AS [offered (req/s)], steady_requests_per_s AS [completed (req/s)],
  steady_output_tokens_per_s AS [output (tokens/s)],
  """ + ",\n  ".join(f"{m}_{s}_ms AS [{lbl} {s} ({unit})]" for m, lbl, unit, _ in LATENCY_COLS for s in STATS) + """,
  srv_running_mean AS [batch: mean running (requests)], srv_waiting_mean AS [queue: mean waiting (requests)],
  srv_waiting_max AS [queue: max waiting (requests)],
  srv_kv_cache_usage_mean * 100 AS [KV cache used, mean (%)], srv_kv_cache_usage_max * 100 AS [KV cache used, max (%)],
  srv_preemptions AS [preemptions (count)], srv_queue_mean_ms AS [vLLM queue wait, mean (ms)],
  [srv_queue_frac_over_1.0s] * 100 AS [waited > 1 s in vLLM queue (%)],
  srv_prefix_cache_hit_rate * 100 AS [prefix cache hit rate (%)],
  srv_resume_cache_hit_rate * 100 AS [resumed after preemption: KV still cached (%)],
  srv_kv_xfer_mean_ms AS [P/D KV transfer, mean (ms)], srv_kv_xfer_gb_per_s AS [P/D KV transfer (GB/s)],
  successes AS [completed (requests)], requests AS [sent (requests)], client_max_lag_ms AS [client max lag (ms)],
  run_id, experiment, from_ms, to_ms
FROM runs WHERE experiment = '$experiment' {extra} ORDER BY mode, scenario, rate, rep"""
TABLE_DECIMALS = {
    "rate (req/s)": 2, "offered (req/s)": 2, "completed (req/s)": 2, "output (tokens/s)": 0,
    **{f"{lbl} {s} ({unit})": dec for _, lbl, unit, dec in LATENCY_COLS for s in STATS},
    "batch: mean running (requests)": 1, "queue: mean waiting (requests)": 1, "queue: max waiting (requests)": 0,
    "KV cache used, mean (%)": 0, "KV cache used, max (%)": 0, "preemptions (count)": 0,
    "vLLM queue wait, mean (ms)": 0, "waited > 1 s in vLLM queue (%)": 1, "prefix cache hit rate (%)": 1,
    "resumed after preemption: KV still cached (%)": 1, "P/D KV transfer, mean (ms)": 1, "P/D KV transfer (GB/s)": 2,
    "completed (requests)": 0, "sent (requests)": 0, "client max lag (ms)": 1,
}


def shades(dark, light):
    """Bar colors for a mean / p50 / p99 chart: mean neutral grey, p50 light, p99 dark."""
    return {"mean": "#94a3b8", "p50": light, "p99": dark}

GUIDE = """**How to use.** Each row below is one scenario's rate sweep: bars are the **median over repeats**
at each offered rate. Latency charts show mean (grey), p50 (light) and p99 (dark); p90/p95 are in the table. The table at the bottom lists every run; click a run name to open it in
**vLLM run detail** and watch load, batch size, queue depth, KV cache and latency change *during* the run.
Select several runs there to overlay them (sweep runs share an elapsed-time axis: 00:01:30 = 90 s in).

Every bar chart: **x-axis = offered load (requests per second)**, y-axis label and unit on each chart.
*completed* is steady-state throughput (requests finished inside the measured interval ÷ its length); when the
server keeps up it matches *offered*. Batch / queue / KV cache are vLLM's own gauges (`num_requests_running`,
`num_requests_waiting`, `kv_cache_usage_perc`), averaged over the measured interval. With two GPUs (P/D or
data parallel) they are summed over both, so KV cache used goes up to 200%."""


def overview():
    panels = [text(GUIDE, {"x": 0, "y": 0, "w": 24, "h": 4})]
    y = 4
    panels.append(row("$scenario", y, repeat="scenario"))
    y += 1
    agg = "FROM sweep_agg WHERE experiment = '$experiment' AND scenario = '$scenario' ORDER BY rate"
    rate_lbl = "printf('%g req/s', rate) AS rate"

    def lat(m):  # mean, p50 and p99 columns of one latency metric
        return f"SELECT {rate_lbl}, {m}_mean_ms_med AS mean, {m}_p50_ms_med AS p50, {m}_p99_ms_med AS p99 {agg}"

    def gp(x):
        return {"x": x, "y": y, "w": 6, "h": 8}

    panels += [  # throughput and the scheduler's view
        barchart("Throughput: offered vs completed (requests/s)",
                 f"SELECT {rate_lbl}, offered_rps_med AS offered, steady_requests_per_s_med AS completed {agg}",
                 gp(0), "throughput (requests/s)", unit="reqps",
                 colors={"offered": "#94a3b8", "completed": "#2563eb"},
                 desc="If completed < offered, requests pile up in vLLM's queue: the server is past saturation."),
        barchart("Output throughput (tokens/s)",
                 f"SELECT {rate_lbl}, steady_output_tokens_per_s_med AS [output tokens/s] {agg}",
                 gp(6), "output tokens per second", unit="none", colors={"output tokens/s": "#2563eb"},
                 desc="Output tokens streamed inside the measured interval ÷ its length."),
        barchart("vLLM batch and queue: mean number of requests",
                 f"SELECT {rate_lbl}, srv_running_mean_med AS [batch (running)], "
                 f"srv_waiting_mean_med AS [queued (waiting)] {agg}",
                 gp(12), "requests (count)", unit="none",
                 colors={"batch (running)": "#2563eb", "queued (waiting)": "#be123c"}),
        barchart("vLLM queue wait: mean (ms)",
                 f"SELECT {rate_lbl}, srv_queue_mean_ms_med AS [mean wait] {agg}",
                 gp(18), "time in vLLM's queue", unit="ms", colors={"mean wait": "#be123c"},
                 desc="Mean time from arriving at vLLM to first being scheduled (includes warmup requests)."),
    ]
    y += 8
    panels += [  # latency: mean (grey), p50 (light), p99 (dark)
        barchart("Time to first token: mean, p50, p99 (log scale)", lat("ttft"), gp(0), "time to first token",
                 unit="ms", log=True, colors=shades("#1d4ed8", "#60a5fa"),
                 desc="Arrival → first token. Queue wait + prefill."),
        barchart("Time per output token: mean, p50, p99 (ms/token)", lat("tpot"), gp(6), "time per output token",
                 unit="ms", colors=shades("#0f766e", "#5eead4"),
                 desc="Per request: (e2e - ttft) / (tokens - 1), the average gap between its tokens."),
        barchart("Inter-token latency: mean, p50, p99 (ms)", lat("itl"), gp(12), "gap between tokens",
                 unit="ms", colors=shades("#7c3aed", "#c4b5fd"),
                 desc="Every gap between two consecutive tokens of a request, pooled (≈ one engine step). "
                      "p99 = decode stalls: a big prefill in the same step, or a preemption."),
        barchart("End-to-end latency: mean, p50, p99 (log scale)", lat("e2e"), gp(18), "end-to-end latency",
                 unit="ms", log=True, colors=shades("#9a3412", "#fdba74"),
                 desc="Arrival → last token. Dominated by output length: compare within a scenario."),
    ]
    y += 8
    panels += [  # normalized latency and KV-cache pressure
        barchart("Normalized latency: mean, p50, p99 (ms per output token, log scale)", lat("norm_latency"),
                 gp(0), "latency per output token", unit="ms", log=True, colors=shades("#a21caf", "#f0abfc"),
                 desc="e2e ÷ output tokens (the vLLM paper's metric); comparable across scenarios."),
        barchart("KV cache used: mean and max (%)",
                 f"SELECT {rate_lbl}, srv_kv_cache_usage_mean_med * 100 AS mean, "
                 f"srv_kv_cache_usage_max_med * 100 AS max {agg}",
                 gp(6), "KV-cache blocks in use (%)", unit="percent", colors={"mean": "#fdba74", "max": "#c2410c"},
                 desc="Near 100% vLLM must preempt running requests."),
        barchart("Preemptions (count per run)",
                 f"SELECT {rate_lbl}, srv_preemptions_med AS preemptions {agg}",
                 gp(12), "preemptions", unit="none", colors={"preemptions": "#be123c"},
                 desc="Requests evicted for lack of KV blocks and recomputed later. > 0 = real KV-cache pressure."),
        barchart("Requests that waited > 1 s in vLLM's queue (%)",
                 f"SELECT {rate_lbl}, [srv_queue_frac_over_1.0s_med] * 100 AS [waited > 1 s] {agg}",
                 gp(18), "requests (%)", unit="percent", colors={"waited > 1 s": "#be123c"},
                 desc="From vLLM's queue-time histogram (includes warmup requests)."),
    ]
    y += 8
    panels += [  # KV cache: what the prefix cache saved, and P/D KV transfers
        barchart("Prefix cache hit rate: new vs resumed requests (%)",
                 f"SELECT {rate_lbl}, srv_prefix_cache_hit_rate_med * 100 AS [new requests], "
                 f"srv_resume_cache_hit_rate_med * 100 AS [resumed after preemption] {agg}",
                 gp(0), "prompt tokens found in cache (%)", unit="percent",
                 colors={"new requests": "#fdba74", "resumed after preemption": "#c2410c"},
                 desc="Share of prompt tokens served from the prefix cache. New requests: our prompts are random, "
                      "so ~0 is expected. Resumed: how much of a preempted request's KV was still cached when it "
                      "came back (the rest is recomputed). Resumed needs our vLLM fork's counters."),
        barchart("Tokens re-queried by requests resuming after preemption",
                 f"SELECT {rate_lbl}, srv_resume_tokens_med AS [tokens] {agg}",
                 gp(6), "tokens", unit="short", colors={"tokens": "#be123c"},
                 desc="Prompt + already generated tokens of preempted requests, looked up again when they resume. "
                      "Times (1 - resumed hit rate) = tokens recomputed."),
        barchart("P/D: KV transfer time per request, mean (ms)",
                 f"SELECT {rate_lbl}, srv_kv_xfer_mean_ms_med AS [mean transfer] {agg}",
                 gp(12), "transfer time", unit="ms", colors={"mean transfer": "#7c3aed"},
                 desc="Disaggregated prefill/decode only: NIXL time to move one request's KV cache from the "
                      "prefill GPU to the decode GPU (decode server's vllm:nixl_xfer_time_seconds)."),
        barchart("P/D: KV transfer bandwidth (GB/s)",
                 f"SELECT {rate_lbl}, srv_kv_xfer_gb_per_s_med AS [bandwidth] {agg}",
                 gp(18), "GB/s", unit="none", colors={"bandwidth": "#7c3aed"},
                 desc="Bytes moved ÷ transfer time. Raw NVLink between these V100s measured ~45 GB/s "
                      "(bench/nixl_check.py)."),
    ]
    y += 8
    panels.append(row("All runs (click a run to open it over time)", y))
    y += 1
    panels.append(table("Runs", RUN_TABLE_SQL.format(extra=""), {"x": 0, "y": y, "w": 24, "h": 14}))
    variables = [
        var("experiment", "Experiment", "SELECT DISTINCT experiment FROM runs ORDER BY experiment"),
        var("scenario", "Scenario",
            "SELECT DISTINCT scenario FROM sweep_agg WHERE experiment = '$experiment' ORDER BY "
            "CASE scenario WHEN 'scheduler' THEN 0 WHEN 'baseline' THEN 1 WHEN 'kv_cache' THEN 2 ELSE 3 END",
            multi=True, include_all=True),
    ]
    d = dashboard("vllm-overview", "vLLM baseline: overview", panels, variables, "now-1h", "now",
                  "Rate sweeps per scenario and every run of an experiment.")
    d["timepicker"] = {"hidden": True}  # nothing on this page is plotted against time
    for v in d["templating"]["list"]:
        if v["name"] == "scenario":
            v["current"] = {"selected": True, "text": ["All"], "value": ["$__all"]}
    return d


def run_detail():
    w = "FROM windows JOIN runs USING (run_id) WHERE " + RUNS.replace("run_id", "windows.run_id") + " ORDER BY time"
    s = "FROM server JOIN runs USING (run_id) WHERE " + RUNS.replace("run_id", "server.run_id") + " ORDER BY time"
    r = "FROM requests JOIN runs USING (run_id) WHERE " + RUNS.replace("run_id", "requests.run_id")
    two = "${__field.name} · ${__field.labels.label}"
    panels = [
        text("**x-axis of every chart = time.** Sweep runs: **elapsed time since the run's first request** "
             "(hh:mm:ss; 00:01:30 = 90 s in; the time picker shows this as 2000-01-01). Replays: the **trace's "
             "own UTC time of day**. The first `warmup` seconds of a sweep are not in its summaries. Pick several "
             "runs in *Run* to overlay them; drag on a chart to zoom.",
             {"x": 0, "y": 0, "w": 24, "h": 2}),
        timeseries("Offered load: requests arriving per second", f"SELECT time, arrivals_per_s AS value, label {w}",
                   {"x": 0, "y": 2, "w": 12, "h": 8}, "arrivals (requests/s)", unit="reqps",
                   desc="Requests arriving in each window (Poisson for sweeps, the real trace for replay)."),
        timeseries("Completions: requests finishing per second", f"SELECT time, completions_per_s AS value, label {w}",
                   {"x": 12, "y": 2, "w": 12, "h": 8}, "completions (requests/s)", unit="reqps",
                   desc="Requests finishing in each window. Falls behind arrivals when vLLM saturates."),
        timeseries("vLLM batch size: requests running (count)", f"SELECT time, running AS value, label {s}",
                   {"x": 0, "y": 10, "w": 8, "h": 8}, "requests running", unit="none", min_=0,
                   desc="vLLM's num_requests_running, sampled every 1 s."),
        timeseries("vLLM queue depth: requests waiting (count)", f"SELECT time, waiting AS value, label {s}",
                   {"x": 8, "y": 10, "w": 8, "h": 8}, "requests waiting", unit="none", min_=0,
                   desc="vLLM's num_requests_waiting, sampled every 1 s: requests held in its scheduler. "
                        "Growing without bound = overloaded."),
        timeseries("KV cache used (% of blocks)", f"SELECT time, kv_cache_usage AS value, label {s}",
                   {"x": 16, "y": 10, "w": 8, "h": 8}, "KV cache used (%)", unit="percentunit", min_=0, max_=1,
                   desc="Fraction of KV-cache blocks in use. Near 100% vLLM preempts running requests."),
        timeseries("Time to first token: p50 and p99 per time window (log scale)",
                   f"SELECT windows.time, windows.ttft_p50_ms AS p50, windows.ttft_p99_ms AS p99, label {w}",
                   {"x": 0, "y": 18, "w": 12, "h": 9}, "time to first token", unit="ms", display=two, log=True,
                   desc="Requests grouped by arrival time into windows (10 s of run time for sweeps)."),
        timeseries("Time per output token: p50 and p99 per time window (ms per token)",
                   f"SELECT windows.time, windows.tpot_p50_ms AS p50, windows.tpot_p99_ms AS p99, label {w}",
                   {"x": 12, "y": 18, "w": 12, "h": 9}, "time per output token", unit="ms", display=two,
                   desc="Requests grouped by arrival time into windows (10 s of run time for sweeps)."),
        timeseries("Every request: time to first token, by arrival time (log scale)",
                   f"SELECT time, ttft_ms AS value, label {r} AND success ORDER BY time",
                   {"x": 0, "y": 27, "w": 12, "h": 9}, "time to first token", unit="ms", points=True, log=True,
                   desc="One dot per request, placed at its scheduled arrival time."),
        timeseries("Every request: end-to-end latency, by arrival time (log scale)",
                   f"SELECT time, e2e_ms AS value, label {r} AND success ORDER BY time",
                   {"x": 12, "y": 27, "w": 12, "h": 9}, "end-to-end latency", unit="ms", points=True, log=True,
                   desc="One dot per request, placed at its scheduled arrival time."),
        timeseries("End-to-end latency: p50 and p99 per time window (log scale)",
                   f"SELECT windows.time, windows.e2e_p50_ms AS p50, windows.e2e_p99_ms AS p99, label {w}",
                   {"x": 0, "y": 36, "w": 12, "h": 9}, "end-to-end latency", unit="ms", display=two, log=True,
                   desc="Requests grouped by arrival time into windows (10 s of run time for sweeps)."),
        timeseries("Normalized latency: p50 and p99 per time window (ms per output token, log scale)",
                   f"SELECT windows.time, windows.norm_latency_p50_ms AS p50, windows.norm_latency_p99_ms AS p99, "
                   f"label {w}",
                   {"x": 12, "y": 36, "w": 12, "h": 9}, "latency per output token", unit="ms", display=two, log=True,
                   desc="e2e ÷ output tokens, requests grouped by arrival time."),
        timeseries("Prefix cache hit rate, per 1 s sample (%)",
                   f"SELECT time, prefix_hit_rate AS [new requests], resume_hit_rate AS [resumed after preemption], "
                   f"label {s}",
                   {"x": 0, "y": 45, "w": 8, "h": 8}, "prompt tokens found in cache", unit="percentunit",
                   display=two, min_=0, max_=1, points=True,
                   desc="Share of prompt tokens looked up in each sample that were already cached. Only samples "
                        "with lookups are shown. Resumed needs our vLLM fork's counters."),
        timeseries("Preemptions per 1 s sample", f"SELECT time, preemptions AS value, label {s}",
                   {"x": 8, "y": 45, "w": 8, "h": 8}, "preemptions", unit="none", min_=0,
                   desc="Requests evicted for lack of KV blocks in each sample; compare with KV cache used."),
        timeseries("P/D: KV transfers per 1 s sample", f"SELECT time, kv_xfers AS value, label {s}",
                   {"x": 16, "y": 45, "w": 8, "h": 8}, "transfers", unit="none", min_=0,
                   desc="Disaggregated prefill/decode only: requests whose KV the decode GPU pulled over NIXL."),
        table("Selected runs", RUN_TABLE_SQL.format(extra="AND " + RUNS), {"x": 0, "y": 53, "w": 24, "h": 6},
              link=False),
    ]
    variables = [
        var("experiment", "Experiment", "SELECT DISTINCT experiment FROM runs ORDER BY experiment"),
        var("run", "Run",
            "SELECT run_id AS __value, label AS __text FROM runs WHERE experiment = '$experiment' "
            "ORDER BY mode, scenario, rate, rep", multi=True),
    ]
    return dashboard("vllm-run", "vLLM run detail", panels, variables, "1999-12-31T23:59:55.000Z", "2000-01-01T00:05:00.000Z",
                     "Load, vLLM scheduler state and latency over the course of selected runs.")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for name, d in (("overview", overview()), ("run_detail", run_detail())):
        (OUT / f"{name}.json").write_text(json.dumps(d, indent=2) + "\n")
        print(f"wrote {OUT / name}.json")
