#!/bin/bash -l
#SBATCH -N 1 -n 1
# The one job template. Starts a vLLM server on this node, waits until it is healthy, runs the
# (optional) priming command and the workload command against it, then stops the server.
#
# Everything that varies per experiment -- partition, GPUs, time, memory, job name, log path, and
# the commands themselves -- comes from run.sh: resources as sbatch flags, the rest as exported
# environment variables (RUN_DIR, PRIME_DIR, SIM_CMD, PRIME_CMD, MODEL, MAX_MODEL_LEN, SERVE_ARGS,
# VENV_PATH, PD). Do not sbatch this file directly; use ./run.sh <experiment>.
#
# PD=1: disaggregated prefill/decode on 2 GPUs. A prefill and a decode vLLM (same SERVE_ARGS plus
# NixlConnector) sit behind vLLM's toy proxy, which sends each request to prefill with max_tokens=1,
# then to decode with the returned KV handle; decode READs the KV over NIXL and streams the output.
set -euo pipefail

cd "${SLURM_SUBMIT_DIR:-$(pwd)}"
: "${RUN_DIR:?run via ./run.sh}" "${SIM_CMD:?}" "${MODEL:?}" "${MAX_MODEL_LEN:?}" "${VENV_PATH:?}"
mkdir -p "$RUN_DIR"

export HF_HUB_OFFLINE=1          # weights are already in ~/.cache/huggingface; GPU nodes have no internet
export VLLM_SERVER_DEV_MODE=1    # enables POST /reset_prefix_cache, which workload_sim calls before every run
                                 # (servers listen on 127.0.0.1 only, so the dev endpoints stay on this node)
export CUDA_HOME=/sw/cuda/cuda-12.9
source "$VENV_PATH/bin/activate"

# ports for this job: base (server or proxy), +1/+2 P/D servers, +3/+4 NIXL side channels.
# Stride 8 so jobs sharing a node never overlap.
PORT=$((20000 + (${SLURM_JOB_ID:-$$} % 5000) * 8))
export URL=http://127.0.0.1:$PORT METRICS_URL=http://127.0.0.1:$PORT

# fp16 because V100 (sm70) has no bf16. SERVE_ARGS is already shell-quoted by bench/resolve.py.
serve() {  # port -> vllm serve command
  echo "vllm serve $(printf %q "$MODEL") --dtype half --max-model-len $MAX_MODEL_LEN --host 127.0.0.1 --port $1 ${SERVE_ARGS:-}"
}

{
  echo "job: ${SLURM_JOB_ID:-local} on $(hostname) at $(date -Is), CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-unset}"
  # nvidia-smi sees every GPU on the node; only the assigned ones matter
  nvidia-smi -i "${CUDA_VISIBLE_DEVICES:-0}" --query-gpu=name,pci.bus_id,memory.total,memory.used,driver_version --format=csv
  echo "processes already on our GPU(s) (should be none):"
  nvidia-smi -i "${CUDA_VISIBLE_DEVICES:-0}" --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
  [ "${PD:-0}" = 1 ] && nvidia-smi topo -m
  echo "venv: $VENV_PATH"
  python -c "import vllm, torch; print('vllm', vllm.__version__, vllm.__file__, '| torch', torch.__version__, '| torch cuda', torch.version.cuda)"
  echo "cpus: $(nproc), node load: $(cut -d' ' -f1-3 /proc/loadavg)"
} > "$RUN_DIR/env.txt" 2>&1
cat "$RUN_DIR/env.txt"

