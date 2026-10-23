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

# October 22, 2026
### What I have learned/accomplished [EH]
    - Completed chapter 2 of the Rust language doc page and learned more of the syntax/fundamentals
    - Some features that I have not fully grasped yet are:
        - println!() is not a normal function as the "!" tells rust that this is a macro. "A way to write code that generates code" which will be explained in more detail later.
        - A module within the standard library(std) known as cmp, has enum Ordering with variants Greater/Less/Equal. Using these variants or calling the cmp(...) method becomes very syntactic heavy and I wonder what the advantages are vs ">/</==/etc."? 
        - To create a new string the syntax is "let x = String::new()" Where "::" means that new is an associated function of the string type. Not sure what this doing vs a dot notation.
    - Learned that all variables are defaulted as immutable so let x = 5 means x will always hold this value unless "let mut x..." is written. 
    - A really different and interesting feature is "Shadowing" where you can have variables of the same name to avoid having to always make a unique identifier. I am curious what the limits are of this or how rust knows which one I am referring to. 
    - Rust also uses similar to syntax to C++ such as "&" which tells rust that an argument is a reference
    - Overall I am finding Rust to be syntactically dense, but has really conveinent/almost flexible features while maintaining to be a precise language. The documentation is very easy to follow and breaks down the language well. I appreciate how much the syntax tries to read like the human language with words such as "use" for calling libraries, "loop {}" to begin a loop, or "match" for creating conditional branches. I suspect that there is going to be more control/optimization decisions while remaining close to the human lanaguage.
    - To summarize:
        - Challenges: I am still developing an understanding of Rust's general syntax, function vs macros, and how exactly references work. It feels more syntactically dense than other languages like Python, but the explicit language and compiler guidance are worth exploring.
        - Connection to the Project: Today introduced several conccepts relevant to request scheduling, including comparisons, conditional brancing, loops, and error handling. I additionally gained more experience using Cargo to manage external dependencies. 
