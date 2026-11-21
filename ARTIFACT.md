# Artifact for "Sub-Millisecond Cold Starts for Serverless Analytics"

This file explains how to check the paper's numbers and how to produce them
again. There are two levels. The first level recomputes every table and
figure from the raw measurements in `results/milestone2`, takes about a
minute and works on any machine with Python. The second level reruns the
experiments themselves and needs a Linux machine with gcc.

## Contents

| Path | What it is |
|---|---|
| `native/coldbench.c` | Benchmark for the six worker types (Sections 5.2, 5.3, Table 2) |
| `native/density.c` | Many workers over one table, and the failure tests (Sections 5.4, 5.5) |
| `native/pool.c` | Pool controller with the spawner and the three sizing policies (Sections 3.4, 3.5, 5.6) |
| `native/bench_native.py` | Runs `coldbench` and `density` over the experiment matrix |
| `native/pool_replay.py` | Replays a trace against `pool`, and holds the pool simulator of Section 3.5 |
| `native/plot_native.py` | Per-run plots, csv files and `summary.md` |
| `coldstart/` | Python prototype (template identity, parts list, fallback to a fresh worker) and the TPC-H generator |
| `tests/` | Correctness tests. Every worker type must return the same answers as plain DuckDB |
| `tools/sysmon.py` | Samples /proc every 200 ms during a run |
| `tools/paper_numbers.py` | Recomputes Table 2, Table 3 and the numbers added in the revision |
| `tools/paper_figures.py` | Redraws Figures 4 to 9 |
| `run_benchmarks.sh`, `Makefile` | One command for everything, and one target per experiment |
| `results/milestone2/` | The raw measurements behind the paper (see below) |

Figures 1 to 3 are drawings of the design and contain no measurements.

## Level 1. Check the paper against the raw data (about 1 minute)

```
pip install numpy matplotlib
python3 tools/paper_numbers.py results/milestone2 > paper_numbers.md
python3 tools/paper_figures.py results/milestone2 paper_figures
```

`paper_numbers.md` should match Table 2, Table 3 and the numbers in Sections
5.2 and 5.6 exactly. The bootstrap intervals use a fixed seed. The six files in
`paper_figures/` are the data figures of the paper.

## Where each result comes from

| Paper | Raw file in `results/milestone2/` | Records used |
|---|---|---|
| Figure 4, Table 2 columns 2 to 5 | `native-sf1/events.jsonl` | `exp=latency`, `conc=1`, `catalog=0`, queries point, count and filter |
| Table 2, p99 over 10,000 | `native-sf1/events.jsonl` (selective, prepared, pooled) and `p99_extra.jsonl` (fresh, generic, warm, later session) | `exp=p99`, and all records of `p99_extra.jsonl` |
| Table 2, last column | `native-sf0.1/events.jsonl` | as for Figure 4 |
| Figure 5 | `native-sf1/events.jsonl`, `native-sf1/throughput.csv` | `exp=latency`, `conc` 1, 8 and 32 |
| Figure 6 | `native-sf1/events.jsonl` | `exp=catalog` (200 and 2,000 extra views) and `exp=latency` |
| Figure 7 | `native-sf1/events.jsonl` | as for Figure 4, fields `faults_ready` and `faults_query` |
| Figure 8a | `native-sf1/events.jsonl` | `exp=density` summary records with `inmem=1` |
| Figure 8b | `native-sf1/events.jsonl` | `mode=pool_memory`, template size from `mode=template_build` |
| Section 5.5 | `native-sf1/events.jsonl` | `exp=isolation` |
| Figure 9, Table 3, Section 5.6 | `pool-azure-busiest/`, `pool-azure-quietest/`, `pool-synthetic/` | `pool_replay.jsonl`, one summary per configuration and one record per request |
| Section 5.7 | `run.log`, `native-sf1/events.jsonl` | block field `block`, throttled first attempt in `run.log` |
| Fresh start-up phases (Section 2.2) | `native-sf1/phases.jsonl` | `mode=fresh_phases` |

