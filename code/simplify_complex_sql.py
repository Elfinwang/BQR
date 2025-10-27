from rewriter_interface import call_rewriter
from utils.cost_estimator import get_query_cost
from sqlglot import parse_one, exp
from config import DB_CONFIG, LOCAL_RULES
from syntax_tree import extract_and_fix_subqueries, find_subqueries
import random
from sqlglot.errors import ParseError
import re


def extract_columns_and_tables(sql):
    try:
        parsed = parse_one(sql)
        columns_all = {f"{c.table}.{c.name}" for c in parsed.find_all(exp.Column) if c.table}
        columns = {c.name for c in parsed.find_all(exp.Column)}
        tables = {t.alias_or_name or t.name for t in parsed.find_all(exp.Table)}
        return columns, tables
    except Exception as e:
        return set(), set()




def extract_where_conditions(sql):
    """
    Use regex to split WHERE clause conditions by AND/OR, return all condition strings.
    """
    try:
        parsed = parse_one(sql)
        where_expr = parsed.args.get("where")
        # print(f"WHERE子句: {where_expr}")
        if where_expr is None:
            return []
        # 提取WHERE子句的SQL文本
        where_sql = where_expr.sql()
        # 按 AND/OR（忽略大小写）分割
        conds = re.split(r'\s+(AND|OR)\s+', where_sql, flags=re.IGNORECASE)
        # 只保留条件部分，去除分隔符
        
        conds = [c.strip() for i, c in enumerate(conds) if i % 2 == 0 and c.strip()]
        conds[0] = conds[0].replace("WHERE", "").strip()  # 去除WHERE关键字
        return conds
    except Exception as e:
        print(f"[解析WHERE失败] SQL: {sql[:80]}, 错误: {e}")
        return []



def compare_column_and_table_mapping(sql_before, sql_after):
    """Print mapping of column and table names (only output changes)"""
    cols_before, tabs_before = extract_columns_and_tables(sql_before)
    cols_after, tabs_after = extract_columns_and_tables(sql_after)
    changed_cols = cols_before.symmetric_difference(cols_after)
    changed_tabs = tabs_before.symmetric_difference(tabs_after)
    print("cols_before: ", cols_before)
    print("cols_after: ", cols_after)
    print("tabs_before: ", tabs_before)
    print("tabs_after: ", tabs_after)
    if changed_cols:
        print(f"  col: {changed_cols}")
    if changed_tabs:
        print(f"  table: {changed_tabs}")

def compare_where_conditions(sql_before, sql_after):
    """Print changed WHERE conditions (only output changes)"""
    conds_before = [c for c in extract_where_conditions(sql_before)]
    conds_after = [c for c in extract_where_conditions(sql_after)]
    print("conds_before: ", conds_before)
    print("conds_after: ", conds_after)
    changed = set(conds_before).symmetric_difference(set(conds_after))
    if changed:
        print(f"  condition: {changed}")



