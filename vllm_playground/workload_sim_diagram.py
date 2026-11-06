#!/usr/bin/env python3
"""Diagram of the benchmarking system: how an experiment is launched, what one run of workload_sim
does, and when every metric is collected.

    python3 workload_sim_diagram.py    # writes workload_sim_diagram.png and .svg next to this file

Only needs matplotlib. Everything is laid out by hand, so when run.sh, slurms/_job.slurm or
workload_sim/ change, update the text here to match.
"""
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import to_rgb  # noqa: E402
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

OUT = Path(__file__).with_suffix("")

W, H = 232, 268  # canvas units; 10 units = 1 inch, so units are square
LINE = 1.9  # card body line height
HDR = 3.6  # card header height
SANS, MONO = "DejaVu Sans", "DejaVu Sans Mono"
INK, MUTED, FAINT = "#1e2430", "#5b6475", "#a3abb9"

COL = {
    "inputs": "#475569",
    "sweep": "#2563eb",
    "replay": "#7c3aed",
    "build": "#4338ca",
    "run": "#0f766e",
    "server": "#c2410c",
    "measure": "#be123c",
    "outputs": "#475569",
    "launch": "#334155",
}


def tint(color, amount):
    """Mix color with white; amount=1 is white."""
    return tuple(c + (1 - c) * amount for c in to_rgb(color))


fig = plt.figure(figsize=(W / 10, H / 10), facecolor="white")
ax = None  # the current section's axes; every drawing helper draws into it


def section(top, height, ylo=0.0):
    """New axes for a horizontal band of the canvas: global y in [top - height, top] maps to local
    y in [ylo, ylo + height], x is 0..W. Units stay square."""
    a = fig.add_axes([0, (top - height) / H, 1, height / H])
    a.set_xlim(0, W)
    a.set_ylim(ylo, ylo + height)
    a.axis("off")
    return a


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def top(self):
        return self.y + self.h

    @property
    def right_x(self):
        return self.x + self.w

    def left(self, f=0.5):
        return (self.x, self.y + self.h * f)

    def right(self, f=0.5):
        return (self.x + self.w, self.y + self.h * f)

    def tc(self, f=0.5):
        return (self.x + self.w * f, self.top)

    def bc(self, f=0.5):
        return (self.x + self.w * f, self.y)


# ----------------------------------------------------------------------------- primitives
def text(x, y, s, size=8.4, color=INK, family=SANS, **kw):
    kw.setdefault("va", "center")
    return ax.text(x, y, s, fontsize=size, color=color, family=family, zorder=kw.pop("zorder", 6), **kw)


def styled_line(s, color):
    """Line markup: `mono   *bold (stage color)   ~muted italic note   plain sans."""
    if s.startswith("`"):
        return s[1:], dict(family=MONO, color=INK)
    if s.startswith("*"):
        return s[1:], dict(family=SANS, color=color, fontweight="bold")
    if s.startswith("~"):
        return s[1:], dict(family=SANS, color=MUTED, style="italic")
    return s, dict(family=SANS, color=INK)


def card(x, top, w, title, lines, color, sub=None, size=8.4, title_size=9.2):
    """Rounded card with a colored header; height follows the number of body lines."""
    h = HDR + 1.3 + LINE * len(lines) + 0.9
    y = top - h
    rs = "round,pad=0,rounding_size=1.1"
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=rs, fc=tint(color, 0.93), ec="none", zorder=2))
    ax.add_patch(FancyBboxPatch((x, top - HDR), w, HDR, boxstyle=rs, fc=color, ec="none", zorder=3))
    ax.add_patch(Rectangle((x, top - HDR), w, HDR / 2, fc=color, ec="none", zorder=3))
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=rs, fc="none", ec=color, lw=1.0, zorder=4))
    text(x + 1.3, top - HDR / 2, title, size=title_size, color="white", family=MONO, fontweight="bold")
    if sub:
        text(x + w - 1.3, top - HDR / 2, sub, size=7.4, color=tint(color, 0.7), ha="right")
    for i, ln in enumerate(lines):
        s, kw = styled_line(ln, color)
        text(x + 1.4, top - HDR - 1.3 - LINE * (i + 0.5), s, size=size, **kw)
    return Box(x, y, w, h)


def group(x, y, w, h, label, color, note=None, z=1):
    """Dashed container with a pill label on its top edge."""
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.8",
                                fc=tint(color, 0.975), ec=tint(color, 0.35), lw=1.2,
                                ls=(0, (5, 3)), zorder=z))
    text(x + 2.0, y + h, label, size=8.8, color="white", family=MONO, fontweight="bold",
         bbox=dict(boxstyle="round,pad=0.32,rounding_size=0.8", fc=color, ec="none"))
    if note:
        text(x + w - 1.5, y + h - 2.6, note, size=7.6, color=MUTED, style="italic", ha="right")
    return Box(x, y, w, h)


