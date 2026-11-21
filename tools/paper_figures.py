"""Redraw the data figures of the paper (Figures 4 to 9) from the raw results.

    python3 tools/paper_figures.py [results/milestone2] [out_dir]

Figures 1 to 3 are drawings of the design and contain no measurements.
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "results/milestone2")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "paper_figures")
OUT.mkdir(parents=True, exist_ok=True)
MODES = ["fresh", "clone_generic", "clone_selective", "clone_prepared", "clone_pooled", "warm"]
NAMES = {"fresh": "fresh", "clone_generic": "generic clone", "clone_selective": "selective clone",
         "clone_prepared": "prepared clone", "clone_pooled": "pooled clone", "warm": "warm process"}
COL = {"fresh": "#a0694d", "clone_generic": "#767171", "clone_selective": "#f5861f",
       "clone_prepared": "#b5739d", "clone_pooled": "#4472a8", "warm": "#4aa84a"}
SHORT = {"point", "count", "filter"}
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "legend.frameon": False, "savefig.dpi": 220})


def load(path):
    rows = []
    for line in open(path):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


MAIN = ROOT / ("native-sf1" if (ROOT / "native-sf1").exists() else "native-sf0.1")
EV = load(MAIN / "events.jsonl")


def sel(mode, exp="latency", conc=1, catalog=0, queries=SHORT):
    return [r for r in EV if r.get("exp") == exp and r.get("mode") == mode and r.get("conc") == conc
            and r.get("catalog", 0) == catalog and r.get("query") in queries and "ready_us" in r]


def fig4():
    fig, ax = plt.subplots(figsize=(5.2, 2.9))
    for m in MODES:
        x = np.sort([r["ready_us"] / 1e3 for r in sel(m)])
        ax.plot(x, np.arange(1, len(x) + 1) / len(x), color=COL[m], lw=1.8, label=NAMES[m])
    ax.axvline(1, color="grey", ls=":", lw=1)
    ax.set_xscale("log"); ax.set_xlabel("activation time (ms, log scale)"); ax.set_ylabel("fraction of requests")
    ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5))
    fig.tight_layout(); fig.savefig(OUT / "fig4_activation_cdf.png"); plt.close(fig)


def fig5():
    concs = [1, 8, 32]
    thr = {}
    for line in open(MAIN / "throughput.csv").read().splitlines()[1:]:
        mode, query, conc, _, _, _, _, rps = line.split(",")
        if query in SHORT:
            thr.setdefault((mode, int(float(conc))), []).append(float(rps))
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.4, 3.0))
    for m in MODES:
        med = [np.median([r["ready_us"] / 1e3 for r in sel(m, conc=c)]) for c in concs]
        p99 = [np.percentile([r["ready_us"] / 1e3 for r in sel(m, conc=c)], 99) for c in concs]
        a.plot(concs, med, "o-", color=COL[m], ms=3, label=NAMES[m])
        a.plot(concs, p99, "--", color=COL[m], lw=1)
        b.plot(concs, [np.median(thr[(m, c)]) for c in concs], "o-", color=COL[m], ms=3, label=NAMES[m])
    for ax in (a, b):
        ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xticks(concs); ax.set_xticklabels(concs)
        ax.set_xlabel("requests arriving at once")
    a.set_ylabel("activation time (ms, log)"); a.set_title("(a) median (solid) and p99 (dashed)", fontsize=8)
    b.set_ylabel("completed requests per second"); b.set_title("(b) burst throughput", fontsize=8)
    b.legend(fontsize=6.5, ncol=2, loc="lower right")
    fig.tight_layout(); fig.savefig(OUT / "fig5_bursts.png"); plt.close(fig)


def fig6():
    cats = [0, 200, 2000]
    fig, ax = plt.subplots(figsize=(5.2, 2.8))
    for m in MODES:
        y = [np.median([r["ready_us"] / 1e3 for r in (sel(m) if c == 0 else sel(m, exp="catalog", catalog=c))])
             for c in cats]
        ax.plot([c + 8 for c in cats], y, "o-", color=COL[m], ms=3, label=NAMES[m])
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xticks([8, 208, 2008]); ax.set_xticklabels([8, 208, 2008])
    ax.set_xlabel("tables and views in the catalog"); ax.set_ylabel("median activation (ms, log)")
    ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5))
    fig.tight_layout(); fig.savefig(OUT / "fig6_catalog.png"); plt.close(fig)


def fig7():
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.4, 2.9))
    xs = np.arange(len(MODES))
    for i, m in enumerate(MODES):
        r = sel(m)
        ready = np.median([x["ready_us"] / 1e3 for x in r])
        query = np.median([(x["done_us"] - x["ready_us"]) / 1e3 for x in r])
        fr = np.median([x["faults_ready"] for x in r]); fq = np.median([x["faults_query"] for x in r])
        a.bar(i, ready, color=COL[m]); a.bar(i, query, bottom=ready, color="white", edgecolor=COL[m], hatch="///")
        b.bar(i, fr, color=COL[m]); b.bar(i, fq, bottom=fr, color="white", edgecolor=COL[m], hatch="///")
        b.text(i, fr + fq + 15, f"{int(fr)}+{int(fq)}", ha="center", fontsize=6)
    labels = ["fresh", "generic", "selective", "prepared", "pooled", "warm"]
    for ax in (a, b):
        ax.set_xticks(xs); ax.set_xticklabels(labels, fontsize=7)
    a.set_yscale("log"); a.set_ylabel("median time (ms, log)"); a.set_title("(a) time until ready, then first query", fontsize=8)
    b.set_ylabel("minor page faults (median)"); b.set_title("(b) faults before ready + during first query", fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "fig7_first_query.png"); plt.close(fig)


def fig8():
    dens = [r for r in EV if r.get("exp") == "density" and r.get("summary") and r.get("inmem")]
    mem = sorted([r for r in EV if r.get("mode") == "pool_memory"], key=lambda r: r["pool"])
    tmpl = np.median([r["private_dirty_kb"] for r in EV if r.get("mode") == "template_build"
                      and r.get("exp") == "latency" and r.get("catalog", 0) == 0])
    warm_idle = np.median([r["idle_private_dirty_kb"] for r in EV if r.get("mode") == "warm"
                           and r.get("idle_private_dirty_kb", -1) > 0])
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.4, 3.0))
    for impl, label, c in [("clone", "clones", COL["clone_pooled"]), ("procs", "separate processes", COL["fresh"]),
                           ("threads", "threads in one process", COL["warm"])]:
        rs = sorted([r for r in dens if r["impl"] == impl], key=lambda r: r["workers"])
        a.plot([r["workers"] for r in rs], [r["total_pss_kb"] / 1024 ** 2 for r in rs], "o-", color=c, ms=3, label=label)
    a.set_xscale("log", base=2); a.set_xticks([1, 2, 4, 8, 16, 32]); a.set_xticklabels([1, 2, 4, 8, 16, 32])
    a.set_xlabel("workers running TPC-H Q6 at once"); a.set_ylabel("total memory, PSS (GiB)")
    a.set_title("(a) workers over an in-memory table", fontsize=8); a.legend(fontsize=7)
    n = [r["pool"] for r in mem]
    b.plot(n, [(tmpl + r["pool_private_dirty_kb"]) / 1024 for r in mem], "o-", color=COL["clone_pooled"], ms=3,
           label="idle pooled clones")
    b.plot(n, [k * warm_idle / 1024 for k in n], "o--", color=COL["warm"], ms=3,
           label=f"idle warm processes ({warm_idle / 1024:.1f} MiB each)")
    b.set_xscale("log"); b.set_yscale("log"); b.set_xticks(n); b.set_xticklabels(n)
    b.set_xlabel("idle workers kept ready"); b.set_ylabel("private memory (MiB, log)")
    b.set_title("(b) cost of keeping workers ready", fontsize=8); b.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(OUT / "fig8_memory.png"); plt.close(fig)


def fig9():
    traces = [("pool-azure-busiest", "Azure busiest hour", COL["clone_pooled"], "-"),
              ("pool-azure-quietest", "Azure quietest hour", COL["clone_selective"], "--"),
              ("pool-synthetic", "synthetic bursts", "grey", ":")]
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.4, 3.0))
    for name, label, c, ls in traces:
        if not (ROOT / name / "pool_replay.jsonl").exists():
            continue
        s = sorted([r for r in load(ROOT / name / "pool_replay.jsonl") if r.get("kind") == "summary"
                    and r["policy"] == "fixed"], key=lambda r: r["pool"])
        x = np.arange(len(s))
        a.plot(x, [100 * r["hit_rate"] for r in s], "o" + ls, color=c, ms=3, label=label)
        a.plot(x, [100 * r["sim_hit"] for r in s], "x", color="black", ms=4)
        b.plot(x, [r["p99"] for r in s], "o" + ls, color=c, ms=3, label=label)
        ticks = [r["pool"] for r in s]
    for ax in (a, b):
        ax.set_xticks(range(len(ticks))); ax.set_xticklabels(ticks); ax.set_xlabel("pool size K")
    a.set_ylabel("requests finding a waiting clone (%)"); a.set_title("(a) hit rate, measured (o) and model (x)", fontsize=8)
    b.set_yscale("log"); b.axhline(1, color="grey", ls=":", lw=1)
    b.set_ylabel("p99 from arrival to ready (ms, log)"); b.set_title("(b) tail latency", fontsize=8)
    a.legend(fontsize=7, loc="lower right")
    fig.tight_layout(); fig.savefig(OUT / "fig9_pool_replay.png"); plt.close(fig)


if __name__ == "__main__":
    # a quick run lacks some experiments (catalog sizes, density, Azure replays), so skip those figures
    for f in (fig4, fig5, fig6, fig7, fig8, fig9):
        try:
            f()
        except (FileNotFoundError, KeyError, ValueError, IndexError) as e:
            plt.close("all")
            print(f"skipped {f.__name__}: {type(e).__name__} {e}")
    print("wrote", ", ".join(sorted(p.name for p in OUT.glob("fig*.png"))), "to", OUT)
