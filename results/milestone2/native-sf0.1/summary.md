Summary for native-sf0.1

AMD Ryzen 9 8945HX with Radeon Graphics (16 CPUs visible), kernel 6.6.114.1-microsoft-standard-WSL2, DuckDB 1.5.6, git a5fb88cfb6

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