def route(points, color=INK, lw=1.4, label=None, label_xy=None, label_ha="center", head=True,
          ls="-", label_color=None, label_size=7.6):
    """Orthogonal polyline with an arrowhead on its last segment."""
    xs, ys = zip(*points)
    if len(points) > 2:
        ax.plot(xs[:-1], ys[:-1], color=color, lw=lw, ls=ls, solid_joinstyle="round",
                solid_capstyle="round", zorder=5)
    if head:
        ax.add_patch(FancyArrowPatch(points[-2], points[-1], arrowstyle="-|>", mutation_scale=11,
                                     lw=lw, color=color, ls=ls, shrinkA=0, shrinkB=0.6, zorder=5))
    else:
        ax.plot(xs[-2:], ys[-2:], color=color, lw=lw, ls=ls, solid_capstyle="round", zorder=5)
    if label:
        text(*label_xy, label, size=label_size, color=label_color or color, ha=label_ha,
             bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="none", alpha=0.92))


def dot(x, y, color=INK):
    ax.add_patch(Circle((x, y), 0.55, fc=color, ec="none", zorder=6))


def stage(x, w, num, title, sub, color, y=134.5):
    ax.add_patch(Circle((x + 2.3, y), 2.1, fc=color, ec="none", zorder=5))
    text(x + 2.3, y - 0.05, str(num), size=10, color="white", fontweight="bold", ha="center")
    text(x + 5.6, y + 0.9, title, size=11.2, fontweight="bold")
    text(x + 5.6, y - 2.0, sub, size=7.8, color=MUTED, family=MONO)
    ax.plot([x, x + w], [y - 4.4, y - 4.4], color=tint(color, 0.55), lw=1.6, solid_capstyle="round")


def heading(y, letter, title, sub, x=4):
    """Section heading: letter badge, title and a one-line explanation."""
    ax.add_patch(FancyBboxPatch((x, y - 1.9), 3.8, 3.8, boxstyle="round,pad=0,rounding_size=0.8",
                                fc=INK, ec="none", zorder=5))
    text(x + 1.9, y - 0.05, letter, size=10.5, color="white", fontweight="bold", ha="center")
    text(x + 6, y + 0.15, title, size=13, fontweight="bold")
    text(x + 6, y - 3.1, sub, size=9, color=MUTED)


def panel(x, y, w, h, title, sub=None):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.8",
                                fc="#f8fafc", ec="#d5dbe3", lw=1.0, zorder=0))
    text(x + 2.2, y + h - 2.8, title, size=10.2, fontweight="bold")
    if sub:
        text(x + 2.2, y + h - 5.6, sub, size=7.8, color=MUTED, style="italic")


def hbracket(xa, xb, y, label, color, size=8.0, down=True, bold=False, family=SANS):
    d = -0.7 if down else 0.7
    ax.plot([xa, xa, xb, xb], [y - d, y, y, y - d], color=color, lw=1.2, zorder=5)
    text((xa + xb) / 2, y + (-1.4 if down else 1.4), label, size=size, color=color, ha="center",
         fontweight="bold" if bold else "normal", family=family)


def legend_row(x, y, items, size=7.8):
    """items: (kind, color, label) with kind in {'box', 'hatch', 'tri'}; laid out left to right."""
    for kind, color, label in items:
        if kind == "tri":
            ax.plot([x + 0.8], [y], marker="v", ms=5.5, color=color, zorder=6)
        else:
            ax.add_patch(Rectangle((x, y - 0.8), 2.4, 1.6, fc=color, ec="#8892a0" if kind == "hatch" else "none",
                                   hatch="////" if kind == "hatch" else None, lw=0, zorder=6))
        text(x + 3.2, y, label, size=size, color=MUTED)
        x += 3.2 + len(label) * size * 0.56 / 7.2 + 3.2


# ============================================================================= title
ax = section(268, 12)
text(4, 7.0, "workload_sim: how an experiment runs, and when every metric is collected", size=17, fontweight="bold")
text(4, 2.6, "Open-loop benchmarking of vLLM. A JSON config is launched as Slurm jobs; each job serves the model "
     "and runs seeded workloads built from the Azure LLM trace, timing every streamed token and polling vLLM's own "
     "metrics.", size=9.6, color=MUTED)

# ============================================================================= A: launch
ax = section(255, 46)
heading(42.5, "A", "Launching an experiment",
        "one config file, one command, one Slurm job per entry in \"runs\" (each with its own V100 and vLLM server)")

