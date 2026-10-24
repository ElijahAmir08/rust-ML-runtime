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



