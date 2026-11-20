#!/bin/bash -l
#SBATCH -N 1 -n 1
# The one job template. Starts a vLLM server on this node, waits until it is healthy, runs the
# (optional) priming command and the workload command against it, then stops the server.
#
# Everything that varies per experiment -- partition, GPUs, time, memory, job name, log path, and
# the commands themselves -- comes from run.sh: resources as sbatch flags, the rest as exported
# environment variables (RUN_DIR, PRIME_DIR, SIM_CMD, PRIME_CMD, MODEL, MAX_MODEL_LEN, SERVE_ARGS,
# VENV_PATH). Do not sbatch this file directly; use ./run.sh <experiment>.
set -euo pipefail

cd "${SLURM_SUBMIT_DIR:-$(pwd)}"
: "${RUN_DIR:?run via ./run.sh}" "${SIM_CMD:?}" "${MODEL:?}" "${MAX_MODEL_LEN:?}" "${VENV_PATH:?}"
mkdir -p "$RUN_DIR"

export HF_HUB_OFFLINE=1          # weights are already in ~/.cache/huggingface; GPU nodes have no internet
export CUDA_HOME=/sw/cuda/cuda-12.9
source "$VENV_PATH/bin/activate"

PORT=$((20000 + ${SLURM_JOB_ID:-$$} % 20000))
export URL=http://127.0.0.1:$PORT

# fp16 because V100 (sm70) has no bf16. SERVE_ARGS is already shell-quoted by bench/resolve.py.
SERVE="vllm serve $(printf %q "$MODEL") --dtype half --max-model-len $MAX_MODEL_LEN --host 127.0.0.1 --port $PORT ${SERVE_ARGS:-}"
echo "$SERVE" > "$RUN_DIR/server_cmd.txt"

{
  echo "job: ${SLURM_JOB_ID:-local} on $(hostname) at $(date -Is), CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-unset}"
  # nvidia-smi sees every GPU on the node; only the assigned one matters
  nvidia-smi -i "${CUDA_VISIBLE_DEVICES:-0}" --query-gpu=name,pci.bus_id,memory.total,memory.used,driver_version --format=csv
  echo "processes already on our GPU (should be none):"
  nvidia-smi -i "${CUDA_VISIBLE_DEVICES:-0}" --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
  echo "venv: $VENV_PATH"
  python -c "import vllm, torch; print('vllm', vllm.__version__, vllm.__file__, '| torch', torch.__version__, '| torch cuda', torch.version.cuda)"
  echo "cpus: $(nproc), node load: $(cut -d' ' -f1-3 /proc/loadavg)"
} > "$RUN_DIR/env.txt" 2>&1
cat "$RUN_DIR/env.txt"

echo "+ $SERVE"
bash -c "exec $SERVE" > "$RUN_DIR/server.log" 2>&1 &  # exec: $! is vLLM itself, so the trap stops it
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null; wait $SERVER_PID 2>/dev/null || true' EXIT

echo "waiting for vLLM on $URL ..."
for _ in $(seq 1 180); do  # up to 15 min: a first launch compiles and captures CUDA graphs
  curl -sf "$URL/health" > /dev/null && break
  kill -0 $SERVER_PID 2>/dev/null || { echo "vLLM exited during startup:"; tail -40 "$RUN_DIR/server.log"; exit 1; }
  sleep 5
done
curl -sf "$URL/health" > /dev/null || { echo "vLLM not healthy after 15 min"; tail -40 "$RUN_DIR/server.log"; exit 1; }
echo "vLLM ready after $SECONDS s"
grep -iE "attention backend|KV cache|maximum concurrency|max_num_seqs|max_num_batched_tokens|chunked prefill|non-default args" \
  "$RUN_DIR/server.log" | head -20 | tee "$RUN_DIR/server_config_lines.txt"

if [ -n "${PRIME_CMD:-}" ]; then
  echo "+ (priming, not measured) $PRIME_CMD"
  eval "$PRIME_CMD"
fi
echo "+ $SIM_CMD"
eval "$SIM_CMD"
echo "done after $SECONDS s"