login = group(4, 2, 90, 31, "login node", COL["launch"])
cfg = card(7, 29, 38, "experiments/<name>.json", [
    "`\"seed\": 0",
    "`\"server\": model, max_model_len,",
    "`          args, venv",
    "`\"slurm\": partition, gpus, time, ...",
    "`\"runs\": [sweep | replay, ...]",
    "~one entry in runs = one job",
], COL["launch"], size=8.0)
rsh = card(52, 29, 39, "./run.sh <name>", [
    "bench/resolve.py validates (typo → error)",
    "builds the exact serve + workload commands",
    "refuses existing results (new copy: --tag)",
    "writes experiment.json, git.txt",
    "appends experiments/runs.tsv",
    "*sbatch slurms/_job.slurm, once per run",
    "~--local: run inline · --dry-run: only print",
], COL["launch"], size=8.0)
route([cfg.right(0.5), (rsh.x, cfg.right(0.5)[1])], color=COL["launch"])
text(7, 6.4, "e.g.  ./run.sh baseline_v1   ·   ./run.sh --dry-run baseline_v1   ·   "
     "./run.sh smoke --tag x --only scheduler", size=7.6, color=MUTED, family=MONO)

# a stack of job outlines behind the job group: one job per run
for k, z in ((2, 0.2), (1, 0.4)):
    ax.add_patch(FancyBboxPatch((100 + 0.9 * k, 2 - 0.9 * k), 128, 31, boxstyle="round,pad=0,rounding_size=1.8",
                                fc="white", ec=tint(COL["run"], 0.45), lw=1.0, zorder=z))
job = group(100, 2, 128, 31, "slurms/_job.slurm  ·  GPU node", COL["run"],
            note="one job per run, all submitted in parallel")
route([rsh.right(0.5), (job.x, rsh.right(0.5)[1])], color=COL["launch"], label="sbatch",
      label_xy=((rsh.right_x + job.x) / 2, rsh.right(0.5)[1] + 1.8))

chip_w, gap, cx = 22.2, 3.0, 102.5
steps = [
    ("1 vllm serve", COL["server"], ["`--dtype half (V100)", "`--max-model-len 8192", "`--seed S + server.args",
                                     "→ server_cmd.txt,", "   server.log"]),
    ("2 wait /health", COL["server"], ["poll every 5 s, ≤ 15 min", "(compile, CUDA graphs)",
                                       "→ env.txt: GPU, other", "   processes, versions",
                                       "→ server_config_lines"]),
    ("3 priming", COL["run"], ["sweeps: 60 s at the", "highest rate", "*not measured",
                               "absorbs one-time", "kernel compiles", "→ results/_priming/"]),
    ("4 workload_sim", COL["run"], ["`for i in repeats:", "`  seed + i", "`  for rate in rates:",
                                    "`    one run (B)", "`    cooldown 5 s", "→ results/<exp>/<run>/"]),
    ("5 stop", COL["server"], ["exit trap stops", "vllm serve", "", "→ slurm-<job>.out"]),
]
chips = []
for title, color, lines in steps:
    lines = lines + [""] * (6 - len(lines))
    chips.append(card(cx, 29.5, chip_w, title, lines, color, size=7.4, title_size=8.4))
    cx += chip_w + gap
for a, b in zip(chips, chips[1:]):
    route([a.right(0.55), b.left(0.55)], color=COL["run"], lw=1.2)

# one job over time
jy, jx0, jx1 = 7.2, 103, 225
segs = [("vLLM startup", 0.15, tint(COL["server"], 0.55)), ("priming", 0.07, tint(COL["run"], 0.6))]
for k in range(6):
    segs += [("run", 0.104, COL["run"]), ("cd", 0.016, "#cbd2db")]
segs += [("stop", 0.04, COL["server"])]
scale = (jx1 - jx0) / sum(f for _, f, _ in segs)
x = jx0
for label, frac, color in segs:
    w_ = frac * scale
    ax.add_patch(Rectangle((x, jy - 1.0), w_, 2.0, fc=color, ec="white", lw=0.6, zorder=3))
    if label in ("vLLM startup", "priming"):
        text(x + w_ / 2, jy, label, size=6.8, color=INK, ha="center")
    x += w_
runs_x0 = jx0 + (0.15 + 0.07) * scale
text(jx0, jy + 2.4, "one job over time:", size=7.4, color=MUTED, style="italic")
hbracket(runs_x0, x - 0.04 * scale, jy - 1.6, "one run per rate × repeat, each followed by a 5 s cooldown",
         COL["run"], size=7.4)

# ============================================================================= B: one run
ax = section(208, 100, ylo=44)
heading(141.5, "B", "One run inside the job",
        "workload_sim builds a seeded list of requests, sends each at its scheduled time, and measures; "
        "the job repeats this for every rate × repeat")

C1, C2, C3, C4, C5 = (4, 36), (47, 48), (103, 40), (151, 30), (189, 39)
stage(*C1, 1, "Inputs", "trace CSV · command from run.sh", COL["inputs"], y=131)
stage(*C2, 2, "Build the workload", "workload.py", COL["sweep"], y=131)
stage(*C3, 3, "Run it (open loop)", "load_generator.py · client.py", COL["run"], y=131)
stage(*C4, 4, "vLLM server", "system under test", COL["server"], y=131)
stage(*C5, 5, "Measure & report", "request.py · metrics.py · server_metrics.py", COL["measure"], y=131)

TOP, BOT = 124, 46.5

