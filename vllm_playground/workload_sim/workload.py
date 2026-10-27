from abc import ABC, abstractmethod

import numpy as np
import pandas as pd

from .request import Request


def load_trace(path, start=None, end=None) -> pd.DataFrame:
    """Load the Azure LLM trace.

    Without a window only the token columns are read. With start/end ("YYYY-MM-DD HH:MM", UTC)
    only rows in [start, end) are kept and TIMESTAMP is parsed.
    """
    if start is None:
        return pd.read_csv(path, usecols=["ContextTokens", "GeneratedTokens"])
    df = pd.read_csv(path, dtype={"TIMESTAMP": str})
    df = df[(df.TIMESTAMP >= start) & (df.TIMESTAMP < end)]  # ISO strings sort chronologically
    df["TIMESTAMP"] = pd.to_datetime(df.TIMESTAMP, format="ISO8601")
    return df


def scenario_rows(trace: pd.DataFrame, scenario: str, short_ctx: int, long_ctx: int) -> pd.DataFrame:
    """Select the trace rows a scenario samples request lengths from."""
    if scenario == "baseline":
        return trace
    if scenario == "kv_cache":
        return trace[trace.ContextTokens >= long_ctx]
    if scenario == "scheduler":
        return trace[trace.ContextTokens <= short_ctx]
    raise ValueError(f"unknown scenario: {scenario}")


class Workload(ABC):
    """A list of requests sorted by arrival time."""

    def __init__(self, max_model_len: int, seed: int = 0):
        self.max_model_len = max_model_len
        self.rng = np.random.default_rng(seed)

    @abstractmethod
    def requests(self) -> list[Request]: ...

    def _build(self, arrivals, prompt_tokens, output_tokens) -> list[Request]:
        """Turn parallel arrays into Requests, clipping lengths to fit the model's context."""
        requests = []
        for i, (t, p, o) in enumerate(zip(arrivals, prompt_tokens, output_tokens)):
            p = int(min(max(p, 1), self.max_model_len - 1))
            o = int(min(max(o, 1), self.max_model_len - p))
            requests.append(Request(i, float(t), p, o))
        return requests


class PoissonWorkload(Workload):
    """Poisson arrivals at a fixed rate, with lengths sampled from trace rows."""

    def __init__(self, rows: pd.DataFrame, rate: float, duration: float, max_model_len: int, seed: int = 0):
        super().__init__(max_model_len, seed)
        self.rows, self.rate, self.duration = rows, rate, duration

    def requests(self) -> list[Request]:
        gaps = self.rng.exponential(1 / self.rate, size=int(self.rate * self.duration * 1.5) + 10)
        arrivals = np.cumsum(gaps)
        arrivals = arrivals[arrivals < self.duration]
        sample = self.rows.sample(len(arrivals), replace=True, random_state=self.rng)
        return self._build(arrivals, sample.ContextTokens, sample.GeneratedTokens)


class ReplayWorkload(Workload):
    """Replays a trace window with its real timestamps, thinned by rate_scale and compressed by speedup."""

    def __init__(self, window: pd.DataFrame, start: str, speedup: float, rate_scale: float,
                 max_model_len: int, seed: int = 0):
        super().__init__(max_model_len, seed)
        self.window, self.speedup, self.rate_scale = window, speedup, rate_scale
        self.start = pd.Timestamp(start, tz="UTC")

    def requests(self) -> list[Request]:
        kept = self.window[self.rng.random(len(self.window)) < self.rate_scale]
        arrivals = (kept.TIMESTAMP - self.start).dt.total_seconds() / self.speedup
        return self._build(arrivals, kept.ContextTokens, kept.GeneratedTokens)
