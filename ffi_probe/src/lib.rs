use pyo3::prelude::*;

// A Python module implemented in Rust.
// The pymodule here tells PyO3 that this module 
// is to be exposed to python
#[pymodule]
mod ffi_probe {
    use rust_scheduler::RequestQueue;
    use pyo3::prelude::*;

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
    }

    //pyfunction is same use as pymodule
    /// Accepts a collection of request IDs and returns how many
    #[pyfunction]
    fn count_requests(ids: Vec<u64>) -> usize {
        ids.len()
    }

    // Basic function to cost of Python to Rust call
    #[pyfunction]
    fn ping() -> u64 {
        1
    }

}
