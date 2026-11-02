/* six ways of starting a worker, timed the same way
 *
 *   coldbench --data DIR --mode MODE --query Q --conc C --reps R [--catalog N] [--pool-mem N]
 *
 * modes: fresh, clone_generic, clone_selective, clone_prepared, clone_pooled, warm
 * queries: point, count, filter, q6, q1
 *
 * JSON line per request on stdout, bench_native.py collects them.
 * For bursts, all C requests arrive at the same t0.
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/wait.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include "duckdb.h"

/* ---------- small helpers ---------- */
static long long now_ns(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)ts.tv_sec * 1000000000LL + ts.tv_nsec;
}
static long minflt(void) {
    FILE *f = fopen("/proc/self/stat", "r"); if (!f) return -1;
    char buf[4096]; size_t n = fread(buf, 1, sizeof buf - 1, f); fclose(f); buf[n] = 0;
    char *p = strrchr(buf, ')'); if (!p) return -1;
    long v = -1; int field = 3;
    for (char *tok = strtok(p + 2, " "); tok; tok = strtok(NULL, " "), field++)
        if (field == 10) { v = atol(tok); break; }
    return v;
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
    if (duckdb_query(con, sql, &r) == DuckDBError) {
        fprintf(stderr, "query failed: %s\n%s\n", sql, duckdb_result_error(&r));
        duckdb_destroy_result(&r); exit(1);
    }
    duckdb_destroy_result(&r);
}
/* run and return row count, so the driver can check results agree */
static long run_rows(duckdb_connection con, const char *sql, double *first) {
    duckdb_result r;
    if (duckdb_query(con, sql, &r) == DuckDBError) {
        fprintf(stderr, "query failed: %s\n%s\n", sql, duckdb_result_error(&r));
        duckdb_destroy_result(&r); exit(1);
    }
    long rows = (long)duckdb_row_count(&r);
    *first = rows ? duckdb_value_double(&r, 0, 0) : 0;
    duckdb_destroy_result(&r);
    return rows;
}

/* ---------- workload ---------- */
static const char *TABLES[] = {"lineitem", "orders", "customer", "part",
                               "supplier", "partsupp", "nation", "region"};
static const char *query_sql(const char *q) {
    if (!strcmp(q, "point"))  return "SELECT n_nationkey FROM nation WHERE n_nationkey = 7";
    if (!strcmp(q, "count"))  return "SELECT count(*) FROM region";
    if (!strcmp(q, "filter")) return "SELECT s_acctbal FROM supplier WHERE s_acctbal > 9990 ORDER BY s_acctbal DESC LIMIT 5";
    if (!strcmp(q, "q6"))     return "SELECT sum(l_extendedprice * l_discount) FROM lineitem WHERE l_shipdate >= DATE '1994-01-01' AND l_shipdate < DATE '1995-01-01' AND l_discount BETWEEN 0.05 AND 0.07 AND l_quantity < 24";
    if (!strcmp(q, "q1"))     return "SELECT sum(l_quantity) FROM lineitem WHERE l_shipdate <= DATE '1998-09-02' GROUP BY l_returnflag, l_linestatus ORDER BY 1";
    die("unknown query"); return NULL;
}

static duckdb_database open_engine(void) {
    duckdb_config cfg; duckdb_database db;
    if (duckdb_create_config(&cfg) == DuckDBError) die("config");
    duckdb_set_config(cfg, "threads", "1");          /* no background threads when we fork */
    duckdb_set_config(cfg, "memory_limit", "512MB");
    duckdb_set_config(cfg, "enable_object_cache", "true");
    char *err = NULL;
    if (duckdb_open_ext(NULL, &db, cfg, &err) == DuckDBError) { fprintf(stderr, "%s\n", err); exit(1); }
    duckdb_destroy_config(&cfg);
    return db;
}
static void build_catalog(duckdb_connection con, const char *dir, int extra) {
    char sql[1024];
    for (int i = 0; i < 8; i++) {
        snprintf(sql, sizeof sql, "CREATE VIEW %s AS SELECT * FROM read_parquet('%s/%s.parquet')", TABLES[i], dir, TABLES[i]);
        run(con, sql);
    }
    for (int i = 0; i < extra; i++) {            /* padding views for the catalog size experiment */
        snprintf(sql, sizeof sql, "CREATE VIEW pad_%d AS SELECT * FROM nation WHERE n_nationkey = %d", i, i % 25);
        run(con, sql);
    }
}
static void warm_metadata(duckdb_connection con, const char *dir) {
    char sql[1024];
    for (int i = 0; i < 8; i++) {
        snprintf(sql, sizeof sql, "SELECT count(*) FROM parquet_metadata('%s/%s.parquet')", dir, TABLES[i]);
        run(con, sql);
    }
}

