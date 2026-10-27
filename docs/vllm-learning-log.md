# This is my learning log for vllm

*I will provide all of my the resources I have been using to learn here. If you want to learn the concepts more in depth I recommend using those resources, but I also hope these notes will be somewhat comprehensive.*

## Week 1
**Resources:**
- VLLM overview: https://vllm.ai/blog/2025-09-05-anatomy-of-vllm#prefix-caching
- Paged attention details: https://arxiv.org/pdf/2309.06180
- Nvidia GPU layout *(sections 3-6)*: https://arxiv.org/pdf/2309.06180

### vLLM overview
This will initially cover the components of a general single GPU system how it generally implements the KV-cache.
#### The LLM core consists of:
- The core client (who process the requests and is responsible for the generating the output.)
- The preprocessor (turns raw input into an `EngineCoreRequest` that the core client can then process)
- The output processors (Responsible for translating the clients output into a `RequestOutput` for the application.)

#### The Engine core client is where the meat and potatoes are:
- the model executer (the thing generates a model forward pass)
- structured output manager which is used for something called guided decoding. Guided decoding is an optimization technique that we have not covered yet.
- scheduler
    - contains:
    - policy setting (e.g. FIFO)
    - waiting & running queues for queries
    - **kv cache manager**
        - contains:
        - free block queue to track which block ids are free

The model executer has its own very important components which we list here:
- During construction  a worker object is created. *(important note that does not yet pertain to us is that for multiproc systems this process is done for each worker across gpus)*
- Init device
    - assigns a CUDA device to the worker and verifies that the model and cuda data types or compatible
    - verify that the gpu has enough VRAM as requested by `gpu_memory_utilization`
    - setup distributed settings *(not there yet)*
    - instantiate the `model_runner`
        - contains:
        - sampler (Pytorch object that lives on cpu but performs calculations on logits stored on the gpu. It turns the model’s output logits into next-token IDs)
        - actual KV-cache (references to VRAM addresses in GPU)
        - forward pass buffers for input tokens  (references to VRAM addresses in GPU)
    - instantiate an `InputBatch` (which holds the cpu side forward pass buffers, block table for kv cache indexing, sampling metadata, etc...)
