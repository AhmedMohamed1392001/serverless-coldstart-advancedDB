# results/milestone2

host: Linux Ahmed 6.6.114.1-microsoft-standard-WSL2 #1 SMP PREEMPT_DYNAMIC Mon Dec  1 20:46:23 UTC 2025 x86_64 x86_64 x86_64 GNU/Linux
cpus: 16
python: Python 3.12.3
duckdb: 1.5.6
scales: 0.1 1  quick: 0  azure: /home/ahmed/AzureFunctionsInvocationTraceForTwoWeeksJan2021.txt
perf not usable on this kernel, using /proc samples only

p99_extra.jsonl holds the 10,000-activation runs (point query, one at a time, SF1) for fresh, generic clone and warm.

## results/milestone2/native-sf0.1/summary.md

Summary for native-sf0.1

AMD Ryzen 9 8945HX with Radeon Graphics (16 CPUs visible), kernel 6.6.114.1-microsoft-standard-WSL2, DuckDB 1.5.6

Activation and end to end time, short queries (point, count, filter), ms.

fresh            conc   1  n   180  ready p50  14.71  p90  16.23  p95  17.18  p99  18.56   done p50  15.31   faults 1057+  34
fresh            conc   8  n   360  ready p50  16.42  p90  17.42  p95  18.06  p99  20.06   done p50  16.96   faults 1104+  38
fresh            conc  32  n  1440  ready p50  32.37  p90  39.82  p95  41.27  p99  43.95   done p50  33.39   faults 1058+  34
generic clone    conc   1  n   180  ready p50   1.32  p90   1.55  p95   1.60  p99   1.68   done p50   2.27   faults  227+ 194
generic clone    conc   8  n   360  ready p50   2.04  p90   2.90  p95   3.12  p99   3.36   done p50   3.10   faults  227+ 194
generic clone    conc  32  n  1440  ready p50   4.94  p90   8.59  p95   9.45  p99  13.75   done p50   5.96   faults  227+ 194
selective        conc   1  n   180  ready p50   1.31  p90   1.58  p95   1.63  p99   1.71   done p50   2.20   faults  232+ 194
selective        conc   8  n   360  ready p50   2.03  p90   2.84  p95   2.99  p99   3.33   done p50   2.94   faults  232+ 195
selective        conc  32  n  1440  ready p50   4.82  p90   8.70  p95   9.53  p99  11.00   done p50   5.84   faults  232+ 194
prepared         conc   1  n   180  ready p50   0.67  p90   0.79  p95   0.83  p99   0.93   done p50   1.98   faults    5+ 410
prepared         conc   8  n   360  ready p50   1.22  p90   1.89  p95   1.96  p99   2.18   done p50   2.71   faults    5+ 410
prepared         conc  32  n  1440  ready p50   3.70  p90   7.20  p95   7.69  p99   8.49   done p50   5.32   faults    5+ 437
pooled           conc   1  n   180  ready p50   0.09  p90   0.21  p95   0.25  p99   0.31   done p50   0.69   faults    1+  52
pooled           conc   8  n   360  ready p50   0.17  p90   0.31  p95   0.35  p99   0.40   done p50   0.95   faults    1+  52
pooled           conc  32  n  1440  ready p50   0.73  p90   3.01  p95   3.26  p99   4.00   done p50   1.80   faults    1+  52
warm             conc   1  n   180  ready p50   0.12  p90   0.16  p95   0.17  p99   0.21   done p50   0.68   faults    0+   0
warm             conc   8  n   360  ready p50   0.25  p90   0.38  p95   0.41  p99   0.45   done p50   1.06   faults    0+   0
warm             conc  32  n  1440  ready p50   1.00  p90   1.69  p95   1.85  p99   3.36   done p50   1.51   faults    0+   0

Burst throughput, short queries, completed requests/s (median over bursts):
fresh            conc 1: 65  conc 8: 446  conc 32: 743
generic clone    conc 1: 441  conc 8: 1,914  conc 32: 3,106
selective        conc 1: 454  conc 8: 1,954  conc 32: 3,036
prepared         conc 1: 506  conc 8: 2,086  conc 32: 3,314
pooled           conc 1: 1,441  conc 8: 6,589  conc 32: 7,297
warm             conc 1: 1,463  conc 8: 6,564  conc 32: 13,288