# ----------------------------------------------------------------------------- 1 inputs
trace = card(C1[0], 123, C1[1], "Azure LLM trace", [
    "`AzureLLMInferenceTrace_conv_1week.csv",
    "`TIMESTAMP, ContextTokens, GeneratedTokens",
    "27.3 M requests, 2024-05-12 → 05-18 (UTC)",
    "~path, size + mtime go in run_info.json",
], COL["inputs"], sub="CSV")

cmd = card(C1[0], trace.y - 3.4, C1[1], "workload_sim command", [
    "`python -m workload_sim sweep",
    "`  --scenario S --rates r1,r2,...",
    "`  --repeats R --duration D --warmup W",
    "*or",
    "`python -m workload_sim replay",
    "`  --start T --hours H --speedup X",
    "`  --rate-scale F --repeats R",
    "*both",
    "`  --seed S --max-model-len 8192",
    "`  --out results/<exp>/<run>",
    "~defaults: --monitor-interval 1 s,",
    "~--cooldown 5 s between runs",
], COL["inputs"], sub="from run.sh")

seed = card(C1[0], cmd.y - 3.0, C1[1], "seeding (repeat i: seed + i)", [
    "arrival times (Poisson gaps)",
    "which trace rows give the lengths",
    "which rows a replay keeps",
    "each request's prompt tokens:",
    "   own RNG seeded by (seed, id)",
    "vllm serve --seed (set by run.sh)",
    "~same seed → same requests, times, prompts",
], COL["inputs"])

# ----------------------------------------------------------------------------- 2 build
ix, iw = C2[0] + 2, C2[1] - 4
group(C2[0], 81.5, C2[1], TOP - 81.5, "sweep", COL["sweep"], note="Poisson arrivals")
lt_s = card(ix, 120, iw, "load_trace(trace)", [
    "reads only ContextTokens, GeneratedTokens",
], COL["sweep"])
sr = card(ix, lt_s.y - 3, iw, "scenario_rows(trace, scenario)", [
    "`baseline    all rows",
    "`kv_cache    ContextTokens >= --long-ctx",
    "`scheduler   ContextTokens <= --short-ctx",
], COL["sweep"])
pw = card(ix, sr.y - 3, iw, "PoissonWorkload(rows, rate)", [
    "*one per rate × repeat, seeded (seed + repeat)",
    "gaps ~ Exponential(mean 1 / rate)",
    "arrivals = cumsum(gaps), kept while < warmup + duration",
    "lengths: trace rows sampled with replacement",
], COL["sweep"])

group(C2[0], BOT, C2[1], 78 - BOT, "replay", COL["replay"], note="real timestamps")
lt_r = card(ix, 74, iw, "load_trace(trace, start, end)", [
    "keeps rows with start <= TIMESTAMP < start + hours",
    "parses TIMESTAMP (only needed for replay)",
], COL["replay"])
rw = card(ix, lt_r.y - 3, iw, "ReplayWorkload(window)", [
    "keeps each row with probability --rate-scale",
    "`arrival = (TIMESTAMP − start) / speedup",
    "lengths: each kept row's own token counts",
], COL["replay"])

for a, b, key in ((lt_s, sr, "sweep"), (sr, pw, "sweep"), (lt_r, rw, "replay")):
    route([a.bc(), b.tc()], color=COL[key], lw=1.3)

route([trace.right(0.55), (lt_s.x, trace.right(0.55)[1])], color=COL["inputs"])
fork_y = trace.right(0.25)[1]
route([trace.right(0.25), (43.5, fork_y), (43.5, lt_r.left()[1]), lt_r.left()], color=COL["inputs"])

# ----------------------------------------------------------------------------- 3 run
jx, jw = C3[0] + 2, C3[1] - 4
group(C3[0], BOT, C3[1], TOP - BOT, "run_workload()", COL["run"])
text(C3[0] + C3[1] - 1.5, TOP - 2.6, "one asyncio.run per run (rate × repeat)", size=7.4,
     color=MUTED, style="italic", ha="right")
bld = card(jx, 119, jw, "Workload._build()", [
    "~called by workload.requests()",
    "`p = clip(prompt, 1, max_model_len − 1)",
    "`o = clip(output, 1, max_model_len − p)",
    "*→ list[Request], in arrival order",
    "`Request(id, arrival_time,",
    "`        prompt_tokens, output_tokens)",
], COL["build"], sub="workload.py")
lg = card(jx, bld.y - 4.2, jw, "LoadGenerator.run()", [
    "`start = time.monotonic()   # t = 0",
    "`for req in requests:",
    "`    due = start + req.arrival_time",
    "`    sleep until due   # absolute: no drift",
    "`    if already late: track max_lag",
    "`    create_task(client.send(req, due))",
    "`results = await gather(*tasks)",
    "*never waits on earlier requests",
    "warns if max_lag > 100 ms (client too slow)",
], COL["run"])
vc = card(jx, lg.y - 4.2, jw, "VLLMClient.send(req, due)", [
    "`POST {url}/v1/completions",
    "`  prompt: prompt_tokens random ids",
    "`    from [1000, 20000), RNG(seed, id)",
    "`  max_tokens: output_tokens",
    "`  ignore_eos, stream, include_usage",
    "each streamed chunk with choices:",
    "`  token_times.append(now − due)",
    "usage chunk → received_tokens",
    "~aiohttp: no connection cap, no timeout",
], COL["run"])