`results/milestone2/SHA256SUMS` lists a checksum for every raw file, so
`cd results/milestone2 && sha256sum -c SHA256SUMS` confirms they are
unchanged. Every request record carries raw `CLOCK_MONOTONIC` stamps (`t_arrive_ns`,
`t_ready_ns`, `t_done_ns`), so any statistic can be recomputed without the
summaries. `env.txt` records the machine, kernel, Python and DuckDB versions,
and `commands.txt` lists the exact commands of the run.

## Level 2. Rerun the experiments

### Machine

The paper's numbers come from a laptop (AMD Ryzen 9 8945HX, 16 logical CPUs,
16 GB RAM) running Ubuntu inside WSL2 with Linux 6.6. Any x86-64 Linux machine
with gcc works. For numbers that can be compared with the paper, use at least
16 cores and 16 GB of RAM. Bare-metal Linux with one CPU socket is better than
a virtual machine, because the virtual machine is the main threat to validity
discussed in Section 6. On CloudLab, a `c6525-25g` node (one AMD EPYC 7302P,
16 cores, 128 GB) is a good match.

The pool replays keep two cores busy, because the controller and the spawner
spin while they wait (Section 6). On a machine with fewer than four cores the
replay numbers are meaningless. We checked `./run_benchmarks.sh --quick` on a
clean copy in a 2-core cloud container. Every step finished, all 16 tests
passed and the tools read the new run, but the replays there were much slower
than on the laptop for this reason.

### Software

Ubuntu 22.04 or 24.04, gcc, make, git and Python 3.10 or newer.

```
sudo apt-get install -y build-essential python3-pip git
pip install -r requirements.txt
```

The first run downloads the DuckDB 1.5.6 C library into `native/libduckdb/`
(`native/duckdb_lib.py`). TPC-H data is generated locally with `tpchgen-cli`.

### Commands

| Command | Time on the laptop | Output |
|---|---|---|
| `make test` | under a minute | correctness tests |
| `./run_benchmarks.sh --quick` | about 5 minutes | a small run at scale factor 0.1, to check that everything works |
| `make bench SCALE=1` | about 20 minutes | `results/native-<time>-sf1/`, the data of Figures 4 to 8 and Table 2 |
| `make pool-replay` | under a minute | synthetic trace replay |
| `make pool-replay-azure PICK=busiest AZURE=<trace file>` | a few minutes | Azure replay, also with `PICK=quietest` |
| `./run_benchmarks.sh --name milestone2 --azure <trace file>` | about 45 minutes | everything above in one folder |

The Azure Functions 2021 invocation trace is not included because of its size.
It is available from the Azure Public Dataset
(`AzureFunctionsInvocationTraceForTwoWeeksJan2021.txt`). The one-hour windows
used in the paper are stored as `trace_ms.txt` in each pool folder, so a replay
can also run straight from them with `native/pool --data data/tpch_sf1 --trace
results/milestone2/pool-azure-busiest/trace_ms.txt --policy fixed --pool 16`.

Then point the two tools at the new run folder, for example
`python3 tools/paper_numbers.py results/<run>`. On a quick run they skip the
tables and figures whose experiments were not run.

### What to expect

Absolute times depend on the machine. Within one machine, the block-to-block
spread of the medians was 2.5% to 15%, and medians moved by about 12% between
two sessions three hours apart (Section 5.7). The claims that should hold on
any Linux machine are the order of the worker types, the near-equal total
fault counts of selective and prepared clones, the flat activation of pooled
and prepared clones as the catalog grows, the memory of clones staying close
to threads, and the shape of the pool-size curves. `perf` was not usable under
WSL2, so `run.log` notes that only /proc samples were taken. On bare metal,
`perf stat` can be wrapped around any of the commands above.

## Known limitations of the artifact

- The 10,000-run tails of fresh workers, generic clones and warm processes
  come from a later session than the other three (`p99_extra.jsonl`). The
  paper compares pooled clones with warm processes only on the interleaved
  runs of one session.
- Each trace configuration was replayed once.
- The experiments listed as future work in Section 6 are not part of this
  artifact.