- load model
    - instantiate model arch.
    - load model weights (onto gpu, we haven't not learned about sharding yet)
    - call model.eval()
    - \[optional\] call model.compile()
- initialize KV-cache (this part tripped me up so i will try to include details I learned here)
    - get KV- cache specs (full attention, sliding window, etc...)
    - run a dummy forward pass to get a snap shot of gpu to see how many blocks we can fit into GPU-VRAM
    - **Allocate reshape and bind kv cache blocks to attention layers**
        - This part tripped me up. I try to explain it below
        - Each attention layer essentially has it's own KV cache whose structure is identical to every other layer. We have these because each layer has its own KV values for a given block.
        - Binding: Essentially aligns the model's kv cache with the root address for the kv cache in vram (layers[l].attn.kv_cache = kv_caches[l])
        - The block id is an kind of offset from the layer kv-cache root (More in the nvidia documentation, and I will explain more later). Because of the duplicate structure across layer's caches, a single block id is used to refer to the KV values for a token block across layers.
        - Side note: The K,V values in an transformer are independent of each other token in the sequence and solely dependent on the output from previous layers. This allows KV values across tokens in a layer to be calculated in parallel.
    - prepare attention metadata (exact use is not covered yet) (e.g. set backend to FlashAttention, ...)
    - unless `--enforce_eager` is provided, do a dummy run to capture CUDA graphs

#### Generate Function
...

#### The Scheduler
**Types of Requests:**
- prefill requests - is a forward pass over all the prompt tokens
- decode request forward pass of the most recent token using the kv-cached values for previous tokens

The Scheduler prioritzes decode requests as their values are already cached and for each request it:
- computes # of new tokens to generate
- calls KV-cache manager to execute `allocate_slots` function
- Updates token budget by subtracting the number of new tokens we are generating

Then it processes the prefill requests:
- retrieves number of computer blocks
- calls KV-cache manager to execute `allocate_slots`
- pops request from waiting and moves it to running, setting the requests status to running
- updates the token budget

```
allocate_slots():
- compute number of blocks
    - determine how many kv-cache blocks (n) must be allocated (each block stores 16 tokens by default)
- check availability
    - if there are not enough blocks exit early
    - Engine may recompute preemption (idk what that is) by evicting low priority requests (using kv cache manager to free blocks) or it might skip scheduling this request or move it back to the waiting queue
- Allocate Blocks
    - via the kv-cache manage's coordintor, fetches the first n free blocks from the block pool(which is a doubly linked list) stores to req_to_block (a dict mappig request ids to kv blocks)
```

### VLLM algorithms

> I'll list all the resources I've been using to learn here. If you want to understand the concepts in more depth, I recommend going through those resources directly, but I hope these notes are fairly comprehensive on their own.

---

## Week 1

### Resources

| Topic | Link |
| --- | --- |
| vLLM overview | [Anatomy of vLLM (blog)](https://vllm.ai/blog/2025-09-05-anatomy-of-vllm#prefix-caching) |
| PagedAttention details | [arXiv:2309.06180](https://arxiv.org/pdf/2309.06180) |
| NVIDIA GPU layout *(sections 3–6)* | [link](https://docs.nvidia.com/cuda/archive/12.9.2/cuda-c-programming-guide/) |
##### Diagrams from [source]()

---

### vLLM Overview

This section covers the components of a general single-GPU system and how it implements the KV cache.

#### The LLM Engine

The LLM engine consists of:

- **Engine core client** — processes requests and is responsible for generating the output.
- **Preprocessor** — turns raw input into an `EngineCoreRequest` that the core client can process.
- **Output processor** — translates the client's output into a `RequestOutput` for the application.

#### The Engine Core

The engine core client is where the meat and potatoes are:

- **Model executor** — runs the model forward pass.
- **Structured output manager** — used for *guided decoding*, an optimization technique not covered yet.
- **Scheduler**
  - Policy setting (e.g. FIFO)
  - Waiting & running queues for requests
  - **KV cache manager**
    - Free block queue that tracks which block IDs are free

#### The Model Executor

The model executor has its own important components:

1. **Construction** — a worker object is created.
   > *Note:* on multi-process systems this is done for each worker across GPUs (not relevant to us yet).

2. **Init device**
   - Assigns a CUDA device to the worker and verifies that the model and CUDA data types are compatible.
   - Verifies the GPU has enough VRAM, as requested by `gpu_memory_utilization`.
   - Sets up distributed settings *(not there yet)*.
   - Instantiates the `model_runner`, which contains:
     - **Sampler** — a PyTorch object that lives on the CPU but performs calculations on logits stored on the GPU. It turns the model's output logits into next-token IDs.
     - **KV cache** — references to VRAM addresses on the GPU.
     - **Forward pass buffers** for input tokens — references to VRAM addresses on the GPU.
   - Instantiates an `InputBatch`, which holds the CPU-side forward pass buffers, the block table for KV cache indexing, sampling metadata, etc.

3. **Load model**
   - Instantiate the model architecture.
   - Load model weights onto the GPU *(sharding not covered yet)*.
   - Call `model.eval()`.
   - *[Optional]* Call `model.compile()`.

4. **Initialize KV cache** *(this part tripped me up, so I've included extra detail)*
   - Get KV cache specs (full attention, sliding window, etc.).
   - Run a dummy forward pass to snapshot the GPU and determine how many blocks fit in VRAM.
   - **Allocate, reshape, and bind KV cache blocks to attention layers:**
     - Each attention layer has its own KV cache, whose structure is identical to every other layer's. This is needed because each layer has its own K/V values for a given block.
     - **Binding** aligns the model's KV cache with the root address of the KV cache in VRAM:
       ```python
       layers[l].attn.kv_cache = kv_caches[l]
       ```
     - The **block ID** is a kind of offset from each layer's KV cache root (more in the NVIDIA docs; I'll explain later). Because every layer's cache has the same structure, a single block ID refers to the K/V values for a token block across *all* layers.
     - > **Side note:** In a transformer, the K/V values for a token don't depend on other tokens in the sequence at that layer — only on the output of previous layers. This lets K/V values for all tokens in a layer be computed in parallel.
   - Prepare attention metadata, e.g. set the backend to FlashAttention *(exact use not covered yet)*.
   - Unless `--enforce-eager` is provided, do a dummy run to capture CUDA graphs.

#### Generate Function

*TODO*

#### The Scheduler

**Types of requests:**

- **Prefill requests** — a forward pass over all the prompt tokens.
- **Decode requests** — a forward pass over only the most recent token, using the cached K/V values for previous tokens.

**Decode requests first.** The scheduler prioritizes decode requests since their values are already cached. For each one it:

1. Computes the number of new tokens to generate.
2. Calls the KV cache manager's `allocate_slots` function.
3. Updates the token budget by subtracting the number of new tokens.

**Then prefill requests.** For each one it:

1. Retrieves the number of computed blocks.
2. Calls the KV cache manager's `allocate_slots`.
3. Pops the request from the waiting queue, moves it to running, and sets its status to running.
4. Updates the token budget.

##### `allocate_slots()`

1. **Compute number of blocks** — determine how many KV cache blocks (*n*) must be allocated. Each block stores 16 tokens by default.
2. **Check availability** — if there aren't enough blocks, exit early. The engine may then:
   - attempt *preemption* (TODO: look into this) by evicting low-priority requests, using the KV cache manager to free their blocks, or
   - skip scheduling this request, or move it back to the waiting queue.
3. **Allocate blocks** — via the KV cache manager's coordinator, fetch the first *n* free blocks from the block pool (a doubly linked list) and store them in `req_to_blocks` (a dict mapping request IDs to KV blocks).

---

### vLLM Algorithms

*TODO*