class SimplifySQL:
    def __init__(self, db_config):
        self.db_config = db_config

    def simplify_subqueries(self, fixed_sql_list):
        result_pairs = []

        for idx, q in enumerate(fixed_sql_list):
            print(f"\n[Algorithm 4] 处理子查询 {idx+1}")
            q_original = q
            q_current = q_original
            q_base_cost = get_query_cost(self.db_config, q_original)
            plan_changed = False

            changed_columns = set()
            changed_tables = set()
            changed_conditions = set()
            all_removable_columns = set()  
            all_removable_conds = set() 

            for rule in LOCAL_RULES:
                try:
                    db_id = "tpch" if self.db_config.get("database") == "tpch10g" else self.db_config.get("database")
                    sql_before = q_original
                    rewritten = call_rewriter(db_id, sql_before, [rule]).replace("$", "")
                    rewritten_cost = get_query_cost(self.db_config, rewritten)

                    if rewritten_cost != q_base_cost:
                        plan_changed = True
                        print(f"  应用 {rule}: {q_base_cost:.2f} → {rewritten_cost:.2f}")

                        print(f"  原始SQL: {sql_before}")
                        print(f"  重写SQL: {rewritten}")
                        # 输出属性名和表名变化
                        compare_column_and_table_mapping(sql_before, rewritten)
                        compare_where_conditions(sql_before, rewritten)

                        # 记录有变化的列、表
                        cols_before, tabs_before = extract_columns_and_tables(sql_before)
                        cols_after, tabs_after = extract_columns_and_tables(rewritten)
                        changed_columns |= cols_before.symmetric_difference(cols_after)
                        changed_tables |= tabs_before.symmetric_difference(tabs_after)

                        # 输出列名映射
                        col_map = {}
                        for col in cols_before:
                            if col not in changed_columns and col in cols_after:
                                col_map[col] = col
                        if col_map:
                            print(f"  列名映射: {col_map}")
                            all_removable_columns.update(col_map.keys())

                        # 记录有变化的条件
                        conds_before = extract_where_conditions(sql_before)
                        conds_after = extract_where_conditions(rewritten)
                        changed_conditions |= set(conds_before).symmetric_difference(set(conds_after))

                        # 输出条件映射
                        cond_map = {}
                        for cond in conds_before:
                            if cond not in changed_conditions and cond in conds_after:
                                cond_map[cond] = cond
                        if cond_map:
                            print(f"  条件映射: {cond_map}")
                            all_removable_conds.update(cond_map.keys())

                        
                        
                        # for cond_b in conds_before:
                        #     cond_b_mapped = cond_b
                        #     for old_col, new_col in col_map.items():
                        #         # 只替换完整的属性名，避免误替换
                        #         cond_b_mapped = cond_b_mapped.replace(old_col, new_col)
                        #     if cond_b_mapped in conds_after:
                        #         # 这对条件可以删除
                        #         mapping_conditions.add(cond_b)
                        #         # 还要把涉及的属性也加入可删除
                        #         for old_col in col_map:
                        #             if old_col in cond_b:
                        #                 mapping_columns.add(old_col)
                        # # --------------------------------------


                        q_current = rewritten
                        q_base_cost = rewritten_cost
                    else:
                        print(f"  跳过规则 {rule}（计划未变化）")
                except Exception as e:
                    print(f"   规则 {rule} 应用失败: {e}")

            try:
                parsed = parse_one(q_original)
                # 1. 列
                select_exprs = parsed.args.get("expressions", [])
                if select_exprs:
                    if not plan_changed:
                        parsed.set("expressions", [random.choice(select_exprs)])
                    else:
                        filtered_exprs = []
                        for expr in select_exprs:
                            if isinstance(expr, exp.Column):
                                col_key = f"{expr.table}.{expr.name}"
                                col_name = f"{expr.name}"
                                # 如果列在可删除映射中，则跳过
                                if all_removable_columns and col_name in all_removable_columns:
                                    continue
                            filtered_exprs.append(expr)
                        if filtered_exprs:
                            parsed.set("expressions", filtered_exprs)
                        else:
                            parsed.set("expressions", [random.choice(select_exprs)])

                # 2. 表
                from_expr = parsed.args.get("from")
                if from_expr and hasattr(from_expr, "expressions") and from_expr.expressions:
                    if not plan_changed:
                        from_expr.set("expressions", [random.choice(from_expr.expressions)])
                    else:
                        filtered_tables = []
                        for t in from_expr.expressions:
                            tab_key = t.alias_or_name or t.name
                            # 如果表在changed_tables且在可删除映射中，则跳过
                            if changed_tables and tab_key not in changed_tables:
                                continue
                            filtered_tables.append(t)
                        if filtered_tables:
                            from_expr.set("expressions", filtered_tables)
                        else:
                            from_expr.set("expressions", [random.choice(from_expr.expressions)])

                # 3. WHERE条件
                where_conds = extract_where_conditions(q_original)
                if where_conds:
                    if not plan_changed:
                        where_sql = " WHERE " + random.choice(where_conds)
                    else:
                        filtered_conds = [c for c in where_conds if c not in all_removable_conds ]
                        if filtered_conds:
                            where_sql = " WHERE " + " AND ".join(filtered_conds)
                        else:
                            where_sql = " WHERE " + random.choice(where_conds)
                    parsed.set("where", None)
                    simplified_sql = parsed.sql()
                    # 保证WHERE前有空格
                    simplified_sql = re.sub(r'(?<! )WHERE', ' WHERE', simplified_sql, flags=re.IGNORECASE)
                    # 拼接WHERE
                    if "WHERE" in simplified_sql.upper():
                        simplified_sql = re.sub(r'\bWHERE\b.*?(GROUP BY|HAVING|ORDER BY|$)', where_sql + r' \1', simplified_sql, flags=re.IGNORECASE|re.DOTALL)
                    else:
                        if "GROUP BY" in simplified_sql.upper():
                            simplified_sql = re.sub(r'(GROUP BY)', where_sql + r' \1', simplified_sql, flags=re.IGNORECASE)
                        elif "HAVING" in simplified_sql.upper():
                            simplified_sql = re.sub(r'(HAVING)', where_sql + r' \1', simplified_sql, flags=re.IGNORECASE)
                        elif "ORDER BY" in simplified_sql.upper():
                            simplified_sql = re.sub(r'(ORDER BY)', where_sql + r' \1', simplified_sql, flags=re.IGNORECASE)
                        else:
                            simplified_sql += where_sql
                else:
                    simplified_sql = parsed.sql()
                simplified_sql = re.sub(r'(?<! )WHERE', ' WHERE', simplified_sql, flags=re.IGNORECASE)
                print(f"   简化后: {simplified_sql}")
                result_pairs.append((q, simplified_sql))
            except Exception as e:
                print(f"   简化失败: {e}")
                result_pairs.append((q, ""))

        return result_pairs

if __name__ == "__main__":

    sql_query = """
    SELECT o.o_orderkey, o.o_orderdate, o.o_totalprice, c.c_name AS customer_name
    FROM orders o
    JOIN customer c ON o.o_custkey = c.c_custkey
    WHERE
        o.o_orderstatus = 'F'
        AND o.o_totalprice > 100000
        AND o.o_orderdate < DATE '1995-03-15'
        AND c.c_mktsegment = 'AUTOMOBILE'
        AND EXISTS (
            SELECT l.l_orderkey
            FROM lineitem l
            WHERE l.l_orderkey = o.o_orderkey
            AND l.l_discount > 0.05
            AND l.l_quantity < 25
        )
    GROUP BY
        o.o_orderkey, o.o_orderdate, o.o_totalprice, c.c_name 
    HAVING
        COUNT(*) > 2
        OR SUM(o.o_totalprice) > 500000
    ORDER BY
        o.o_orderkey ASC; 
    """

    # 提取子查询
    result = extract_and_fix_subqueries(sql_query)
    fixed_sql_list = [fixed for _, fixed in result["fixed_subqueries"]]

    # 简化
    simplifier = SimplifySQL(DB_CONFIG)
    simplified_list = simplifier.simplify_subqueries(fixed_sql_list)
    
    for i, (fixed, simplified) in enumerate(simplified_list, 1):
        print(f"\n简化后的子查询 {i}:\n{simplified}")


