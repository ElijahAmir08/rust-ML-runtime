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

- **Engine core client** — sends requests to the engine core (usually a separate process, talked to over ZMQ) and receives its outputs.
- **Preprocessor** — turns raw input into an `EngineCoreRequest` (tokenized prompt + sampling params) that the engine core can process.
- **Output processor** — turns the engine core's per-step token deltas into `RequestOutput`s for the application (detokenizes, checks stop strings — see *Finishing & Output*).

#### The Engine Core

The engine core is where the meat and potatoes are:

- **Model executor** — runs the model forward pass (via workers / model runner).
- **Structured output manager** — used for *guided decoding*: forcing output to follow a grammar / JSON schema by masking invalid tokens *(not covered yet)*.
- **Scheduler**
  - Policy setting (FCFS by default, or priority)
  - Waiting & running queues for requests
  - **KV cache manager**
    - Free block queue that tracks which block IDs are free
    - Only manages **block IDs (integers) on the CPU** — it never touches the actual KV tensors on the GPU

#### The Model Executor

The model executor has its own important components:

1. **Construction** — a worker object is created.
   > *Note:* on multi-process systems this is done for each worker across GPUs (not relevant to us yet).

2. **Init device**
   - Assigns a CUDA device to the worker and verifies that the model and CUDA data types are compatible.
   - Verifies the GPU has enough VRAM, as requested by `gpu_memory_utilization`.
   - Sets up distributed settings *(not there yet)*.
   - Instantiates the `model_runner`, which contains:
     - **Sampler** — a PyTorch module that runs on the GPU logits; turns them into next-token IDs using each request's sampling params (temperature, top-p/k, ...).
     - **KV cache** — references to VRAM addresses on the GPU.
     - **Forward pass buffers** — see *InputBatch vs Forward Pass Buffers* below.
   - Instantiates an `InputBatch` — persistent per-request state (token history, block table, sampling params). See below.

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
     - > **Side note:** At a given layer, each token's K/V is just a projection of *that token's* hidden state entering the layer (earlier tokens only influence it through previous layers' attention). So K/V for all tokens in a layer can be computed in parallel.
   - Prepare attention metadata, e.g. set the backend to FlashAttention *(exact use not covered yet)*.
   - Unless `--enforce-eager` is provided, do a dummy run to capture CUDA graphs.

---

#### The Engine Loop (`EngineCore.step()`)

The engine core runs a simple synchronous busy loop:

```
while True:
    process input queue      # new requests / aborts from frontend; blocks if no work
    step():
      1. scheduler.schedule()              → SchedulerOutput  (the plan for this step)
      2. executor.execute_model(plan)      → ModelRunnerOutput (sampled tokens)
      3. scheduler.update_from_output(...) (advance state, check stops, free blocks)
```

- **No batching window** — the plan is sent the moment `schedule()` returns. Whatever is in the queues at that time is the batch. A request arriving mid-step joins next iteration (= *continuous batching*).
- **Nothing pulls from the queues except the scheduler.** The executor/workers only ever see the `SchedulerOutput`.
- **Async scheduling / pipeline parallel:** `step_with_batch_queue()` schedules step N+1 while step N is still on the GPU (hides CPU overhead).

**`SchedulerOutput` contains:**
- `scheduled_new_reqs` — full data for requests admitted from waiting (prompt ids, sampling params, block ids, `num_computed_tokens` incl. prefix-cache hits)
- `scheduled_cached_reqs` — **diffs only** for already-running requests (new block ids, updated `num_computed_tokens`, resumed-from-preemption flag)
- `num_scheduled_tokens` — `{req_id: tokens to process this step}` ← the real "work order"
- finished / preempted request ids so workers drop their state

---

#### The Scheduler

**There is no separate prefill vs decode in V1.** Each request just has `num_computed_tokens` and tries to catch up to `num_tokens`:
- a prefill chunk = a request with e.g. 512 scheduled tokens
- a decode = a request with 1 scheduled token

Both go through the **same forward pass**.

**Running queue first.** For each request in `running` (walked front → back):
1. Compute new tokens = `num_tokens − num_computed_tokens`, capped by the token budget and `long_prefill_token_threshold`.
2. Call[118;1:3u `allocate_slots`. If it fails → **preempt** (see below) and retry.
3. Subtract from the token budget.

**Then waiting queue** (only if nothing was preempted this step). For each request:
1. Look up prefix-cache hits (`get_computed_blocks`) → `num_computed_tokens`.
2. Chunk the rest to fit the leftover budget (chunked prefill).
3. Call `allocate_slots`. If it fails → **`break`** (request stays in waiting; running requests are *never* preempted to admit new ones).
4. Pop from waiting, append to running, set status RUNNING — **even if only one chunk of its prefill was scheduled**.
5. Update the token budget.

**Key consequences:**
- A partially-prefilled request (`[cached, cached, to-prefill, to-prefill, ...]`) lives in **running**, not waiting. Its later chunks are scheduled from the running loop.
- A forward pass runs everything **scheduled** this step — usually all of `running`, but if the budget (`max_num_batched_tokens`) runs out, the remaining running requests **sit out this step** (keep their blocks, not preempted). Newly admitted waiting requests join the same pass.
- Limits: `max_num_seqs` (requests running at once), `max_num_batched_tokens` (tokens per step).

**Queue order (FCFS):**
- `running` keeps **admission order** — nothing rotates to the back after running.
- Priority within running = age: oldest gets budget first.
- New admissions are appended to the back; preemption also takes from the back (`running.pop()`).
- Priority policy: victim = lowest priority (ties → latest arrival); waiting becomes a heap.
- Trade-off: a long prefill near the front can starve the tail until it finishes (by design).

**Preemption:**
- Victim's blocks are **all** freed, status → PREEMPTED, `num_computed_tokens = 0`, put at the **front** of waiting.
- If the victim would be the request being scheduled, it preempts itself and stops.
- With prefix caching, its freed full blocks keep their hashes, so on reschedule it often gets cache hits on its own old blocks (if not evicted yet).

##### `allocate_slots()`

1. **Compute number of blocks** — *n* = blocks needed to cover `num_computed_tokens + num_new_tokens (+ lookahead)` **minus blocks the request already has** (incremental). Each block stores 16 tokens by default.
2. **Check availability** — free blocks must cover *n*, also accounting for prefix-hit blocks with ref_cnt 0 (they're still in the free queue, so reusing them uses up capacity). If not enough → return `None`:
   - running request → scheduler preempts and retries
   - waiting request → scheduler stops admitting for this step
   - prefix-hit blocks are only "touched" (ref count++) *after* the check passes, so a failed allocation leaves the request holding nothing
3. **Allocate blocks** — via the KV cache manager's coordinator, pop *n* blocks from the front of the free block queue (a doubly linked list in **LRU eviction order**; popping a cached block evicts its hash). Store them in `req_to_blocks` (dict: request ID → blocks; one per KV-cache group, in each `SingleTypeKVCacheManager`).

> Edge case: with KV connectors / disaggregated prefill, a request can sit in `WAITING_FOR_REMOTE_KVS` while holding blocks.

---





# Week 2
To Read: https://gordicaleksa.medium.com/eli5-flash-attention-5c44017022ad


#### InputBatch vs Forward Pass Buffers

**Big picture:** the scheduler's output is a **diff** that the model runner applies to the `InputBatch` (persistent per-request state). Each step, the model runner does index arithmetic over the `InputBatch` to fill the **forward pass buffers** (flat token inputs + attention metadata), which are what the GPU computes on.

| | **InputBatch** | **Forward pass buffers** |
|---|---|---|
| Describes | Requests (full history + settings) | Tokens being computed *this step* |
| Shape | one **row per request** (`max_num_reqs` rows) | one **entry per token**, flat (`max_num_batched_tokens`) |
| Lifetime | persists across steps, updated incrementally | rewritten every step |
| Purpose | never re-send / rebuild request state | single packed input + info for attention to split it |

**Why flatten?** Requests have different lengths (1 token vs 500). Padding to `[batch, max_len]` wastes compute, so all scheduled tokens are concatenated. Linear layers/MLPs don't care; only **attention** needs to know request boundaries and where KV lives.

**InputBatch fields:**
- `req_ids`, `req_id_to_index` — bookkeeping; row order = batch order
- `token_ids_cpu` `[max_num_reqs, max_model_len]` — full token history per request
- `num_tokens`, `num_prompt_tokens`, `num_computed_tokens_cpu` — where each request's new work starts
- `block_table` `[max_num_reqs, max_blocks_per_req]` — logical → physical KV block per request (blocks needn't be contiguous = PagedAttention)
- sampling params as tensors — one batched sampling op, no per-request loop
- `condense()` — fills holes left by finished requests so live rows stay packed in `[0, num_reqs)`; some attention backends also reorder rows (decodes before prefills)

**Forward pass buffers** (filled by `_prepare_inputs()`, vectorized numpy):
- `input_ids` — actual token IDs for the embedding layer
- `positions` — each token's position **in its own sequence** (for rotary embeddings)
- `query_start_loc` `[num_reqs+1]` — where each request's tokens start in the flat batch (stops requests attending to each other)
- `seq_lens` `[num_reqs]` — total context length of each request **after this step** (`num_computed + scheduled`) = how many KV entries to attend over
- `slot_mapping` — physical KV slot for each new token = `block_table[req][pos // block_size] * block_size + pos % block_size`

**Worked example** (block_size = 4 for readability):

| Req | Situation | Tokens | Computed | Scheduled | block_table |
|---|---|---|---|---|---|
| A | decode | `11 12 13 14 15 16` | 5 | 1 | `[7, 2]` |
| B | new, chunked prefill | `21 … 26` | 0 | 4 | `[5]` |
| C | decode | `31 32 33` | 2 | 1 | `[9]` |

*(A has computed 5/6 because `16` was just sampled — a decode step feeds the last sampled token back in.)*

```
req_indices     = [0, 1, 1, 1, 1, 2]      # owner row per token
positions       = [5, 0, 1, 2, 3, 2]      # num_computed + offset
input_ids       = [16, 21, 22, 23, 24, 33]
query_start_loc = [0, 1, 5, 6]            # A=[0:1], B=[1:5], C=[5:6]
seq_lens        = [6, 4, 3]
slot_mapping    = [9, 20, 21, 22, 23, 38] # e.g. A pos5 → block 2 → 2*4+1 = 9
```

**What attention does with it (every layer):**
1. Compute Q, K, V for all 6 tokens.
2. **Write** K/V into the KV cache at `slot_mapping`.
3. **Read**: for request *i*, queries `[query_start_loc[i] : query_start_loc[i+1]]` attend over `seq_lens[i]` entries found via `block_table[i]`.

→ `slot_mapping` = **write** this step's KV. `block_table` + `seq_lens` = **read** full context.

**After the last layer:** logits only at each request's last token (`query_start_loc[1:] − 1 = [0, 4, 5]`). B is mid-prefill → its sampled token is **discarded**.

**Why preallocated + CPU/GPU copies:**
- CPU numpy: cheap vectorized index math, no per-token Python loops
- pinned CPU memory: fast async CPU→GPU copy
- GPU copy: what kernels read
- fixed buffers: no per-step allocation, and **CUDA graphs need fixed memory addresses** → batch is padded to a captured size (padding slots = `-1`, nothing written)

---

#### Layers & Activations

```
h_L → norm → Q, K, V
              ├─ K, V → written to layer L's KV cache   (the ONLY thing that survives the step)
              └─ attention(Q, cached K/V) → out proj
    → + residual → norm → MLP → + residual → h_{L+1}
```

- What flows to the next layer is the **hidden state** (whole block's output), not Q/K/V. Layer L+1 computes its own Q/K/V from `h_{L+1}` with its own weights.
- Q is used once and discarded; all other activations are transient (memory reused).
- Final hidden state → final norm → LM head → logits.

---

#### Where Things Live (CPU vs GPU)

| CPU only | CPU + GPU copy | GPU only |
|---|---|---|
| Scheduler, queues, `Request` objects | `block_table` | Model weights |
| KV cache manager, `BlockPool`, free queue, prefix hashes, `req_to_blocks` | sampling-param tensors | **KV cache tensors** |
| InputBatch bookkeeping (`token_ids_cpu`, counts) | forward pass buffers | Activations |
| numpy index arithmetic | | Logits, sampling |

- **GPU → CPU:** sampled token IDs (+ logprobs) copied back each step = a **sync point** (CPU waits on GPU). Async scheduling hides this.
- Newer versions move more input prep to the GPU (e.g. Triton kernels for `slot_mapping`) — check your version.

---

#### Output Tokens

The forward pass buffers hold **inputs only**. Sampled tokens:
1. Sampler writes `sampled_token_ids` on GPU (`[num_reqs, 1]`).
2. Copied to CPU, then used twice:
   - model runner appends to its `InputBatch.token_ids_cpu` (`num_tokens++`) → next step's `input_ids` gathers from here
   - returned in `ModelRunnerOutput` to the engine core
3. `update_from_output()` appends to the scheduler's `Request` objects (source of truth).

→ Each token is recorded twice on CPU (worker + scheduler) because of the process boundary.
- **Async scheduling exception:** last step's GPU tensor is scattered directly into the next step's GPU `input_ids`; CPU uses placeholders and catches up later.

---

#### Finishing & Output

**Token-level stops — caught by the scheduler** in `update_from_output()` → `check_stop()`:
- EOS (unless `ignore_eos`), `stop_token_ids`, `max_tokens`, `max_model_len`
- → status `FINISHED_STOPPED` / `FINISHED_LENGTH_CAPPED`, then:
  1. free KV blocks (full ones stay in prefix cache)
  2. remove from `running`
  3. add to `finished_req_ids` → next `SchedulerOutput` tells workers to drop the `InputBatch` row

**Sending to frontend:** every request that produced a token gets an `EngineCoreOutput` with **only the new token IDs (a delta)** + finish reason if done → batched → ZMQ → frontend.

**Output processor** (`AsyncLLM` output handler → `OutputProcessor.process_outputs()`), per request:
- keeps accumulated state (`RequestState`: detokenizer, tokens + text so far); the full sequence/prompt is never re-sent
- **incrementally detokenizes** — deltas are tokens, not words (e.g. `" Vict"`, `"or"`), and may hold text back until it decodes cleanly (partial UTF-8)
- **checks stop strings** — must happen here since they're text (can span tokens)
- pushes `RequestOutput` to the request's queue → API server

**Stop strings flow backwards:** output processor finds it → marks finished, truncates text → sends **abort** to engine core → blocks freed. A step or two of extra tokens may be generated and thrown away. Client disconnects use the same abort path.

**Streaming vs non-streaming** (engine/GPU work is identical either way):
- `DELTA` (streaming): emit new text every step
- `CUMULATIVE`: emit full text so far each time (built on frontend)
- `FINAL_ONLY` (non-streaming): still processes every delta + checks stop strings, emits once at the end
- Streaming doesn't speed generation; it lowers perceived latency (time-to-first-token).

---


### vLLM Algorithms


#### Prefix Caching (full blocks only)

- **KV is written for every token immediately**, into its slot, even if the block isn't full.
- What's limited to full blocks is **caching**: when a block fills, it's hashed (block tokens + parent block's hash + extras like LoRA) and registered in the prefix-cache table (`cache_full_blocks`).
  - Full cached blocks can be shared by other requests (ref count++) and stay findable in the free queue after being freed, until evicted.
- **Partial last block** = real KV, used for attention, but **no hash** → private; can never be a cache hit.
- Why: a hash identifies exact contents, and a partial block's contents are still changing.
- Even on a full prefix hit, the **last prompt token is always recomputed** (needed for the logits of the first sampled token).

---


## Where Rust Could Help (project notes)

Rust helps where the **CPU is on the critical path doing per-request Python work**; not where work is already vectorized or on GPU.

**Strong:**
1. **KV cache manager / BlockPool** — linked-list ops, ref counts, **prefix-cache hashing** (CPU-heavy for long prompts). Clean boundary: state is just ints + hashes.
2. **`schedule()` loop** — O(num_reqs) Python per step; matters with many concurrent requests + short GPU steps.
3. **`update_from_output()`** — per-request append, stop checks, output objects; serial on critical path.

**Medium:**
4. InputBatch diff application / `condense()` (index math is already numpy; upstream trend is moving prep to GPU instead).
5. Frontend: incremental detokenization, stop strings, API server, ZMQ/msgspec IPC (tokenizer core already Rust; SGLang and TGI routers are Rust).

**Won't help:** forward pass, attention, sampling (GPU); already-native code (numpy, tokenizers, xgrammar/llguidance); CPU time already hidden by async scheduling (only helps if CPU time > GPU step time).

**FFI design > language:**
- one call per **step** with batched arrays, not per request/block
- ideally Rust **owns** scheduler/KV state (Python holds handles) — avoids mirror sync cost, but big refactor
- pass numpy / buffer-protocol arrays zero-copy; avoid `.tolist()` across the boundary

**V100 measurement plan:** V100 = longer GPU steps → CPU overhead is a smaller fraction. Make overhead visible with a small model, many short-context concurrent decodes, high `max_num_seqs`. Measure inter-step GPU idle gaps (`nsys` / torch profiler), attribute CPU time (`py-spy`) **before** porting — that gap is the ceiling on Rust's gains.

---
