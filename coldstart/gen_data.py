"""make TPC-H parquet files using tpchgen-cli"""
from __future__ import annotations

import hashlib
import subprocess
import sys

from . import settings


def generate(scale: float) -> str:
    d = settings.dataset_dir(scale)
    d.mkdir(parents=True, exist_ok=True)
    if not (d / "VERSION").exists():
        subprocess.check_call(["tpchgen-cli", "parquet", "-s", str(scale),
                               "--output-dir", str(d)])
        h = hashlib.sha1()
        for tb in settings.TPCH_TABLES:
            p = d / f"{tb}.parquet"
            h.update(f"{tb}:{p.stat().st_size}".encode())
        (d / "VERSION").write_text(f"tpch-sf{scale:g}-{h.hexdigest()[:10]}\n")
    return settings.dataset_version(scale)


if __name__ == "__main__":
    for s in sys.argv[1:] or ["1"]:
        print(generate(float(s)))
