"""Polls a vLLM server's Prometheus /metrics endpoint during a run.

This shows what the client can't see from outside: how many requests vLLM is running (its batch) and
holding in its waiting queue, KV-cache usage, preemptions, and vLLM's own queue-time histogram.
"""
import asyncio
import math
import time
from collections import defaultdict

import aiohttp
import numpy as np
import pandas as pd

GAUGES = {
    "running": "vllm:num_requests_running",  # requests in the current batch
    "waiting": "vllm:num_requests_waiting",  # requests queued in vLLM's scheduler
    "kv_cache_usage": "vllm:kv_cache_usage_perc",  # fraction of KV-cache blocks in use, 0..1
}
QUEUE_HIST = "vllm:request_queue_time_seconds"
PREEMPTIONS = "vllm:num_preemptions_total"
PREFIX_HITS, PREFIX_QUERIES = "vllm:prefix_cache_hits_total", "vllm:prefix_cache_queries_total"


def parse_prometheus(text: str) -> dict:
    """Prometheus text format -> {(name, le): value}, summed over every other label (model, engine, ...).

    `le` is the bucket bound for histogram _bucket series and None for everything else.
    """
    out = defaultdict(float)
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        series, _, value = line.rpartition(" ")
        name, _, labels = series.partition("{")
        le = labels.split('le="', 1)[1].split('"', 1)[0] if 'le="' in labels else None
        try:
            out[(name, le)] += float(value)
        except ValueError:
            pass
    return out


def histogram_quantile(q: float, buckets: list[tuple[float, float]]) -> float | None:
    """Quantile from cumulative (upper_bound, count) buckets, interpolating linearly inside a bucket
    (same method as Prometheus' histogram_quantile)."""
    total = buckets[-1][1] if buckets else 0
    if total <= 0:
        return None
    rank = q * total
    prev_ub, prev_count = 0.0, 0.0
    for ub, count in buckets:
        if count >= rank:
            if math.isinf(ub):
                return prev_ub
            return prev_ub + (ub - prev_ub) * (rank - prev_count) / max(count - prev_count, 1e-12)
        prev_ub, prev_count = ub, count
    return prev_ub


class ServerMonitor:
    """Samples vLLM's gauges every `interval` seconds and snapshots its counters/histograms at the
    start and end of a run, so they can be differenced.

    Use as `async with ServerMonitor(url) as mon:` around LoadGenerator.run().
    """

    def __init__(self, base_url: str, interval: float = 1.0):
        self.url = base_url.rstrip("/") + "/metrics"
        self.interval = interval
        self.samples: list[tuple[float, float, float, float]] = []  # (monotonic time, running, waiting, kv)
        self.start_snap = self.end_snap = None

    async def _scrape(self) -> dict:
        async with self.session.get(self.url) as resp:
            resp.raise_for_status()
            return parse_prometheus(await resp.text())

    async def _poll(self):
        while True:
            try:
                snap = await self._scrape()
                self.samples.append((time.monotonic(), *(snap.get((m, None), math.nan) for m in GAUGES.values())))
            except (aiohttp.ClientError, asyncio.TimeoutError):
                pass  # a missed sample is fine; don't let monitoring break the run
            await asyncio.sleep(self.interval)

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        self.start_snap = await self._scrape()
        self._task = asyncio.create_task(self._poll())
        return self

    async def __aexit__(self, *exc):
        self._task.cancel()
        try:
            self.end_snap = await self._scrape()
        finally:
            await self.session.close()

    def timeseries(self, start: float) -> pd.DataFrame:
        """Gauge samples with t = seconds after `start` (the LoadGenerator's start time)."""
        df = pd.DataFrame(self.samples, columns=["t", *GAUGES])
        df["t"] -= start
        return df

    def summary(self, start: float, warmup: float) -> dict:
        """Gauge stats over samples after warmup, plus counter/histogram deltas over the whole run.

        The deltas (queue time, preemptions, prefix cache) cover every request in the run, including
        warmup ones, because vLLM only exposes them in aggregate.
        """
        out = {}
        ts = self.timeseries(start)
        ts = ts[ts.t >= warmup]
        for g in GAUGES:
            v = ts[g].dropna().to_numpy()
            if len(v):
                out |= {f"srv_{g}_mean": v.mean(), f"srv_{g}_p50": np.median(v),
                        f"srv_{g}_p95": np.percentile(v, 95), f"srv_{g}_max": v.max()}

        if self.start_snap is None or self.end_snap is None:
            return out

        def delta(name, le=None):
            return self.end_snap.get((name, le), 0.0) - self.start_snap.get((name, le), 0.0)

        n = delta(QUEUE_HIST + "_count")
        if n > 0:
            out["srv_queue_requests"] = n
            out["srv_queue_mean_ms"] = delta(QUEUE_HIST + "_sum") / n * 1000
            # vLLM's smallest bucket is 0.3 s, so interpolated percentiles (histogram_quantile) would be
            # guesses at normal load. Report exact bucket fractions instead.
            for le in ("0.3", "1.0"):
                if (QUEUE_HIST + "_bucket", le) in self.end_snap:
                    out[f"srv_queue_frac_over_{le}s"] = 1 - delta(QUEUE_HIST + "_bucket", le) / n
        out["srv_preemptions"] = delta(PREEMPTIONS)
        queries = delta(PREFIX_QUERIES)
        if queries > 0:
            out["srv_prefix_cache_hit_rate"] = delta(PREFIX_HITS) / queries
        return out
