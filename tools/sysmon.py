"""samples /proc while a benchmark runs and writes raw counters to a csv

    python3 tools/sysmon.py results/run-x/resources.csv [--interval 0.2] [--pid PID]

raw values only (jiffies, kB, counts), the plots turn them into cpu % etc.
stops when killed, or when --pid exits. t_mono_ns is CLOCK_MONOTONIC, same
clock as the t_*_ns fields in the event logs, so the two line up.
"""
import argparse, csv, os, signal, sys, time

CPU_COLS = ["user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal"]


def read_stat():
    cpu, ctxt, running, blocked = None, 0, 0, 0
    with open("/proc/stat") as f:
        for line in f:
            parts = line.split()
            if parts[0] == "cpu":
                cpu = [int(x) for x in parts[1:9]]
            elif parts[0] == "ctxt":
                ctxt = int(parts[1])
            elif parts[0] == "procs_running":
                running = int(parts[1])
            elif parts[0] == "procs_blocked":
                blocked = int(parts[1])
    return cpu, ctxt, running, blocked


def read_kv(path, keys):
    out = {}
    with open(path) as f:
        for line in f:
            k, v = line.split(None, 1)
            k = k.rstrip(":")
            if k in keys:
                out[k] = int(v.split()[0])
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out")
    p.add_argument("--interval", type=float, default=0.2)
    p.add_argument("--pid", type=int, help="stop when this process is gone")
    a = p.parse_args()
    stop = False

    def _stop(*_):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    ncpu = os.cpu_count()
    cols = (["t_mono_ns", "t_wall"] + [f"cpu_{c}" for c in CPU_COLS] +
            ["ncpu", "ctxt", "procs_running", "procs_blocked", "mem_total_kb", "mem_available_kb",
             "pgfault", "pgmajfault", "load1"])
    with open(a.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        while not stop:
            cpu, ctxt, run, blk = read_stat()
            mem = read_kv("/proc/meminfo", {"MemTotal", "MemAvailable"})
            vm = read_kv("/proc/vmstat", {"pgfault", "pgmajfault"})
            load1 = open("/proc/loadavg").read().split()[0]
            w.writerow([time.monotonic_ns(), f"{time.time():.3f}"] + cpu +
                       [ncpu, ctxt, run, blk, mem.get("MemTotal"), mem.get("MemAvailable"),
                        vm.get("pgfault"), vm.get("pgmajfault"), load1])
            fh.flush()
            if a.pid and not os.path.exists(f"/proc/{a.pid}"):
                break
            time.sleep(a.interval)


if __name__ == "__main__":
    main()
