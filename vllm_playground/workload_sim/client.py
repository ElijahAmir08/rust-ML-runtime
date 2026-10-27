import asyncio
import json
import random
import time

import aiohttp

from .request import Request, RequestResult


class VLLMClient:
    """Streams completions from a vllm OpenAI-compatible server and times each response.

    Prompts are random token ids of the exact requested length, so no tokenizer is needed and
    requests don't accidentally share cached prefixes. ignore_eos makes vllm generate exactly
    max_tokens, matching the trace's output length.
    """

    def __init__(self, base_url: str, model: str, token_id_range=(1000, 20000), seed: int = 0):
        self.url = base_url.rstrip("/") + "/v1/completions"
        self.model = model
        self.token_ids = range(*token_id_range)
        self.rng = random.Random(seed)
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=0),  # no cap on concurrent requests (open loop)
            timeout=aiohttp.ClientTimeout(total=None),
        )
        return self

    async def __aexit__(self, *exc):
        await self.session.close()

    def _payload(self, req: Request) -> dict:
        return {
            "model": self.model,
            "prompt": self.rng.choices(self.token_ids, k=req.prompt_tokens),
            "max_tokens": req.output_tokens,
            "ignore_eos": True,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

    async def send(self, req: Request, scheduled_at: float) -> RequestResult:
        """Send req and time it from scheduled_at (a time.monotonic() value), not from when it was sent."""
        result = RequestResult(req)
        try:
            async with self.session.post(self.url, json=self._payload(req)) as resp:
                if resp.status != 200:
                    result.error = f"HTTP {resp.status}: {(await resp.text())[:200]}"
                    return result
                async for line in resp.content:
                    if not line.startswith(b"data: ") or line.strip() == b"data: [DONE]":
                        continue
                    chunk = json.loads(line[6:])
                    if chunk.get("choices"):
                        result.token_times.append(time.monotonic() - scheduled_at)
                    if chunk.get("usage"):
                        result.received_tokens = chunk["usage"]["completion_tokens"]
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            result.error = repr(e)
            return result

        if result.token_times:
            result.success = True
            result.ttft, result.e2e = result.token_times[0], result.token_times[-1]
        return result
