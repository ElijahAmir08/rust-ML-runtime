#!/usr/bin/env bash
# One entry point for every experiment. Each experiment is experiments/<name>.json; every entry in
# its "runs" list becomes one Slurm job (one GPU, its own vLLM server), all submitted in parallel.
#
#   ./run.sh <name>                      submit every run of experiments/<name>.json
#   ./run.sh <name> --only scheduler     submit just the named run(s) (repeatable)
#   ./run.sh <name> --tag v2             write to results/<name>_v2/ (results are never overwritten)
#   ./run.sh --dry-run <name>            print what would be submitted and stop
#   ./run.sh --local <name> --only X     run inline on this node (must have a GPU, e.g. inside srun)
#   ./run.sh --after 12345 <name>        start only if job 12345 succeeds
#   ./run.sh --list                      list experiments
#
# Results: results/<name>[_<tag>]/<run>/ (plus the slurm log there). Every submission is appended
# to experiments/runs.tsv with the git commit. See workload_sim.md for the config format.
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXP_DIR=experiments
TEMPLATE=slurms/_job.slurm
RUN_LOG=$EXP_DIR/runs.tsv
RESOLVE=(python3 -I bench/resolve.py)

usage() { sed -n '2,16p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'; exit 1; }

list_experiments() {
    echo "Experiments in $EXP_DIR/:"
    for f in "$EXP_DIR"/*.json; do
        [ -e "$f" ] || { echo "  (none yet)"; return; }
        printf '  %-22s %s\n' "$(basename "$f" .json)" "$("${RESOLVE[@]}" "$f" --describe 2>&1 | head -1 | cut -c1-90)"
    done
}

local_run=0; dry_run=0; after=""; tag=""; only=()
args=()
while [ $# -gt 0 ]; do  # flags may come before or after the experiment name
    case "$1" in
        --local)   local_run=1; shift ;;
        --dry-run) dry_run=1; shift ;;
        --after)   after="$2"; shift 2 ;;
        --tag)     tag="$2"; shift 2 ;;
        --only)    only+=("$2"); shift 2 ;;
        --list)    list_experiments; exit 0 ;;
        -h|--help) usage ;;
        -*)        echo "unknown flag: $1" >&2; usage ;;
        *)         args+=("$1"); shift ;;
    esac
done
[ ${#args[@]} -eq 1 ] || usage
name=${args[0]}
conf=$EXP_DIR/$name.json
[ -f "$conf" ] || { echo "No experiment '$name' ($conf not found)" >&2; list_experiments >&2; exit 1; }

n=$("${RESOLVE[@]}" "$conf" --count)  # also validates the whole config
mapfile -t names < <("${RESOLVE[@]}" "$conf" --names)
for o in ${only[@]+"${only[@]}"}; do
    printf '%s\n' "${names[@]}" | grep -qx "$o" || { echo "$conf has no run '$o' (runs: ${names[*]})" >&2; exit 1; }
done

out_name=$name${tag:+_$tag}
results=results/$out_name
selected() { [ ${#only[@]} -eq 0 ] && return 0; printf '%s\n' "${only[@]}" | grep -qx "$1"; }

if [ "$dry_run" -eq 0 ]; then  # check everything before submitting anything
    for r in "${names[@]}"; do
        selected "$r" || continue
        [ -e "$results/$r" ] && { echo "$results/$r already exists; use --tag to write a new copy (results are never overwritten)" >&2; exit 1; }
    done
    if [ -f "$results/experiment.json" ] && ! cmp -s "$conf" "$results/experiment.json"; then
        echo "$conf changed since runs were submitted to $results/; use --tag for the new version" >&2; exit 1
    fi
fi

git_sha=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)
git_dirty=$(git status --porcelain -- workload_sim bench slurms run.sh experiments 2>/dev/null | grep -c . || true)

record_run() {  # job id, run name, results dir
    [ -f "$RUN_LOG" ] || printf 'when\tjob_id\texperiment\trun\tgit_sha\tuncommitted_files\tresults\n' > "$RUN_LOG"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$name" "$2" "$git_sha" "$git_dirty" "$3" >> "$RUN_LOG"
}

for i in $(seq 0 $((n - 1))); do
    # RUN_NAME RUN_MODE SIM_CMD PRIME_CMD MODEL MAX_MODEL_LEN SERVE_ARGS VENV_PATH SEED PARTITION GPUS CPUS MEM TIME
    eval "$("${RESOLVE[@]}" "$conf" --run "$i")"
    selected "$RUN_NAME" || continue
    run_dir=$results/$RUN_NAME
    job_name="${out_name}:${RUN_NAME}"

    if [ "$dry_run" -eq 1 ]; then
        echo "== $RUN_NAME ($RUN_MODE, seed $SEED) -> $run_dir/"
        echo "  server:  vllm serve $MODEL --dtype half --max-model-len $MAX_MODEL_LEN $SERVE_ARGS   (venv $VENV_PATH)"
        [ -n "$PRIME_CMD" ] && echo "  priming: $PRIME_CMD"
        echo "  command: $SIM_CMD"
        [ "$local_run" -eq 0 ] && echo "  sbatch:  --job-name=$job_name --partition=$PARTITION --gres=gpu:$GPUS --cpus-per-task=$CPUS --mem=$MEM --time=$TIME${after:+ --dependency=afterok:$after}"
        continue
    fi

    mkdir -p "$run_dir"
    cp "$conf" "$results/experiment.json"
    {
        echo "submitted: $(date -Is) from $(hostname)"
        echo "rust-ML-runtime: $git_sha, uncommitted files in workload_sim/ bench/ slurms/ experiments/ run.sh: $git_dirty"
        git status --porcelain -- workload_sim bench slurms run.sh experiments 2>/dev/null | sed 's/^/  /'
        echo "vllm: $(git -C "$VENV_PATH/../" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    } > "$run_dir/git.txt"  # GPU nodes have no git, so record it here

    export RUN_DIR="$(pwd)/$run_dir" PRIME_DIR="$(pwd)/results/_priming/$out_name/$RUN_NAME"
    export SIM_CMD PRIME_CMD MODEL MAX_MODEL_LEN SERVE_ARGS VENV_PATH

    if [ "$local_run" -eq 1 ]; then
        record_run local "$RUN_NAME" "$run_dir"
        echo "== $RUN_NAME: running inline"
        bash "$TEMPLATE" 2>&1 | tee "$run_dir/local.out"
        continue
    fi

    sb=(--parsable --job-name="$job_name" --partition="$PARTITION" --gres="gpu:$GPUS"
        --cpus-per-task="$CPUS" --mem="$MEM" --time="$TIME" --output="$run_dir/slurm-%j.out" --export=ALL)
    [ -n "$after" ] && sb+=(--dependency="afterok:$after")
    job_id=$(sbatch "${sb[@]}" "$TEMPLATE")
    record_run "$job_id" "$RUN_NAME" "$run_dir"
    echo "$job_id  $job_name  -> $run_dir/slurm-$job_id.out"
done
