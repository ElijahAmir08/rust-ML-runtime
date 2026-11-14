use pyo3::prelude::*;

/// A Python module implemented in Rust.
/// //The pymodule here tells PyO3 that this module 
/// is to be exposed to python
#[pymodule]
mod ffi_probe {
    use pyo3::prelude::*;

    //pyfunction is same use as pymodule
    /// Accepts a collection of request IDs and returns how many
    #[pyfunction]
    fn count_requests(ids: Vec<u64>) -> usize {
        ids.len()
    }
}
