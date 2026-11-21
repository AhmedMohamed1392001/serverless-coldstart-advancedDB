# Author changelog

"Sub-Millisecond Cold Starts for Serverless Analytics". Changes to the paper
and to the code, newest first. Dates are when the change was made.

## 2026-11-21. Artifact release

Code and artifact
- Added `tools/paper_numbers.py`, which recomputes Table 2, Table 3 and every
  number added in the revision from `results/milestone2`.
- Added `tools/paper_figures.py`, which redraws Figures 4 to 9 from the same
  files. The paper now uses these regenerated figures.
- Added `ARTIFACT.md` with the map from each table and figure to its raw
  records, the commands to rerun every experiment, and the expected variation.
- Checked the release with `./run_benchmarks.sh --quick` on a clean copy
  (see the release notes for the result).

Paper
- Figure 8b now includes the 5.6 MiB template in the pooled-clone line, as
  its caption and Section 5.4 already said. The earlier figure plotted the
  clones alone. No number in the text changed.
- Figures 4 to 9 are redrawn by the artifact script. The data are the same.

## 2026-11-20. Revision after the reviews of Paper 3

Paper
- Pooled clones and warm processes are now compared only on the interleaved
  runs of one session (point query 0.67 against 0.74 ms, bootstrap interval of
  the difference −0.14 to 0.01 ms, filter 0.97 against 0.86 ms). The
  cross-session tail comparison was removed from the abstract, introduction,
  Section 5.2 and conclusion.
- The abstract states that sub-millisecond activation assumes a warmed clone
  of a resident template is waiting, and that warm processes still complete
  1.8 times as many requests per second in large bursts.
- Section 5.1 describes the warm-process protocol. Section 5.2 interprets the
  generic clone, notes which queries each design had seen before the run, and
  gives the sample basis of the 99.9th percentiles. Table 2 labels the 180-run
  99th percentiles as indicative.
- The burst explanation in Section 5.2 was wrong. Faults that happen after a
  worker is ready cannot explain its activation tail. The sentence was
  replaced by a statement that the cause is not known.
- Section 5.3 estimates how the gain of a pooled clone over a prepared clone
  splits between skipping the fork and the warm-up, and says the split is
  inferred from fault counts.
- Section 5.4 states the 2 GB memory limit, why the table is loaded into
  memory, and why idle workers are reported as private memory.
- Section 5.6 adds a check of the simulator's refill time, a cross-hour
  prediction, the idle-time analysis from the quietest hour, and an
  equal-memory comparison of the sizing policies. The conclusion changed.
  Neither reactive policy beats a well-chosen fixed pool size.
- Section 6 adds the limits of the trace replay for sparse tenants, untested
  idle periods and template sizes, the CPU cost of spinning, the missing
  threaded baseline, the cost of replacing a template, and the untested file
  descriptor and spill paths.
- To stay within 12 pages, about 300 words of repeated text were removed,
  including the paragraph on the organization of the paper, and the wide
  figures were made slightly smaller.
- A response letter answers every comment of both reviewers.

Code
- The template in `coldbench.c`, `pool.c` and `density.c` reads its thread
  count from `/proc/self/status` before the first fork and refuses to fork
  unless it is one. The check runs once, so measured intervals are unchanged.

## 2026-11-02. Submission version

Paper
- Converted from the Word draft to the PVLDB template (acmart, sigconf).
  The body fits in 12 pages plus references.
- Two internal review passes, one acting as a systems reviewer and one as a
  data management reviewer, led to corrected memory accounting with the
  template included, the warm-up bias of the count query, end-to-end and
  99.9th-percentile tails, the serial forking in bursts, and a new Table 3.
- A final pass on wording removed stiff and repetitive phrasing. The paper
  has an AI disclosure before the references.
- The PVLDB reference block and the licence footnote were removed for the
  submission. The artifact link is kept.

Code
- The template moved into a separate single-threaded spawner process, so no
  clone is ever forked from a multithreaded process. The controller and the
  spawner spin instead of sleeping, to avoid slow wake-ups under WSL2.
- Trial code and superseded result folders were removed. The README
  describes the final system only. The final runs are in `results/milestone2`.
- New public repository `serverless-coldstart-advancedDB` with the final code
  and results.

## 2026-10-06 to 2026-11-01. Development

- 2026-11-01. One script runs every benchmark, /proc sampling, raw
  timestamps, p90 and throughput.
- 2026-10-20. Model-driven pool sizing and its replays, oldest-clone fix.
- 2026-10-18. Late hits, oldest-clone dispatch, busy-wait replay, threaded
  refill, memory-limit isolation test and Azure hour replays.
- 2026-10-17. Pool controller and trace replay.
- 2026-10-12. Memory density and isolation experiment (clones, processes,
  threads).
- 2026-10-10. C benchmark with six worker types, prepared and pooled clones,
  bursts, catalog sizes, memory, refill and 10,000-run tails.
- 2026-10-06. Python prototype, four worker types, selective clone, tests.