/* ---------- the measured part, same for every mode ---------- */
static const char *MODE, *QUERY; static int CONC, CATALOG;
static int REP;

static void report(const char *mode, int idx, long long t0, long long t_ready, long f_ready,
                   long long t_done, long f_done, long rows, double first, long idle_kb) {
    /* raw CLOCK_MONOTONIC stamps too, plus this process's cpu time and context switches */
    struct rusage ru; getrusage(RUSAGE_SELF, &ru);
    printf("{\"mode\":\"%s\",\"query\":\"%s\",\"conc\":%d,\"rep\":%d,\"idx\":%d,\"catalog\":%d,\"pid\":%d,"
           "\"ready_us\":%.1f,\"done_us\":%.1f,\"faults_ready\":%ld,\"faults_query\":%ld,"
           "\"rows\":%ld,\"first\":%.4f,\"private_dirty_kb\":%ld,\"idle_private_dirty_kb\":%ld,"
           "\"t_arrive_ns\":%lld,\"t_ready_ns\":%lld,\"t_done_ns\":%lld,"
           "\"utime_us\":%ld,\"stime_us\":%ld,\"vcsw\":%ld,\"ivcsw\":%ld}\n",
           mode, QUERY, CONC, REP, idx, CATALOG, getpid(),
           (t_ready - t0) / 1e3, (t_done - t0) / 1e3, f_ready, f_done, rows, first,
           smaps_kb("Private_Dirty:"), idle_kb, t0, t_ready, t_done,
           ru.ru_utime.tv_sec * 1000000L + ru.ru_utime.tv_usec, ru.ru_stime.tv_sec * 1000000L + ru.ru_stime.tv_usec,
           ru.ru_nvcsw, ru.ru_nivcsw);
    fflush(stdout);
}

/* child does the private setup itself (selective / generic) */
static void child_rebuild(duckdb_database db, const char *mode, long long t0, int idx) {
    long f0 = minflt();
    duckdb_connection con; if (duckdb_connect(db, &con) == DuckDBError) die("connect");
    char sql[256]; snprintf(sql, sizeof sql, "SET temp_directory = '/tmp/coldbench-%d'", getpid());
    run(con, sql);
    long long tr = now_ns(); long f1 = minflt();
    double first; long rows = run_rows(con, query_sql(QUERY), &first);
    long long td = now_ns(); long f2 = minflt();
    report(mode, idx, t0, tr, f1 - f0, td, f2 - f1, rows, first, -1);
}
/* child inherits a prepared connection (prepared / pooled) */
static void child_inherit(duckdb_connection con, const char *mode, long long t0, int idx, long idle_kb) {
    long f0 = minflt(); long long tr = now_ns(); long f1 = minflt();
    double first; long rows = run_rows(con, query_sql(QUERY), &first);
    long long td = now_ns(); long f2 = minflt();
    report(mode, idx, t0, tr, f1 - f0, td, f2 - f1, rows, first, idle_kb);
}

/* ---------- fresh: a brand new process per request ---------- */
static void fresh_main(const char *dir, long long t0, int idx) {
    long long ta = now_ns(); long f0 = minflt();           /* ta: process is running main() */
    duckdb_database db = open_engine();
    long long tb = now_ns();
    duckdb_connection con; duckdb_connect(db, &con);
    long long tc = now_ns();
    build_catalog(con, dir, CATALOG);
    long long tr = now_ns(); long f1 = minflt();
    double first; long rows = run_rows(con, query_sql(QUERY), &first);
    long long td = now_ns(); long f2 = minflt();
    /* where the fresh start-up goes: spawn+exec+linking, open, connect, catalog */
    printf("{\"mode\":\"fresh_phases\",\"query\":\"%s\",\"conc\":%d,\"rep\":%d,\"idx\":%d,\"catalog\":%d,"
           "\"spawn_us\":%.1f,\"open_us\":%.1f,\"connect_us\":%.1f,\"catalog_us\":%.1f}\n",
           QUERY, CONC, REP, idx, CATALOG, (ta - t0) / 1e3, (tb - ta) / 1e3, (tc - tb) / 1e3, (tr - tc) / 1e3);
    report("fresh", idx, t0, tr, f1 - f0, td, f2 - f1, rows, first, -1);
}

