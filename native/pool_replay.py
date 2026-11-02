"""replay a trace with different pool policies and compare results

    python3 native/pool_replay.py                       # synthetic bursty trace, SF0.1
    python3 native/pool_replay.py --azure path/to/AzureFunctionsInvocationTraceForTwoWeeksJan2021.txt
    python3 native/pool_replay.py --scale 1 --out results/native-<id>

Try fixed pool sizes 0,1,2,4,8,16,32 and adaptive.
Saves pool_replay.jsonl, pool_replay.md and plots/pool_replay.png in the run dir.
Prints model prediction next to actual measurements too.
"""
import argparse, csv, json, math, os, random, subprocess, sys, time
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from duckdb_lib import ensure_lib, LIB  # noqa: E402

# measured on the laptop run: refill 2.4 ms, hit 0.11 ms, miss 0.69 ms, 0.7 MiB per idle clone
REFILL_MS, HIT_MS, MISS_MS, MIB_PER_CLONE = 2.4, 0.11, 0.69, 0.70


def build():
    exe = HERE / "pool"; src = HERE / "pool.c"
    if not exe.exists() or exe.stat().st_mtime < src.stat().st_mtime:
        subprocess.check_call(["cc", "-O2", "-o", str(exe), str(src), f"-I{LIB}", f"-L{LIB}",
                               "-lduckdb", "-lm", "-lpthread", f"-Wl,-rpath,{LIB}"])
    return exe


# ---------------- traces ----------------
def synthetic(seconds=30.0, base_rate=50.0, burst_rate=600.0, burst_every=5.0, burst_len=0.5, seed=1):
    """poisson arrivals at base_rate/s, with short bursts at burst_rate/s"""
    rng = random.Random(seed); t = 0.0; out = []
    while t < seconds:
        in_burst = (t % burst_every) < burst_len
        rate = burst_rate if in_burst else base_rate
        t += rng.expovariate(rate); out.append(t)
    return [x * 1000.0 for x in out]            # ms


