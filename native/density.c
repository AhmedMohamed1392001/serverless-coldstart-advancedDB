/* memory and speed with N workers running together
 *
 *   density --data DIR --impl clone|procs|threads --workers N --query q6 [--kill K]
 *
 * clone: template runs the query once first, so file cache is warm.
 * Then fork N clones. Memory is shared copy-on-write.
 * procs: N separate processes, own engine and warm cache each.
 * Basically the cost of keeping N warm workers around.
 * threads: one process with N connections on N threads. Memory shared,
 * but no isolation if something goes wrong.
 *
 * --kill K: send SIGKILL to worker K while it's running, check the others.
 * --hog: with --kill K, worker K keeps allocating memory until it hits
 * the per-worker address-space limit and aborts. Trying to imitate a
 * runaway query. Limit is per process though, so threads share it across
 * all N workers.
 *
 * Memory = sum of PSS for all involved processes. Shared pages only count
 * once in the total. JSON per worker, then one summary line.
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <signal.h>
#include <pthread.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include "duckdb.h"

static long long now_ns(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)ts.tv_sec * 1000000000LL + ts.tv_nsec;
}
static long smaps_kb_of(pid_t pid, const char *key) {
    char path[64]; snprintf(path, sizeof path, "/proc/%d/smaps_rollup", pid);
    FILE *f = fopen(path, "r"); if (!f) return -1;
    char line[256]; long v = -1; size_t k = strlen(key);
    while (fgets(line, sizeof line, f)) if (!strncmp(line, key, k)) { v = atol(line + k); break; }
    fclose(f); return v;
}
static void die(const char *w) { fprintf(stderr, "error: %s\n", w); exit(1); }

static const char *TABLES[] = {"lineitem", "orders", "customer", "part", "supplier", "partsupp", "nation", "region"};
static const char *query_sql(const char *q) {
    if (!strcmp(q, "point")) return "SELECT n_nationkey FROM nation WHERE n_nationkey = 7";
    if (!strcmp(q, "q6"))    return "SELECT sum(l_extendedprice * l_discount) FROM lineitem WHERE l_shipdate >= DATE '1994-01-01' AND l_shipdate < DATE '1995-01-01' AND l_discount BETWEEN 0.05 AND 0.07 AND l_quantity < 24";
    if (!strcmp(q, "q1"))    return "SELECT sum(l_quantity) FROM lineitem WHERE l_shipdate <= DATE '1998-09-02' GROUP BY l_returnflag, l_linestatus ORDER BY 1";
    if (!strcmp(q, "q3"))    return "SELECT l_orderkey, sum(l_extendedprice * (1 - l_discount)) AS revenue FROM customer, orders, lineitem WHERE c_mktsegment = 'BUILDING' AND c_custkey = o_custkey AND l_orderkey = o_orderkey AND o_orderdate < DATE '1995-03-15' AND l_shipdate > DATE '1995-03-15' GROUP BY l_orderkey ORDER BY revenue DESC LIMIT 10";
    die("unknown query"); return NULL;
}

static int run_ok(duckdb_connection con, const char *sql, double *first) {
    duckdb_result r;
    if (duckdb_query(con, sql, &r) == DuckDBError) { duckdb_destroy_result(&r); return 0; }
    *first = duckdb_row_count(&r) ? duckdb_value_double(&r, 0, 0) : 0;
    duckdb_destroy_result(&r); return 1;
}
static void run(duckdb_connection con, const char *sql) { double x; if (!run_ok(con, sql, &x)) { fprintf(stderr, "failed: %s\n", sql); exit(1); } }

static duckdb_database open_engine(int threads) {
    duckdb_config cfg; duckdb_database db; char t[16]; snprintf(t, sizeof t, "%d", threads);
    duckdb_create_config(&cfg);
    duckdb_set_config(cfg, "threads", t);
    duckdb_set_config(cfg, "memory_limit", "2GB");
    duckdb_set_config(cfg, "enable_object_cache", "true");
    char *err = NULL;
    if (duckdb_open_ext(NULL, &db, cfg, &err) == DuckDBError) { fprintf(stderr, "%s\n", err); exit(1); }
    duckdb_destroy_config(&cfg); return db;
}
static int INMEM = 0;
static duckdb_connection setup(duckdb_database db, const char *dir, const char *q) {
    duckdb_connection con; duckdb_connect(db, &con);
    char sql[1024];
    for (int i = 0; i < 8; i++) {
        /* in-memory mode: tables are in the engine buffer pool. Clones share
         * those pages, separate processes have to load their own copies
         */
        int hot = INMEM && (!strcmp(TABLES[i], "lineitem") || !strcmp(q, "q3"));   /* only what the query reads */
        snprintf(sql, sizeof sql, "CREATE %s %s AS SELECT * FROM read_parquet('%s/%s.parquet')",
                 hot ? "TABLE" : "VIEW", TABLES[i], dir, TABLES[i]);
        run(con, sql);
    }
    run(con, query_sql(q));           /* warm once */
    return con;
}