bus_x = 99
route([pw.right(), (bus_x, pw.right()[1])], color=COL["sweep"], head=False)
route([rw.right(), (bus_x, rw.right()[1]), (bus_x, bld.left()[1]), bld.left()], color=COL["build"])
ax.plot([bus_x, bus_x], [rw.right()[1], pw.right()[1]], color=COL["replay"], lw=1.4, zorder=5)
dot(bus_x, pw.right()[1], COL["build"])
text(bus_x - 0.8, bld.left()[1] + 1.9, "requests()", size=7.4, color=COL["build"], family=MONO, ha="center")

route([bld.bc(), lg.tc()], color=COL["run"], label="list[Request]", label_xy=(lg.tc()[0] + 1.2, (bld.y + lg.top) / 2),
      label_ha="left", label_color=COL["build"])
route([lg.bc(), vc.tc()], color=COL["run"], label="one asyncio task per request",
      label_xy=(lg.tc()[0] + 1.2, (lg.y + vc.top) / 2), label_ha="left")

# ----------------------------------------------------------------------------- 4 server
srv = card(C4[0], 97, C4[1], "vLLM server", [
    "OpenAI-compatible API",
    "~started by slurms/_job.slurm",
    "", "", "", "", "", "",
    "*the system under test",
    "requests queue inside vLLM's",
    "scheduler, never in the client",
    "ignore_eos: exactly max_tokens",
    "random ids: no shared prefixes",
    "`GET /metrics  (Prometheus)",
], COL["server"])
mon = card(C4[0], srv.y - 3.6, C4[1], "ServerMonitor", [
    "polls /metrics every 1 s:",
    "`running, waiting, kv_cache",
    "counters at start and end:",
    "`queue time, preemptions",
    "*→ srv_* metrics, _server.csv",
], COL["run"], sub="client side")
route([srv.bc(), mon.tc()], color=COL["run"])
text(srv.bc()[0] + 1.0, (srv.y + mon.top) / 2, "scrape", size=7.0, color=COL["run"], style="italic")
gy = srv.top - HDR - 1.3 - LINE * 2
for row, (label, n, fill) in enumerate((("waiting", 6, tint(COL["server"], 0.6)), ("running", 4, COL["server"]))):
    yy = gy - 2.2 - row * 5.2
    text(srv.x + 1.4, yy, label, size=7.4, color=MUTED, family=MONO)
    for k in range(n):
        ax.add_patch(FancyBboxPatch((srv.x + 9.6 + k * 2.9, yy - 1.1), 2.2, 2.2,
                                    boxstyle="round,pad=0,rounding_size=0.4", fc=fill, ec="none", zorder=6))
    if row == 0:
        route([(srv.x + 16, yy - 1.6), (srv.x + 16, yy - 3.6)], color=COL["server"], lw=1.1)
        text(srv.x + 17.2, yy - 2.6, "scheduler", size=7.0, color=COL["server"], style="italic", va="center")
    else:
        text(srv.x + 9.6 + n * 2.9 + 0.2, yy, "→ GPU", size=7.4, color=MUTED)

req_y, resp_y = vc.y + vc.h * 0.62, vc.y + vc.h * 0.38
route([(vc.right_x, req_y), (srv.x, req_y)], color=COL["server"], label="HTTP POST",
      label_xy=((vc.right_x + srv.x) / 2, req_y + 1.6))
route([(srv.x, resp_y), (vc.right_x, resp_y)], color=COL["server"], label="SSE stream",
      label_xy=((vc.right_x + srv.x) / 2, resp_y - 1.6))

# ----------------------------------------------------------------------------- 5 measure
rr = card(C5[0], 123, C5[1], "RequestResult", [
    "`success, error",
    "`token_times  # s since due, per chunk",
    "`ttft = token_times[0]",
    "`e2e  = token_times[-1]",
    "`itls = gaps between token_times",
    "`tpot = (e2e − ttft) / (tokens − 1)",
    "`received_tokens  # from usage chunk",
], COL["measure"], sub="one per request")
rm = card(C5[0], rr.y - 4.2, C5[1], "RunMetrics(results, warmup)", [
    "*to_csv(): one row per request",
    "`id, arrival_time, prompt_tokens,",
    "`output_tokens, received_tokens,",
    "`success, ttft, e2e, tpot, mean_itl, error",
    "*summary()  (windows: see C)",
    "latency: requests arriving after warmup",
    "TTFT · TPOT · ITL · E2E: mean, p50/90/95/99",
    "steady state: requests + tokens finished",
    "   inside [warmup, warmup + duration)",
    "+ srv_* from ServerMonitor",
    "~replay: warmup 0, ends at last arrival",
], COL["measure"])
res = card(C5[0], rm.y - 4.2, C5[1], "results/<exp>/<run>/", [
    "`sweep_{scenario}_rate{r}_rep{i}.csv",
    "`  + ..._server.csv  (vLLM gauges)",
    "`sweep_{scenario}_summary.csv",
    "~one summary row per rate × repeat",
    "`replay_{start}_rep{i}.csv, ..._summary",
    "`*_run_info.json  (args, GPU, server)",
], COL["outputs"], sub="--out")

