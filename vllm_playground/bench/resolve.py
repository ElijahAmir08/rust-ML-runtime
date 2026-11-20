#!/usr/bin/env python3
"""Read and validate an experiment JSON for run.sh. Standard library only.

    resolve.py <config.json> --count           number of runs
    resolve.py <config.json> --names           run names, one per line
    resolve.py <config.json> --run <i>         shell assignments for run i (eval'd by run.sh)
    resolve.py <config.json> --describe        the config's description

Unknown keys are errors, so a typo like "warmpu" fails at submit time instead of silently
running with the default.

Seeding: the top-level "seed" (required; a run may override it) seeds the workload (arrival times,
which trace rows set the lengths, replay thinning), every request's prompt tokens, and
`vllm serve --seed`. Repeat i of a run uses seed + i.
"""
import json
import shlex
import sys
from datetime import datetime
from pathlib import Path

SERVER = {"model": "Qwen/Qwen2.5-7B-Instruct", "max_model_len": 8192, "args": [], "venv": "../vllm/.venv"}
SLURM = {"partition": "gpu", "gpus": 1, "cpus": 8, "mem": "64G", "time": "8:00:00"}
SWEEP = {"repeats": 3, "duration": 180, "warmup": 45, "prime": True, "short_ctx": 512, "long_ctx": 3072}
REPLAY = {"repeats": 1}
SCENARIOS = {"baseline", "scheduler", "kv_cache"}
TOP = {"description", "notes", "seed", "server", "slurm", "runs"}


def fail(msg):
    sys.exit(f"{CONFIG}: {msg}")


def merged(name, given, defaults, extra=()):
    if not isinstance(given, dict):
        fail(f'"{name}" must be an object')
    unknown = set(given) - set(defaults) - set(extra)
    if unknown:
        fail(f'unknown key(s) in "{name}": {", ".join(sorted(unknown))} (allowed: {", ".join(sorted(set(defaults) | set(extra)))})')
    return {**defaults, **given}


def positive(run, key):
    v = run[key]
    if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
        fail(f'run "{run["name"]}": "{key}" must be a positive number, got {v!r}')
    return v


