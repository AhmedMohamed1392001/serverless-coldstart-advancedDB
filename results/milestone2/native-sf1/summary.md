Summary for native-sf1

AMD Ryzen 9 8945HX with Radeon Graphics (16 CPUs visible), kernel 6.6.114.1-microsoft-standard-WSL2, DuckDB 1.5.6, git a5fb88cfb6

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
