import timeit
from statistics import median
import ffi_probe


# Create mock request size lists first to not measure the time creating these
empty_ids = []
small_ids = list(range(10))
large_ids = list(range(1000))


def python_ping():
    return 1

def rust_ping():
    return ffi_probe.ping()

def count_empty():
    return ffi_probe.count_requests(empty_ids)


def count_small():
    return ffi_probe.count_requests(small_ids)


def count_large():
    return ffi_probe.count_requests(large_ids)

def python_count_empty():
    return len(empty_ids)


def python_count_small():
    return len(small_ids)


def python_count_large():
    return len(large_ids)

def benchmark(name, function, calls = 100_000):
    results = timeit.repeat(function, number = calls, repeat=5)
    nanosecs_per_call = median(results) * 1e9 / calls

    print(f"{name}: {nanosecs_per_call:.1f} ns/call")


benchmark("Python function", python_ping)
benchmark("Rust function via PyO3", ffi_probe.ping)


benchmark("Rust count (0 IDs)", count_empty, 10_000)
benchmark("Rust count (10 IDs)", count_small, 10_000)
benchmark("Rust count (1000 IDs)", count_large, 10_000)
benchmark("Python count (0 IDs)", python_count_empty, 10_000)
benchmark("Python count (10 IDs)", python_count_small, 10_000)
benchmark("Python count (1000 IDs)", python_count_large, 10_000)