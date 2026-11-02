"""paths and constants used everywhere"""
from __future__ import annotations

import os
from pathlib import Path

# only run with this duckdb version so all results are comparable
DUCKDB_VERSION = "1.5.6"

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(os.environ.get("COLDSTART_DATA", REPO_ROOT / "data"))
RESULTS_ROOT = Path(os.environ.get("COLDSTART_RESULTS", REPO_ROOT / "results"))

TPCH_TABLES = [
    "lineitem", "orders", "customer", "part",
    "supplier", "partsupp", "nation", "region",
]

# same settings for every worker type
ENGINE_SETTINGS = {
    "threads": 1,               # no background threads when we fork
    "memory_limit": "512MB",
    "enable_object_cache": True,  # parquet footer cache, the template can fill it
}

WORKER_MODES = ("fresh", "clone_generic", "clone_selective", "warm")


def dataset_dir(scale: float) -> Path:
    return DATA_ROOT / f"tpch_sf{scale:g}"


def dataset_version(scale: float) -> str:
    d = dataset_dir(scale)
    stamp = d / "VERSION"
    if stamp.exists():
        return stamp.read_text().strip()
    return "missing"