ret_y = rr.y + rr.h * 0.5
route([(vc.right_x, vc.top - 2.2), (146.5, vc.top - 2.2), (146.5, ret_y), (rr.x, ret_y)],
      color=COL["measure"], label="each send() returns a RequestResult; LoadGenerator gathers them",
      label_xy=((146.5 + rr.x) / 2 - 0.5, ret_y + 1.9), label_size=7.4)
route([rr.bc(), rm.tc()], color=COL["measure"], label="list[RequestResult]",
      label_xy=(rr.bc()[0] + 1.2, (rr.y + rm.top) / 2), label_ha="left", label_color=COL["measure"])
mx = (mon.right_x + rm.x) / 2
route([mon.right(0.35), (mx, mon.right(0.35)[1]), (mx, rm.left(0.3)[1]), rm.left(0.3)], color=COL["run"])
text(mx - 0.7, mon.right(0.35)[1] + 6, "srv_*", size=7.0, color=COL["run"], family=MONO, rotation=90, ha="center")
route([rm.bc(), res.tc()], color=COL["outputs"], label="report(): to_csv() + summary()",
      label_xy=(rm.bc()[0] + 1.2, (rm.y + res.top) / 2), label_ha="left")

# ============================================================================= C: metric timeline
ax = section(106, 60)
teal, red = COL["run"], COL["measure"]
panel(4, 1, 224, 56.5, "")
heading(54.0, "C", "When metrics are collected during one run",
        "illustrative sweep run; a replay works the same way with warmup = 0, no priming, and the measured "
        "interval ending at its last arrival", x=6.5)

T0, T1 = -0.8, 16.0
px0, px1 = 56, 222


def tx(t):
    return px0 + (px1 - px0) * (t - T0) / (T1 - T0)


WARM, DUR = 3.0, 6.0
reqs = [(0.5, 0.5, 2.0), (1.7, 0.6, 2.2), (3.2, 0.8, 2.5), (4.0, 1.1, 3.0),
        (5.0, 1.4, 3.1), (6.1, 1.2, 2.6), (7.0, 1.0, 3.3), (8.3, 1.3, 2.7)]
END = max(a + e for a, _, e in reqs)
COOL0, COOL1 = END + 0.25, END + 2.25
SNAP0, SNAP1 = -0.45, END + 0.1

text(150, 50.9, "each bar starts at its scheduled arrival:", size=7.4, color=MUTED)
legend_row(185, 50.9, [
    ("box", tint(teal, 0.55), "queued + prefill"),
    ("box", teal, "decoding"),
    ("box", "#c3c9d3", "arrived in warmup"),
], size=7.4)

# lane: requests
bar_top, bar_bot = 47.8, 35.4
ax.add_patch(Rectangle((tx(0), bar_bot - 0.5), tx(WARM) - tx(0), bar_top - bar_bot + 1.3, fc="#e9edf2", ec="none", zorder=1))
rh = (bar_top - bar_bot) / len(reqs)
for i, (a, ttft, e2e) in enumerate(reqs):
    yc = bar_top - rh * (i + 0.5)
    warm = a < WARM
    c1, c2 = ("#d5dae2", "#b4bcc8") if warm else (tint(teal, 0.55), teal)
    ax.add_patch(Rectangle((tx(a), yc - 0.5), tx(a + ttft) - tx(a), 1.0, fc=c1, ec="none", zorder=3))
    ax.add_patch(Rectangle((tx(a + ttft), yc - 0.5), tx(a + e2e) - tx(a + ttft), 1.0, fc=c2, ec="none", zorder=3))
    t = a + ttft
    while t <= a + e2e + 1e-9:  # one timestamp per streamed chunk
        ax.plot([tx(t)] * 2, [yc - 0.5, yc + 0.5], color="white", lw=0.7, zorder=4)
        t += 0.3
text(6.5, 46.0, "requests (client side)", size=8.6, color=teal, fontweight="bold")
text(6.5, 43.6, "VLLMClient.send() records one timestamp", size=7.8)
text(6.5, 41.5, "per streamed chunk (white ticks)", size=7.8)
text(6.5, 39.4, "→ token_times → TTFT, TPOT, ITL, E2E", size=7.8)
text(6.5, 37.3, "→ _rep{i}.csv, one row per request", size=7.8, color=MUTED)

