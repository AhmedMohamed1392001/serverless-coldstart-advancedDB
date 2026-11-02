#!/usr/bin/env bash
# runs everything in one go: checks, tests, the C benchmark at each scale,
# memory/isolation, pool replays, and the plots. one folder per run.
#
#   ./run_benchmarks.sh                    # full run, SF 0.1 and 1 (~45 min on my laptop)
#   ./run_benchmarks.sh --quick            # ~5 min sanity run, SF 0.1 only
#   ./run_benchmarks.sh --scales "0.1 1 3" --azure ~/AzureFunctionsInvocationTraceForTwoWeeksJan2021.txt
#   ./run_benchmarks.sh --name milestone2 ...   # fixed folder name instead of run-<time>
#
# output: results/run-<time>/ with run.log, commands.txt, failures.txt and
# one sub folder per experiment (events.jsonl/csv, resources.csv, plots/, summary.md)
set -u
cd "$(dirname "$0")"

QUICK=0; SCALES="0.1 1"; AZURE=""; NAME=""; PY=${PY:-python3}
while [ $# -gt 0 ]; do
  case "$1" in
    --quick) QUICK=1; SCALES="0.1" ;;
    --scales) SCALES="$2"; shift ;;
    --azure) AZURE="$2"; shift ;;
    --name) NAME="$2"; shift ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "unknown option $1"; exit 2 ;;
  esac
  shift
done

RUN=results/${NAME:-run-$(date +%Y%m%d-%H%M%S)}
mkdir -p "$RUN"
LOG=$RUN/run.log; : > "$RUN/failures.txt"
echo "run dir: $RUN" | tee "$LOG"

# run one step: log the command, keep going if it fails but write it down
step() {
  local name=$1; shift
  echo "== $name: $*" | tee -a "$LOG"
  echo "$*" >> "$RUN/commands.txt"
  local t0=$(date +%s)
  if ! "$@" >> "$LOG" 2>&1; then
    echo "FAILED: $name ($*)" | tee -a "$LOG" "$RUN/failures.txt"
  fi
  echo "   took $(( $(date +%s) - t0 )) s" | tee -a "$LOG"
}

# sample /proc in the background while a step runs, into that step's folder
with_sysmon() {
  local dir=$1; shift
  mkdir -p "$dir"
  $PY tools/sysmon.py "$dir/resources.csv" --interval 0.2 &
  local mon=$!
  "$@"
  kill $mon 2>/dev/null; wait $mon 2>/dev/null
}

# ---- checks ----
for tool in gcc make "$PY"; do
  command -v "$tool" >/dev/null || { echo "missing: $tool" | tee -a "$LOG"; exit 1; }
done
$PY -c "import duckdb, pandas, numpy, matplotlib, pyarrow" 2>>"$LOG" \
  || { echo "python packages missing, run: pip install -r requirements.txt" | tee -a "$LOG"; exit 1; }
{ echo "host: $(uname -a)"; echo "cpus: $(nproc)"; echo "python: $($PY --version 2>&1)";
  echo "duckdb: $($PY -c 'import duckdb; print(duckdb.__version__)')"; echo "git: $(git rev-parse HEAD 2>/dev/null)";
  echo "scales: $SCALES  quick: $QUICK  azure: ${AZURE:-none}"; } | tee -a "$LOG" > "$RUN/env.txt"

# perf works on some kernels only (not on stock WSL2), so just record if it does
if command -v perf >/dev/null && perf stat -e task-clock true >/dev/null 2>&1; then PERF=1; else PERF=0
  echo "perf not usable on this kernel, using /proc samples only" | tee -a "$LOG" "$RUN/env.txt"; fi

# ---- tests ----
step tests make test

# ---- C benchmark per scale ----
for S in $SCALES; do
  step "data sf$S" make data SCALE="$S"
  D=$RUN/native-sf$S
  if [ $QUICK = 1 ]; then
    step "bench sf$S" with_sysmon "$D" $PY native/bench_native.py --quick --out "$D"
  else
    # the 10k-activation p99 part only at the biggest scale, it is slow
    EXTRA=""; [ "$S" = "${SCALES##* }" ] && EXTRA="--p99"
    step "bench sf$S" with_sysmon "$D" $PY native/bench_native.py --scale "$S" --out "$D" $EXTRA
  fi
  if [ $PERF = 1 ]; then
    step "perf sf$S" perf stat -e task-clock,context-switches,cpu-migrations,page-faults,cycles,instructions \
      -o "$D/perf_stat.txt" native/coldbench --data "data/tpch_sf$S" --mode clone_pooled --query point --conc 1 --reps 200
  fi
  step "plots sf$S" $PY native/plot_native.py "$D"
done

# ---- pool replays (sustained arrivals) ----
POOLS=""; SECS=30; [ $QUICK = 1 ] && { POOLS="--pools 0 2 8"; SECS=10; }
P=$RUN/pool-synthetic
step "pool synthetic" with_sysmon "$P" $PY native/pool_replay.py --scale "${SCALES##* }" --rate 200 --seconds $SECS $POOLS --out "$P"
if [ -n "$AZURE" ]; then
  for PICK in busiest quietest; do
    P=$RUN/pool-azure-$PICK
    step "pool azure $PICK" with_sysmon "$P" $PY native/pool_replay.py --scale "${SCALES##* }" --rate 200 \
      --azure-window 3600 --azure-pick $PICK --azure-compress 72 --azure "$AZURE" $POOLS --out "$P"
  done
fi

# ---- index ----
{ echo "# $RUN"; echo; cat "$RUN/env.txt"; echo;
  for f in "$RUN"/*/summary.md "$RUN"/*/pool_replay.md; do [ -f "$f" ] && { echo "## $f"; echo; cat "$f"; echo; }; done
  echo "## failures"; cat "$RUN/failures.txt"; } > "$RUN/index.md"

n=$(wc -l < "$RUN/failures.txt")
echo "done, $n failed steps, see $RUN/index.md" | tee -a "$LOG"
[ "$n" = 0 ]
