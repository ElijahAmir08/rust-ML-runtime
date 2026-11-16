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


# October 25, 2026
### What I have accomplished [EH]
    - Was not as quick moving today, but began the chapter about Ownership. Which serves the main purpose of making memory safe gurantees without needing a garbage collector.
        - There are three rules: 
            1. Each value in Rust has an owner 
            2. Only one owner at a time 
            3. When owner out of scope, drop value (aka free space)
    - This chapter also reviewed the stack and heap, focusing on how mem is allocated/managed. The String type was used as an example since its contents are stored on the heap.
    - A key takeaway is that Rust calls drop automatically when a variable is out of scope, to release resources such as heap-allocated memory without manually deallocating.
        - However, this leaves a problem of double free errors. Such as when (s1 = String::from("string"); s2 = s1;) both strings now point to the same heap which will try to free the same memory. To solve this Rust simply invalidates the s1 variable after s2 A.k.A s1 moves into s2. 
            - If programmer wants s1 to be still valid with independent copies of heap data, the method .clone() can be used (s2 = s1.clone())
        - It is important to understand this intuition applies to function calls/returns in which passing a variable into a method that function now has ownership.  
    - Overall, I find this approach of memory management  clever and straightforward conceptually. I am still appreciating the descriptive terminology, such as move and ownership.
    - Further Exploration:
        - How can functions access values without taking ownership?
        - How does Rust's ownership model affect concurrency and sharing data between threads?
    - Connection to Project:
        - Avoiding unnecessary cloning of large request data or prompt strings could help reduce memory allocation and copying overhead.
# November 5, 2026
### What I have accomplished [EH]
    - Completed chapters 4 through 6 in Rust's documentation, building ontop of the ownership topic from previous log. 
    - Chapter 4: References, Borrowing, and Slices
        - Learned the terminology borrowing which is using '&'symbol before a var_name to reference/point to it and not actually take ownership
        - Mutable references (&mut V) which allows you to modify the value, but with the restriction that there can only be one mutable reference to variable. Versus an immutable reference which there can exist many
        - Additionally, covered slices which is referencing portion of a collection without taking ownership or copying the entirety of it. String slices (&str) were a good example in the doc to understand this. 
    - Chapter 5: Structs and Mutables
        - Learned how structs group related fields into a custom data type, similar in purpose to classes or structures in languages I've used previously
        - The impl keyword allows defining methods associated with a struct, with &self providing borrowed access to the instance
        - This also clarified my earlier confusion between :: and . notation. Associated functions can be accessed through the type using ::, while methods operate on a value using dot notation
        - Important for when representing LLM inference requests, with fields such as request ID, arrival time, and token count
    - Chapter 6: Enums and Pattern Matching
        - enums were pretty standard for any other programming language, represent different possible states, including variants that carry associated data
        - The Option<T> enum was particularly interesting because it explicitly represents whether a value exists through Some(T) or None, rather than relying on null values. Rust has does not have null at all
        - These concepts should be useful for handling scheduling outcomes, empty request queues, and different request states
    - Current Observations / Learning Curve:
        - Rust's syntax is becoming more familiar, although ownership and borrowing require some extra thinking about how data is passed and modified
        - I like how Rust's type system and compiler make certain assumptions and possible errors explicit
        - Having completed these chapters, my next goal is to apply these concepts independently rather than only following the documentation

### November 13th, 2026
### What I have accomplished [EH]
    - Began working on integrating Rust with Python using PyO3, which is an important tool for our goal of replacing a CPU-side component of vLLM with a Rust implementation
    - First, I was able to initialize Victor's vLLM git module and verify that the files are accessible for me. I located the FCFSRequestQueue py file, which is a high contender for what we will replace
        - Wrote a python benchmark for this existing queue to create a baseline before comparing to Rust
        - However, I was unable to run the benchmark locally due to additional vLLM modules and dependencies. The first missing one was pybase64. Rather than attempting to install the entire environment, I figured it is easiest for Victor to run it
    - Began experimenting/setting up PyO3 and Maturin:
        - PyO3 in short is a Rust library that allows Rust code to interact with Python, including exposing Rust functions that can be called directly from Python.
        - Maturin is a build tool that compiles Rust code into a Python extension and installs it into a Python environment
        - I created a seperate ffi_probe directory to experiment with the interface before applying to the main project.
        - Some new syntax:
            - #[pymodule]/#[pyfunction] tells PyO3 to expose the Rust module/function to Python
            - Vec<u64> as explored in a previous log is a Rust vector containing unsigned integers. PyO3 can construct this from a Python list of valid integers
    - Challenges/Further Exploration:
        - Understand how PyO3 converts Python objects into Rust types and whether certain logic will introduce more overhead than others
        - Determine if calling Rust is actually faster after accounting for the cost of crossing Python/Rust
        
    - Connection to Project:
        - This is the first step toward connecting my Rust queue implementation to Python, which will eventually allow us to evaluate whether Rust can replace an existing component of vLLM
        - The next step is to verify the Python-to-Rust function calls, introduce basic correctness tests, and measure the overhead of PyO3 before attempting to integrate the actual request queue
        - 
# November 15th
### What I have accomplished [EH]
    - Continued experimenting with PyO3, this time focusing on the overhead of calling Rust functions from Python and passing data between the two languages
    - Added a simple ping() function in Rust to measure the cost of calling a function through PyO3 without any args
        - Used Python's timeit.repeat() to benchmark both a regular Python function and Rust function
        - Ran each experiment multiple times and used the median result to compare
        - The Python function averaged 27.6 ns/call compared to 38.5 ns/call for the Rust function through PyO3
        - Due to the functions using different calling mechamisms this is not exactly 10.9 ns of overhead
    - Expanded the experiments to measure cost of passing Python lists containing 0, 10, and 1000 request IDs and returning the length
        - Originally I created lists inside the functions being benchmarks, but realized this would accrue costs for creating the lists. Which is why they are moved outside of the functions
        - Rust function accepts a Vec<u64> and returns the length. Although .len() is an O(1) operation, PyO3 must convert the Python list into a Rust vector before execution
        - For 1000 IDs, the Rust call took approximately 13,777 ns compared to 51.2 ns for Python's len()
        
    - Began looking into how to expose the existing Rust RequestQueue to Python rather than implementing a separate queue.
        - Learned about #[pyclass] & #[pymethods] to expose Rust code
        
    - Challenges: 
        - These experiments demonstrate why the interface between Python and Rust is important when considering replacing CPU-side components of vLLM
        - I will continue to expose the existing Rust queue through PyO3 and benchmark its operations. As well as exploring any other strategies. However, for something like vLLM it does not seem likely that a Rust replacement in this form will show many improvements. 
        