Memory, MiB private dirty: 1 pooled = 1.4, 8 pooled = 6.3, 32 pooled = 23.0, 64 pooled = 45.4
One idle warm worker process = 4.5 MiB; one idle pooled clone = 0.70 MiB.
Pool refill (fork + warm-up of one replacement clone): median 2.34 ms, p95 3.53 ms.

Memory for N concurrent workers running Q6 on an in-memory lineitem (total PSS, MiB):
clones of one template   N=1: 145  N=2: 147  N=4: 150  N=8: 157  N=16: 169  N=32: 194
separate processes       N=1: 137  N=2: 253  N=4: 481  N=8: 937
threads in one process   N=1: 144  N=2: 194  N=4: 217  N=8: 254  N=16: 260  N=32: 263

Isolation: worker 2 of 8 killed (SIGKILL) mid-query; queries that still completed:
clones of one template   7 of 8
separate processes       7 of 8
threads in one process   0 of 8  (the whole process died)

Isolation: worker 2 of 8 allocates memory until its limit stops it; queries that still completed:
clones of one template   7 of 8
separate processes       7 of 8
threads in one process   0 of 8  (the whole process died)

Resources over the run (1318 samples): CPU busy mean 5%, peak 72%; context switches mean 4,468/s; memory in use peak 2.5 GiB; major page faults 826.

Result check (distinct first values per query across all modes, 1 = all agree): count=1, filter=1, point=1, q1=1, q6=1

## results/milestone2/native-sf1/summary.md

Summary for native-sf1

AMD Ryzen 9 8945HX with Radeon Graphics (16 CPUs visible), kernel 6.6.114.1-microsoft-standard-WSL2, DuckDB 1.5.6

Activation and end to end time, short queries (point, count, filter), ms.

fresh            conc   1  n   180  ready p50  16.25  p90  17.21  p95  17.67  p99  18.43   done p50  16.85   faults 1258+  34
fresh            conc   8  n   360  ready p50  17.77  p90  18.56  p95  18.89  p99  19.71   done p50  18.48   faults 1307+  38
fresh            conc  32  n  1440  ready p50  35.82  p90  44.09  p95  45.89  p99  48.81   done p50  36.93   faults 1259+  34
generic clone    conc   1  n   180  ready p50   1.28  p90   1.52  p95   1.57  p99   1.64   done p50   2.26   faults  223+ 197
generic clone    conc   8  n   360  ready p50   2.15  p90   3.04  p95   3.18  p99   3.44   done p50   3.15   faults  223+ 197
generic clone    conc  32  n  1440  ready p50   4.80  p90   8.61  p95   9.30  p99  10.25   done p50   5.89   faults  223+ 197
selective        conc   1  n   180  ready p50   1.32  p90   1.59  p95   1.64  p99   1.71   done p50   2.24   faults  233+ 195
selective        conc   8  n   360  ready p50   2.15  p90   2.99  p95   3.17  p99   3.48   done p50   3.09   faults  233+ 195
selective        conc  32  n  1440  ready p50   4.88  p90   8.57  p95   9.24  p99  10.66   done p50   6.00   faults  233+ 195
prepared         conc   1  n   180  ready p50   0.67  p90   0.76  p95   0.81  p99   0.87   done p50   2.08   faults    5+ 412
prepared         conc   8  n   360  ready p50   1.29  p90   1.93  p95   2.05  p99   2.26   done p50   2.84   faults    5+ 413
prepared         conc  32  n  1440  ready p50   3.89  p90   7.69  p95   8.39  p99   9.25   done p50   5.55   faults    5+ 438
pooled           conc   1  n   180  ready p50   0.10  p90   0.22  p95   0.24  p99   0.36   done p50   0.72   faults    1+  51
pooled           conc   8  n   360  ready p50   0.17  p90   0.32  p95   0.36  p99   0.40   done p50   1.08   faults    1+  51
pooled           conc  32  n  1440  ready p50   0.90  p90   3.26  p95   3.53  p99   4.64   done p50   2.02   faults    1+  51
warm             conc   1  n   180  ready p50   0.12  p90   0.16  p95   0.17  p99   0.21   done p50   0.70   faults    0+   0
warm             conc   8  n   360  ready p50   0.25  p90   0.37  p95   0.41  p99   0.49   done p50   1.07   faults    0+   0
warm             conc  32  n  1440  ready p50   0.94  p90   1.83  p95   1.97  p99   2.67   done p50   1.61   faults    0+   0

