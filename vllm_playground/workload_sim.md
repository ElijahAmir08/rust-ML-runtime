### Workload_simulator for benchmarking

Below we include our workload simulator for benchmarking. The goal is to provide a thorough description of its capabilities and purpose. This serves as information to any reader and also a place for us to ideate about the workload simulator.

#### Things we need to test
- baseline could be just a completely full queue where order is sampled randomly from our data.
- stress testing kv caching by including many long context prompts...
- stress testing the scheduler by including many high concurrency jobs (low context length that require a lot of parallelism)
- real world simulated env (testing time done as a time variable in seconds)


**open question:** how to track metrics and which metrics to track when benchmarking
- time to completion?
- time to first token
- tokens per second
- avg end to end latency
- request per second
- Inter-Token Latency
