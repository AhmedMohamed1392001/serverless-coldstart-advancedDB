PY ?= python3
SCALE ?= 1
RATE ?= 200
PICK ?= busiest

.PHONY: setup data data-small test bench bench-quick pool-replay pool-replay-azure all clean help

setup:            ## install pinned dependencies
	$(PY) -m pip install -r requirements.txt

data:             ## generate TPC-H Parquet at SCALE (default 1) into data/
	$(PY) -m coldstart.gen_data $(SCALE)

data-small:       ## SF0.1 dataset used by the tests
	$(PY) -m coldstart.gen_data 0.1

test: data-small  ## correctness tests (worker types agree with plain DuckDB, harness log format)
	$(PY) -m pytest -q tests

bench: data       ## C benchmark at SCALE: six worker types, bursts, catalog sizes, memory, isolation, 10k-activation tail (~20 min)
	$(PY) native/bench_native.py --scale $(SCALE) --p99

bench-quick: data-small  ## ~5 minute version at SF0.1
	$(PY) native/bench_native.py --quick

pool-replay:      ## bursty synthetic arrival trace against the pool controller (RATE mean req/s)
	$(PY) native/pool_replay.py --scale $(SCALE) --rate $(RATE) --seconds 30

pool-replay-azure: ## one hour of the Azure Functions 2021 trace (PICK=busiest|median|quietest), compressed 72x: AZURE=path/to/AzureFunctionsInvocationTraceForTwoWeeksJan2021.txt
	$(PY) native/pool_replay.py --scale $(SCALE) --rate $(RATE) --azure-window 3600 --azure-pick $(PICK) --azure-compress 72 --azure $(AZURE)

all:              ## everything in one go, see run_benchmarks.sh
	bash run_benchmarks.sh

clean:            ## remove caches and built binaries
	rm -rf .pytest_cache coldstart/__pycache__ tests/__pycache__ native/__pycache__
	rm -f native/coldbench native/density native/pool

help:
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/'
