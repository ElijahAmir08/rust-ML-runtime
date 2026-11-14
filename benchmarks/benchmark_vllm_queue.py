from time import perf_counter_ns
from statistics import median

from vllm.v1.core.sched.request_queue import FCFSRequestQueue

def run_trial(count):
    requests = list(range(count))
    queue = FCFSRequestQueue()

    start_time = perf_counter_ns()

    for request in requests:
        queue.add_request(request)

    enqueue_time = perf_counter_ns() - start_time

    removed = []
    start_time = perf_counter_ns()

    for _ in range(count):
        removed.append(queue.pop_request())

    dequeue_time = perf_counter_ns() - start_time

    assert removed == requests
    assert len(queue) == 0
    return enqueue_time, dequeue_time
for count in [1_000, 10_000, 100_000]:
    results = []

    for _ in range(6):
        results.append(run_trial(count))

    results = results[1:] # Ignoring the first run as a warm-up

    enqueue_times = [result[0] for result in results]
    dequeue_times = [result[1] for result in results]

    print(f"Requests: {count}")
    print(f"Median enqueue time: {median(enqueue_times) / 1_000_000:.3f} ms")
    print(f"Median dequeue time: {median(dequeue_times) / 1_000_000:.3f} ms")
    print()