static const char *IMPL, *QUERY; static int N, KILL = -1, HOG = 0;

/* cap this process at its current address-space usage plus 1 GB.
 * using that as the per-worker budget an operator might set
 */
static void cap_memory(void) {
    FILE *f = fopen("/proc/self/statm", "r"); long pages = 0;
    if (f) { if (fscanf(f, "%ld", &pages) != 1) pages = 0; fclose(f); }
    struct rlimit rl; rl.rlim_cur = rl.rlim_max = (rlim_t)pages * 4096 + (1L << 30);
    setrlimit(RLIMIT_AS, &rl);
}
/* failing worker gets SIGKILL, or keeps allocating and touching
 * memory until the cap stops it
 */
static void fail_now(void) {
    if (!HOG) { usleep(1000); raise(SIGKILL); }
    usleep(1000);
    for (;;) {
        char *p = malloc(64 << 20);
        if (!p) abort();
        for (long i = 0; i < (64 << 20); i += 4096) p[i] = 1;
    }
}

static void report(int idx, pid_t pid, long long t0, long long t1, int ok, double first) {
    printf("{\"impl\":\"%s\",\"query\":\"%s\",\"workers\":%d,\"idx\":%d,\"pid\":%d,\"query_us\":%.1f,\"ok\":%d,\"first\":%.4f}\n",
           IMPL, QUERY, N, idx, pid, (t1 - t0) / 1e3, ok, first);
    fflush(stdout);
}

/* ---- threads impl ---- */
static duckdb_database TDB; static int GO_FD;
static void *thread_main(void *arg) {
    int idx = (int)(long)arg;
    duckdb_connection con; duckdb_connect(TDB, &con);
    char c; if (read(GO_FD, &c, 1) != 1) return NULL;
    if (idx == KILL) fail_now();                               /* a crash in one thread */
    double first; long long t0 = now_ns();
    int ok = run_ok(con, query_sql(QUERY), &first);
    report(idx, getpid(), t0, now_ns(), ok, first);
    duckdb_disconnect(&con);
    return NULL;
}

