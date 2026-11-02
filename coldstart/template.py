"""engine startup steps, reusable/private parts, and running a query"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Callable

from . import settings
from .measure import now_ns, smaps_rollup, minor_faults
from .queries import QUERIES, catalog_padding_sql, CATALOG_SIZES


@dataclass
class Request:
    req_id: str
    query_id: str
    scale: float
    catalog: str = "small"
    dataset_version: str = ""
    engine_version: str = settings.DUCKDB_VERSION
    sql: str = ""                  # only used by tests, else QUERIES[query_id]

    def template_key(self) -> str:
        return template_key(self.engine_version, self.dataset_version,
                            self.catalog)

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @staticmethod
    def from_dict(d: dict) -> "Request":
        return Request(**{k: d[k] for k in Request.__dataclass_fields__ if k in d})


def template_key(engine_version: str, dataset_version: str, catalog: str) -> str:
    # a request can only use a template with the same key
    engine_opts = ",".join(f"{k}={v}" for k, v in sorted(settings.ENGINE_SETTINGS.items()))
    raw = f"{engine_version}|{dataset_version}|{catalog}|{engine_opts}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


class Phases:

    def __init__(self) -> None:
        self.items: list[tuple[str, int, int]] = []

    def record(self, name: str, start: int, end: int | None = None) -> None:
        self.items.append((name, start, end if end is not None else now_ns()))

    def as_list(self) -> list[dict]:
        return [{"phase": n, "start_ns": s, "end_ns": e, "dur_us": (e - s) / 1e3}
                for n, s, e in self.items]


# start-up steps, each one is timed as a phase
def import_engine(phases: Phases):
    t = now_ns()
    import duckdb  # noqa: F401  (the import is what we time)
    phases.record("lib_load", t)
    if duckdb.__version__ != settings.DUCKDB_VERSION:
        raise RuntimeError(f"DuckDB {duckdb.__version__} found, "
                           f"{settings.DUCKDB_VERSION} pinned")
    return duckdb


def open_engine(duckdb, phases: Phases):
    t = now_ns()
    con = duckdb.connect(database=":memory:", config=dict(settings.ENGINE_SETTINGS))
    phases.record("engine_open", t)
    return con


def build_catalog(con, scale: float, catalog: str, phases: Phases) -> None:
    t = now_ns()
    d = settings.dataset_dir(scale)
    for tb in settings.TPCH_TABLES:
        con.execute(f"CREATE VIEW {tb} AS SELECT * FROM read_parquet('{d / tb}.parquet')")
    for stmt in catalog_padding_sql(CATALOG_SIZES[catalog]):
        con.execute(stmt)
    phases.record("catalog_build", t)


def warm_metadata(con, scale: float, phases: Phases) -> None:
    # read the parquet footers once here so workers do not have to
    t = now_ns()
    d = settings.dataset_dir(scale)
    for tb in settings.TPCH_TABLES:
        con.execute(f"SELECT count(*) FROM parquet_metadata('{d / tb}.parquet')").fetchall()
        con.execute(f"DESCRIBE SELECT * FROM {tb}").fetchall()
    phases.record("metadata_warm", t)


# parts of the engine: reusable ones come from the template, private ones are rebuilt
@dataclass
class Component:
    name: str
    kind: str                      # "reusable" or "private"
    deps: list[str]
    description: str
    reconstruct: Callable | None = None   # only for private parts


@dataclass
class State:
    duckdb: object = None
    template_con: object = None    # connection made in the template
    con: object = None             # connection this worker runs on
    temp_dir: str | None = None
    rebuilt: list[str] = field(default_factory=list)


def _rebuild_connection(st: State) -> None:
    # new cursor: own transaction state, same catalog and settings
    st.con = st.template_con.cursor()


def _rebuild_temp_dir(st: State) -> None:
    # only sets the path, duckdb makes the folder when it first spills
    st.temp_dir = f"/tmp/coldstart-{os.getpid()}"
    st.con.execute(f"SET temp_directory = '{st.temp_dir}'")


PARTS: list[Component] = [
    Component("library", "reusable", [],
              "libduckdb code pages and Python extension module"),
    Component("database_instance", "reusable", ["library"],
              "DatabaseInstance, buffer manager, extension settings"),
    Component("catalog", "reusable", ["database_instance"],
              "table/view/column/type descriptors (read-only for a template)"),
    Component("parquet_metadata_cache", "reusable", ["catalog"],
              "object cache of Parquet footers and schemas"),
    Component("connection", "private", ["database_instance", "catalog"],
              "ClientContext: transaction state, query buffers, result storage",
              _rebuild_connection),
    Component("engine_settings", "reusable", ["database_instance"],
              "threads / memory_limit: part of the template key, inherited"),
    Component("temp_directory", "private", ["connection"],
              "per-worker spill directory", _rebuild_temp_dir),
]


def reconstruction_order() -> list[Component]:
    # topological sort, a part is rebuilt after the parts it depends on
    by_name = {c.name: c for c in PARTS}
    done: set[str] = {c.name for c in PARTS if c.kind == "reusable"}
    order: list[Component] = []
    pending = [c for c in PARTS if c.kind == "private"]
    while pending:
        ready = [c for c in pending if all(d in done for d in c.deps)]
        if not ready:
            raise RuntimeError("dependency cycle among private components: "
                               + ", ".join(c.name for c in pending))
        for c in ready:
            order.append(c)
            done.add(c.name)
            pending.remove(c)
    return order


def rebuild_private_parts(st: State, phases: Phases) -> None:
    for comp in reconstruction_order():
        t = now_ns()
        comp.reconstruct(st)
        phases.record(f"rebuild:{comp.name}", t)
        st.rebuilt.append(comp.name)


# template is built once before any fork
def build_template(scale: float, catalog: str, phases: Phases,
                   freeze_heap: bool = True) -> State:
    st = State()
    st.duckdb = import_engine(phases)
    st.template_con = open_engine(st.duckdb, phases)
    build_catalog(st.template_con, scale, catalog, phases)
    warm_metadata(st.template_con, scale, phases)
    quiesce(st, phases, freeze_heap)
    return st


def quiesce(st: State, phases: Phases, freeze_heap: bool) -> None:
    # get ready to fork: no other threads, and freeze the heap so gc does not touch shared pages
    import gc
    import threading
    t = now_ns()
    if threading.active_count() != 1:
        raise RuntimeError("background threads alive at clone boundary: "
                           f"{threading.active_count()}")
    gc.collect()
    if freeze_heap:
        gc.freeze()
    phases.record("quiesce", t)


def result_digest(rows) -> str:
    h = hashlib.sha256()
    for r in rows:
        h.update(repr(r).encode())
    return h.hexdigest()[:16]


def run_query(con, req: Request, emit: Callable[[dict], None],
                    phases: Phases, mode: str, extra: dict | None = None) -> str:
    # events: ready (t_a), first_row (t_v), done (t_f)
    base = {"req_id": req.req_id, "mode": mode, "pid": os.getpid(),
            "query_id": req.query_id}
    base.update(extra or {})
    t_ready = now_ns()           # t_a: take the time first, reading /proc costs ~0.5 ms
    emit({**base, "event": "ready", "ns": t_ready, "mem": smaps_rollup(),
          "minflt": minor_faults(), "phases": phases.as_list()})
    sql = req.sql or QUERIES[req.query_id]
    t = now_ns()
    cur = con.execute(sql)
    first = cur.fetchone()
    tv = now_ns()
    rows = [first] + cur.fetchall() if first is not None else []
    tf = now_ns()                # t_f: before hashing the rows
    digest = result_digest(rows)
    emit({**base, "event": "first_row", "ns": tv, "exec_start_ns": t})
    emit({**base, "event": "done", "ns": tf, "rows": len(rows),
          "digest": digest, "mem": smaps_rollup(), "minflt": minor_faults()})
    return digest


def emit_to_fd(fd: int) -> Callable[[dict], None]:
    import json

    def emit(ev: dict) -> None:
        data = (json.dumps(ev, separators=(",", ":")) + "\n").encode()
        # writes up to 4096 bytes (PIPE_BUF) are atomic, so workers do not mix lines
        assert len(data) <= 4096, "event too large for atomic pipe write"
        os.write(fd, data)
    return emit


def stderr_note(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)