# lane: ServerMonitor gauge samples (bar height = requests in flight at that moment)
g0 = 28.4
t = SNAP0 + 0.25
while t <= END:
    n = sum(a <= t < a + e for a, _, e in reqs)
    ax.add_patch(Rectangle((tx(t) - 0.7, g0), 1.4, 0.05 + 1.15 * n, fc=tint(teal, 0.45), ec="none", zorder=3))
    ax.add_patch(Circle((tx(t), g0), 0.35, fc=teal, ec="none", zorder=4))
    t += 0.5
ax.plot([tx(SNAP0), tx(END)], [g0, g0], color=tint(teal, 0.3), lw=0.8, zorder=2)
text(6.5, 32.6, "ServerMonitor gauges", size=8.6, color=teal, fontweight="bold")
text(6.5, 30.4, "GET /metrics every 1 s: running, waiting,", size=7.8)
text(6.5, 28.3, "kv_cache_usage → _rep{i}_server.csv", size=7.8)

# lane: counter snapshots
s0 = 24.6
for t_, lbl in ((SNAP0, "start"), (SNAP1, "end")):
    ax.plot([tx(t_)], [s0], marker="D", ms=6, color=red, zorder=5)
    text(tx(t_) + (-1.0 if lbl == "start" else 1.0), s0, lbl, size=7.2, color=red,
         ha="right" if lbl == "start" else "left")
ax.plot([tx(SNAP0), tx(SNAP1)], [s0, s0], color=tint(red, 0.6), lw=0.8, ls=(0, (2, 2)), zorder=2)
text(6.5, 25.6, "ServerMonitor counter snapshots", size=8.6, color=red, fontweight="bold")
text(6.5, 23.4, "queue-time histogram, preemptions, prefix cache", size=7.8)

# markers for t = 0 and the end of the run
for t_, lbl in ((0, "t = 0"), (END, "last request done")):
    ax.plot([tx(t_)] * 2, [21.4, 49.2], color=INK, lw=0.9, ls=(0, (3, 2)), zorder=2)
    text(tx(t_) + 0.6, 49.2, lbl, size=7.2, color=INK, ha="left", va="bottom")

# after the run
card(tx(END) + 3.6, 47.6, px1 - tx(END) - 3.6, "when the last request is done", [
    "1. stop polling, take the end snapshot",
    "2. write _rep{i}.csv + _rep{i}_server.csv",
    "3. compute summary() (printed to the job log)",
    "4. cooldown 5 s, then the row goes into _summary.csv",
], red, size=7.6, title_size=8.2)

# time axis and phases
ay = 20.6
ax.plot([tx(T0 + 0.3), px1], [ay, ay], color=MUTED, lw=1.0, zorder=3)
ax.add_patch(FancyArrowPatch((px1 - 1, ay), (px1 + 1.4, ay), arrowstyle="-|>", mutation_scale=9, color=MUTED))
ax.add_patch(Rectangle((tx(COOL0), ay - 0.7), tx(COOL1) - tx(COOL0), 1.4, fc="#eef0f4", ec="#8892a0",
                       hatch="////", lw=0, zorder=3))
for xa, xb, lbl in ((0, WARM, "--warmup"), (WARM, WARM + DUR, "--duration (arrivals stop)"),
                    (WARM + DUR, END, "drain"), (COOL0, COOL1, "cooldown 5 s")):
    hbracket(tx(xa), tx(xb), ay - 1.4, lbl, MUTED, size=7.4, family=MONO if lbl.startswith("--") else SANS)
text(6.5, ay - 1.0, "phases of one run", size=8.6, color=MUTED, fontweight="bold")

# summary windows
text(6.5, 15.0, "summary windows", size=8.6, color=red, fontweight="bold")
text(6.5, 12.8, "what each summary number is computed", size=7.8)
text(6.5, 10.7, "over, once the run is finished", size=7.8)
wins = [
    (WARM, WARM + DUR, "latency (TTFT, TPOT, ITL, E2E): requests that ARRIVE here, each followed to its last token"),
    (WARM, WARM + DUR, "steady-state throughput: requests that FINISH here and tokens STREAMED here, ÷ duration"),
    (WARM, END, "server gauges (srv_running / waiting / kv_cache_usage): 1 s samples from warmup to the end"),
    (SNAP0, SNAP1, "server counters (srv_queue_*, srv_preemptions, prefix-cache hit rate): end − start, incl. warmup"),
]
for k, (xa, xb, lbl) in enumerate(wins):
    yb = 16.0 - 3.6 * k
    ax.plot([tx(xa), tx(xa), tx(xb), tx(xb)], [yb - 0.7, yb, yb, yb - 0.7], color=red, lw=1.2, zorder=5)
    text(tx(xb) + 1.2 if k < 2 else tx(xa) + 1.0, yb - (0 if k < 2 else 1.3), lbl, size=7.4, color=red,
         ha="left", va="center")