PIDS=()
trap 'kill ${PIDS[*]} 2>/dev/null; wait ${PIDS[*]} 2>/dev/null || true' EXIT
launch() {  # log file, command (run with exec so the PID is the process itself)
  echo "+ $2"
  bash -c "exec $2" > "$RUN_DIR/$1" 2>&1 &
  PIDS+=($!)
}
wait_healthy() {  # url, log file, pid
  for _ in $(seq 1 180); do  # up to 15 min: a first launch compiles and captures CUDA graphs
    curl -sf "$1" > /dev/null && return 0
    kill -0 "$3" 2>/dev/null || { echo "$2: process exited during startup:"; tail -40 "$RUN_DIR/$2"; exit 1; }
    sleep 5
  done
  echo "$2: not healthy after 15 min"; tail -40 "$RUN_DIR/$2"; exit 1
}

if [ "${PD:-0}" = 1 ]; then
  IFS=, read -r GPU_P GPU_D <<< "$CUDA_VISIBLE_DEVICES"
  KV='{"kv_connector":"NixlConnector","kv_role":"kv_both"}'
  P_CMD="env CUDA_VISIBLE_DEVICES=$GPU_P VLLM_NIXL_SIDE_CHANNEL_PORT=$((PORT + 3)) $(serve $((PORT + 1))) --kv-transfer-config '$KV'"
  D_CMD="env CUDA_VISIBLE_DEVICES=$GPU_D VLLM_NIXL_SIDE_CHANNEL_PORT=$((PORT + 4)) $(serve $((PORT + 2))) --kv-transfer-config '$KV'"
  PROXY_CMD="python $VENV_PATH/../tests/v1/kv_connector/nixl_integration/toy_proxy_server.py --host 127.0.0.1 --port $PORT \
--prefiller-hosts 127.0.0.1 --prefiller-ports $((PORT + 1)) --decoder-hosts 127.0.0.1 --decoder-ports $((PORT + 2))"
  printf '%s\n' "# prefill" "$P_CMD" "# decode" "$D_CMD" "# proxy" "$PROXY_CMD" > "$RUN_DIR/server_cmd.txt"
  export UCX_NET_DEVICES=all
  launch prefill.log "$P_CMD"; P_PID=$!
  launch decode.log "$D_CMD"; D_PID=$!
  echo "waiting for prefill and decode vLLM ..."
  wait_healthy "http://127.0.0.1:$((PORT + 1))/health" prefill.log $P_PID
  wait_healthy "http://127.0.0.1:$((PORT + 2))/health" decode.log $D_PID
  launch proxy.log "$PROXY_CMD"
  wait_healthy "$URL/healthcheck" proxy.log $!
  METRICS_URL=http://127.0.0.1:$((PORT + 1)),http://127.0.0.1:$((PORT + 2))
  LOGS=(prefill.log decode.log)
else
  SERVE=$(serve $PORT)
  echo "$SERVE" > "$RUN_DIR/server_cmd.txt"
  launch server.log "$SERVE"
  echo "waiting for vLLM on $URL ..."
  wait_healthy "$URL/health" server.log $!
  LOGS=(server.log)
fi
echo "ready after $SECONDS s"
for log in "${LOGS[@]}"; do
  echo "== $log"
  # grep -m, not | head: head closing the pipe early would SIGPIPE grep and, with pipefail, end the job
  grep -m 25 -iE "attention backend|KV cache|maximum concurrency|max_num_seqs|max_num_batched_tokens|chunked prefill|non-default args|nixl" \
    "$RUN_DIR/$log" || true
done | tee "$RUN_DIR/server_config_lines.txt"

if [ -n "${PRIME_CMD:-}" ]; then
  echo "+ (priming, not measured) $PRIME_CMD"
  eval "$PRIME_CMD"
fi
echo "+ $SIM_CMD"
eval "$SIM_CMD"
for log in "${LOGS[@]}"; do  # the reset endpoint always answers 200; vLLM only logs a refusal
  n=$(grep -c "Failed to reset prefix cache" "$RUN_DIR/$log" || true)
  if [ "$n" -gt 0 ]; then
    echo "WARNING: $log: $n prefix-cache resets refused (requests still holding KV); those runs may have cache hits"
  fi
done
echo "done after $SECONDS s"
