use pyo3::prelude::*;

// A Python module implemented in Rust.
// The pymodule here tells PyO3 that this module
// is to be exposed to python
#[pymodule]
mod ffi_probe {
    use pyo3::prelude::*;
    use rust_scheduler::{Request, RequestQueue};

    // Exposes a Rust struct as a python class
    #[pyclass]
    struct PyRequestQueue {
        //inner is common Rust naming for fields that store an object being wrapped
        inner: RequestQueue,
    }

    #[pymethods]
    impl PyRequestQueue {
        // new exposes this as a constructor for python to use when an instance is created
        #[new]
        fn new() -> Self {
            Self {
                inner: RequestQueue::new(),
            }
        }

        //Add a request to the back of Rust queue
        fn enqueue(&mut self, id: u64, arrival_ms: u64, duration_ms: u64) {
            self.inner.enqueue(Request {
                id,
                arrival_ms,
                duration_ms,
            });
        }

        fn dequeue(&mut self) -> Option<(u64, u64, u64)> {
            //Turn the popped request into a tuple for Python
            match self.inner.dequeue() {
                Some(popped_request) => Some((
                    popped_request.id,
                    popped_request.arrival_ms,
                    popped_request.duration_ms,
                )),
                None => None,
            }
        }

        //Append a batch after PyO3 converts and validates each tuple
        fn enqueue_batch(&mut self, requests: Vec<(u64, u64, u64)>) {
            for (id, arrival_ms, duration_ms) in requests {
                self.enqueue(id, arrival_ms, duration_ms);
            }
        }

        //Remove up to max_requests items, in FIFO order
        fn dequeue_batch(&mut self, max_requests: usize) -> Vec<(u64, u64, u64)> {
            //Let count be the requested amount or if queue contains less then take the len
            let count = max_requests.min(self.inner.len());
            let mut requests = Vec::with_capacity(count);
            for _ in 0..count {
                if let Some(request) = self.dequeue() {
                    requests.push(request)
                }
            }
            requests
        }

        // Support Python's len(queue) without changing the queue
        fn __len__(&self) -> usize {
            self.inner.len()
        }
    }

    // Expose this function directly on the Python module
    #[pyfunction]
    fn count_requests(ids: Vec<u64>) -> usize {
        ids.len()
    }

    // Basic function to measure the cost of a Python to Rust call
    #[pyfunction]
    fn ping() -> u64 {
        1
    }
}
