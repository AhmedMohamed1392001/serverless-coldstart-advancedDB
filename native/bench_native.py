"""run coldbench across the experiment matrix and save results

    python3 native/bench_native.py --scale 1            # the full run
    python3 native/bench_native.py --quick              # a few minutes at SF0.1
    python3 native/bench_native.py --scale 1 --p99      # 10,000 activations per clone mode

Results go in results/native-<time>-sf<scale>/{events.jsonl, manifest.json}.
Then run plot_native.py for plots and summary.
"""
import argparse, json, os, platform, random, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from duckdb_lib import ensure_lib, LIB, VERSION  # noqa: E402

MODES = ["fresh", "clone_generic", "clone_selective", "clone_prepared", "clone_pooled", "warm"]
QUERIES = ["point", "count", "filter", "q6", "q1"]
BURST_QUERIES = ["point", "count", "filter", "q6"]     # q1 is too slow for 32-way bursts
CATALOGS = [0, 200, 2000]
POOL_SIZES = [1, 8, 32, 64]


def build(name="coldbench"):
    exe = HERE / name; src = HERE / f"{name}.c"
    if not exe.exists() or exe.stat().st_mtime < src.stat().st_mtime:
        subprocess.check_call(["cc", "-O2", "-o", str(exe), str(src), f"-I{LIB}", f"-L{LIB}",
                               "-lduckdb", "-lpthread", f"-Wl,-rpath,{LIB}"])
    return exe

DENSITY_N = [1, 2, 4, 8, 16, 32]


def host():
    cpu = "unknown"
    try:
        for line in open("/proc/cpuinfo"):
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip(); break
    except OSError:
        pass
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=ROOT).strip()
    except Exception:
        commit = "unknown"
    return {"cpu": cpu, "cpus": os.cpu_count(), "kernel": platform.release(), "node": platform.node(),
            "duckdb": VERSION, "git": commit, "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            # one reading of both clocks, so the CLOCK_MONOTONIC stamps in the logs can be
            # turned into wall-clock time: wall = clock_wall + (t_ns - clock_mono_ns) / 1e9
            "clock_mono_ns": time.monotonic_ns(), "clock_wall": time.time(),
            "argv": sys.argv}