/* ---------- warm: a full process that stays alive between requests ---------- */
static void warm_main(const char *dir, int fd, int idx) {
    duckdb_database db = open_engine();
    duckdb_connection con; duckdb_connect(db, &con);
    build_catalog(con, dir, CATALOG);
    warm_metadata(con, dir);
    double first; run_rows(con, query_sql(QUERY), &first);   /* warm, like a long-running worker */
    long idle = smaps_kb("Private_Dirty:");
    long long t0;
    while (read(fd, &t0, sizeof t0) == sizeof t0) {
        REP = (int)(t0 & 0xffff); t0 &= ~0xffffLL;             /* rep is packed into the low bits */
        child_inherit(con, "warm", t0, idx, idle);
    }
}

/* ---------- driver ---------- */
static char *SELF;
static void spawn_self(const char *dir, const char *what, long long t0, int idx, int fd) {
    char a[32], b[32], c[32], d[32], e[32], g[32];
    snprintf(a, 32, "%lld", t0); snprintf(b, 32, "%d", idx); snprintf(c, 32, "%d", fd);
    snprintf(d, 32, "%d", CATALOG); snprintf(e, 32, "%d", REP); snprintf(g, 32, "%d", CONC);
    execl(SELF, SELF, "--child", what, dir, a, b, c, QUERY, d, e, g, (char *)NULL);
    die("exec");
}

