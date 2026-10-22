# Rust Learning Log

# October 20, 2026

### What I have learned/accomplished [EH]
    - Went through Rust's documentation on the package handler "Cargo" and its fundamentals
        - cargo build reads a project's configuration, resolve dependencies and invokes the compiler (rustc), and finally become an executable program or library. 
    - Immediate thought is that I am a big fan of the terminology such as as "crates" (Code that the compiler processes) and "cargo" being the project manager that invokes rustc. 
    - An important distinction is a Binary Crate vs Library Crate: 
        - Binary being an executable program
        - Library being what provides functions and types for other code to use
    - An additional emphasis in the documentation was understanding Cargo.toml & Cargo.lock:
        - The key being that toml is programmer defined and declares the package & dependencies (external packages) will be needed
        - lock is what Cargo maintains and records the exact resolved dependency version/sources. It helps to ensure consistent repeatable builds across programmers.
    - Without going in too much detail there is of course a list of commands that all begin with "cargo" that I will become more familiar with as this project continues.
    - Cargo is important in helping us manage the external libraries required for our Rust scheduler and FFI implementation, while Cargo.lock will help keep dependencies consistent for benchmarking. 