def azure(path, window_s=3600, pick="busiest", target_mean_rate=None, compress=None, seed=1):
    """Azure Functions 2021 trace. Columns are app,func,end_timestamp,duration,
    start = end - duration. Only a few invocations per second in this sample.
    Take one window (default one hour) and compress it to the target mean
    rate. Bursts and quiet parts should still have the same shape.
    pick selects busiest, median or quietest hour from day 1.
    """
    starts = []
    with open(path) as f:
        r = csv.reader(f); header = next(r)
        ie = header.index("end_timestamp"); idur = header.index("duration")
        for row in r:
            try:
                starts.append(float(row[ie]) - float(row[idur]))
            except (ValueError, IndexError):
                continue
    starts.sort()
    import bisect
    day0 = starts[0]; windows = []
    for off in range(0, 86400 - int(window_s), 600):
        n = bisect.bisect_left(starts, day0 + off + window_s) - bisect.bisect_left(starts, day0 + off)
        windows.append((n, off))
    windows.sort()
    start_s = {"busiest": windows[-1], "quietest": windows[0], "median": windows[len(windows) // 2]}[pick][1]
    t0 = starts[0] + start_s
    w = [s - t0 for s in starts if t0 <= s < t0 + window_s]
    if compress is None:
        compress = target_mean_rate / (len(w) / window_s) if target_mean_rate else 1.0   # >1 squeezes the window in time
    w = [x / compress for x in w]
    return [x * 1000.0 for x in w], {"window_s": window_s, "pick": pick, "start_s": start_s, "arrivals": len(w),
                                     "raw_rate": len(w) / window_s, "time_compression": compress,
                                     "replay_s": window_s / compress}


# ---------------- model ----------------
def model(rate_per_s, K):
    """simple Poisson model with refill R. Miss if more than K arrivals
    happen in one refill window. Return miss probability, p99 and memory.
    """
    lam = rate_per_s * REFILL_MS / 1000.0          # expected arrivals per refill window
    if K == 0:
        pmiss = 1.0
    else:
        # P(N >= K) for N ~ Poisson(lam)
        cdf = sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(K))
        pmiss = max(0.0, 1 - cdf)
    p99 = MISS_MS if pmiss > 0.01 else HIT_MS
    return pmiss, p99, K * MIB_PER_CLONE


SIM_EXTRA = {}


def simulate(arrivals_ms, K, refill_ms=REFILL_MS, miss_cost_ms=1.0):
    """replay trace with a rough model of the controller.
    Refill thread asks for one clone every refill_ms while the pool is
    below K, alongside dispatch. Misses also go through the spawner, so
    they delay refills. If pool is empty but a refill is under way, wait
    for that clone. Still a hit, just late.
    Returns (hit_rate, avg_pool).
    """
    pool = K; hits = 0; pool_sum = 0.0; n = len(arrivals_ms)
    engine_free = 0.0          # when the spawner is next free to fork
    busy_end = None            # finish time of the refill under way, if any
    late = 0; waits = []
    for t in arrivals_ms:
        while busy_end is not None and busy_end <= t:      # refills that finished before t
            pool += 1; engine_free = busy_end; busy_end = None
            if pool < K: busy_end = engine_free + refill_ms
        if pool > 0:
            pool -= 1; hits += 1; waits.append(0.0)
        elif busy_end is not None:     # take the clone being made, after it is done
            late += 1; waits.append(busy_end - t); engine_free = busy_end; busy_end = None
        else:                          # miss: a prepared clone forked on the spot
            start = max(engine_free, t); engine_free = start + miss_cost_ms
            waits.append(engine_free - t)
        if busy_end is None and pool < K:
            busy_end = max(engine_free, t) + refill_ms
        pool_sum += pool
    SIM_EXTRA.update(late=late / n, wait_p99=float(np.percentile(waits, 99)))
    return hits / n, pool_sum / n


# ---------------- run ----------------
def run_policy(exe, data, trace_file, policy, K, kmax):
    out = subprocess.run([exe, "--data", str(data), "--trace", str(trace_file), "--policy", policy,
                          "--pool", str(K), "--max-pool", str(kmax)],
                         capture_output=True, text=True)
    if out.returncode:
        print("FAILED", policy, K, out.stderr[-300:]); return None, []
    rows = [json.loads(l) for l in out.stdout.splitlines() if l.startswith("{")]
    summ = [r for r in rows if r["kind"] == "summary"][0]
    reqs = [r for r in rows if r["kind"] == "req"]
    return summ, reqs


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scale", type=float, default=0.1)
    p.add_argument("--azure", help="path to the Azure Functions 2021 invocation trace CSV")
    p.add_argument("--azure-window", type=float, default=3600, help="seconds of trace to replay (compressed to --rate)")
    p.add_argument("--azure-pick", default="busiest", choices=["busiest", "median", "quietest"], help="which hour of day 1 to replay")
    p.add_argument("--azure-compress", type=float, help="fixed time compression factor instead of compressing to --rate (so different hours keep their relative rates)")
    p.add_argument("--rate", type=float, default=200.0, help="mean arrival rate per second to replay at")
    p.add_argument("--seconds", type=float, default=30.0)
    p.add_argument("--out", help="results dir to write into (default: new results/pool-<time>)")
    p.add_argument("--pools", nargs="+", type=int, default=[0, 1, 2, 4, 8, 16, 32])
    a = p.parse_args()

    data = ROOT / "data" / f"tpch_sf{a.scale:g}"
    if not (data / "VERSION").exists():
        subprocess.check_call([sys.executable, "-m", "coldstart.gen_data", str(a.scale)], cwd=ROOT)
    ensure_lib(); exe = build()
    out = Path(a.out) if a.out else ROOT / "results" / f"pool-{time.strftime('%Y%m%d-%H%M%S')}"
    out.mkdir(parents=True, exist_ok=True); (out / "plots").mkdir(exist_ok=True)

    if a.azure:
        arrivals, info = azure(a.azure, window_s=a.azure_window, pick=a.azure_pick, target_mean_rate=a.rate, compress=a.azure_compress)
        src = (f"Azure Functions 2021 trace, {info['pick']} {info['window_s']/3600:.1f} h window of day 1 (starts at {info['start_s']/3600:.1f} h, "
               f"{info['raw_rate']:.2f}/s raw): {info['arrivals']} invocations, "
               f"time compressed {info['time_compression']:.0f}x to {info['arrivals']/info['replay_s']:.0f}/s ({info['replay_s']:.0f} s replay)")
    else:
        arrivals = synthetic(seconds=a.seconds, base_rate=a.rate * 0.6, burst_rate=a.rate * 6)
        src = f"synthetic: Poisson {a.rate*0.6:.0f}/s with 0.5 s bursts at {a.rate*6:.0f}/s every 5 s"
    trace_file = out / "trace_ms.txt"
    trace_file.write_text("\n".join(f"{x:.3f}" for x in arrivals) + "\n")
    mean_rate = len(arrivals) / (arrivals[-1] / 1000.0)
    # peak rate over 100 ms windows, the thing a pool actually has to absorb
    bins = np.bincount((np.array(arrivals) // 100).astype(int))
    peak_rate = bins.max() * 10.0

    f = open(out / "pool_replay.jsonl", "w")
    f.write(json.dumps({"kind": "trace", "source": src, "arrivals": len(arrivals), "mean_rate": mean_rate, "peak_rate_100ms": peak_rate}) + "\n")
    results = []
    jobs = [("fixed", K, 64) for K in a.pools] + [("adaptive", 1, 64), ("model", 1, 64)]
    for policy, K, kmax in jobs:
        print("replay", policy, K, flush=True)
        summ, reqs = run_policy(exe, data, trace_file, policy, K, kmax)
        if not summ: continue
        ready = np.array([r["ready_us"] for r in reqs]) / 1e3
        disp = np.array([r["dispatch_us"] for r in reqs]) / 1e3
        rec = {**summ, "p50": float(np.percentile(ready, 50)), "p99": float(np.percentile(ready, 99)),
               "max": float(ready.max()), "hit_rate": summ["hits"] / max(1, summ["requests"]),
               "late_rate": summ.get("late_hits", 0) / max(1, summ["requests"]),
               "dispatch_p50": float(np.percentile(disp, 50)), "dispatch_p99": float(np.percentile(disp, 99)),
               "mem_mib": summ["avg_pool"] * MIB_PER_CLONE}
        Keff = K if policy == "fixed" else max(1, round(summ["avg_pool"]))
        pm, p99m, memm = model(mean_rate, Keff)
        # the model uses the template-side refill cost the controller just measured
        spawn_ms = summ.get("spawn_us", 1000.0) / 1000.0 or 1.0
        sim_hit, sim_pool = simulate(arrivals, Keff, refill_ms=spawn_ms, miss_cost_ms=spawn_ms)
        rec.update({"model_miss": pm, "model_p99": p99m, "model_mem": memm, "sim_hit": sim_hit, "sim_pool": sim_pool,
                    "sim_late": SIM_EXTRA.get("late", 0.0), "sim_wait_p99": SIM_EXTRA.get("wait_p99", 0.0)})
        SIM_EXTRA.clear()
        results.append(rec); f.write(json.dumps(rec) + "\n")
        for r in reqs: f.write(json.dumps({**r, "policy": policy, "pool": K}) + "\n")
        time.sleep(0.5)
    f.close()

    # ---- summary ----
    L = [f"Pool replay: {src}", f"mean rate {mean_rate:.0f}/s, peak (100 ms) {peak_rate:.0f}/s, {len(arrivals)} requests",
         "template in a single-threaded spawner, refill from a helper thread", ""]
    L.append("latency is from the scheduled arrival (includes controller queueing); 'after dispatch' is the worker part only")
    L.append("")
    L.append("'hit' = a waiting clone was there; 'late' = the pool was empty and the request took the clone being made")
    L.append("adaptive = rate rule (recent 100 ms peak x refill time x 2); model = picks K with the trace model on the last 5 s, held for 20 s")
    L.append("")
    L.append("policy     pool   hit rate   late   p50 ms   p99 ms   max ms   after dispatch p99   avg clones   memory MiB   | model hit   model late   Poisson miss")
    for r in results:
        L.append(f"{r['policy']:9s} {r['pool'] if r['policy']=='fixed' else 'auto':>5}   {r['hit_rate']:7.1%}  {r['late_rate']:5.1%}   {r['p50']:6.2f}   {r['p99']:6.2f}   {r['max']:6.2f}   {r['dispatch_p99']:18.2f}   {r['avg_pool']:9.1f}   {r['mem_mib']:9.1f}   |  " + (f"{r['sim_hit']:8.1%}   {r['sim_late']:9.1%}   {r['model_miss']:11.1%}" if r['policy'] == 'fixed' else f"{'-':>8}   {'-':>9}   {'-':>11}"))
    (out / "pool_replay.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))

    # ---- plot ----
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fx = [r for r in results if r["policy"] == "fixed" and r["pool"] > 0]
    ad = [r for r in results if r["policy"] == "adaptive"]
    md = [r for r in results if r["policy"] == "model"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.5, 3.2))
    a1.plot([r["pool"] for r in fx], [r["p99"] for r in fx], marker="o", lw=2, color="#e87ba4", label="measured p99")
    a1.plot([r["pool"] for r in fx], [r["hit_rate"] for r in fx], marker="s", lw=2, color="#2a78d6", label="measured hit rate")
    a1.plot([r["pool"] for r in fx], [r["sim_hit"] for r in fx], ls="--", lw=1.5, color="#2a78d6", label="model hit rate (trace replay)")
    if ad:
        a1.axhline(ad[0]["p99"], color="#e87ba4", ls=":", lw=1.5, label=f"adaptive p99 (avg {ad[0]['avg_pool']:.1f} clones)")
    a1.axhline(1.0, color="#8a8a85", ls="--", lw=1); a1.set_xscale("log", base=2)
    a1.set_xticks([r["pool"] for r in fx], [str(r["pool"]) for r in fx]); a1.set_xlabel("fixed pool size")
    a1.set_ylabel("ms  /  fraction"); a1.set_title("Activation p99 and hit rate vs pool size", loc="left", fontsize=9); a1.legend(fontsize=7)
    a2.plot([r["mem_mib"] for r in fx], [r["p99"] for r in fx], marker="o", lw=2, color="#e87ba4", label="fixed pools")
    for r in fx: a2.annotate(str(r["pool"]), (r["mem_mib"], r["p99"]), fontsize=7, xytext=(3, 3), textcoords="offset points")
    if ad: a2.plot([ad[0]["mem_mib"]], [ad[0]["p99"]], marker="*", ms=12, color="#1baf7a", ls="none", label="adaptive (rate rule)")
    if md: a2.plot([md[0]["mem_mib"]], [md[0]["p99"]], marker="D", ms=8, color="#eda100", ls="none", label="model-driven")
    a2.set_xlabel("memory held by idle clones, MiB"); a2.set_ylabel("p99 activation, ms")
    a2.set_title("Memory vs tail latency", loc="left", fontsize=9); a2.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(out / "plots" / "pool_replay.png"); plt.close(fig)
    print("wrote", out)


if __name__ == "__main__":
    main()
