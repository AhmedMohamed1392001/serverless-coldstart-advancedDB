/* pool controller for replaying arrival traces.
 *
 *   pool --data DIR --trace FILE --policy fixed|adaptive --pool K [--max-pool M] [--query point]
 *
 * Trace has one arrival time per line, ms from start.
 * Keep up to K warmed clones forked ahead of time. Idle clone means hit,
 * otherwise fork a prepared one on the spot (miss). Refill between arrivals,
 * one clone at a time.
 *
 * adaptive: estimate arrivals during one refill from recent rate, multiply
 * by safety factor. K stays in [1, max-pool]. Retire idle extras if target drops.
 *
 * model: every 250 ms, replay arrivals from last --window-ms using the same
 * simulation as the trace model. Refill thread and misses share the template,
 * refill cost is whatever we measured so far. Find smallest K with at most
 * 1 - --target requests missing a waiting clone. Use the largest K from
 * last --hold-ms as target. Quiet gaps shouldn't shrink it too early.
 *
 * Refill runs in a helper thread so dispatch doesn't wait on a fork.
 *
 * The template lives in its own process (the spawner), forked off before
 * the controller starts any thread. It is single threaded, so its children
 * can run duckdb safely. POSIX only promises async-signal-safe calls in a
 * child of a multithreaded process, so we never fork from the controller.
 * Controller asks for a clone over a unix socket, spawner forks it and
 * sends back the pid and the write end of the clone's pipe (SCM_RIGHTS).
 *
 * One JSON line per request, also pool-size samples.
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <math.h>
#include <unistd.h>
#include <signal.h>
#include <sys/wait.h>
#include <pthread.h>
#include <sys/socket.h>
#include <errno.h>
#include <sys/uio.h>
#include "duckdb.h"

static long long now_ns(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)ts.tv_sec * 1000000000LL + ts.tv_nsec;
}
static void sleep_until(long long t) {
    /* pure busy-wait here. In a real service arrivals wake the controller,
     * but sleeping during replay just adds error. WSL2 is annoying with this,
     * a 100 ms sleep can wake several ms late. Windows host timer is coarse
     * when nothing asks for finer resolution. Eats one core while replay runs.
     */
    while (now_ns() < t) {}
}
static long smaps_kb(const char *key) {
    FILE *f = fopen("/proc/self/smaps_rollup", "r"); if (!f) return -1;
    char line[256]; long v = -1; size_t k = strlen(key);
    while (fgets(line, sizeof line, f)) if (!strncmp(line, key, k)) { v = atol(line + k); break; }
    fclose(f); return v;
}
static void die(const char *w) { fprintf(stderr, "error: %s\n", w); exit(1); }
static void run(duckdb_connection con, const char *sql) {
    duckdb_result r;
    if (duckdb_query(con, sql, &r) == DuckDBError) { fprintf(stderr, "failed: %s\n%s\n", sql, duckdb_result_error(&r)); exit(1); }
    duckdb_destroy_result(&r);
}
static const char *TABLES[] = {"lineitem", "orders", "customer", "part", "supplier", "partsupp", "nation", "region"};
static const char *query_sql(const char *q) {
    if (!strcmp(q, "point")) return "SELECT n_nationkey FROM nation WHERE n_nationkey = 7";
    if (!strcmp(q, "count")) return "SELECT count(*) FROM region";
    if (!strcmp(q, "q6"))    return "SELECT sum(l_extendedprice * l_discount) FROM lineitem WHERE l_shipdate >= DATE '1994-01-01' AND l_shipdate < DATE '1995-01-01' AND l_discount BETWEEN 0.05 AND 0.07 AND l_quantity < 24";
    die("unknown query"); return NULL;
}

/* ---- one idle clone in the pool ---- */
typedef struct { pid_t pid; int fd; } slot_t;
static duckdb_database DB; static const char *QUERY; static int SEQ;
static int SPAWN_SOCK = -1; static long TEMPLATE_KB = -1;   /* controller side: socket to the spawner */

