import numpy as np
import pandas as pd

from .request import RequestResult


def _stats(name: str, values) -> dict:
    """Mean and p50/p90/p99 of values, in milliseconds."""
    if len(values) == 0:
        return {}
    ms = np.asarray(values) * 1000
    return {f"{name}_mean_ms": ms.mean(),
            **{f"{name}_p{q}_ms": np.percentile(ms, q) for q in (50, 90, 99)}}


class RunMetrics:
    """Per-request results of one run, plus a summary that skips requests arriving during warmup."""

    def __init__(self, results: list[RequestResult], warmup: float = 0.0):
        self.results = results
        self.warmup = warmup

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
            "mean_itl": np.mean(r.itls) if r.itls else None,
            "error": r.error,
        } for r in self.results])

    def to_csv(self, path) -> None:
        self.to_dataframe().to_csv(path, index=False)

    def summary(self) -> dict:
        measured = [r for r in self.results if r.request.arrival_time >= self.warmup]
        ok = [r for r in measured if r.success]
        if not ok:
            return {"requests": len(measured), "successes": 0}

        # Measurement window: first measured arrival to last completion.
        first = min(r.request.arrival_time for r in measured)
        last = max(r.request.arrival_time + r.e2e for r in ok)
        window = last - first
        return {
            "requests": len(measured),
            "successes": len(ok),
            "requests_per_s": len(ok) / window,
            "output_tokens_per_s": sum(r.received_tokens for r in ok) / window,
            **_stats("ttft", [r.ttft for r in ok]),
            **_stats("itl", [gap for r in ok for gap in r.itls]),
            **_stats("e2e", [r.e2e for r in ok]),
        }
