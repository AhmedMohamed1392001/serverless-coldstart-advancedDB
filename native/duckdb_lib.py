"""where the DuckDB C library lives, and a download if it isn't there yet.
The C programs link against this exact version."""
import urllib.request, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = HERE / "libduckdb"
VERSION = "1.5.6"
URL = f"https://github.com/duckdb/duckdb/releases/download/v{VERSION}/libduckdb-linux-amd64.zip"


def ensure_lib():
    if (LIB / "libduckdb.so").exists():
        return
    LIB.mkdir(exist_ok=True)
    print("downloading libduckdb", VERSION, "...", flush=True)
    urllib.request.urlretrieve(URL, LIB / "lib.zip")
    with zipfile.ZipFile(LIB / "lib.zip") as z:
        z.extractall(LIB)
    (LIB / "lib.zip").unlink()