static void child_main(duckdb_connection con, int fd, int warm) {
    if (warm) { run(con, "SELECT 1"); run(con, "SELECT count(*) FROM region"); }
    long long t0, t_sched;                  /* dispatch time, scheduled arrival time (both ns) */
    if (read(fd, &t0, sizeof t0) != sizeof t0) _exit(1);
    if (read(fd, &t_sched, sizeof t_sched) != sizeof t_sched) _exit(1);
    long long tr = now_ns();
    duckdb_result r; duckdb_query(con, query_sql(QUERY), &r); duckdb_destroy_result(&r);
    long long td = now_ns();
    /* ready_us starts at scheduled arrival, includes waiting for controller.
     * dispatch_us only counts after dispatch
     */
    /* write(2), not printf, one line per request so lines from many clones don't mix */
    char line[512];
    int len = snprintf(line, sizeof line, "{\"kind\":\"req\",\"hit\":%d,\"ready_us\":%.1f,\"dispatch_us\":%.1f,\"done_us\":%.1f,\"queue_us\":%.1f,"
           "\"pid\":%d,\"t_sched_ns\":%lld,\"t_dispatch_ns\":%lld,\"t_ready_ns\":%lld,\"t_done_ns\":%lld}\n",
           warm, (tr - t_sched) / 1e3, (tr - t0) / 1e3, (td - t_sched) / 1e3, (t0 - t_sched) / 1e3,
           getpid(), t_sched, t0, tr, td);
    if (write(1, line, len) != len) _exit(1);
    _exit(0);
}

