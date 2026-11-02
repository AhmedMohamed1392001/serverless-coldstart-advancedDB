"""four worker modes: fresh, clone_generic, clone_selective, warm

Events written to a pipe fd. Requests from argv for fresh, stdin for the rest
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import traceback

from . import settings
from .template import (Phases, Request, State, build_template,
                     run_query, emit_to_fd, import_engine, open_engine,
                     build_catalog, rebuild_private_parts)
from .measure import now_ns, smaps_rollup


def _error(emit, req: Request, mode: str, exc: BaseException) -> None:
    emit({"req_id": req.req_id, "mode": mode, "pid": os.getpid(),
          "query_id": req.query_id, "event": "error", "ns": now_ns(),
          "error": repr(exc)[:1500]})


def run_fresh(req: Request, emit, proc_start_ns: int) -> None:
    phases = Phases()
    emit({"req_id": req.req_id, "mode": "fresh", "pid": os.getpid(),
          "query_id": req.query_id, "event": "proc_start", "ns": proc_start_ns})
    try:
        duckdb = import_engine(phases)
        con = open_engine(duckdb, phases)
        build_catalog(con, req.scale, req.catalog, phases)
        run_query(con, req, emit, phases, "fresh")
    except BaseException as e:  # noqa: BLE001
        _error(emit, req, "fresh", e)


def _serve_template(mode: str, scale: float, catalog: str, emit,
                    ctrl_in, ctrl_out) -> None:
    # build the template once, then fork a child for every request
    selective = mode == "clone_selective"
    phases = Phases()
    t0 = now_ns()
    if selective:
        st = build_template(scale, catalog, phases, freeze_heap=True)
    else:
        # generic clone: no metadata warm-up, no heap freeze, child keeps the connection as is
        st = State()
        st.duckdb = import_engine(phases)
        st.template_con = open_engine(st.duckdb, phases)
        build_catalog(st.template_con, scale, catalog, phases)
        from .template import quiesce
        quiesce(st, phases, freeze_heap=False)
    key = template_key_for(scale, catalog)
    emit({"event": "template_ready", "mode": mode, "pid": os.getpid(),
          "template_key": key, "ns": now_ns(), "build_ns": now_ns() - t0,
          "phases": phases.as_list(), "mem": smaps_rollup()})
    ctrl_out.write("READY\n"); ctrl_out.flush()

    children: list[int] = []
    for line in ctrl_in:
        line = line.strip()
        if not line or line == "STOP":
            break
        req = Request.from_dict(json.loads(line))
        if req.template_key() != key:
            # wrong template, controller will start a fresh worker
            emit({"req_id": req.req_id, "mode": mode, "pid": os.getpid(),
                  "query_id": req.query_id, "event": "template_mismatch",
                  "ns": now_ns(), "template_key": key,
                  "request_key": req.template_key()})
            continue
        t_fork = now_ns()
        pid = os.fork()
        if pid == 0:
            _clone_child(st, req, mode, emit, t_fork)
            os._exit(0)
        children.append(pid)
        # clean up finished children, WNOHANG so we do not wait
        children = [c for c in children if os.waitpid(c, os.WNOHANG)[0] == 0]
    for c in children:
        try:
            os.waitpid(c, 0)
        except ChildProcessError:
            pass


def template_key_for(scale: float, catalog: str) -> str:
    from .template import template_key
    return template_key(settings.DUCKDB_VERSION, settings.dataset_version(scale), catalog)


def _clone_child(st: State, req: Request, mode: str, emit, t_fork: int) -> None:
    phases = Phases()
    phases.record("fork", t_fork)
    emit({"req_id": req.req_id, "mode": mode, "pid": os.getpid(),
          "query_id": req.query_id, "event": "proc_start", "ns": now_ns(),
          "fork_ns": t_fork})
    try:
        if mode == "clone_selective":
            rebuild_private_parts(st, phases)
            con = st.con
        else:
            con = st.template_con   # use it as is
        run_query(con, req, emit, phases, mode,
                        extra={"rebuilt": st.rebuilt})
    except BaseException as e:  # noqa: BLE001
        _error(emit, req, mode, e)
    finally:
        if st.temp_dir:
            shutil.rmtree(st.temp_dir, ignore_errors=True)


def _serve_warm(scale: float, catalog: str, emit, ctrl_in, ctrl_out) -> None:
    phases = Phases()
    duckdb = import_engine(phases)
    con = open_engine(duckdb, phases)
    build_catalog(con, scale, catalog, phases)
    from .template import warm_metadata
    warm_metadata(con, scale, phases)
    ctrl_out.write("READY\n"); ctrl_out.flush()
    for line in ctrl_in:
        line = line.strip()
        if not line or line == "STOP":
            break
        req = Request.from_dict(json.loads(line))
        emit({"req_id": req.req_id, "mode": "warm", "pid": os.getpid(),
              "query_id": req.query_id, "event": "proc_start", "ns": now_ns()})
        try:
            run_query(con, req, emit, Phases(), "warm")
        except BaseException as e:  # noqa: BLE001
            _error(emit, req, "warm", e)


def main(argv: list[str]) -> int:
    proc_start = now_ns()
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=settings.WORKER_MODES)
    p.add_argument("--fd", type=int, required=True, help="event pipe fd")
    p.add_argument("--req", help="JSON request (fresh mode)")
    p.add_argument("--scale", type=float)
    p.add_argument("--catalog", default="small")
    a = p.parse_args(argv)
    emit = emit_to_fd(a.fd)
    try:
        if a.mode == "fresh":
            run_fresh(Request.from_dict(json.loads(a.req)), emit, proc_start)
        elif a.mode in ("clone_generic", "clone_selective"):
            _serve_template(a.mode, a.scale, a.catalog, emit, sys.stdin, sys.stdout)
        else:
            _serve_warm(a.scale, a.catalog, emit, sys.stdin, sys.stdout)
    except BaseException:  # noqa: BLE001
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
