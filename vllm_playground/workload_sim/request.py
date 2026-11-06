from dataclasses import dataclass, field


@dataclass(frozen=True)
class Request:
    """One inference request in a workload."""
    id: int
    arrival_time: float  # seconds after the start of the run
    prompt_tokens: int
    output_tokens: int


@dataclass
class RequestResult:
    """Timing of one request. All times are seconds after its scheduled arrival."""
    request: Request
    success: bool = False
    ttft: float | None = None
    e2e: float | None = None
    token_times: list[float] = field(default_factory=list)  # arrival time of each streamed chunk
    received_tokens: int = 0
    error: str = ""

    @property
    def itls(self) -> list[float]:
        """Inter-token latencies: gaps between consecutive streamed chunks."""
        return [b - a for a, b in zip(self.token_times, self.token_times[1:])]

    @property
    def tpot(self) -> float | None:
        """Time per output token after the first: (e2e - ttft) / (output tokens - 1).

        Unlike ITL this is per token even when a chunk carries several tokens. Uses the server's
        usage count, falling back to the number of chunks if usage wasn't reported.
        """
        n = self.received_tokens or len(self.token_times)
        if not self.success or n < 2:
            return None
        return (self.e2e - self.ttft) / (n - 1)
