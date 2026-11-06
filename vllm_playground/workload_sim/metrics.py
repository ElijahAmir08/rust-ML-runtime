import numpy as np
import pandas as pd

from .request import RequestResult

QUANTILES = (50, 90, 95, 99)


def _stats(name: str, values) -> dict:
    """Mean and p50/p90/p95/p99 of values, in milliseconds."""
    if len(values) == 0:
        return {}
    ms = np.asarray(values) * 1000
    return {f"{name}_mean_ms": ms.mean(),
            **{f"{name}_p{q}_ms": np.percentile(ms, q) for q in QUANTILES}}


class RunMetrics:
    """Per-request results of one run, plus a summary that skips requests arriving during warmup."""

    def __init__(self, results: list[RequestResult], warmup: float = 0.0, max_lag: float = 0.0,
                 end: float | None = None, start_unix: float | None = None):
        self.results = results
        self.start_unix = start_unix
        self.warmup = warmup
        self.max_lag = max_lag  # worst client dispatch lag, from LoadGenerator
        self.end = end  # end of the measured interval [warmup, end), normally warmup + duration

    def steady_state(self) -> dict:
        """Throughput inside the measured interval [warmup, end): requests completed and tokens streamed
        in it, divided by its length. Counts work on any request (warmup arrivals still running too), so
        unlike the arrival-to-last-completion window it isn't diluted by the drain after arrivals stop.
        If the server keeps up, steady_requests_per_s ~= the offered rate."""
        if self.end is None or self.end <= self.warmup:
            return {}
        span = self.end - self.warmup
        done, tokens = 0, 0.0
        for r in self.results:
            if not r.token_times:
                continue
            t0 = r.request.arrival_time
            if r.success and self.warmup <= t0 + r.e2e < self.end:
                done += 1
            per_chunk = (r.received_tokens / len(r.token_times)) if r.received_tokens else 1.0
            tokens += per_chunk * sum(self.warmup <= t0 + t < self.end for t in r.token_times)
        return {"steady_window_s": span, "steady_requests_per_s": done / span, "steady_output_tokens_per_s": tokens / span}

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([{
            "id": r.request.id,
            "arrival_time": r.request.arrival_time,
            "prompt_tokens": r.request.prompt_tokens,
            "output_tokens": r.request.output_tokens,
            "received_tokens": r.received_tokens,
            "success": r.success,
            "ttft": r.ttft,
            "e2e": r.e2e,
            "tpot": r.tpot,
            "mean_itl": np.mean(r.itls) if r.itls else None,
            "error": r.error,
        } for r in self.results])

    def to_csv(self, path) -> None:
        self.to_dataframe().to_csv(path, index=False)

    def summary(self) -> dict:
        measured = [r for r in self.results if r.request.arrival_time >= self.warmup]
        ok = [r for r in measured if r.success]
        base = {"start_unix": self.start_unix, "requests": len(measured), "successes": len(ok), "client_max_lag_ms": self.max_lag * 1000}
        if not ok:
            return base

        # Measurement window: first measured arrival to last completion.
        first = min(r.request.arrival_time for r in measured)
        last = max(r.request.arrival_time + r.e2e for r in ok)
        window = last - first
        return {
            **base,
            "window_s": window,
            "offered_rps": len(measured) / (max(r.request.arrival_time for r in measured) - first or 1),
            **self.steady_state(),
            "requests_per_s": len(ok) / window,
            "output_tokens_per_s": sum(r.received_tokens for r in ok) / window,
            "prompt_tokens_per_s": sum(r.request.prompt_tokens for r in ok) / window,
            **_stats("ttft", [r.ttft for r in ok]),
            **_stats("tpot", [r.tpot for r in ok if r.tpot is not None]),
            **_stats("itl", [gap for r in ok for gap in r.itls]),
            **_stats("e2e", [r.e2e for r in ok]),
        }
