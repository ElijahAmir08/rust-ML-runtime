import gc
import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "benchmark_local_queue.py"
SPEC = importlib.util.spec_from_file_location("benchmark_local_queue", SCRIPT)
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


class LocalBenchmarkTests(unittest.TestCase):
    def test_all_runners_and_partial_batches_preserve_requests(self):
        requests = [(index, 100 - index, index % 3) for index in range(17)]
        for case in benchmark.make_cases([len(requests)], [1, 4, 64]):
            with self.subTest(case=case):
                prepared = list(benchmark.sliced_batches(requests, case[2]))
                enqueue_ns, dequeue_ns = benchmark.run_sample(case, requests, prepared, 3)
                self.assertGreater(enqueue_ns, 0)
                self.assertGreater(dequeue_ns, 0)

    def test_sample_restores_gc_after_correctness_failure(self):
        before = gc.isenabled()
        with self.assertRaises(AssertionError):
            benchmark.run_sample((2, "deque_single", 1, "individual"), [(1, 2, 3)], None, 1)
        self.assertEqual(gc.isenabled(), before)

    def test_summary_ignores_warmups_and_reports_inclusive_quartiles(self):
        rows = []
        for stage, value in [("warmup", 1000), ("measured", 10), ("measured", 20), ("measured", 30)]:
            rows.append({"stage": stage, "queue_size": 1, "mode": "rust_single",
                         "batch_size": 1, "input_layout": "individual", "operation": "enqueue",
                         "ns_per_request": value})
        row = benchmark.summarize(rows)[0]
        self.assertEqual(row["trials"], 3)
        self.assertEqual(row["median_ns_per_request"], 20)
        self.assertEqual(row["q1_ns_per_request"], 15)
        self.assertEqual(row["q3_ns_per_request"], 25)


if __name__ == "__main__":
    unittest.main()
