"""worker tests, run with make test (makes SF0.1 data first)"""
from __future__ import annotations

import os
import signal
import time

import duckdb
import pytest

from coldstart import settings
from coldstart.control import Controller
from coldstart.gen_data import generate
from coldstart.template import (Phases, Request, PARTS, build_template,
                              reconstruction_order, result_digest)
from coldstart.queries import QUERIES

SCALE = 0.1


@pytest.fixture(scope="session", autouse=True)
def dataset():
    generate(SCALE)


@pytest.fixture(scope="session")
def reference():
    # result digests from plain duckdb
    con = duckdb.connect(config={"threads": 1})
    d = settings.dataset_dir(SCALE)
    for tb in settings.TPCH_TABLES:
        con.execute(f"CREATE VIEW {tb} AS SELECT * FROM read_parquet('{d / tb}.parquet')")
    return {q: result_digest(con.execute(sql).fetchall()) for q, sql in QUERIES.items()}


# --------------------------------------------------------------------------
@pytest.mark.parametrize("mode", settings.WORKER_MODES)
def test_results_match_unmodified_duckdb(mode, reference):
    with Controller(mode, SCALE) as c:
        reqs = [Request(f"{mode}-{q}", q, SCALE) for q in QUERIES]
        rows = c.run_burst(reqs) if mode != "warm" else \
            [c.run_burst([r])[0] for r in reqs]
    for r in rows:
        assert r["error"] is None, r
        assert r["digest"] == reference[r["query_id"]], r["query_id"]


def test_concurrent_clones_are_independent(reference):
    with Controller("clone_selective", SCALE) as c:
        rows = c.run_burst([Request(f"c{i}", "q6", SCALE) for i in range(16)])
    assert all(r["error"] is None for r in rows)
    assert {r["digest"] for r in rows} == {reference["q6"]}
    assert len({r["pid"] for r in rows}) == 16, "each request must run in its own worker"


def test_template_mismatch_falls_back_to_fresh(reference):
    # wrong dataset version -> fresh worker, same result
    with Controller("clone_selective", SCALE) as c:
        ok = c.run_burst([Request("ok", "s_point", SCALE)])[0]
        bad = c.run_burst([Request("bad", "s_point", SCALE,
                                   dataset_version="retired-version")])[0]
    assert ok["fallback"] is False and ok["digest"] == reference["s_point"]
    assert bad["fallback"] is True and bad["digest"] == reference["s_point"]
    assert "phase:lib_load_us" in bad, "fallback must have paid full initialization"


def test_no_state_carried_between_requests():
    # what one clone creates must not show up in the next one
    st = build_template(SCALE, "small", Phases())
    r, w = os.pipe()

    def child(body):
        pid = os.fork()
        if pid == 0:
            os.close(r)
            from coldstart.template import rebuild_private_parts
            rebuild_private_parts(st, Phases())
            try:
                os.write(w, body(st.con).encode())
            finally:
                os._exit(0)
        os.waitpid(pid, 0)

    child(lambda con: (con.execute("CREATE TEMP TABLE leak AS SELECT 1 AS x"),
                       con.execute("SET memory_limit='64MB'"), "made")[-1])
    child(lambda con: "leaked" if con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name='leak'"
    ).fetchone()[0] else "clean:" + con.execute(
        "SELECT current_setting('memory_limit')").fetchone()[0])
    os.close(w)
    out = os.read(r, 4096).decode()
    assert out.startswith("madeclean:"), out
    assert "64" not in out.split(":")[1], "per-worker setting leaked into the template"


def test_cancelled_worker_does_not_damage_template():
    # kill a worker mid-query, template should still work
    with Controller("clone_selective", SCALE) as c:
        tr = c.submit(Request("victim", "q18", SCALE))
        # wait until it is ready, then kill it while it runs
        ev = c._read_until("ready")
        time.sleep(0.05)
        os.kill(ev["pid"], signal.SIGKILL)
        c.traces.pop("victim")
        after = c.run_burst([Request("after", "q6", SCALE)])[0]
    assert after["error"] is None and after["rows"] == 1


def test_unsupported_sql_is_reported_not_fatal():
    with Controller("clone_selective", SCALE) as c:
        bad = c.run_burst([Request("bad", "adhoc", SCALE,
                                   sql="SELECT * FROM table_that_does_not_exist")])[0]
        good = c.run_burst([Request("good", "s_count", SCALE)])[0]
    assert bad["error"] and "table_that_does_not_exist" in bad["error"]
    assert good["error"] is None


def test_parts_dependencies_are_acyclic_and_declared():
    names = {c.name for c in PARTS}
    for c in PARTS:
        assert set(c.deps) <= names, c.name
        assert (c.reconstruct is not None) == (c.kind == "private"), c.name
    order = [c.name for c in reconstruction_order()]
    assert order.index("connection") < order.index("temp_directory")


def test_clone_boundary_requires_quiescence():
    import threading
    stop = threading.Event()
    t = threading.Thread(target=stop.wait); t.start()
    try:
        with pytest.raises(RuntimeError, match="background threads"):
            build_template(SCALE, "small", Phases())
    finally:
        stop.set(); t.join()


def test_clone_private_memory_is_below_fresh():
    # just a sanity check of the memory numbers
    with Controller("fresh", SCALE) as c:
        fresh = c.run_burst([Request("f", "s_point", SCALE)])[0]
    with Controller("clone_selective", SCALE) as c:
        clone = c.run_burst([Request("c", "s_point", SCALE)])[0]
    assert clone["mem_done_private_dirty_kb"] < fresh["mem_done_private_dirty_kb"]
