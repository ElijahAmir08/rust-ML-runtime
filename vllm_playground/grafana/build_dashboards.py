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


def timeseries(title, sql, gp, unit=None, display="${__field.labels.label}", desc="", points=False,
               min_=None, max_=None, log=False, stack=False):
    custom = {"drawStyle": "points" if points else "line", "lineWidth": 1, "spanNulls": True,
              "showPoints": "never" if not points else "always", "pointSize": 3 if points else 4,
              "fillOpacity": 0, "lineInterpolation": "linear"}
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


def barchart(title, sql, gp, unit=None, desc="", log=False, colors=None):
    custom = {"fillOpacity": 85, "lineWidth": 0}
    if log:
        custom["scaleDistribution"] = {"type": "log", "log": 10}
    overrides = [{"matcher": {"id": "byName", "options": name},
                  "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": c}}]}
                 for name, c in (colors or {}).items()]
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
    for col, unit, dec in (("offered", "reqps", 2), ("done req/s", "reqps", 2), ("out tok/s", "none", 0),
                           ("TTFT p50", "ms", 0), ("TTFT p99", "ms", 0), ("TPOT p50", "ms", 1),
                           ("TPOT p99", "ms", 1), ("E2E p99", "ms", 0), ("batch", "none", 1),
                           ("queued", "none", 1), ("KV used", "percentunit", 0), ("vLLM queue", "ms", 0)):
        overrides.append({"matcher": {"id": "byName", "options": col},
                          "properties": [{"id": "unit", "value": unit}, {"id": "decimals", "value": dec}]})
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
    for col, steps in (("queued", [("green", None), ("orange", 1), ("red", 5)]),
                       ("KV used", [("green", None), ("orange", 0.7), ("red", 0.9)])):
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


RUN_TABLE_SQL = """SELECT label AS run, scenario, rate, rep,
  offered_rps AS offered, steady_requests_per_s AS [done req/s], steady_output_tokens_per_s AS [out tok/s],
  ttft_p50_ms AS [TTFT p50], ttft_p99_ms AS [TTFT p99], tpot_p50_ms AS [TPOT p50], tpot_p99_ms AS [TPOT p99],
  e2e_p99_ms AS [E2E p99], srv_running_mean AS batch, srv_waiting_mean AS queued,
  srv_kv_cache_usage_mean AS [KV used], srv_queue_mean_ms AS [vLLM queue], srv_preemptions AS preemptions,
  successes, requests, run_id, experiment, from_ms, to_ms
FROM runs WHERE experiment = '$experiment' {extra} ORDER BY mode, scenario, rate, rep"""

GUIDE = """**How to use.** Each row below is one scenario's rate sweep: bars are the **median over repeats**
at each offered rate. The table at the bottom lists every run; click a run name to open it in
**vLLM run detail** and watch load, batch size, queue depth, KV cache and latency change *during* the run.
Select several runs there to overlay them (sweep runs share an elapsed-time axis: 00:01:30 = 90 s in).

*done req/s* is steady-state throughput (requests finished inside the measured interval / its length);
when the server keeps up it matches *offered*. *batch* / *queued* / *KV used* are vLLM's own gauges
(`num_requests_running`, `num_requests_waiting`, `kv_cache_usage_perc`) averaged over the measured interval."""