int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IOLBF, 0);
    signal(SIGPIPE, SIG_IGN);          /* writing to a dead worker's pipe must not kill us */
    const char *dir = NULL; IMPL = "clone"; QUERY = "q6"; N = 4;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--data")) dir = argv[++i];
        else if (!strcmp(argv[i], "--impl")) IMPL = argv[++i];
        else if (!strcmp(argv[i], "--workers")) N = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--query")) QUERY = argv[++i];
        else if (!strcmp(argv[i], "--kill")) KILL = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--inmem")) INMEM = 1;
        else if (!strcmp(argv[i], "--hog")) HOG = 1;
    }
    if (!dir) die("--data");
    long long t_setup = now_ns();

    if (!strcmp(IMPL, "threads")) {
        TDB = open_engine(N);                      /* N threads inside the engine too */
        duckdb_connection c0 = setup(TDB, dir, QUERY);
        if (KILL >= 0) cap_memory();              /* one limit for the whole process */
        int go[2]; pipe(go); GO_FD = go[0];
        pthread_t th[N];
        for (int i = 0; i < N; i++) pthread_create(&th[i], NULL, thread_main, (void *)(long)i);
        usleep(50000);
        long long t0 = now_ns();
        for (int i = 0; i < N; i++) if (write(go[1], "g", 1) != 1) die("write");
        for (int i = 0; i < N; i++) pthread_join(th[i], NULL);
        long long t1 = now_ns();
        printf("{\"impl\":\"threads\",\"query\":\"%s\",\"workers\":%d,\"summary\":1,\"inmem\":%d,\"total_pss_kb\":%ld,\"wall_us\":%.1f,\"setup_us\":%.1f,\"completed\":%d}\n",
               QUERY, N, INMEM, smaps_kb_of(getpid(), "Pss:"), (t1 - t0) / 1e3, (t0 - t_setup) / 1e3, N);
        duckdb_disconnect(&c0);
        return 0;
    }

    int clone = !strcmp(IMPL, "clone");
    duckdb_database db = NULL; duckdb_connection c0 = NULL;
    if (clone) { db = open_engine(1); c0 = setup(db, dir, QUERY); }

    pid_t pids[N]; int go[N][2], done[N][2];
    for (int i = 0; i < N; i++) {
        pipe(go[i]); pipe(done[i]);
        pids[i] = fork();
        if (pids[i] == 0) {
            close(done[i][0]); close(go[i][1]);
            duckdb_connection con;
            if (clone) duckdb_connect(db, &con);
            else { duckdb_database mydb = open_engine(1); con = setup(mydb, dir, QUERY); }
            if (KILL >= 0) cap_memory();                        /* one limit per worker */
            if (write(done[i][1], "r", 1) != 1) _exit(1);      /* ready */
            char c; if (read(go[i][0], &c, 1) != 1) _exit(1);
            if (i == KILL) fail_now();
            double first; long long t0 = now_ns();
            int ok = run_ok(con, query_sql(QUERY), &first);
            report(i, getpid(), t0, now_ns(), ok, first);
            if (write(done[i][1], "d", 1) != 1) _exit(1);
            if (read(go[i][0], &c, 1) != 1) _exit(1);   /* wait until the parent has measured memory */
            _exit(0);
        }
        close(done[i][1]); close(go[i][0]);   /* so a dead child shows up as EOF */
    }
    for (int i = 0; i < N; i++) { char c; if (read(done[i][0], &c, 1) != 1) die("ready"); }
    long long t0 = now_ns();
    for (int i = 0; i < N; i++) if (write(go[i][1], "g", 1) != 1) die("write");
    int completed = 0;
    for (int i = 0; i < N; i++) {
        char c; if (read(done[i][0], &c, 1) == 1) completed++;   /* EOF = that worker died */
    }
    long long t1 = now_ns();
    long total = clone ? smaps_kb_of(getpid(), "Pss:") : 0;
    for (int i = 0; i < N; i++) { long v = smaps_kb_of(pids[i], "Pss:"); if (v > 0) total += v; }
    printf("{\"impl\":\"%s\",\"query\":\"%s\",\"workers\":%d,\"summary\":1,\"inmem\":%d,\"total_pss_kb\":%ld,\"wall_us\":%.1f,\"setup_us\":%.1f,\"completed\":%d}\n",
           IMPL, QUERY, N, INMEM, total, (t1 - t0) / 1e3, (t0 - t_setup) / 1e3, completed);
    for (int i = 0; i < N; i++) { if (write(go[i][1], "x", 1) < 0) {} }
    for (int i = 0; i < N; i++) waitpid(pids[i], NULL, 0);
    return 0;
}
