"""plots and summary.md for a native benchmark run

python3 native/plot_native.py results/native-<time>-sf1
"""
import json, sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

COLORS = {"fresh": "#2a78d6", "clone_generic": "#eb6834", "clone_selective": "#1baf7a",
          "clone_prepared": "#eda100", "clone_pooled": "#e87ba4", "warm": "#008300"}
LABELS = {"fresh": "fresh", "clone_generic": "generic clone", "clone_selective": "selective",
          "clone_prepared": "prepared", "clone_pooled": "pooled", "warm": "warm"}
MODES = list(COLORS)
plt.rcParams.update({"figure.dpi": 130, "savefig.dpi": 200, "font.size": 9, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.grid": True, "grid.color": "#e4e4e0",
                     "grid.linewidth": 0.6, "legend.frameon": False})


def pct(s, q):
    s = s.dropna(); return float(np.percentile(s, q)) if len(s) else np.nan


def ci_p99(s, boots=400, seed=1):
    """upper 95% bootstrap bound on the 99th percentile"""
    s = s.dropna().values
    if len(s) < 100: return np.nan
    rng = np.random.default_rng(seed)
    return float(np.percentile([np.percentile(rng.choice(s, len(s)), 99) for _ in range(boots)], 97.5))


def main(run):
    run = Path(run); out = run / "plots"; out.mkdir(exist_ok=True)
    rows = []
    for l in open(run / "events.jsonl"):
        try:
            rows.append(json.loads(l))
        except json.JSONDecodeError:
            pass   # a garbled line from an old run; ignore it
    df = pd.DataFrame(rows)
    man = json.loads((run / "manifest.json").read_text())
    lat = df[(df.exp == "latency") & df["mode"].isin(MODES)].copy()
    lat["query_us"] = lat.done_us - lat.ready_us
    short = lat[lat["query"].isin(["point", "count", "filter"])]

    # flat csv copies of the raw request events, for anyone who'd rather not parse jsonl
    req = df[df["mode"].isin(MODES)].drop(columns=[c for c in ("first",) if c in df], errors="ignore")
    req.to_csv(run / "events.csv", index=False)

    # p50/p90/p95/p99 for ready and done, per mode, query and concurrency
    perc = (lat.groupby(["mode", "query", "conc"])
               .agg(n=("ready_us", "size"),
                    ready_p50=("ready_us", lambda s: pct(s, 50)), ready_p90=("ready_us", lambda s: pct(s, 90)),
                    ready_p95=("ready_us", lambda s: pct(s, 95)), ready_p99=("ready_us", lambda s: pct(s, 99)),
                    done_p50=("done_us", lambda s: pct(s, 50)), done_p90=("done_us", lambda s: pct(s, 90)),
                    done_p99=("done_us", lambda s: pct(s, 99)))
               .reset_index())
    perc.to_csv(run / "latency_percentiles.csv", index=False)

    # burst throughput: all requests of a burst arrive at the same t0, so
    # throughput = requests in the burst / (time from t0 until the last one finished)
    burst = (lat.groupby(["mode", "query", "conc", "block", "rep"])
                .agg(n=("done_us", "size"), span_us=("done_us", "max")).reset_index())
    burst["req_per_s"] = burst.n / (burst.span_us / 1e6)
    burst.to_csv(run / "throughput.csv", index=False)

    # 1 activation CDF, one request at a time, short queries
    fig, ax = plt.subplots(figsize=(6, 3.4))
    for m in MODES:
        x = np.sort(short[(short["mode"] == m) & (short.conc == 1)].ready_us.values) / 1e3
        if len(x): ax.plot(x, np.arange(1, len(x) + 1) / len(x), lw=2, color=COLORS[m], label=LABELS[m])
    ax.axvline(1, color="#8a8a85", ls="--", lw=1); ax.text(1, 0.03, " 1 ms", fontsize=8, color="#555")
    ax.set_xscale("log"); ax.set_xlabel("time until the worker can execute, ms (log)")
    ax.set_ylabel("fraction of requests"); ax.set_title("Activation, one request at a time, short queries", loc="left")
    ax.legend(loc="lower right", fontsize=8); fig.tight_layout(); fig.savefig(out / "activation_cdf.png"); plt.close(fig)

    # 2 ready vs ready+query, short queries, conc 1
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    x = np.arange(len(MODES)); w = 0.38
    r = [short[(short["mode"] == m) & (short.conc == 1)].ready_us.median() / 1e3 for m in MODES]
    d = [short[(short["mode"] == m) & (short.conc == 1)].done_us.median() / 1e3 for m in MODES]
    ax.bar(x - w/2, r, w, color=[COLORS[m] for m in MODES], label="ready")
    ax.bar(x + w/2, d, w, color=[COLORS[m] for m in MODES], alpha=0.45, label="ready + first query")
    for i in range(len(MODES)):
        ax.text(x[i] - w/2, r[i] * 1.15, f"{r[i]:.2f}", ha="center", fontsize=7)
        ax.text(x[i] + w/2, d[i] * 1.15, f"{d[i]:.2f}", ha="center", fontsize=7)
    ax.set_yscale("log"); ax.set_xticks(x, [LABELS[m] for m in MODES]); ax.set_ylabel("ms (log)")
    ax.set_title("Where the cost lands: before ready, or inside the first query", loc="left"); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(out / "ready_vs_done.png"); plt.close(fig)

    # 3 scaling with concurrency
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.2), sharey=True)
    for ax, q in zip(axes, (50, 95)):
        for m in MODES:
            g = short[short["mode"] == m].groupby("conc").ready_us.apply(lambda s: pct(s, q))
            if len(g): ax.plot(g.index, g.values / 1e3, marker="o", ms=4, lw=2, color=COLORS[m], label=LABELS[m])
        ax.set_xscale("log", base=2); ax.set_yscale("log"); ax.set_xticks(sorted(short.conc.unique()), [str(int(c)) for c in sorted(short.conc.unique())])
        ax.set_xlabel("requests arriving at once"); ax.set_title(f"p{q} activation", loc="left")
    axes[0].set_ylabel("ms (log)"); axes[0].legend(fontsize=7)
    fig.tight_layout(); fig.savefig(out / "activation_vs_concurrency.png"); plt.close(fig)

    # 4 memory: idle pooled clones vs warm workers
    mem = df[(df.exp == "memory") & (df["mode"] == "pool_memory")]
    fig, ax = plt.subplots(figsize=(6, 3.2))
    if len(mem):
        ax.plot(mem.pool, (mem.pool_private_dirty_kb + mem.template_private_dirty_kb) / 1024, marker="o", lw=2,
                color=COLORS["clone_pooled"], label="template + N idle pooled clones")
    warm_idle = lat[lat["mode"] == "warm"].idle_private_dirty_kb.median()
    if warm_idle == warm_idle:
        ns = np.array(sorted(mem.pool.unique())) if len(mem) else np.array([1, 8, 32, 64])
        ax.plot(ns, ns * warm_idle / 1024, marker="o", lw=2, color=COLORS["warm"], label="N warm worker processes")
    ax.set_xscale("log", base=2); ax.set_xticks([1, 8, 32, 64], ["1", "8", "32", "64"])
    ax.set_xlabel("workers kept ready"); ax.set_ylabel("private memory, MiB")
    ax.set_title("Memory cost of keeping workers ready", loc="left"); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(out / "memory_vs_pool_size.png"); plt.close(fig)

    # 5 catalog size
    cat = df[(df.exp.isin(["latency", "catalog"])) & (df["query"] == "point") & (df.conc == 1)]
    fig, ax = plt.subplots(figsize=(6, 3.2))
    for m in MODES:
        g = cat[cat["mode"] == m].groupby("catalog").ready_us.median()
        if len(g): ax.plot(range(len(g)), g.values / 1e3, marker="o", lw=2, color=COLORS[m], label=LABELS[m])
    ax.set_xticks(range(3), ["8 views", "208 views", "2008 views"]); ax.set_yscale("log")
    ax.set_ylabel("median activation, ms (log)"); ax.set_title("Activation vs catalog size", loc="left"); ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(out / "activation_vs_catalog.png"); plt.close(fig)

    # 6 per query, complete time
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    qs = [q for q in ["point", "count", "filter", "q6", "q1"] if q in set(lat["query"])]
    w = 0.14
    for i, m in enumerate(MODES):
        g = lat[(lat["mode"] == m) & (lat.conc == 1)].groupby("query").done_us.median().reindex(qs)
        ax.bar(np.arange(len(qs)) + (i - 2.5) * w, g.values / 1e3, w, color=COLORS[m], label=LABELS[m])
    ax.set_xticks(range(len(qs)), qs); ax.set_yscale("log"); ax.set_ylabel("median time to full result, ms (log)")
    ax.set_title("End to end per query, one request at a time", loc="left"); ax.legend(fontsize=7, ncol=3)
    fig.tight_layout(); fig.savefig(out / "done_per_query.png"); plt.close(fig)

    # 7 memory density and isolation
    den = df[(df.exp == "density") & (df.get("summary", 0) == 1)] if "summary" in df else df.iloc[0:0]
    if len(den):   # a later --density-only run into the same dir replaces the earlier rows
        den = den.drop_duplicates(subset=["impl", "workers"], keep="last")
    IMPL = {"clone": ("clones of one template", COLORS["clone_pooled"]),
            "procs": ("separate processes", COLORS["warm"]),
            "threads": ("threads in one process", COLORS["fresh"])}
    if len(den):
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.5, 3.2))
        for impl, (lab, col) in IMPL.items():
            g = den[den.impl == impl].sort_values("workers")
            if len(g):
                a1.plot(g.workers, g.total_pss_kb / 1024, marker="o", lw=2, color=col, label=lab)
                a2.plot(g.workers, g.wall_us / 1e3, marker="o", lw=2, color=col, label=lab)
        a1.set_xscale("log", base=2); a1.set_xticks(DN := sorted(den.workers.unique()), [str(int(x)) for x in DN])
        a1.set_xlabel("concurrent workers"); a1.set_ylabel("total memory, MiB (PSS, shared pages counted once)")
        a1.set_title("Memory for N workers on an in-memory table", loc="left", fontsize=9); a1.legend(fontsize=7)
        a2.set_xscale("log", base=2); a2.set_xticks(DN, [str(int(x)) for x in DN]); a2.set_yscale("log")
        a2.set_xlabel("concurrent workers"); a2.set_ylabel("time until all N finish Q6, ms (log)")
        a2.set_title("Throughput is the same", loc="left", fontsize=9)
        fig.tight_layout(); fig.savefig(out / "density.png"); plt.close(fig)
    iso = df[(df.exp == "isolation") & (df.get("summary", 0) == 1)] if "summary" in df else df.iloc[0:0]

    # 8 throughput vs concurrency, short queries; line = median over bursts, band = 25th-75th
    bs = burst[burst["query"].isin(["point", "count", "filter"])]
    fig, ax = plt.subplots(figsize=(6, 3.4))
    for m in MODES:
        g = bs[bs["mode"] == m].groupby("conc").req_per_s
        if not len(g): continue
        med, lo, hi = g.median(), g.quantile(0.25), g.quantile(0.75)
        ax.plot(med.index, med.values, marker="o", ms=4, lw=2, color=COLORS[m], label=LABELS[m])
        ax.fill_between(med.index, lo.values, hi.values, color=COLORS[m], alpha=0.15, lw=0)
    cs = sorted(bs.conc.unique())
    ax.set_xscale("log", base=2); ax.set_yscale("log"); ax.set_xticks(cs, [str(int(c)) for c in cs])
    ax.set_xlabel("requests arriving at once (burst size)"); ax.set_ylabel("completed requests per second (log)")
    ax.set_title("Burst throughput, short queries (median, band = IQR)", loc="left"); ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(out / "throughput_vs_concurrency.png"); plt.close(fig)

    # 9 cpu use over the run, from the /proc samples if the run has them
    res = None
    if (run / "resources.csv").exists():
        res = pd.read_csv(run / "resources.csv")
        cpu = res[[c for c in res if c.startswith("cpu_")]]
        busy = cpu.drop(columns=["cpu_idle", "cpu_iowait"]).sum(axis=1).diff()
        total = cpu.sum(axis=1).diff()
        res["cpu_util"] = (busy / total * 100).clip(0, 100)
        res["ctxt_per_s"] = res.ctxt.diff() / (res.t_mono_ns.diff() / 1e9)
        res["t_s"] = (res.t_mono_ns - res.t_mono_ns.iloc[0]) / 1e9
        fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 4.2), sharex=True)
        a1.plot(res.t_s, res.cpu_util, lw=0.8, color="#2a78d6"); a1.set_ylabel("CPU busy, % of all cores")
        a2.plot(res.t_s, (res.mem_total_kb - res.mem_available_kb) / 1024 / 1024, lw=0.8, color="#eb6834")
        a2.set_ylabel("memory in use, GiB"); a2.set_xlabel("seconds since the start of the run")
        if (run / "phases.jsonl").exists():
            ph = pd.read_json(run / "phases.jsonl", lines=True)
            shade = {"density": "#1baf7a", "isolation": "#e87ba4", "p99": "#eda100", "memory": "#8a8a85"}
            for e, col in shade.items():
                for r in ph[ph.exp == e].itertuples():
                    for ax in (a1, a2):
                        ax.axvspan((r.t_start_ns - res.t_mono_ns.iloc[0]) / 1e9, (r.t_end_ns - res.t_mono_ns.iloc[0]) / 1e9,
                                   color=col, alpha=0.12, lw=0)
            a1.set_title("Whole run from /proc (shaded: density green, isolation pink, p99 yellow, memory grey)", loc="left", fontsize=8)
        fig.tight_layout(); fig.savefig(out / "resources.png"); plt.close(fig)

    # summary
    L = [f"Summary for {run.name}", "",
         f"{man.get('cpu')} ({man.get('cpus')} CPUs visible), kernel {man.get('kernel')}, DuckDB {man.get('duckdb')}, git {str(man.get('git'))[:10]}", ""]
    L.append("Activation and end to end time, short queries (point, count, filter), ms.")
    L.append("")
    for m in MODES:
        for c, g in short[short["mode"] == m].groupby("conc"):
            L.append(f"{LABELS[m]:16s} conc {int(c):3d}  n {len(g):5d}  ready p50 {pct(g.ready_us,50)/1e3:6.2f}  p90 {pct(g.ready_us,90)/1e3:6.2f}  p95 {pct(g.ready_us,95)/1e3:6.2f}  p99 {pct(g.ready_us,99)/1e3:6.2f}"
                     f"   done p50 {pct(g.done_us,50)/1e3:6.2f}   faults {g.faults_ready.median():4.0f}+{g.faults_query.median():4.0f}")
    L.append("")
    L.append("Burst throughput, short queries, completed requests/s (median over bursts):")
    for m in MODES:
        g = bs[bs["mode"] == m].groupby("conc").req_per_s.median()
        if len(g):
            L.append(f"{LABELS[m]:16s} " + "  ".join(f"conc {int(c)}: {v:,.0f}" for c, v in g.items()))
    L.append("")
    if len(mem):
        L.append("Memory, MiB private dirty: " + ", ".join(
            f"{int(r.pool)} pooled = {(r.pool_private_dirty_kb + r.template_private_dirty_kb)/1024:.1f}" for r in mem.itertuples()))
        if warm_idle == warm_idle:
            L.append(f"One idle warm worker process = {warm_idle/1024:.1f} MiB; one idle pooled clone = "
                     f"{lat[lat['mode']=='clone_pooled'].idle_private_dirty_kb.median()/1024:.2f} MiB.")
    refill = df[df["mode"] == "pool_refill"]
    if len(refill):
        L.append(f"Pool refill (fork + warm-up of one replacement clone): median {refill.refill_us.median()/1e3:.2f} ms, p95 {pct(refill.refill_us,95)/1e3:.2f} ms.")
    p99 = df[(df.exp == "p99") & df["mode"].isin(MODES)]
    if len(p99):
        L.append("")
        L.append("10,000 activations, point query, one at a time:")
        for m, g in p99.groupby("mode"):
            L.append(f"{LABELS.get(m,m):16s} p50 {pct(g.ready_us,50)/1e3:.3f}  p99 {pct(g.ready_us,99)/1e3:.3f}  "
                     f"upper 95% bound on p99 {ci_p99(g.ready_us)/1e3:.3f} ms  -> {'under 1 ms' if ci_p99(g.ready_us) < 1000 else 'not under 1 ms'}")
    if len(den):
        L.append("")
        L.append("Memory for N concurrent workers running Q6 on an in-memory lineitem (total PSS, MiB):")
        for impl, (lab, _) in IMPL.items():
            g = den[den.impl == impl].sort_values("workers")
            if len(g):
                L.append(f"{lab:24s} " + "  ".join(f"N={int(r.workers)}: {r.total_pss_kb/1024:.0f}" for r in g.itertuples()))
    if len(iso):
        if "fault" not in iso: iso = iso.assign(fault="kill")
        iso = iso.assign(fault=iso.fault.fillna("kill")).drop_duplicates(subset=["impl", "fault"], keep="last")
        for fault, title in [("kill", "worker 2 of 8 killed (SIGKILL) mid-query"),
                             ("hog", "worker 2 of 8 allocates memory until its limit stops it")]:
            gi = iso[iso.fault == fault]
            if not len(gi): continue
            L.append("")
            L.append(f"Isolation: {title}; queries that still completed:")
            for impl, (lab, _) in IMPL.items():
                g = gi[gi.impl == impl]
                if len(g):
                    L.append(f"{lab:24s} {int(g.completed.iloc[0])} of 8" + ("  (the whole process died)" if g.get("died", pd.Series([0])).iloc[0] == 1 else ""))
    if res is not None:
        L.append("")
        L.append(f"Resources over the run ({len(res)} samples): CPU busy mean {res.cpu_util.mean():.0f}%, peak {res.cpu_util.max():.0f}%; "
                 f"context switches mean {res.ctxt_per_s.mean():,.0f}/s; memory in use peak "
                 f"{((res.mem_total_kb - res.mem_available_kb).max())/1024/1024:.1f} GiB; "
                 f"major page faults {int(res.pgmajfault.iloc[-1] - res.pgmajfault.iloc[0])}.")
    if (run / "perf_stat.txt").exists():
        L.append("perf stat output: perf_stat.txt")
    bad = lat.groupby("query")["first"].nunique()
    L.append("")
    L.append("Result check (distinct first values per query across all modes, 1 = all agree): " + ", ".join(f"{q}={n}" for q, n in bad.items()))
    (run / "summary.md").write_text("\n".join(L) + "\n")
    print("\n".join(L)); print("plots ->", out)


if __name__ == "__main__":
    main(sys.argv[1])