/* ---- spawner process: owns the template, forks clones on request ---- */
typedef struct { int warm, idx; } spawn_req;
typedef struct { pid_t pid; long template_kb; } spawn_rep;
static void spawner_main(const char *dir, int sock) {
    signal(SIGCHLD, SIG_IGN);                 /* clones are reaped by the kernel */
    duckdb_config cfg; duckdb_create_config(&cfg);
    duckdb_set_config(cfg, "threads", "1"); duckdb_set_config(cfg, "memory_limit", "512MB");
    duckdb_set_config(cfg, "enable_object_cache", "true");
    char *err = NULL; if (duckdb_open_ext(NULL, &DB, cfg, &err) == DuckDBError) { fprintf(stderr, "%s\n", err); _exit(1); }
    duckdb_connection c0; duckdb_connect(DB, &c0);
    char sql[1024];
    for (int i = 0; i < 8; i++) {
        snprintf(sql, sizeof sql, "CREATE VIEW %s AS SELECT * FROM read_parquet('%s/%s.parquet')", TABLES[i], dir, TABLES[i]);
        run(c0, sql);
    }
    run(c0, query_sql(QUERY));
    long tkb = smaps_kb("Private_Dirty:"); int nspawn = 0;
    spawn_req q;
    for (;;) {
        /* spin on the socket instead of sleeping in read(). On WSL2 a wakeup
         * from a blocking read can take a ms or more when the core is idle,
         * same timer problem as in sleep_until. Eats one core while it runs. */
        ssize_t got;
        while ((got = recv(sock, &q, sizeof q, MSG_DONTWAIT)) < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {}
        if (got != sizeof q) break;
        /* warm=1 warms up in the child then waits in the pool.
         * warm=0 uses the connection prepared here and runs at once (miss) */
        duckdb_connection con; if (duckdb_connect(DB, &con) == DuckDBError) die("connect");
        snprintf(sql, sizeof sql, "SET temp_directory = '/tmp/pool-%d'", q.idx);
        run(con, sql);
        int pfd[2]; if (pipe(pfd)) die("pipe");
        pid_t pid = fork();
        if (pid == 0) { close(sock); close(pfd[1]); child_main(con, pfd[0], q.warm); }
        close(pfd[0]);
        duckdb_disconnect(&con);
        if (++nspawn % 1024 == 0) tkb = smaps_kb("Private_Dirty:");   /* /proc read is not free, don't do it per clone */
        spawn_rep rep = {pid, tkb};
        struct iovec io = {&rep, sizeof rep};
        char cbuf[CMSG_SPACE(sizeof(int))]; memset(cbuf, 0, sizeof cbuf);
        struct msghdr m = {0}; m.msg_iov = &io; m.msg_iovlen = 1; m.msg_control = cbuf; m.msg_controllen = sizeof cbuf;
        struct cmsghdr *c = CMSG_FIRSTHDR(&m); c->cmsg_level = SOL_SOCKET; c->cmsg_type = SCM_RIGHTS; c->cmsg_len = CMSG_LEN(sizeof(int));
        memcpy(CMSG_DATA(c), &pfd[1], sizeof(int));
        if (sendmsg(sock, &m, 0) < 0) die("sendmsg");
        close(pfd[1]);
    }
    _exit(0);
}

/* controller side: ask the spawner for a clone, get back its pid and pipe */
static slot_t spawn(int warm, int idx) {
    spawn_req q = {warm, idx};
    if (write(SPAWN_SOCK, &q, sizeof q) != sizeof q) die("spawn request");
    spawn_rep rep; struct iovec io = {&rep, sizeof rep};
    char cbuf[CMSG_SPACE(sizeof(int))];
    struct msghdr m = {0}; m.msg_iov = &io; m.msg_iovlen = 1; m.msg_control = cbuf; m.msg_controllen = sizeof cbuf;
    ssize_t got;
    while ((got = recvmsg(SPAWN_SOCK, &m, MSG_DONTWAIT)) < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {}   /* spin, see spawner */
    if (got != sizeof rep) die("spawn reply");
    struct cmsghdr *c = CMSG_FIRSTHDR(&m); if (!c || c->cmsg_type != SCM_RIGHTS) die("no fd from spawner");
    int fd; memcpy(&fd, CMSG_DATA(c), sizeof fd);
    TEMPLATE_KB = rep.template_kb;
    slot_t s = {rep.pid, fd}; return s;
}
static void dispatch(slot_t s, long long t0, long long t_arr) {
    if (write(s.fd, &t0, sizeof t0) != sizeof t0 || write(s.fd, &t_arr, sizeof t_arr) != sizeof t_arr) die("write");
    close(s.fd);
}
static void reap(void) { while (waitpid(-1, NULL, WNOHANG) > 0) {} }
static double spawn_total_us = 0; static int spawn_n = 0;   /* template-side cost of a refill */

/* the pool, shared between the dispatch loop and the refill thread */
static slot_t *POOL; static int NPOOL = 0, TARGET, KMAX_, REFILLS = 0, STOP = 0;
static pthread_mutex_t mu = PTHREAD_MUTEX_INITIALIZER;   /* protects the pool */
static pthread_mutex_t spawn_mu = PTHREAD_MUTEX_INITIALIZER; /* one request at a time on the spawner socket */
static pthread_cond_t cv = PTHREAD_COND_INITIALIZER;
static pthread_cond_t filled = PTHREAD_COND_INITIALIZER;  /* a refill just finished */
static int REFILLING = 0;                  /* the refill thread is forking right now */
static void *refill_main(void *arg) {
    (void)arg;
    for (;;) {
        pthread_mutex_lock(&mu);
        while (!STOP && (NPOOL >= TARGET || NPOOL >= KMAX_)) pthread_cond_wait(&cv, &mu);
        if (STOP) { pthread_mutex_unlock(&mu); return NULL; }
        REFILLING = 1;
        pthread_mutex_unlock(&mu);
        long long ts = now_ns();
        pthread_mutex_lock(&spawn_mu); slot_t s = spawn(1, __sync_fetch_and_add(&SEQ, 1)); pthread_mutex_unlock(&spawn_mu);
        pthread_mutex_lock(&mu);
        spawn_total_us += (now_ns() - ts) / 1e3; spawn_n++; REFILLS++;
        if (NPOOL < KMAX_) POOL[NPOOL++] = s; else { kill(s.pid, SIGKILL); close(s.fd); }
        REFILLING = 0; pthread_cond_broadcast(&filled);
        pthread_mutex_unlock(&mu);
    }
}

/* ---- the controller model, for --policy model ---- */
/* how many requests in t[0..n) miss a waiting clone with K clones,
 * as a fraction. Same logic as simulate() in pool_replay.py, threaded mode
 */
static double sim_not_instant(const long long *t, int n, int K, double refill_ns, double miss_ns) {
    if (n == 0) return 0;
    if (K == 0) return 1;
    int pool = K, bad = 0; double engine_free = 0, busy_end = -1;
    for (int i = 0; i < n; i++) {
        double ti = (double)t[i];
        if (engine_free == 0) engine_free = ti;
        while (busy_end >= 0 && busy_end <= ti) {
            pool++; engine_free = busy_end; busy_end = -1;
            if (pool < K) busy_end = engine_free + refill_ns;
        }
        if (pool > 0) pool--;
        else if (busy_end >= 0) { bad++; engine_free = busy_end; busy_end = -1; }
        else { bad++; engine_free = (engine_free > ti ? engine_free : ti) + miss_ns; }
        if (busy_end < 0 && pool < K) busy_end = (engine_free > ti ? engine_free : ti) + refill_ns;
    }
    return (double)bad / n;
}
/* smallest K in [1, kmax] meeting the target; not_instant falls as K grows, so binary search */
static int model_pick(const long long *t, int n, int kmax, double target, double refill_ns, double miss_ns) {
    int lo = 1, hi = kmax;
    if (sim_not_instant(t, n, hi, refill_ns, miss_ns) > 1 - target) return kmax;
    while (lo < hi) {
        int mid = (lo + hi) / 2;
        if (sim_not_instant(t, n, mid, refill_ns, miss_ns) <= 1 - target) hi = mid; else lo = mid + 1;
    }
    return lo;
}

int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IOLBF, 0);
    signal(SIGPIPE, SIG_IGN);
    const char *dir = NULL, *trace = NULL, *policy = "fixed"; int K = 4, KMAX = 64; QUERY = "point";
    double safety = 2.0;
    double target_frac = 0.995; long long win_ns = 5000000000LL, hold_ns = 20000000000LL;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--data")) dir = argv[++i];
        else if (!strcmp(argv[i], "--trace")) trace = argv[++i];
        else if (!strcmp(argv[i], "--policy")) policy = argv[++i];
        else if (!strcmp(argv[i], "--pool")) K = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--max-pool")) KMAX = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--query")) QUERY = argv[++i];
        else if (!strcmp(argv[i], "--safety")) safety = atof(argv[++i]);
        else if (!strcmp(argv[i], "--target")) target_frac = atof(argv[++i]);
        else if (!strcmp(argv[i], "--window-ms")) win_ns = atoll(argv[++i]) * 1000000LL;
        else if (!strcmp(argv[i], "--hold-ms")) hold_ns = atoll(argv[++i]) * 1000000LL;
    }
    if (!dir || !trace) die("--data and --trace required");
    int adaptive = !strcmp(policy, "adaptive"), modelp = !strcmp(policy, "model");

    /* arrivals */
    FILE *tf = fopen(trace, "r"); if (!tf) die("trace");
    int cap = 1 << 16, n = 0; long long *arr = malloc(cap * sizeof *arr);
    double v;
    while (fscanf(tf, "%lf", &v) == 1) { if (n == cap) { cap *= 2; arr = realloc(arr, cap * sizeof *arr); } arr[n++] = (long long)(v * 1000000.0); }   /* ms -> ns */
    fclose(tf);

    /* template, in its own single-threaded process, started before any thread */
    int sv[2]; if (socketpair(AF_UNIX, SOCK_STREAM, 0, sv)) die("socketpair");
    pid_t spawner = fork();
    if (spawner == 0) { close(sv[0]); spawner_main(dir, sv[1]); }
    close(sv[1]); SPAWN_SOCK = sv[0];

    KMAX_ = KMAX > 0 ? KMAX : 1; POOL = malloc(KMAX_ * sizeof *POOL); TARGET = K;
    for (int i = 0; i < TARGET && i < KMAX_; i++) POOL[NPOOL++] = spawn(1, SEQ++);
    usleep(20000);
    pthread_t refiller; pthread_create(&refiller, NULL, refill_main, NULL);

    /* rate estimate for the adaptive policy: arrivals in the last window */
    const long long WINDOW = 100000000LL;           /* 100 ms rate windows */
    const double REFILL_MS = 2.5;                    /* measured refill cost */
    int win_count = 0; long long win_start = now_ns();
    double peak[50] = {0}; int pk = 0;               /* per-100ms counts over the last 5 s */
    long long t_begin = now_ns(), last_sample = t_begin;
    int hits = 0, late_hits = 0, misses = 0; double pool_sum = 0; int samples = 0;
    /* model policy state: recent arrival times, and the K picked at each decision */
    long long next_decide = t_begin + 250000000LL; int dec_k[1024]; long long dec_t[1024]; int ndec = 0;
    double decide_total_us = 0; int decide_n = 0, wstart = 0;

    for (int i = 0; i < n; i++) {
        long long t_arr = t_begin + arr[i];
        /* retire extras if the adaptive target dropped */
        pthread_mutex_lock(&mu);
        while (NPOOL > TARGET && NPOOL > 1 && t_arr - now_ns() > 500000LL) {
            slot_t s = POOL[--NPOOL]; kill(s.pid, SIGKILL); close(s.fd);
        }
        pthread_mutex_unlock(&mu);
        reap();
        sleep_until(t_arr);
        long long t0 = now_ns();
        pthread_mutex_lock(&mu);
        /* pool empty but refill is halfway done. Take that clone when ready,
         * no point waiting behind it just to fork another one
         */
        int waited = 0;
        while (NPOOL == 0 && REFILLING) { pthread_cond_wait(&filled, &mu); waited = 1; }
        /* take the OLDEST idle clone. Newest one might still be running
         * warm-up queries after fork, so safer to leave it
         */
        slot_t s; int have = NPOOL > 0;
        if (have) { s = POOL[0]; memmove(POOL, POOL + 1, (NPOOL - 1) * sizeof *POOL); NPOOL--; }
        pthread_mutex_unlock(&mu);
        if (have) { dispatch(s, t0, t_arr); if (waited) late_hits++; else hits++; }
        else {
            pthread_mutex_lock(&spawn_mu); s = spawn(0, __sync_fetch_and_add(&SEQ, 1)); pthread_mutex_unlock(&spawn_mu);
            dispatch(s, t0, t_arr); misses++;
        }
        pthread_cond_signal(&cv);   /* a slot just opened */

        if (adaptive) {
            win_count++;
            if (t0 - win_start >= WINDOW) {
                peak[pk++ % 50] = win_count / ((t0 - win_start) / 1e6);
                double mx = 0; for (int j = 0; j < 50; j++) if (peak[j] > mx) mx = peak[j];
                int want = (int)ceil(mx * REFILL_MS * safety) + 1;   /* cover the recent peak */
                if (want < 1) want = 1;
                if (want > KMAX_) want = KMAX_;
                pthread_mutex_lock(&mu); TARGET = want; pthread_mutex_unlock(&mu);
                pthread_cond_signal(&cv);
                win_count = 0; win_start = t0;
            }
        }
        if (modelp && t0 >= next_decide) {
            long long td = now_ns();
            while (wstart < i && arr[wstart] < (t_arr - t_begin) - win_ns) wstart++;
            double refill_ns = spawn_n ? spawn_total_us / spawn_n * 1000.0 : 1500000.0;
            int want = model_pick(arr + wstart, i + 1 - wstart, KMAX_, target_frac, refill_ns, refill_ns);
            dec_k[ndec % 1024] = want; dec_t[ndec % 1024] = t0; ndec++;
            int hold = 1;
            for (int j = 0; j < ndec && j < 1024; j++) if (dec_t[j] >= t0 - hold_ns && dec_k[j] > hold) hold = dec_k[j];
            pthread_mutex_lock(&mu); TARGET = hold; pthread_mutex_unlock(&mu);
            pthread_cond_signal(&cv);
            decide_total_us += (now_ns() - td) / 1e3; decide_n++;
            next_decide = t0 + 250000000LL;
        }
        if (t0 - last_sample > 100000000LL) {       /* pool size sample every 100 ms */
            printf("{\"kind\":\"pool\",\"t_us\":%.0f,\"size\":%d,\"target\":%d}\n", (t0 - t_begin) / 1e3, NPOOL, TARGET);
            pool_sum += NPOOL; samples++; last_sample = t0;
        }
    }
    usleep(50000); reap();
    pthread_mutex_lock(&mu); STOP = 1; pthread_cond_signal(&cv); pthread_mutex_unlock(&mu);
    pthread_join(refiller, NULL);
    for (int i = 0; i < NPOOL; i++) { kill(POOL[i].pid, SIGKILL); close(POOL[i].fd); }
    close(SPAWN_SOCK); waitpid(spawner, NULL, 0);
    printf("{\"kind\":\"summary\",\"policy\":\"%s\",\"pool\":%d,\"max_pool\":%d,\"requests\":%d,\"hits\":%d,\"late_hits\":%d,\"misses\":%d,"
           "\"refills\":%d,\"avg_pool\":%.2f,\"template_private_kb\":%ld,\"duration_s\":%.2f,\"spawn_us\":%.1f,\"refill\":\"%s\",\"decide_us\":%.1f}\n",
           policy, K, KMAX, n, hits, late_hits, misses, REFILLS, samples ? pool_sum / samples : (double)NPOOL,
           TEMPLATE_KB, (now_ns() - t_begin) / 1e9, spawn_n ? spawn_total_us / spawn_n : 0.0,
           "spawner", decide_n ? decide_total_us / decide_n : 0.0);
    return 0;
}