# ============================================================================= D: one request + outputs
ax = section(45, 44)
P2 = (4, 1, 109, 42)
panel(*P2, "D   One request: what VLLMClient.send() measures",
      "all times are seconds after the request's scheduled arrival (due), not after it was actually sent")
x0, y0, w, h = P2
qx0, qx1 = x0 + 6, x0 + w - 8


def qx(t):
    return qx0 + (qx1 - qx0) * t / 10


by = y0 + h - 17.0
lag, first_tok = 0.6, 3.0
chunks = [3.0, 3.75, 4.5, 5.25, 6.0, 6.75, 7.5, 8.25, 9.0]
ax.add_patch(Rectangle((qx(0), by - 1.0), qx(lag) - qx(0), 2.0, fc="#eef0f4", ec="#8892a0", hatch="////",
                       lw=0, zorder=3))
ax.add_patch(Rectangle((qx(lag), by - 1.0), qx(first_tok) - qx(lag), 2.0, fc=tint(teal, 0.55), ec="none", zorder=3))
ax.add_patch(Rectangle((qx(first_tok), by - 1.0), qx(chunks[-1]) - qx(first_tok), 2.0, fc=teal, ec="none", zorder=3))
for t in chunks:
    ax.plot([qx(t)] * 2, [by + 1.0, by + 2.6], color=teal, lw=1.4, zorder=4)
    ax.add_patch(Circle((qx(t), by + 2.9), 0.42, fc=teal, ec="none", zorder=4))
ax.plot([qx(0)] * 2, [by - 13.0, by + 4.4], color=INK, lw=1.0, ls=(0, (3, 2)), zorder=4)
text(qx(0), by + 5.6, "due", size=8.0, family=MONO, fontweight="bold", ha="center")
text(qx(lag / 2), by + 1.5, "client lag", size=6.8, color=MUTED, ha="center", va="bottom")
text((qx(lag) + qx(first_tok)) / 2, by, "queued + prefill", size=7.4, color=INK, ha="center")
text((qx(first_tok) + qx(chunks[-1])) / 2, by, "decode", size=7.6, color="white", ha="center", fontweight="bold")
text(qx(chunks[-1]) + 1.0, by + 2.9, "chunks", size=7.4, color=teal, ha="left")
hbracket(qx(chunks[3]), qx(chunks[4]), by + 4.4, "ITL", teal, size=8.0, down=False, bold=True)
hbracket(qx(0), qx(first_tok), by - 3.6, "TTFT = token_times[0]", red, size=7.8, family=MONO)
hbracket(qx(0), qx(chunks[-1]), by - 7.6, "E2E = token_times[-1]", red, size=7.8, family=MONO)
hbracket(qx(first_tok), qx(chunks[-1]), by - 11.6, "TPOT = (E2E − TTFT) / (tokens − 1)", red, size=7.8, family=MONO)
for i, s in enumerate([
    "Client lag (a late create_task) counts toward TTFT and E2E; LoadGenerator warns once it passes 100 ms.",
    "ITL is the gap between streamed chunks; TPOT uses the token count, so it is per token either way.",
]):
    text(x0 + 2.2, y0 + 4.4 - i * 2.3, s, size=7.4, color=MUTED)

P3 = (119, 1, 109, 42)
panel(*P3, "E   What gets written, and when",
      "under results/<experiment>/<run>/ unless noted; nothing is ever overwritten")
x0, y0, w, h = P3
rows = [
    ("at submit", "login node", ["experiment.json, git.txt (commits; GPU nodes have no git)",
                                 "experiments/runs.tsv: time, job id, run, git commit"]),
    ("job start", "GPU node", ["server_cmd.txt, env.txt (GPU, anything else on it, versions)",
                               "server.log (all job long), server_config_lines.txt"]),
    ("workload_sim start", "", ["<mode>_run_info.json: args, seed, trace size + mtime,",
                                "host, GPU, vLLM version, served model"]),
    ("after every run", "rate × repeat", ["_rep{i}.csv: one row per request",
                                           "_rep{i}_server.csv: the 1 s gauge samples",
                                           "_summary.csv: rewritten with the new row (a crash keeps the rest)"]),
    ("whole job", "", ["slurm-<job>.out: the job's log (every command and its output)"]),
]
ry = y0 + h - 9.6
for when, where, what in rows:
    text(x0 + 2.4, ry, when, size=8.2, fontweight="bold")
    if where:
        text(x0 + 2.4, ry - 2.1, where, size=7.2, color=MUTED, style="italic")
    for j, line in enumerate(what):
        text(x0 + 24, ry - 2.1 * j, line, size=7.6)
    ry -= 2.1 * max(len(what), 2 if where else 1) + 1.6

# ----------------------------------------------------------------------------- save
for ext in ("png", "svg"):
    fig.savefig(OUT.with_suffix(f".{ext}"), dpi=170 if ext == "png" else None, facecolor="white")
print(f"wrote {OUT.with_suffix('.png')} and .svg")