def resolve_run(cfg, i):
    raw = cfg["runs"][i]
    if not isinstance(raw, dict) or "name" not in raw or "mode" not in raw:
        fail(f"runs[{i}] needs at least \"name\" and \"mode\"")
    name, mode = raw["name"], raw["mode"]
    if not name.replace("_", "").replace("-", "").isalnum():
        fail(f'run name "{name}" may only contain letters, digits, - and _')
    seed = raw.get("seed", cfg["seed"])
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        fail(f'run "{name}": "seed" must be a non-negative integer, got {seed!r}')
    server = merged("server", cfg.get("server", {}), SERVER)
    slurm = merged("slurm", cfg.get("slurm", {}), SLURM)
    common = ["--model", server["model"], "--url", "$URL", "--max-model-len", str(server["max_model_len"]),
              "--out", "$RUN_DIR"]
    run_slurm = {k: raw[k] for k in SLURM if k in raw}  # per-run overrides, e.g. a longer "time"

    if mode == "sweep":
        run = merged(f"runs[{i}]", raw, SWEEP, extra={"name", "mode", "scenario", "rates", "seed", *SLURM})
        if run.get("scenario") not in SCENARIOS:
            fail(f'run "{name}": "scenario" must be one of {sorted(SCENARIOS)}')
        rates = run.get("rates")
        if not rates or not all(isinstance(r, (int, float)) and r > 0 for r in rates):
            fail(f'run "{name}": "rates" must be a non-empty list of positive numbers')
        for k in ("repeats", "duration"):
            positive(run, k)
        rate_list = ",".join(f"{r:g}" for r in rates)
        sim = ["python", "-m", "workload_sim", "sweep", *common, "--scenario", run["scenario"],
               "--rates", rate_list, "--repeats", str(run["repeats"]), "--duration", str(run["duration"]),
               "--warmup", str(run["warmup"]), "--seed", str(seed),
               "--short-ctx", str(run["short_ctx"]), "--long-ctx", str(run["long_ctx"])]
        prime = []
        if run["prime"]:
            # one-time kernel compiles stalled the first run on a fresh server ~9 s; absorb them here
            prime = ["python", "-m", "workload_sim", "sweep", *common[:-1], "$PRIME_DIR", "--scenario",
                     run["scenario"], "--rates", f"{max(rates):g}", "--duration", "60", "--warmup", "0",
                     "--seed", "1000", "--monitor-interval", "0", "--cooldown", "10",
                     "--short-ctx", str(run["short_ctx"]), "--long-ctx", str(run["long_ctx"])]
    elif mode == "replay":
        run = merged(f"runs[{i}]", raw, REPLAY,
                     extra={"name", "mode", "start", "hours", "speedup", "rate_scale", "seed", *SLURM})
        try:
            datetime.strptime(str(run.get("start")), "%Y-%m-%d %H:%M")
        except ValueError:
            fail(f'run "{name}": "start" must look like "2024-05-14 10:00" (UTC)')
        for k in ("hours", "speedup", "rate_scale", "repeats"):
            if k not in run:
                fail(f'run "{name}": replay needs "{k}"')
            positive(run, k)
        sim = ["python", "-m", "workload_sim", "replay", *common, "--start", run["start"],
               "--hours", str(run["hours"]), "--speedup", str(run["speedup"]),
               "--rate-scale", str(run["rate_scale"]), "--repeats", str(run["repeats"]), "--seed", str(seed)]
        prime = []
    else:
        fail(f'run "{name}": "mode" must be "sweep" or "replay", got {mode!r}')

    def cmd(argv):  # quote everything except the $URL / $RUN_DIR / $PRIME_DIR placeholders, expanded in the job
        return " ".join(a if a.startswith("$") else shlex.quote(a) for a in argv)

    slurm = {**slurm, **run_slurm}
    out = {
        "RUN_NAME": name, "RUN_MODE": mode,
        "SIM_CMD": cmd(sim), "PRIME_CMD": cmd(prime) if prime else "",
        "MODEL": server["model"], "MAX_MODEL_LEN": str(server["max_model_len"]),
        # vLLM's own seed too, unless the config sets one in server.args
        "SERVE_ARGS": " ".join(shlex.quote(str(a)) for a in
                               (server["args"] if "--seed" in server["args"] else [*server["args"], "--seed", seed])),
        "VENV_PATH": server["venv"], "SEED": str(seed),
        "PARTITION": slurm["partition"], "GPUS": str(slurm["gpus"]), "CPUS": str(slurm["cpus"]),
        "MEM": slurm["mem"], "TIME": slurm["time"],
    }
    return "\n".join(f"{k}={shlex.quote(v)}" for k, v in out.items())


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    CONFIG = sys.argv[1]
    try:
        cfg = json.loads(Path(CONFIG).read_text())
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"{CONFIG}: {e}")
    if not isinstance(cfg, dict):
        fail("top level must be an object")
    if set(cfg) - TOP:
        fail(f"unknown top-level key(s): {', '.join(sorted(set(cfg) - TOP))} (allowed: {', '.join(sorted(TOP))})")
    if "seed" not in cfg:
        fail('"seed" is required (top level) so every run is reproducible, e.g. "seed": 0')
    if not isinstance(cfg.get("runs"), list) or not cfg["runs"]:
        fail('"runs" must be a non-empty list')
    names = [r.get("name") for r in cfg["runs"] if isinstance(r, dict)]
    if len(set(names)) != len(names):
        fail("run names must be unique")
    resolved = [resolve_run(cfg, i) for i in range(len(cfg["runs"]))]  # validate every run up front
    what = sys.argv[2]
    if what == "--count":
        print(len(cfg["runs"]))
    elif what == "--names":
        print("\n".join(names))
    elif what == "--describe":
        print(cfg.get("description", ""))
    elif what == "--run":
        print(resolved[int(sys.argv[3])])
    else:
        sys.exit(__doc__)
