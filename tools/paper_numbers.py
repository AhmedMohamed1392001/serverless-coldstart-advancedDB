"""Recompute the tables and the main numbers of the paper from the raw results.

    python3 tools/paper_numbers.py [results/milestone2] > paper_numbers.md

Reads only the files under results/milestone2 and prints markdown:
Table 2, Table 3, and the numbers added in the revision (same-session
comparison with warm processes, idle-time check, simulator checks and the
equal-memory comparison of the sizing policies). Nothing is re-measured.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "results/milestone2")
MODES = ["fresh", "clone_generic", "clone_selective", "clone_prepared", "clone_pooled", "warm"]
NAMES = {"fresh": "fresh", "clone_generic": "generic clone", "clone_selective": "selective clone",
         "clone_prepared": "prepared clone", "clone_pooled": "pooled clone", "warm": "warm process"}
SHORT = {"point", "count", "filter"}


def load(path):
    rows = []
    for line in open(path):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def single(ev, mode, queries=SHORT, catalog=0):
    return [r for r in ev if r.get("exp") == "latency" and r.get("mode") == mode and r.get("conc") == 1
            and r.get("catalog", 0) == catalog and r.get("query") in queries and "ready_us" in r]


def med(x):
    return float(np.median(x))


def p(x, q):
    return float(np.percentile(x, q))


def table2(sf1, sf01, tails):
    print("## Table 2. Single short requests at scale factor 1\n")
    print("| Worker type | Ready p50 (ms) | Ready p99 (ms, indicative) | Done p50 (ms) | Faults before ready + in query "
          "| p99 over 10,000 (ms) | Ready p50 at SF 0.1 (ms) |")
    print("|---|---|---|---|---|---|---|")
    for m in MODES:
        r = single(sf1, m)
        ready = [x["ready_us"] / 1e3 for x in r]
        done = [x["done_us"] / 1e3 for x in r]
        fr = int(np.median([x["faults_ready"] for x in r]))
        fq = int(np.median([x["faults_query"] for x in r]))
        tail = [x["ready_us"] / 1e3 for x in tails if x.get("mode") == m and "ready_us" in x]
        r01 = [x["ready_us"] / 1e3 for x in single(sf01, m)]
        t = f"{p(tail, 99):.3f} (n={len(tail):,})" if tail else "not run"
        print(f"| {NAMES[m]} | {med(ready):.2f} | {p(ready, 99):.2f} | {med(done):.2f} | {fr:,} + {fq} "
              f"| {t} | {med(r01):.2f} |")
    print()


def same_session(sf1, boots=50000, seed=0):
    print("## Pooled clone against warm process, interleaved runs of one session (done time, ms)\n")
    print("| Query | n | Pooled p50 | Warm p50 | 95% bootstrap interval of the difference |")
    print("|---|---|---|---|---|")
    rng = np.random.default_rng(seed)
    for q in ["point", "filter", "count"]:
        a = np.array([x["done_us"] / 1e3 for x in single(sf1, "clone_pooled", {q})])
        b = np.array([x["done_us"] / 1e3 for x in single(sf1, "warm", {q})])
        d = [np.median(rng.choice(a, len(a))) - np.median(rng.choice(b, len(b))) for _ in range(boots)]
        lo, hi = np.percentile(d, [2.5, 97.5])
        print(f"| {q} | {len(a)} | {np.median(a):.2f} | {np.median(b):.2f} | {lo:.2f} to {hi:.2f} |")
    print()


def replay(name):
    rows = load(ROOT / name / "pool_replay.jsonl")
    summ = [r for r in rows if r.get("kind") == "summary"]
    reqs = [r for r in rows if r.get("kind") == "req"]
    return summ, reqs


def key(s):
    return "fixed, %d clone%s" % (s["pool"], "" if s["pool"] == 1 else "s") if s["policy"] == "fixed" and s["pool"] \
        else ("no pool" if s["policy"] == "fixed" else ("rate rule" if s["policy"] == "adaptive" else "model policy"))


def table3(traces):
    print("## Table 3. Share of requests ready within 1 ms of their scheduled arrival (%)\n")
    cols = {}
    for label, name in traces:
        summ, reqs = replay(name)
        for s in summ:
            rs = [r for r in reqs if r["policy"] == s["policy"] and r["pool"] == s["pool"]]
            cols.setdefault(key(s), {})[label] = 100.0 * np.mean([r["ready_us"] <= 1000 for r in rs])
    print("| Pool | " + " | ".join(l for l, _ in traces) + " |")
    print("|---|" + "---|" * len(traces))
    for k, v in cols.items():
        print(f"| {k} | " + " | ".join(f"{v[l]:.1f}" if l in v else "" for l, _ in traces) + " |")
    print()


def policies(traces):
    print("## Sizing policies at their memory budget (avg_pool is the mean number of waiting clones)\n")
    print("| Trace | Policy | avg_pool | hits (%) | late hits (%) | p99 ready (ms) | simulator hits (%) |")
    print("|---|---|---|---|---|---|---|")
    for label, name in traces:
        for s in replay(name)[0]:
            print(f"| {label} | {key(s)} | {s['avg_pool']:.1f} | {100 * s['hit_rate']:.1f} | "
                  f"{100 * s['late_rate']:.1f} | {s['p99']:.2f} | {100 * s['sim_hit']:.1f} |")
    print()


def simulator_checks():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "native"))
    import pool_replay as pr
    print("## Simulator checks\n")
    arr = [float(x) for x in open(ROOT / "pool-azure-busiest" / "trace_ms.txt").read().split()]
    s1 = [s for s in replay("pool-azure-busiest")[0] if s["policy"] == "fixed" and s["pool"] == 1][0]
    fork = s1["spawn_us"] / 1e3
    h_fork, _ = pr.simulate(arr, 1, refill_ms=fork, miss_cost_ms=fork)
    h_full, _ = pr.simulate(arr, 1, refill_ms=2.2, miss_cost_ms=fork)
    print(f"- Busiest hour, one clone: measured hits {100 * s1['hit_rate']:.1f}%, simulator with the fork time "
          f"({fork:.2f} ms) {100 * h_fork:.1f}%, simulator with fork plus warm-up (2.2 ms) {100 * h_full:.1f}%.")
    q = [float(x) for x in open(ROOT / "pool-azure-quietest" / "trace_ms.txt").read().split()]
    out = []
    for s in replay("pool-azure-quietest")[0]:
        if s["policy"] == "fixed" and 1 <= s["pool"] <= 8:
            h, _ = pr.simulate(q, s["pool"], refill_ms=fork, miss_cost_ms=fork)
            out.append(f"K={s['pool']}: {100 * h:.1f} vs {100 * s['hit_rate']:.1f}")
    print("- Quietest hour predicted with the busiest hour's fork time (predicted vs measured hits): "
          + ", ".join(out) + ".\n")


def idle_check():
    print("## Activation after long waits in the pool (quietest hour)\n")
    print("A full pool hands out its oldest clone, so the clone used by request i was made about when request i-K "
          "was served. The wait is approximated by the time between those two requests.\n")
    print("| K | wait | n | ready p50 (ms) | ready p99 (ms) |")
    print("|---|---|---|---|---|")
    reqs = replay("pool-azure-quietest")[1]
    for K in (16, 32):
        rs = sorted([r for r in reqs if r["policy"] == "fixed" and r["pool"] == K], key=lambda r: r["t_sched_ns"])
        bins = {}
        for i in range(K, len(rs)):
            w = (rs[i]["t_sched_ns"] - rs[i - K]["t_sched_ns"]) / 1e9
            b = "under 0.1 s" if w < 0.1 else "0.1 to 1 s" if w < 1 else "1 to 5 s" if w < 5 else "5 s or more"
            bins.setdefault(b, []).append(rs[i]["ready_us"] / 1e3)
        for b, v in bins.items():
            print(f"| {K} | {b} | {len(v)} | {med(v):.3f} | {p(v, 99):.2f} |")
    print()


def main():
    # a full run has native-sf1, native-sf0.1, the 10k tails and three replays.
    # a quick run (run_benchmarks.sh --quick) has only some of them, so skip what is missing.
    main_dir = "native-sf1" if (ROOT / "native-sf1").exists() else "native-sf0.1"
    sf1 = load(ROOT / main_dir / "events.jsonl")
    sf01 = load(ROOT / "native-sf0.1" / "events.jsonl") if (ROOT / "native-sf0.1").exists() else sf1
    extra = load(ROOT / "p99_extra.jsonl") if (ROOT / "p99_extra.jsonl").exists() else []
    tails = [r for r in sf1 if r.get("exp") == "p99"] + extra
    print(f"# Numbers in the paper, recomputed from {ROOT}\n")
    if main_dir != "native-sf1":
        print("(no scale factor 1 run here, so Table 2 uses scale factor 0.1)\n")
    table2(sf1, sf01, tails)
    same_session(sf1)
    traces = [(label, name) for label, name in [("Busiest hour", "pool-azure-busiest"),
              ("Quietest hour", "pool-azure-quietest"), ("Synthetic", "pool-synthetic")]
              if (ROOT / name / "pool_replay.jsonl").exists()]
    if traces:
        table3(traces)
        policies(traces)
    if (ROOT / "pool-azure-busiest").exists() and (ROOT / "pool-azure-quietest").exists():
        simulator_checks()
        idle_check()


if __name__ == "__main__":
    main()
