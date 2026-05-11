import sqlglot
from sqlglot import exp
from sqlglot import parse_one


def _build_alias_origin_map(select_expr: exp.Select) -> dict:
    """为单个 SELECT 构建 {别名: 原始表达式 SQL} 映射，仅作用于当前 SELECT 作用域。"""
    alias_origin_map = {}
    for expression in select_expr.expressions:
        if isinstance(expression, exp.Alias):
            original = expression.this.sql()
            alias = expression.alias_or_name
            if alias:
                alias_origin_map[alias.lower()] = original
        else:
            # 对无别名投影，如果有 name 可作为匹配键
            alias = getattr(expression, "alias_or_name", None) or getattr(expression, "name", None)
            if alias:
                alias_origin_map[str(alias).lower()] = expression.sql()
    return alias_origin_map


def _align_group_for_select(select_expr: exp.Select):
    """仅用当前 SELECT 的别名映射替换其 GROUP BY 内的别名，避免误用父层别名。"""
    group_node = select_expr.args.get("group") or select_expr.args.get("group_by")
    if not group_node:
        return

    alias_origin_map = _build_alias_origin_map(select_expr)
    if not alias_origin_map:
        return

    group_cls = getattr(exp, "GroupBy", exp.Group)
    if not isinstance(group_node, group_cls):
        return

    for i, expr in enumerate(group_node.expressions or []):
        expr_sql = expr.sql().lower()
        if expr_sql in alias_origin_map:
            try:
                new_expr = parse_one(alias_origin_map[expr_sql])
                group_node.expressions[i] = new_expr
            except Exception:
                # 如果解析失败，保持原样
                continue


def align_group_by_with_select(sql: str) -> str:
    """
    对每个 SELECT 作用域：用该 SELECT 自己的投影别名映射替换 GROUP BY 中的别名。
    避免跨作用域误匹配；支持嵌套子查询的逐层处理。
    """
    ast = parse_one(sql)

    # 逐个 SELECT 作用域处理（find_all 会遍历所有嵌套）
    for select_expr in ast.find_all(exp.Select):
        _align_group_for_select(select_expr)

    return ast.sql(pretty=False)


# 测试示例
if __name__ == "__main__":
    # 原始SQL（GROUP BY含pmdume等别名）
    original_sql = """SELECT pm_table.collecttime, MAX(pm_table.timezoneoffset) AS timezoneoffset, pm_table.dstsaving, MAX(pm_table.granularity) AS granularity, AVG(pm_table.granularity) AS granularityforgr, NRCELLATT.dume AS pmdume, NRCELLATT.NRRadioInfrastructure, NRCELLATT.NRPhysicalCellDU, COUNT(DISTINCT pm_table.me || pm_table.GNBCUCPFunction || pm_table.NRCellCU) AS ITBBU_NRCellCU_NO FROM A_N_CELLCU_HO_MERGE_h AS pm_table INNER JOIN NRCELLATT ON pm_table.collecttime = NRCELLATT.collecttime AND pm_table.me = NRCELLATT.me AND pm_table.GNBCUCPFunction = NRCELLATT.GNBCUCPFunction AND pm_table.NRCellCU = NRCELLATT.NRCellCU AND pm_table.dstsaving = NRCELLATT.dstsaving WHERE pm_table.collecttime > '2023-07-27 19:00:00' AND pm_table.collecttime <= '2023-08-03 19:00:00' AND ((pm_table.collecttime > '2023-07-27 19:00:00' AND pm_table.collecttime <= '2023-07-27 20:00:00')) AND (pm_table.collecttime > '2023-07-27 19:00:00' AND pm_table.collecttime <= '2023-07-27 20:00:00') GROUP BY pm_table.collecttime, pm_table.dstsaving, NRCELLATT.dume, NRCELLATT.NRRadioInfrastructure, NRCELLATT.NRPhysicalCellDU"""
    
    # 处理SQL
    processed_sql = align_group_by_with_select(original_sql)
    print("处理后的SQL：")
    print(processed_sql)