Burst throughput, short queries, completed requests/s (median over bursts):
fresh            conc 1: 59  conc 8: 415  conc 32: 672
generic clone    conc 1: 442  conc 8: 1,829  conc 32: 2,968
selective        conc 1: 446  conc 8: 1,841  conc 32: 3,126
prepared         conc 1: 481  conc 8: 1,989  conc 32: 3,208
pooled           conc 1: 1,392  conc 8: 5,948  conc 32: 6,757
warm             conc 1: 1,429  conc 8: 6,583  conc 32: 11,974

Memory, MiB private dirty: 1 pooled = 1.4, 8 pooled = 6.4, 32 pooled = 23.7, 64 pooled = 46.4
One idle warm worker process = 5.7 MiB; one idle pooled clone = 0.71 MiB.
Pool refill (fork + warm-up of one replacement clone): median 2.23 ms, p95 2.75 ms.

10,000 activations, point query, one at a time:
pooled           p50 0.096  p99 0.334  upper 95% bound on p99 0.338 ms  -> under 1 ms
prepared         p50 0.652  p99 0.850  upper 95% bound on p99 0.858 ms  -> under 1 ms
selective        p50 1.303  p99 1.769  upper 95% bound on p99 1.819 ms  -> not under 1 ms

Memory for N concurrent workers running Q6 on an in-memory lineitem (total PSS, MiB):
clones of one template   N=1: 1095  N=2: 1098  N=4: 1105  N=8: 1122  N=16: 1154  N=32: 1216
separate processes       N=1: 1083  N=2: 2143  N=4: 4265  N=8: 8510
threads in one process   N=1: 1091  N=2: 1127  N=4: 1157  N=8: 1221  N=16: 1248  N=32: 1273

Isolation: worker 2 of 8 killed (SIGKILL) mid-query; queries that still completed:
clones of one template   7 of 8
separate processes       7 of 8
threads in one process   0 of 8  (the whole process died)

Isolation: worker 2 of 8 allocates memory until its limit stops it; queries that still completed:
clones of one template   7 of 8
separate processes       7 of 8
threads in one process   0 of 8  (the whole process died)

Resources over the run (3430 samples): CPU busy mean 8%, peak 100%; context switches mean 4,024/s; memory in use peak 9.9 GiB; major page faults 48.

Result check (distinct first values per query across all modes, 1 = all agree): count=1, filter=1, point=1, q1=1, q6=1

## results/milestone2/pool-azure-busiest/pool_replay.md

Pool replay: Azure Functions 2021 trace, busiest 1.0 h window of day 1 (starts at 2.3 h, 2.78/s raw): 10014 invocations, time compressed 72x to 200/s (50 s replay)
mean rate 200/s, peak (100 ms) 680/s, 10014 requests
refill: helper thread

latency is from the scheduled arrival (includes controller queueing); 'after dispatch' is the worker part only

'hit' = a waiting clone was there; 'late' = the pool was empty and the request took the clone being made
adaptive = rate rule (recent 100 ms peak x refill time x 2); model = picks K with the trace model on the last 5 s, held for 20 s

policy     pool   hit rate   late   p50 ms   p99 ms   max ms   after dispatch p99   avg clones   memory MiB   | model hit   model late   Poisson miss
fixed         0      0.0%   0.0%     0.48     3.29     9.01                 0.77         0.0         0.0   |      0.0%        0.0%        100.0%
fixed         1     81.9%  12.2%     0.05     3.55    10.98                 2.07         0.0         0.0   |     82.2%       17.8%         38.2%
fixed         2     95.5%   4.2%     0.04     3.53     8.46                 1.96         1.0         0.7   |     95.7%        4.3%          8.4%
fixed         4     98.5%   1.5%     0.04     2.98    13.76                 1.71         3.0         2.1   |     98.6%        1.4%          0.2%
fixed         8     99.3%   0.7%     0.05     0.19     6.77                 0.19         7.0         4.9   |     99.3%        0.7%          0.0%
fixed        16    100.0%   0.0%     0.05     0.15     2.71                 0.14        15.0        10.5   |    100.0%        0.0%          0.0%
fixed        32    100.0%   0.0%     0.05     0.16     2.39                 0.14        31.0        21.7   |    100.0%        0.0%          0.0%
adaptive   auto     98.4%   1.6%     0.05     2.87     8.38                 1.80         2.8         1.9   |         -           -             -
model      auto     99.6%   0.3%     0.05     0.16     4.92                 0.14        10.5         7.4   |         -           -             -

