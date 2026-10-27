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




# Week 2
To Read: https://gordicaleksa.medium.com/eli5-flash-attention-5c44017022ad
