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
        - Challenges: 
            - I am still developing an understanding of Rust's general syntax, function vs macros, and how exactly references work. It feels more syntactically dense than other languages like Python, but the explicit language and compiler guidance are worth exploring.
            - Interested in how shadowing interacts with scopes
        - Connection to the Project: 
            - Today introduced several conccepts relevant to request scheduling, including comparisons, conditional brancing, loops, and error handling. I additionally gained more experience using Cargo to manage external dependencies.

# October 23, 2026

### What I have learned/accomplished [EH]
    - Completed Chapter 3 of the Rust Book, covering common programming concepts in the context of Rust. This chapter was relatively straightforward given previous programming experience, although certain Rust-specific features stood out.
    - Shadowing was covered in more detail, which clearified my confusion from yesterday:
        - A phrase from the doc that helped me was "The first variable is shadowed by the second". The compiler resolves references to the most recent visible binding within the current scope. 
        - The keyword let is needed when shadowing as it is creates a new variable binding with the same name rather than modifying the original. This allows the programmer to transform its value while still preserving immutability, including changing its type such as (let spaces = "  "; let spaces = spaces.len() // Calling .len() on the original spaces)
        - I am however still curious how exactly the compiler is resolving shadowing or if this introduces additional runtime overhead?
    - Data types were covered as well which was straightforward, but I did encounter the term known as "panicking" in this section. It is an unrecoverable error condition, which may be a common term but was entertaining to see.
    - The chapter also covered tuples, arrays, statements versus expressions, functions, and control flow.
        - One interesting distinction is that Rust treats variable declarations as statements rather than expressions, meaning syntax such as let x = (let y = 6); is invalid. 
            - Assignments are treated as expressions that evaluate to () not the assigned value. Rust does not want assignments to be used as meaningful values. 
        - Rust relies heavily on expressions. Even blocks {} and if/else can evaluate to values that can be assigned to a variable.
        - I also learned that Rust functions can implicitly return the value of their final expression. For example, fn five() -> i32 { 5 } returns 5, whereas placing a semicolon after the 5 discards the value and causes a return-type mismatch.
        - The distinction between statements and expressions is still somewhat unfamiliar, particularly because entire blocks of Rust code can evaluate to values. As well as the fact that the documentation for this topic felt overexplained. 
    - Challenges:
        - Understanding how shadowing is implemented by the compiler and whether it affects runtime performance.
        - Becoming comfortable distinguishing statements from expressions and recognizing when semicolons change behavior.
        - Learning to recognize which Rust features differ meaningfully from C/C++ and Python rather than simply having different syntax.
    - Connection to the project:
        - Shadowing, control flow, and Rust's type system will be definitely relevant when implementing request scheduling and dispatching algorithms.
        - Understanding Rust's compilation model and how it handles variable bindings will help to explain runtime behavior and performance differences.

