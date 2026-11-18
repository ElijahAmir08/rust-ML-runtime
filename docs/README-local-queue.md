# Rust/PyO3 queue experiments

The goal is to compare Python's `collections.deque` with a Rust FIFO queue called
through PyO3. The experiments measure individual operations and batches to see
how the cost of passing data between Python and Rust affects performance.
They run without installing vLLM or loading a model.

## Build the extension

The commands below use Windows PowerShell and run from the repository root.
The experiments were run with Python 3.14.3, Rust 1.99.1, Maturin 1.16.0, and
PyO3 0.29.3. Python and Rust/Cargo must be installed first.

```powershell
python -m venv ffi_probe/.venv
.\ffi_probe\.venv\Scripts\python.exe -m pip install maturin==1.16.0
$env:VIRTUAL_ENV = (Resolve-Path ffi_probe/.venv).Path
$env:CARGO_TARGET_DIR = Join-Path (Get-Location).Path 'target\ffi-probe'
.\ffi_probe\.venv\Scripts\python.exe -m maturin develop --manifest-path ffi_probe/Cargo.toml --release --locked
```

Maturin builds the Rust extension and installs it into the Python environment.
`--release` uses an optimized build, while `--locked` keeps the dependency
versions recorded in `Cargo.lock`.

## Run correctness tests

Run the tests before measuring performance:

```powershell
cargo test --manifest-path rust_scheduler/Cargo.toml --release --locked --target-dir target/scheduler
.\ffi_probe\.venv\Scripts\python.exe -m unittest discover -s ffi_probe/tests -v
.\ffi_probe\.venv\Scripts\python.exe -m unittest discover -s benchmarks/tests -v
```

The tests check FIFO order, request fields, empty queues, repeated operations,
batch handling, and invalid inputs. They also check the timing calculations in
`simulate_fifo()` and compare mixed queue operations against `collections.deque`.

## Queue interface

Each request contains `(id, arrival_ms, duration_ms)`. FIFO follows insertion
order, regardless of the arrival timestamp.

```python
from ffi_probe import PyRequestQueue

queue = PyRequestQueue()
queue.enqueue(id=1, arrival_ms=0, duration_ms=50)
queue.enqueue_batch([(2, 3, 60), (3, 5, 66)])
assert len(queue) == 3
assert queue.dequeue() == (1, 0, 50)
assert queue.dequeue_batch(10) == [(2, 3, 60), (3, 5, 66)]
assert queue.dequeue() is None
```

An empty single dequeue returns `None`; an empty batch dequeue returns `[]`.
A batch removes up to the requested count. Request fields must fit in `u64`,
and invalid input conversion rejects an enqueue batch before changing the queue.

## Run the benchmarks

Run the experiment twice in separate Python processes, changing the case-order
seed for the second run. Choose unused output directories; results are not
overwritten.

```powershell
.\ffi_probe\.venv\Scripts\python.exe benchmarks/benchmark_local_queue.py --output benchmarks/results/reproduction-a
.\ffi_probe\.venv\Scripts\python.exe benchmarks/benchmark_local_queue.py --seed 264 --output benchmarks/results/reproduction-b
```

The benchmark checks that the installed extension matches the release library
at `target/ffi-probe/release/ffi_probe.dll` using a file hash. If the build is in
a different directory, supply its path with `--release-library`.

Default settings:

- Queue sizes: 100, 1,000, 10,000, and 100,000 requests.
- Batch sizes: 1, 8, 64, 256, 1,024, and the whole queue. Sizes larger than the
  queue are clipped, and duplicate cases are removed.
- Two warm-up rounds and nine measured rounds per case, in shuffled order.
- Repeated fill/drain cycles targeting 5 ms for the faster phase, with a limit
  of 10,000 cycles per sample. Actual times and cycle counts are saved.

Each cycle fills an empty queue and drains it, measuring enqueue and dequeue
separately. The benchmark compares these interfaces:

| Modes | What is measured |
| --- | --- |
| `deque_single`, `rust_single` | One queue call per request. |
| `deque_batch`, `rust_batch` | Batches using `deque.extend()` or the PyO3 batch methods. Deque batch removal uses a Python loop. |
| `deque_copy_single`, `deque_copy_batch` | Additional deque cases that build new tuples during enqueue and dequeue to examine allocation costs. |

Batch inputs have two forms: `prepared` creates the batch lists before timing,
while `sliced` includes creating each slice during enqueue timing. This makes
the cost of preparing batches visible.

Request creation, queue construction, correctness checks, and final result
destruction are outside the timers. Queue growth, data conversion, Python loop
work, and output creation are included. Every cycle checks the returned fields,
FIFO order, and final queue length. Cyclic garbage collection is disabled during
samples; reference counting remains active.

## Results and interpretation

Each output directory contains:

- `environment.json`: software versions, machine information, parameters, and
  source/build hashes.
- `raw.csv`: individual samples, including separately marked warm-ups.
- `summary.csv` and `summary.md`: medians, quartiles, and variability.
- `comparisons.csv`: ratios of median times. A `deque_*_over_rust` ratio above
  one favors Rust; `rust_single_over_rust` compares against individual Rust calls.

Times are reported in **nanoseconds per request**, including repeated cycles.
Lower is faster. Warm-ups are excluded from the summaries. Quartiles describe
variation between trials and are not confidence intervals.

An important distinction is that deque stores references to Python objects,
while the Rust interface converts numeric values and creates Python objects on
return. The tuple-copy cases help examine allocation costs, but still share
Python integers and do not reproduce PyO3 conversion exactly. Batching reduces
the number of calls without removing per-request conversion costs.

These are queue fill/drain microbenchmarks on one machine. They do not measure
vLLM inference throughput or token latency. The measured results and their
implications are discussed in the [experiment report](../docs/local-queue-report.md).