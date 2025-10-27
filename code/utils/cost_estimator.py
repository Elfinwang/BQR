import psycopg2
import json

def get_query_cost(db_config: dict, sql_query: str) -> float:
    """
    连接 PostgreSQL 通过 EXPLAIN 获取 SQL 查询的估算成本。

    参数：
        db_config (dict): 包含 database, user, password, host, port 的配置
        sql_query (str): 要估算成本的 SQL 查询

    返回：
        float: EXPLAIN 输出的 Total Cost,若失败则返回 inf。
    """
    try:
        conn = psycopg2.connect(
            database=db_config["database"],
            user=db_config["user"],
            password=db_config["password"],
            host=db_config["host"],
            port=db_config["port"]
        )
        cur = conn.cursor()
        cur.execute(f"EXPLAIN (FORMAT JSON) {sql_query}")
        result = cur.fetchone()
        explain_json = result[0][0] if isinstance(result[0], list) else result[0]
        cost = explain_json["Plan"]["Total Cost"]
        cur.close()
        conn.close()
        return float(cost)
    except Exception as e:
        print(f"[EXPLAIN ERROR] {e} for query: {sql_query}")
        return float("inf")