import psycopg2
import json
import os
import re
from typing import Any, Dict, Optional

from sqlglot import parse_one, exp


def _wrap_sql_with_ctes_if_needed(sql_query: str, cte_definitions: Dict[str, str]) -> str:
    """
    根据 cte_definitions，在前面添加 WITH <name> AS (<body>), ...
    """
    if not cte_definitions:
        print(f"[CTE ADDED] No CTEs provided, returning original SQL")
        return sql_query

    # 构建所有 CTE 定义
    with_parts = [f"{name} AS ({body})" for name, body in cte_definitions.items()]
    with_clause = "WITH " + ", ".join(with_parts)

    stripped = sql_query.lstrip()
    # 保留原始前导空白
    leading_ws_len = len(sql_query) - len(stripped)
    leading_ws = sql_query[:leading_ws_len]
    # 若原 SQL 已经以 WITH 开头，则把 CTE 放在其前面并用逗号合并现有 WITH 内容
    if stripped.lower().startswith("with "):
        # 去掉原始 "WITH " 前缀，检查已有 CTE 名称
        rest_after_with = stripped[len("with "):]
        try:
            parsed = parse_one(stripped)
            with_expr = parsed.args.get("with")
            existing_names = set()
            if with_expr:
                for c in getattr(with_expr, "expressions", []) or []:
                    try:
                        existing_names.add(c.alias_or_name.lower())
                    except Exception:
                        pass
        except Exception:
            existing_names = set()

        # 比较名字集合（不区分大小写）
        to_add = []
        defs_lower = {name.lower(): (name, body) for name, body in cte_definitions.items()}
        missing = [defs_lower[n] for n in defs_lower.keys() if n not in existing_names]

        if not missing:
            print(f"[CTE ADDED] Existing WITH already contains same CTE names, skipping prepend: {list(existing_names)}")
            return sql_query

        # 仅添加缺失的 CTE
        with_parts_missing = [f"{name} AS ({body})" for name, body in missing]
        merged = f"WITH " + ", ".join(with_parts_missing) + ", " + rest_after_with
        print(f"[CTE ADDED] Prepended missing CTEs: {[n for n,_ in missing]}")
        return leading_ws + merged

    # 在顶部添加新的 WITH 子句
    # print(f"[CTE ADDED] Prepended all CTEs: {list(cte_definitions.keys())}")
    return with_clause + " " + stripped
    

