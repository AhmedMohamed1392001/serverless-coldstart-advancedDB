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