def plan(a):
    conds = []
    for m in MODES:
        for q in QUERIES:
            for c in a.conc:
                if c > 1 and q not in BURST_QUERIES:
                    continue
                conds.append(dict(exp="latency", mode=m, query=q, conc=c, catalog=0,
                                  reps=a.reps if c == 1 else max(2, a.reps // 4)))
        for cat in CATALOGS[1:]:
            conds.append(dict(exp="catalog", mode=m, query="point", conc=1, catalog=cat, reps=a.reps))
    return conds


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scale", type=float, default=1.0)
    p.add_argument("--blocks", type=int, default=3)
    p.add_argument("--reps", type=int, default=20)
    p.add_argument("--conc", nargs="+", type=int, default=[1, 8, 32])
    p.add_argument("--quick", action="store_true")
    p.add_argument("--p99", action="store_true", help="also run 10,000 activations per clone mode")
    p.add_argument("--p99-only", metavar="RUN_DIR", help="only the p99 part, appended to an existing run dir")
    p.add_argument("--density-only", metavar="RUN_DIR", help="only the memory density + isolation part, appended to a run dir")
    p.add_argument("--procs-max", type=int, default=8, help="largest N for separate processes (each holds its own copy of the hot table)")
    p.add_argument("--out", help="run dir to write into (default results/native-<time>-sf<scale>)")
    a = p.parse_args()
    if a.quick:
        a.scale, a.blocks, a.reps, a.conc = 0.1, 1, 6, [1, 8]

    data = ROOT / "data" / f"tpch_sf{a.scale:g}"
    if not (data / "VERSION").exists():
        subprocess.check_call([sys.executable, "-m", "coldstart.gen_data", str(a.scale)], cwd=ROOT)
    ensure_lib(); exe = build(); dens = build("density")

    only = a.p99_only or a.density_only
    if only:
        out = Path(only).resolve()
        f = open(out / "events.jsonl", "a")
    else:
        out = Path(a.out).resolve() if a.out else ROOT / "results" / f"native-{time.strftime('%Y%m%d-%H%M%S')}-sf{a.scale:g}"
        out.mkdir(parents=True, exist_ok=True)
        (out / "manifest.json").write_text(json.dumps({**host(), "args": vars(a), "scale": a.scale}, indent=2))
        f = open(out / "events.jsonl", "w")

    phases = open(out / "phases.jsonl", "a")       # start/end of every program run, to line up with resources.csv

    def run(args, extra, prog=None, allow_fail=False):
        ts = time.monotonic_ns()
        t = subprocess.run([prog or exe, "--data", str(data)] + args, capture_output=True, text=True)
        phases.write(json.dumps({**extra, "cmd": [Path(prog or exe).name] + args, "t_start_ns": ts,
                                 "t_end_ns": time.monotonic_ns(), "rc": t.returncode}) + "\n"); phases.flush()
        if t.returncode and not allow_fail:
            print("FAILED", args, t.stderr[-500:], flush=True); return
        if t.returncode and allow_fail:            # the whole process died: record that
            f.write(json.dumps({**extra, "summary": 1, "completed": 0, "died": 1,
                                "impl": args[args.index("--impl") + 1], "workers": int(args[args.index("--workers") + 1])}) + "\n")
            f.flush(); return
        for line in t.stdout.splitlines():
            if line.startswith("{"):
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    print("skipped a bad line:", line[:60], flush=True); continue
                r.update(extra); f.write(json.dumps(r) + "\n")
        f.flush()

    rng = random.Random(7)
    conds = [] if only else plan(a)
    t_start = time.time()
    for b in range(a.blocks if not only else 0):
        block = conds[:]; rng.shuffle(block)
        for i, c in enumerate(block):
            run(["--mode", c["mode"], "--query", c["query"], "--conc", str(c["conc"]),
                 "--reps", str(c["reps"]), "--catalog", str(c["catalog"])],
                {"exp": c["exp"], "block": b})
            if i % 10 == 0:
                print(f"block {b+1}/{a.blocks} {i+1}/{len(block)} {time.time()-t_start:.0f}s", flush=True)

    # memory: N idle pooled clones vs the template
    for n in ([] if only else POOL_SIZES):
        run(["--mode", "clone_pooled", "--query", "point", "--pool-mem", str(n)], {"exp": "memory"})

    if not a.p99_only:
        # memory density: N concurrent workers on an in-memory hot table
        for impl in ["clone", "procs", "threads"]:
            for n in DENSITY_N:
                if impl == "procs" and n > a.procs_max:
                    continue
                print("density", impl, n, flush=True)
                run(["--impl", impl, "--workers", str(n), "--query", "q6", "--inmem"],
                    {"exp": "density"}, prog=dens)
        # isolation: worker 2 of 8 is killed while running, then the same with a
        # worker that allocates memory until its per-worker limit stops it
        for impl in ["clone", "procs", "threads"]:
            run(["--impl", impl, "--workers", "8", "--query", "q6", "--inmem", "--kill", "2"],
                {"exp": "isolation", "fault": "kill"}, prog=dens, allow_fail=True)
        for impl in ["clone", "procs", "threads"]:
            print("isolation hog", impl, flush=True)
            run(["--impl", impl, "--workers", "8", "--query", "q6", "--inmem", "--kill", "2", "--hog"],
                {"exp": "isolation", "fault": "hog"}, prog=dens, allow_fail=True)

    if a.p99 or a.p99_only:
        for m in ["clone_selective", "clone_prepared", "clone_pooled"]:
            print("p99 run", m, flush=True)
            run(["--mode", m, "--query", "point", "--conc", "1", "--reps", "10000"], {"exp": "p99"})

    f.close()
    print("wrote", out.relative_to(ROOT))
    subprocess.call([sys.executable, str(HERE / "plot_native.py"), str(out)])


if __name__ == "__main__":
    main()
