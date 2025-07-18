import pandas as pd
import sqlglot
from sqlglot import exp

def generate_sql_template(sql_query):
    try:
        tree = sqlglot.parse_one(sql_query)
    except Exception:
        return sql_query

    # 表名映射
    tables = []
    for t in tree.find_all(exp.Table):
        name = t.name
        if name not in tables:
            tables.append(name)
    table_map = {name: f"t{i+1}" for i, name in enumerate(tables)}

    # 列名映射
    col_map = {}
    col_idx = 1

    def replace_columns(node):
        nonlocal col_idx
        # 替换表名
        if isinstance(node, exp.Table):
            if node.name in table_map:
                node.set("this", exp.to_identifier(table_map[node.name]))
        # 替换列名
        if isinstance(node, exp.Column):
            tbl = node.table
            col = node.name
            key = (tbl, col)
            if key not in col_map:
                if tbl and tbl in table_map:
                    col_map[key] = f"{table_map[tbl]}.col{col_idx}"
                else:
                    col_map[key] = f"col{col_idx}"
                col_idx += 1
            # 替换
            if tbl and tbl in table_map:
                node.set("this", exp.to_identifier(col_map[key].split(".")[1]))
                node.set("table", exp.to_identifier(table_map[tbl]))
            else:
                node.set("this", exp.to_identifier(col_map[key]))
                node.set("table", None)
        # 递归
        for arg in node.args.values():
            if isinstance(arg, exp.Expression):
                replace_columns(arg)
            elif isinstance(arg, list):
                for item in arg:
                    if isinstance(item, exp.Expression):
                        replace_columns(item)

    replace_columns(tree)

    # 替换字符串常量、日期、数字
    sql_str = tree.sql()
    import re
    sql_str = re.sub(r"'[^']*'", "'value'", sql_str)
    sql_str = re.sub(r"DATE\s*'[\d\-]+'", "DATE 'YYYY-MM-DD'", sql_str, flags=re.IGNORECASE)
    sql_str = re.sub(r'\b\d+\b', 'X', sql_str)

    return sql_str

