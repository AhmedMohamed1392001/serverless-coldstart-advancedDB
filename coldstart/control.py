"""controller sends requests to workers and collects their events"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field

from . import settings
from .template import Request
from .measure import now_ns

PY = [sys.executable, "-m", "coldstart.workers"]


@dataclass
class Trace:
    req: Request
    mode: str
    t0_ns: int
    events: dict = field(default_factory=dict)
    fallback: bool = False

    def done(self) -> bool:
        return "done" in self.events or "error" in self.events

    def row(self) -> dict:
        e = self.events
        r = {"req_id": self.req.req_id, "mode": self.mode,
             "query_id": self.req.query_id, "scale": self.req.scale,
             "catalog": self.req.catalog, "fallback": self.fallback,
             "t0_ns": self.t0_ns, "error": e.get("error", {}).get("error")}
        if "proc_start" in e:
            r["proc_start_us"] = (e["proc_start"]["ns"] - self.t0_ns) / 1e3
        if "ready" in e:
            r["T_a_us"] = (e["ready"]["ns"] - self.t0_ns) / 1e3
            r["mem_ready_private_dirty_kb"] = e["ready"]["mem"].get("Private_Dirty")
            r["mem_ready_rss_kb"] = e["ready"]["mem"].get("Rss")
            r["minflt_ready"] = e["ready"].get("minflt")
            for ph in e["ready"].get("phases", []):
                r[f"phase:{ph['phase']}_us"] = ph["dur_us"]
        if "first_row" in e:
            r["T_v_us"] = (e["first_row"]["ns"] - self.t0_ns) / 1e3
            r["exec_to_first_row_us"] = (e["first_row"]["ns"] - e["first_row"]["exec_start_ns"]) / 1e3
        if "done" in e:
            r["T_e_us"] = (e["done"]["ns"] - self.t0_ns) / 1e3
            r["rows"] = e["done"]["rows"]
            r["digest"] = e["done"]["digest"]
            r["mem_done_private_dirty_kb"] = e["done"]["mem"].get("Private_Dirty")
            r["mem_done_rss_kb"] = e["done"]["mem"].get("Rss")
            r["mem_done_shared_clean_kb"] = e["done"]["mem"].get("Shared_Clean")
            r["minflt_done"] = e["done"].get("minflt")
            r["pid"] = e["done"]["pid"]
        return r


class Controller:
    def __init__(self, mode: str, scale: float, catalog: str = "small",
                 pool_size: int = 1) -> None:
        assert mode in settings.WORKER_MODES
        self.mode, self.scale, self.catalog = mode, scale, catalog
        self.pool_size = pool_size
        self.ev_r, self.ev_w = os.pipe()
        os.set_inheritable(self.ev_w, True)
        try:  # bigger pipe so 32 workers can write without blocking
            import fcntl
            fcntl.fcntl(self.ev_w, 1031, 1 << 20)  # F_SETPIPE_SZ
        except OSError:
            pass
        self.log = open(os.environ.get("COLDSTART_WORKER_LOG", os.devnull), "a")
        self._buf = b""
        self.servers: list[subprocess.Popen] = []
        self.template_info: dict | None = None
        self.traces: dict[str, Trace] = {}
        self._rr = 0
        self.env = {**os.environ, "COLDSTART_DATA": str(settings.DATA_ROOT),
                    "PYTHONPATH": str(settings.REPO_ROOT)}

    def start(self) -> None:
        if self.mode == "fresh":
            return
        n = self.pool_size if self.mode == "warm" else 1
        for _ in range(n):
            p = subprocess.Popen(
                PY + [self.mode, "--fd", str(self.ev_w), "--scale", str(self.scale),
                      "--catalog", self.catalog],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
                text=True, pass_fds=(self.ev_w,), env=self.env, cwd=settings.REPO_ROOT)
            line = p.stdout.readline()
            if line.strip() != "READY":
                raise RuntimeError(f"{self.mode} server failed to start: {p.stderr}")
            self.servers.append(p)
        if self.mode.startswith("clone"):
            self.template_info = self._read_until("template_ready")

    def stop(self) -> None:
        for p in self.servers:
            try:
                p.stdin.write("STOP\n"); p.stdin.flush(); p.stdin.close()
                p.wait(timeout=30)
            except Exception:
                p.kill()
        self.servers.clear()

    def __enter__(self):
        self.start(); return self

    def __exit__(self, *a):
        self.stop()

    def submit(self, req: Request) -> Trace:
        req.dataset_version = req.dataset_version or settings.dataset_version(self.scale)
        t0 = now_ns()   # t_0
        tr = Trace(req, self.mode, t0)
        self.traces[req.req_id] = tr
        if self.mode == "fresh":
            self._spawn_fresh(req)
        else:
            srv = self.servers[self._rr % len(self.servers)]
            self._rr += 1
            srv.stdin.write(json.dumps(req.to_dict()) + "\n"); srv.stdin.flush()
        return tr

    def _spawn_fresh(self, req: Request) -> None:
        subprocess.Popen(PY + ["fresh", "--fd", str(self.ev_w), "--req",
                               json.dumps(req.to_dict())],
                         pass_fds=(self.ev_w,), env=self.env, cwd=settings.REPO_ROOT,
                         stdin=subprocess.DEVNULL, stderr=self.log)

    def _read_events(self, timeout: float = 120.0):
        import select
        deadline = time.monotonic() + timeout
        while True:
            nl = self._buf.find(b"\n")
            if nl >= 0:
                line, self._buf = self._buf[:nl], self._buf[nl + 1:]
                yield json.loads(line)
                continue
            r, _, _ = select.select([self.ev_r], [], [], max(0, deadline - time.monotonic()))
            if not r:
                raise TimeoutError("no worker events")
            self._buf += os.read(self.ev_r, 65536)

    def _read_until(self, event: str) -> dict:
        for ev in self._read_events():
            if ev.get("event") == event:
                return ev
            self._dispatch(ev)
        raise RuntimeError("unreachable")

    def _dispatch(self, ev: dict) -> None:
        tr = self.traces.get(ev.get("req_id"))
        if tr is None:
            return
        if ev["event"] == "template_mismatch":
            # template does not match, so start a fresh worker instead
            tr.fallback = True
            self._spawn_fresh(tr.req)
            return
        tr.events[ev["event"]] = ev

    def wait(self, traces: list[Trace], timeout: float = 300.0) -> list[dict]:
        # a worker that stays silent for `timeout` s is counted as an error
        pending = {t.req.req_id for t in traces}
        try:
            for ev in self._read_events(timeout):
                self._dispatch(ev)
                tr = self.traces.get(ev.get("req_id"))
                if tr and tr.done():
                    pending.discard(tr.req.req_id)
                if not pending:
                    break
        except TimeoutError:
            for p in self.servers:
                if p.poll() is not None:
                    raise RuntimeError(f"{self.mode} server exited with {p.returncode}")
            for t in traces:
                if not t.done():
                    t.events["error"] = {"error": f"lost worker: no event for {timeout}s",
                                         "ns": now_ns()}
        return [t.row() for t in traces]

    def run_burst(self, reqs: list[Request]) -> list[dict]:
        traces = [self.submit(r) for r in reqs]
        return self.wait(traces)
