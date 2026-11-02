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
