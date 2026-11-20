## This is brief instructions on how to set up vllm repo in dev mode
*The instructions are based off the ones found here: https://docs.vllm.ai/en/latest/contributing/index.html#developing*

- Make you hav cded into the vllm repo
- if uv isnt installed run `python -m pip install uv`
```
uv venv --python 3.12 --seed --managed-python
source .venv/bin/activate
uv pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu129
cd requirments
grep -v '^torch==' cuda.txt | uv pip install -r -
cd ..
uv pip install setuptools_scm
export MAX_JOBS=4
export CUDA_HOME=/sw/cuda/cuda-12.9
export TORCH_CUDA_ARCH_LIST="7.0"
uv pip install -e . --no-build-isolation`
```

### Optional: NIXL, for disaggregated prefill/decode (P/D)
vLLM's `NixlConnector` moves the KV cache from the prefill GPU to the decode GPU with NIXL. Install it
**into the vllm venv** (with it activated, or with `VIRTUAL_ENV` pointing at it):
```
uv pip install "nixl>=0.7.1,<0.10.0"
```
- The version range comes from `requirements/kv_connectors.txt`. It adds just `nixl` and `nixl-cu12`
  (which bundles its own CUDA-enabled UCX); it leaves torch alone.
- Don't install it into a fresh/empty venv: there the resolver also pulls the newest torch (CUDA 13).
- Check it: `python -c "import nixl._api"`, then on a GPU node from `vllm_playground/`:
  `mkdir -p results/nixl_check && sbatch slurms/nixl_check.slurm` (2-GPU transfer test, see `bench/nixl_check.py`).
- Remove it: `uv pip uninstall nixl nixl-cu12`.



