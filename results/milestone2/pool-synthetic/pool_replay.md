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