def overview():
    panels = [text(GUIDE, {"x": 0, "y": 0, "w": 24, "h": 4})]
    y = 4
    panels.append(row("$scenario", y, repeat="scenario"))
    y += 1
    agg = "FROM sweep_agg WHERE experiment = '$experiment' AND scenario = '$scenario' ORDER BY rate"
    rate_lbl = "printf('%g/s', rate) AS rate"
    panels += [
        barchart("Throughput: offered vs completed (steady state)",
                 f"SELECT {rate_lbl}, offered_rps_med AS offered, steady_requests_per_s_med AS completed {agg}",
                 {"x": 0, "y": y, "w": 6, "h": 8}, unit="reqps",
                 colors={"offered": "#94a3b8", "completed": "#2563eb"},
                 desc="If completed < offered, requests pile up in vLLM's queue: the server is past saturation."),
        barchart("Time to first token", f"SELECT {rate_lbl}, ttft_p50_ms_med AS p50, ttft_p99_ms_med AS p99 {agg}",
                 {"x": 6, "y": y, "w": 6, "h": 8}, unit="ms", log=True,
                 colors={"p50": "#60a5fa", "p99": "#1d4ed8"}, desc="Log scale. Includes queueing + prefill."),
        barchart("Time per output token", f"SELECT {rate_lbl}, tpot_p50_ms_med AS p50, tpot_p99_ms_med AS p99 {agg}",
                 {"x": 12, "y": y, "w": 6, "h": 8}, unit="ms",
                 colors={"p50": "#5eead4", "p99": "#0f766e"},
                 desc="(e2e - ttft) / (tokens - 1). Grows when prefill chunks share steps with decodes."),
        barchart("vLLM scheduler state (mean over measured interval)",
                 f"SELECT {rate_lbl}, srv_running_mean_med AS [batch (running)], "
                 f"srv_waiting_mean_med AS [queued (waiting)] {agg}",
                 {"x": 18, "y": y, "w": 6, "h": 8},
                 colors={"batch (running)": "#2563eb", "queued (waiting)": "#be123c"}),
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
        text("Selected runs over time. Sweep runs are on an **elapsed-time axis** (00:01:30 = 90 s after the "
             "first request; the first `warmup` seconds are not in the summaries). The replay is on the "
             "**trace's own time of day**. Pick several runs in *Run* to overlay them. Drag on any graph to zoom.",
             {"x": 0, "y": 0, "w": 24, "h": 2}),
        timeseries("Offered load (arrivals per second)", f"SELECT time, arrivals_per_s AS value, label {w}",
                   {"x": 0, "y": 2, "w": 12, "h": 8}, unit="reqps",
                   desc="Requests arriving in each window (Poisson for sweeps, the real trace for replay)."),
        timeseries("Completions per second", f"SELECT time, completions_per_s AS value, label {w}",
                   {"x": 12, "y": 2, "w": 12, "h": 8}, unit="reqps",
                   desc="Requests finishing in each window. Falls behind arrivals when vLLM saturates."),
        timeseries("vLLM batch size (num_requests_running)", f"SELECT time, running AS value, label {s}",
                   {"x": 0, "y": 10, "w": 8, "h": 8}, min_=0),
        timeseries("vLLM queue depth (num_requests_waiting)", f"SELECT time, waiting AS value, label {s}",
                   {"x": 8, "y": 10, "w": 8, "h": 8}, min_=0,
                   desc="Requests held in vLLM's scheduler. Growing without bound = overloaded."),
        timeseries("KV cache used", f"SELECT time, kv_cache_usage AS value, label {s}",
                   {"x": 16, "y": 10, "w": 8, "h": 8}, unit="percentunit", min_=0, max_=1,
                   desc="Fraction of KV-cache blocks in use. Near 100% vLLM preempts running requests."),
        timeseries("Time to first token (per window, by arrival)",
                   f"SELECT windows.time, windows.ttft_p50_ms AS p50, windows.ttft_p99_ms AS p99, label {w}",
                   {"x": 0, "y": 18, "w": 12, "h": 9}, unit="ms", display=two, log=True),
        timeseries("Time per output token (per window, by arrival)",
                   f"SELECT windows.time, windows.tpot_p50_ms AS p50, windows.tpot_p99_ms AS p99, label {w}",
                   {"x": 12, "y": 18, "w": 12, "h": 9}, unit="ms", display=two),
        timeseries("Every request: time to first token", f"SELECT time, ttft_ms AS value, label {r} AND success ORDER BY time",
                   {"x": 0, "y": 27, "w": 12, "h": 9}, unit="ms", points=True, log=True,
                   desc="One dot per request, at its arrival time."),
        timeseries("Every request: end-to-end latency", f"SELECT time, e2e_ms AS value, label {r} AND success ORDER BY time",
                   {"x": 12, "y": 27, "w": 12, "h": 9}, unit="ms", points=True, log=True),
        table("Selected runs", RUN_TABLE_SQL.format(extra="AND " + RUNS), {"x": 0, "y": 36, "w": 24, "h": 6},
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
