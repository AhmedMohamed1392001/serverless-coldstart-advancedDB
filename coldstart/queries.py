"""TPC-H queries, some short ones and different catalog sizes. Not an official TPC-H run"""
from __future__ import annotations

TPCH = {
    "q1": """
SELECT l_returnflag, l_linestatus, sum(l_quantity) AS sum_qty,
       sum(l_extendedprice) AS sum_base_price,
       sum(l_extendedprice * (1 - l_discount)) AS sum_disc_price,
       sum(l_extendedprice * (1 - l_discount) * (1 + l_tax)) AS sum_charge,
       avg(l_quantity) AS avg_qty, avg(l_extendedprice) AS avg_price,
       avg(l_discount) AS avg_disc, count(*) AS count_order
FROM lineitem
WHERE l_shipdate <= DATE '1998-12-01' - INTERVAL 90 DAY
GROUP BY l_returnflag, l_linestatus
ORDER BY l_returnflag, l_linestatus""",
    "q3": """
SELECT l_orderkey, sum(l_extendedprice * (1 - l_discount)) AS revenue,
       o_orderdate, o_shippriority
FROM customer, orders, lineitem
WHERE c_mktsegment = 'BUILDING' AND c_custkey = o_custkey
  AND l_orderkey = o_orderkey AND o_orderdate < DATE '1995-03-15'
  AND l_shipdate > DATE '1995-03-15'
GROUP BY l_orderkey, o_orderdate, o_shippriority
ORDER BY revenue DESC, o_orderdate
LIMIT 10""",
    "q5": """
SELECT n_name, sum(l_extendedprice * (1 - l_discount)) AS revenue
FROM customer, orders, lineitem, supplier, nation, region
WHERE c_custkey = o_custkey AND l_orderkey = o_orderkey
  AND l_suppkey = s_suppkey AND c_nationkey = s_nationkey
  AND s_nationkey = n_nationkey AND n_regionkey = r_regionkey
  AND r_name = 'ASIA' AND o_orderdate >= DATE '1994-01-01'
  AND o_orderdate < DATE '1994-01-01' + INTERVAL 1 YEAR
GROUP BY n_name
ORDER BY revenue DESC""",
    "q6": """
SELECT sum(l_extendedprice * l_discount) AS revenue
FROM lineitem
WHERE l_shipdate >= DATE '1994-01-01'
  AND l_shipdate < DATE '1994-01-01' + INTERVAL 1 YEAR
  AND l_discount BETWEEN 0.05 AND 0.07 AND l_quantity < 24""",
    "q12": """
SELECT l_shipmode,
       sum(CASE WHEN o_orderpriority = '1-URGENT' OR o_orderpriority = '2-HIGH'
                THEN 1 ELSE 0 END) AS high_line_count,
       sum(CASE WHEN o_orderpriority <> '1-URGENT' AND o_orderpriority <> '2-HIGH'
                THEN 1 ELSE 0 END) AS low_line_count
FROM orders, lineitem
WHERE o_orderkey = l_orderkey AND l_shipmode IN ('MAIL', 'SHIP')
  AND l_commitdate < l_receiptdate AND l_shipdate < l_commitdate
  AND l_receiptdate >= DATE '1994-01-01'
  AND l_receiptdate < DATE '1994-01-01' + INTERVAL 1 YEAR
GROUP BY l_shipmode
ORDER BY l_shipmode""",
    "q18": """
SELECT c_name, c_custkey, o_orderkey, o_orderdate, o_totalprice, sum(l_quantity)
FROM customer, orders, lineitem
WHERE o_orderkey IN (SELECT l_orderkey FROM lineitem
                     GROUP BY l_orderkey HAVING sum(l_quantity) > 300)
  AND c_custkey = o_custkey AND o_orderkey = l_orderkey
GROUP BY c_name, c_custkey, o_orderkey, o_orderdate, o_totalprice
ORDER BY o_totalprice DESC, o_orderdate
LIMIT 100""",
}

# short queries, start-up is most of their time
SHORT = {
    "s_point":  "SELECT n_name FROM nation WHERE n_nationkey = 7",
    "s_count":  "SELECT count(*) FROM region",
    "s_filter": "SELECT s_name, s_acctbal FROM supplier WHERE s_acctbal > 9990 ORDER BY s_acctbal DESC LIMIT 5",
}

QUERIES = {**TPCH, **SHORT}

# number of extra views created at start-up
CATALOG_SIZES = {"small": 0, "medium": 200, "large": 2000}


def catalog_padding_sql(n_extra: int) -> list[str]:
    # views on the tiny nation table, so no query reads more data
    return [f"CREATE VIEW pad_{i} AS SELECT * FROM nation WHERE n_nationkey = {i % 25}"
            for i in range(n_extra)]
