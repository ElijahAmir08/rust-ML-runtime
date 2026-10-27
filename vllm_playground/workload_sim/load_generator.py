import asyncio
import time

from .client import VLLMClient
from .request import Request, RequestResult


class LoadGenerator:
    """Open-loop dispatcher: fires each request at its scheduled time and never waits on earlier ones,
    so any queueing happens inside vllm's scheduler rather than in the client."""

    def __init__(self, client: VLLMClient, lag_warning: float = 0.1):
        self.client = client
        self.lag_warning = lag_warning
        self.max_lag = 0.0  # worst delay between a request's scheduled and actual send time

    async def run(self, requests: list[Request]) -> list[RequestResult]:
        start = time.monotonic()
        self.max_lag = 0.0
        tasks = []
        for req in requests:
            due = start + req.arrival_time  # absolute target, so small sleep errors don't accumulate
            delay = due - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                self.max_lag = max(self.max_lag, -delay)
            tasks.append(asyncio.create_task(self.client.send(req, due)))
        results = await asyncio.gather(*tasks)

        if self.max_lag > self.lag_warning:
            print(f"WARNING: client fell up to {self.max_lag * 1000:.0f} ms behind schedule; "
                  "the client may be the bottleneck")
        return results
