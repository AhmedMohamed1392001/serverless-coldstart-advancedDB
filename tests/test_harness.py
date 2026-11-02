"""end to end check of the C harness: build coldbench, run a tiny burst,
make sure the log lines have what the plots and the report need.
skips if the duckdb C library isn't downloaded yet (make bench downloads it)."""
import json, subprocess, sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "native"))
from duckdb_lib import LIB  # noqa: E402

DATA = ROOT / "data" / "tpch_sf0.1"
NEEDED = {"mode", "conc", "ready_us", "done_us", "t_arrive_ns", "t_ready_ns", "t_done_ns",
          "faults_ready", "utime_us", "vcsw", "private_dirty_kb"}

pytestmark = pytest.mark.skipif(not (Path(LIB) / "libduckdb.so").exists(), reason="libduckdb not downloaded")


@pytest.fixture(scope="module")
def exe():
    from bench_native import build
    return build()


@pytest.mark.parametrize("mode", ["fresh", "clone_prepared", "clone_pooled"])
def test_burst_log_lines(exe, mode):
    out = subprocess.run([str(exe), "--data", str(DATA), "--mode", mode, "--query", "point",
                          "--conc", "4", "--reps", "2"], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-300:]
    reqs = [json.loads(l) for l in out.stdout.splitlines() if l.startswith("{")]
    reqs = [r for r in reqs if r.get("mode") == mode]
    assert len(reqs) == 8                                   # 2 bursts of 4
    for r in reqs:
        assert NEEDED <= r.keys()
        # the raw stamps and the durations have to agree
        assert r["t_arrive_ns"] <= r["t_ready_ns"] <= r["t_done_ns"]
        assert abs((r["t_ready_ns"] - r["t_arrive_ns"]) / 1e3 - r["ready_us"]) < 1.0
        assert abs((r["t_done_ns"] - r["t_arrive_ns"]) / 1e3 - r["done_us"]) < 1.0
    # every request in a burst arrives at the same time
    for rep in {r["rep"] for r in reqs}:
        assert len({r["t_arrive_ns"] for r in reqs if r["rep"] == rep}) == 1


def test_percentiles_match_numpy():
    from plot_native import pct
    import pandas as pd
    x = pd.Series(np.random.default_rng(3).exponential(1.0, 5000))
    for q in (50, 90, 99):
        assert pct(x, q) == pytest.approx(np.percentile(x, q))