int main(int argc, char **argv) {
    SELF = argv[0];
    setvbuf(stdout, NULL, _IOLBF, 0);   /* one line per write, so a fork never inherits half a line */
    if (argc > 1 && !strcmp(argv[1], "--child")) {
        const char *what = argv[2], *dir = argv[3];
        long long t0 = atoll(argv[4]); int idx = atoi(argv[5]), fd = atoi(argv[6]);
        QUERY = argv[7]; CATALOG = atoi(argv[8]); REP = atoi(argv[9]); CONC = atoi(argv[10]);
        if (!strcmp(what, "fresh")) fresh_main(dir, t0, idx);
        else warm_main(dir, fd, idx);
        return 0;
    }
    const char *dir = NULL; int reps = 10, pool_mem = 0;
    MODE = "clone_selective"; QUERY = "point"; CONC = 1; CATALOG = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--data")) dir = argv[++i];
        else if (!strcmp(argv[i], "--mode")) MODE = argv[++i];
        else if (!strcmp(argv[i], "--query")) QUERY = argv[++i];
        else if (!strcmp(argv[i], "--conc")) CONC = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--reps")) reps = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--catalog")) CATALOG = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--pool-mem")) pool_mem = atoi(argv[++i]);
    }
    if (!dir) die("--data required");
    int conc = CONC;

    /* ----- fresh ----- */
    if (!strcmp(MODE, "fresh")) {
        for (REP = 0; REP < reps; REP++) {
            long long t0 = now_ns();
            for (int i = 0; i < conc; i++) { pid_t p = fork(); if (p == 0) spawn_self(dir, "fresh", t0, i, -1); }
            for (int i = 0; i < conc; i++) wait(NULL);
            usleep(20000);
        }
        return 0;
    }

    /* ----- warm: conc persistent processes, each a full engine ----- */
    if (!strcmp(MODE, "warm")) {
        int fds[conc]; pid_t pids[conc];
        for (int i = 0; i < conc; i++) {
            int pfd[2]; if (pipe(pfd)) die("pipe");
            pids[i] = fork();
            if (pids[i] == 0) { close(pfd[1]); spawn_self(dir, "warm", 0, i, pfd[0]); }
            close(pfd[0]); fds[i] = pfd[1];
        }
        sleep(2);                                      /* let them all come up */
        for (REP = 0; REP < reps; REP++) {
            long long t0 = (now_ns() & ~0xffffLL) | (REP & 0xffff);
            for (int i = 0; i < conc; i++) if (write(fds[i], &t0, sizeof t0) != sizeof t0) die("write");
            usleep(conc > 1 ? 200000 : 20000);        /* wait for the burst to finish */
        }
        for (int i = 0; i < conc; i++) close(fds[i]);
        for (int i = 0; i < conc; i++) waitpid(pids[i], NULL, 0);
        return 0;
    }

    /* ----- clone modes: one template process ----- */
    int selective = strcmp(MODE, "clone_generic") != 0;
    long long tb = now_ns();
    duckdb_database db = open_engine();
    duckdb_connection c0; duckdb_connect(db, &c0);
    build_catalog(c0, dir, CATALOG);
    if (selective) warm_metadata(c0, dir);
    printf("{\"mode\":\"template_build\",\"query\":\"%s\",\"catalog\":%d,\"build_us\":%.1f,\"rss_kb\":%ld,\"private_dirty_kb\":%ld}\n",
           QUERY, CATALOG, (now_ns() - tb) / 1e3, smaps_kb("Rss:"), smaps_kb("Private_Dirty:"));
    fflush(stdout);

    int prepared = !strcmp(MODE, "clone_prepared"), pooled = !strcmp(MODE, "clone_pooled");

    /* memory experiment: keep N pooled clones idle and report the total */
    if (pool_mem > 0) {
        int fds[pool_mem]; pid_t pids[pool_mem];
        for (int i = 0; i < pool_mem; i++) {
            duckdb_connection next; duckdb_connect(db, &next);
            int pfd[2]; if (pipe(pfd)) die("pipe");
            pids[i] = fork();
            if (pids[i] == 0) {
                close(pfd[1]); run(next, "SELECT 1"); run(next, "SELECT count(*) FROM region");
                long long x; if (read(pfd[0], &x, sizeof x) < 0) _exit(1); _exit(0);
            }
            close(pfd[0]); fds[i] = pfd[1]; duckdb_disconnect(&next);
        }
        usleep(200000);
        long total = 0;
        for (int i = 0; i < pool_mem; i++) {
            char path[64]; snprintf(path, sizeof path, "/proc/%d/smaps_rollup", pids[i]);
            FILE *f = fopen(path, "r"); char line[256];
            while (f && fgets(line, sizeof line, f)) if (!strncmp(line, "Private_Dirty:", 14)) total += atol(line + 14);
            if (f) fclose(f);
        }
        printf("{\"mode\":\"pool_memory\",\"pool\":%d,\"template_private_dirty_kb\":%ld,\"pool_private_dirty_kb\":%ld}\n",
               pool_mem, smaps_kb("Private_Dirty:"), total);
        for (int i = 0; i < pool_mem; i++) { long long x = 1; if (write(fds[i], &x, sizeof x) < 0) die("write"); close(fds[i]); }
        for (int i = 0; i < pool_mem; i++) waitpid(pids[i], NULL, 0);
        return 0;
    }

    for (REP = 0; REP < reps; REP++) {
        pid_t pids[conc]; int fds[conc]; duckdb_connection cons[conc];
        if (pooled) {
            /* fork and warm up conc children before the burst arrives; also time the refill */
            for (int i = 0; i < conc; i++) {
                long long tf = now_ns();
                duckdb_connect(db, &cons[i]);
                char sql[256]; snprintf(sql, sizeof sql, "SET temp_directory = '/tmp/coldbench-%d-%d'", REP, i);
                run(cons[i], sql);
                int pfd[2], ack[2]; if (pipe(pfd) || pipe(ack)) die("pipe");
                pids[i] = fork();
                if (pids[i] == 0) {
                    close(pfd[1]); close(ack[0]);
                    run(cons[i], "SELECT 1"); run(cons[i], "SELECT count(*) FROM region");
                    char ok = 1; if (write(ack[1], &ok, 1) < 0) _exit(1); close(ack[1]);
                    long idle = smaps_kb("Private_Dirty:");
                    long long t0; if (read(pfd[0], &t0, sizeof t0) != sizeof t0) _exit(1);
                    child_inherit(cons[i], "clone_pooled", t0, i, idle);
                    _exit(0);
                }
                close(pfd[0]); close(ack[1]); fds[i] = pfd[1];
                char ok; if (read(ack[0], &ok, 1) < 0) die("ack"); close(ack[0]);
                duckdb_disconnect(&cons[i]);
                if (i == 0) printf("{\"mode\":\"pool_refill\",\"query\":\"%s\",\"rep\":%d,\"refill_us\":%.1f}\n",
                                   QUERY, REP, (now_ns() - tf) / 1e3);
            }
            long long t0 = now_ns();
            for (int i = 0; i < conc; i++) if (write(fds[i], &t0, sizeof t0) < 0) die("write");
            for (int i = 0; i < conc; i++) { close(fds[i]); }
            for (int i = 0; i < conc; i++) waitpid(pids[i], NULL, 0);
        } else {
            if (prepared)
                for (int i = 0; i < conc; i++) {
                    duckdb_connect(db, &cons[i]);
                    char sql[256]; snprintf(sql, sizeof sql, "SET temp_directory = '/tmp/coldbench-%d-%d'", REP, i);
                    run(cons[i], sql);
                }
            long long t0 = now_ns();
            for (int i = 0; i < conc; i++) {
                pids[i] = fork();
                if (pids[i] == 0) {
                    if (prepared) child_inherit(cons[i], "clone_prepared", t0, i, -1);
                    else child_rebuild(db, MODE, t0, i);
                    _exit(0);
                }
            }
            for (int i = 0; i < conc; i++) waitpid(pids[i], NULL, 0);
            if (prepared) for (int i = 0; i < conc; i++) duckdb_disconnect(&cons[i]);
        }
        usleep(conc > 1 ? 50000 : 5000);
    }
    return 0;
}