## results/milestone2/pool-azure-quietest/pool_replay.md

Pool replay: Azure Functions 2021 trace, quietest 1.0 h window of day 1 (starts at 13.8 h, 0.12/s raw): 429 invocations, time compressed 72x to 9/s (50 s replay)
mean rate 9/s, peak (100 ms) 200/s, 429 requests
refill: helper thread

latency is from the scheduled arrival (includes controller queueing); 'after dispatch' is the worker part only

'hit' = a waiting clone was there; 'late' = the pool was empty and the request took the clone being made
adaptive = rate rule (recent 100 ms peak x refill time x 2); model = picks K with the trace model on the last 5 s, held for 20 s

policy     pool   hit rate   late   p50 ms   p99 ms   max ms   after dispatch p99   avg clones   memory MiB   | model hit   model late   Poisson miss
fixed         0      0.0%   0.0%     0.92     7.82     8.64                 2.21         0.0         0.0   |      0.0%        0.0%        100.0%
fixed         1     58.3%  21.9%     0.08     9.15    10.23                 2.33         0.0         0.0   |     57.8%       42.2%          2.0%
fixed         2     66.2%  33.1%     0.07     7.69     8.11                 2.57         1.0         0.7   |     66.2%       33.8%          0.0%
fixed         4     73.9%  26.1%     0.07     7.35    10.15                 3.00         3.0         2.1   |     73.7%       26.3%          0.0%
fixed         8     88.6%  11.4%     0.07     5.65     6.78                 2.66         7.0         4.9   |     88.3%       11.7%          0.0%
fixed        16    100.0%   0.0%     0.07     1.76     2.05                 1.53        15.0        10.5   |    100.0%        0.0%          0.0%
fixed        32    100.0%   0.0%     0.08     1.39     2.01                 1.26        31.0        21.7   |    100.0%        0.0%          0.0%
adaptive   auto     66.0%  31.5%     0.07     8.29     8.86                 2.68         1.0         0.7   |         -           -             -
model      auto     95.1%   3.5%     0.08     4.29     6.15                 2.07        14.2         9.9   |         -           -             -

## results/milestone2/pool-synthetic/pool_replay.md

Pool replay: synthetic: Poisson 120/s with 0.5 s bursts at 1200/s every 5 s
mean rate 225/s, peak (100 ms) 1340/s, 6754 requests
refill: helper thread

latency is from the scheduled arrival (includes controller queueing); 'after dispatch' is the worker part only

'hit' = a waiting clone was there; 'late' = the pool was empty and the request took the clone being made
adaptive = rate rule (recent 100 ms peak x refill time x 2); model = picks K with the trace model on the last 5 s, held for 20 s

policy     pool   hit rate   late   p50 ms   p99 ms   max ms   after dispatch p99   avg clones   memory MiB   | model hit   model late   Poisson miss
fixed         0      0.0%   0.0%     0.50     2.48     4.49                 0.72         0.0         0.0   |      0.0%        0.0%        100.0%
fixed         1     67.3%  22.7%     0.56     3.02     5.22                 2.26         0.0         0.0   |     67.0%       33.0%         41.7%
fixed         2     87.2%  12.7%     0.05     3.03     6.79                 2.24         1.0         0.7   |     89.4%       10.6%         10.3%
fixed         4     98.3%   1.7%     0.05     1.98     3.34                 1.91         3.0         2.1   |     98.9%        1.1%          0.2%
fixed         8    100.0%   0.0%     0.05     0.14     2.18                 0.14         7.0         4.9   |    100.0%        0.0%          0.0%
fixed        16    100.0%   0.0%     0.05     0.12     0.56                 0.12        15.0        10.5   |    100.0%        0.0%          0.0%
fixed        32    100.0%   0.0%     0.05     0.13     2.78                 0.13        31.0        21.7   |    100.0%        0.0%          0.0%
adaptive   auto     98.6%   1.1%     0.05     1.51     3.94                 1.48         6.9         4.9   |         -           -             -
model      auto     97.4%   1.8%     0.05     1.71     3.79                 1.58         6.3         4.4   |         -           -             -

## failures