def _load_cte_map_from_path(cte_map_path: Optional[str]) -> Dict[str, str]:
    """
    尝试从给定路径加载 xxx_cte_map.json，失败则返回空 dict
    """
    if not cte_map_path:
        return {}

    try:
        if not os.path.isfile(cte_map_path):
            return {}
        with open(cte_map_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 只保留 name -> sql_body 字符串映射
        return {str(k): str(v) for k, v in data.items()}
    except Exception as e:
        print(f"[CTE MAP LOAD ERROR] {e} for path: {cte_map_path}")
        return {}


def get_explain_plan_json(
    db_config: dict,
    sql_query: str,
    cte_map: Optional[Dict[str, str]] = None,
    cte_map_path: Optional[str] = None,
    analyze: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Return the first plan object from PostgreSQL EXPLAIN (FORMAT JSON).

    If analyze=True, runs EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) so the plan
    contains Actual Total Time / Actual Rows (executes the query).

    On failure returns None.
    """
    sql_for_explain = ""
    try:
        if cte_map is None:
            cte_map = _load_cte_map_from_path(cte_map_path)

        sql_for_explain = _wrap_sql_with_ctes_if_needed(sql_query, cte_map or {})
        sql_for_explain = sql_for_explain.replace("STR_POSITION", "STRPOS")
        sql_for_explain = sql_for_explain.replace("str_position", "STRPOS")

        conn = psycopg2.connect(
            database=db_config["database"],
            user=db_config["user"],
            password=db_config["password"],
            host=db_config["host"],
            port=db_config["port"],
            connect_timeout=int(os.getenv("PG_CONNECT_TIMEOUT_S", "5")),
        )
        cur = conn.cursor()
        stmt_timeout_ms = int(os.getenv("PG_STATEMENT_TIMEOUT_MS", "0"))
        if stmt_timeout_ms > 0:
            cur.execute(f"SET statement_timeout = {stmt_timeout_ms}")

        if analyze:
            cur.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql_for_explain}")
        else:
            cur.execute(f"EXPLAIN (FORMAT JSON) {sql_for_explain}")
        result = cur.fetchone()
        explain_json = result[0][0] if isinstance(result[0], list) else result[0]
        cur.close()
        conn.close()
        if isinstance(explain_json, list) and explain_json:
            explain_json = explain_json[0]
        if not isinstance(explain_json, dict) or "Plan" not in explain_json:
            return None
        return explain_json
    except Exception as e:
        print(f"[EXPLAIN ERROR] {e} for query: {sql_for_explain}")
        return None


def get_query_cost(
    db_config: dict,
    sql_query: str,
    cte_map: Optional[Dict[str, str]] = None,
    cte_map_path: Optional[str] = None,
) -> float:
    """
    连接 PostgreSQL 通过 EXPLAIN 获取 SQL 查询的估算成本。

    参数：
        db_config (dict): 包含 database, user, password, host, port 的配置
        sql_query (str): 要估算成本的 SQL 查询
        cte_map (dict, 可选): {cte_name: cte_sql_body} 的映射
        cte_map_path (str, 可选): xxx_cte_map.json 的路径

    返回：
        float: EXPLAIN 输出的 Total Cost, 若失败则返回 inf。
    """
    root = get_explain_plan_json(db_config, sql_query, cte_map=cte_map, cte_map_path=cte_map_path, analyze=False)
    if root is None:
        return float("inf")
    try:
        return float(root["Plan"]["Total Cost"])
    except (KeyError, TypeError):
        return float("inf")


# ---------- 不依赖 PG 的启发式 Cost（用于无库/离线改写） ----------

def get_heuristic_cost(sql_query: str) -> float:
    """
    仅基于 SQL 文本的启发式复杂度分数，不连接数据库。
    数值越大表示越「重」，改写后分数下降可视为改进。
    用于 cost_strategy='heuristic' 时替代 get_query_cost。
    """
    try:
        tree = parse_one(sql_query)
    except Exception:
        return float("inf")
    score = 0.0
    # 子查询数量与嵌套深度（子查询内再含子查询则加重）
    subqs = list(tree.find_all(exp.Subquery))
    score += 100.0 * len(subqs)
    for sq in subqs:
        inner = list(sq.find_all(exp.Subquery))
        if inner:
            score += 50.0 * len(inner)
    # JOIN 数量
    joins = list(tree.find_all(exp.Join))
    score += 10.0 * len(joins)
    # 表/From 数量（近似）
    froms = list(tree.find_all(exp.From))
    score += 5.0 * len(froms)
    # GROUP BY / DISTINCT / ORDER BY 增加权重
    if list(tree.find_all(exp.Group)):
        score += 30.0
    if list(tree.find_all(exp.Distinct)):
        score += 20.0
    if list(tree.find_all(exp.Order)):
        score += 15.0
    # 聚合函数
    aggs = list(tree.find_all(exp.AggFunc))
    score += 5.0 * len(aggs)
    return score


def get_predicted_runtime_sec(
    sql_query: str,
    db_config: dict,
    calibrator_model_path: str,
    cte_map: Optional[Dict[str, str]] = None,
    cte_map_path: Optional[str] = None,
) -> Optional[float]:
    """
    Predict query runtime (seconds) using a saved PGCostCalibrator model (JSON).

    Runs EXPLAIN (no ANALYZE), extracts (C, R, J, S, D), applies log-linear model.
    Returns None if EXPLAIN fails or the model cannot be loaded.
    """
    try:
        from utils.pg_cost_calibrator import PGCostCalibrator
        from utils.pg_plan_features import extract_features_from_explain_json
    except ImportError:
        return None
    try:
        cal = PGCostCalibrator.load(calibrator_model_path)
    except Exception:
        return None
    root = get_explain_plan_json(
        db_config, sql_query, cte_map=cte_map, cte_map_path=cte_map_path, analyze=False
    )
    if root is None:
        return None
    feat = extract_features_from_explain_json(root)
    return cal.predict_runtime_sec(feat)


def get_cost(
    sql_query: str,
    db_config: Optional[dict] = None,
    cte_map: Optional[Dict[str, str]] = None,
    cte_map_path: Optional[str] = None,
    strategy: str = "pg_explain",
) -> float:
    """
    统一入口：按 strategy 选择用 PG EXPLAIN 或启发式 cost。
    - strategy='pg_explain': 使用 get_query_cost（需 db_config）
    - strategy='heuristic': 使用 get_heuristic_cost（不需 db_config，无 PG 交互）
    """
    if strategy == "heuristic":
        return get_heuristic_cost(sql_query)
    if strategy == "pg_explain":
        if not db_config:
            raise ValueError("db_config required when strategy is pg_explain")
        return get_query_cost(db_config, sql_query, cte_map=cte_map, cte_map_path=cte_map_path)
    raise ValueError(f"Unknown cost strategy: {strategy}")