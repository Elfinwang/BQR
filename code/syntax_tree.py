#构建语法树
import json
import re
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from sqlglot import parse_one, exp
from sqlglot.expressions import Expression

from config import DB_CONFIG
from rename_group_alias import align_group_by_with_select
from utils.sql_parser import SQLParser

REPO_ROOT = Path(__file__).resolve().parent
SCHEMA_DIR = REPO_ROOT / "data" / "schemas"
DEFAULT_DB_ID = str(DB_CONFIG.get("database", "tpch")).strip()

TPCH_PREFIX_TO_TABLE = {
    "ps": "partsupp",
    "l": "lineitem",
    "p": "part",
    "s": "supplier",
    "c": "customer",
    "o": "orders",
    "n": "nation",
    "r": "region",
}


@dataclass(frozen=True)
class CorrelatedColumnReplacement:
    original_sql: str
    outer_alias: str
    table_name: str
    column_name: str
    column_type: str
    placeholder_column: str
    placeholder_literal_sql: str
    placeholder_match_sqls: Tuple[str, ...] = ()


@dataclass(frozen=True)
class StandaloneSubqueryPreparation:
    original_sql: str
    prepared_sql: str
    placeholder_context_alias: str = ""
    replacements: Tuple[CorrelatedColumnReplacement, ...] = ()
    external_aliases: Tuple[str, ...] = ()


def _schema_path(db_id: str) -> Path:
    db = str(db_id or DEFAULT_DB_ID).strip()
    return SCHEMA_DIR / f"{db}.json"


@lru_cache(maxsize=16)
def _load_schema_column_types(db_id: str) -> Dict[str, Dict[str, str]]:
    path = _schema_path(db_id)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: Dict[str, Dict[str, str]] = {}
    for table in payload:
        table_name = str(table.get("table") or "").lower()
        cols: Dict[str, str] = {}
        for col in table.get("columns", []):
            col_name = str(col.get("name") or "").lower()
            cols[col_name] = str(col.get("type") or "")
        if cols:
            out[table_name] = cols
    return out


def _placeholder_literal_for_type(type_name: str, token: str) -> str:
    t = (type_name or "").strip().lower()
    token_num = int(re.sub(r"\D+", "", token) or "0")

    if any(x in t for x in ("char", "text", "string")):
        raw_sql = f"'__DG_CORR_LITERAL_{token_num}__'"
    elif "timestamp" in t:
        month = (token_num % 12) + 1
        day = (token_num % 27) + 1
        second = token_num % 60
        raw_sql = f"TIMESTAMP '1901-{month:02d}-{day:02d} 00:00:{second:02d}'"
    elif t.startswith("date") or ("date" in t and "update" not in t):
        month = (token_num % 12) + 1
        day = (token_num % 27) + 1
        raw_sql = f"DATE '1901-{month:02d}-{day:02d}'"
    elif "time" in t and "timestamp" not in t:
        second = token_num % 60
        raw_sql = f"TIME '00:00:{second:02d}'"
    elif "interval" in t:
        raw_sql = f"INTERVAL '{1000 + token_num}' DAY"
    elif "bool" in t:
        raw_sql = "TRUE" if token_num % 2 == 0 else "FALSE"
    elif any(x in t for x in ("numeric", "decimal", "double", "float", "real")):
        raw_sql = str(-900000000.123 - token_num)
    elif any(x in t for x in ("int", "number")):
        raw_sql = str(-2147483000 - token_num)
    else:
        raw_sql = f"'__DG_CORR_LITERAL_{token_num}__'"

    try:
        return parse_one(raw_sql).sql()
    except Exception:
        return raw_sql


def _placeholder_match_sqls(placeholder_literal_sql: str, type_name: str) -> Tuple[str, ...]:
    matches = {placeholder_literal_sql, " ".join(placeholder_literal_sql.split())}
    t = (type_name or "").strip().lower()

    date_match = re.search(r"'(\d{4}-\d{2}-\d{2})'", placeholder_literal_sql)
    time_match = re.search(r"'(\d{2}:\d{2}:\d{2})'", placeholder_literal_sql)
    ts_match = re.search(r"'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'", placeholder_literal_sql)

    if ts_match and "timestamp" in t:
        matches.add(f"TIMESTAMP '{ts_match.group(1)}'")
        matches.add(f"CAST('{ts_match.group(1)}' AS TIMESTAMP)")
    elif date_match and ("date" in t and "update" not in t):
        matches.add(f"DATE '{date_match.group(1)}'")
        matches.add(f"CAST('{date_match.group(1)}' AS DATE)")
    elif time_match and "time" in t and "timestamp" not in t:
        matches.add(f"TIME '{time_match.group(1)}'")
        matches.add(f"CAST('{time_match.group(1)}' AS TIME)")

    return tuple(sorted(matches))


class SyntaxTreeNode:
    def __init__(self, expression: Expression, parent=None):
        self.expression = expression
        self.children = []
        self.parent = parent

    def add_child(self, child_node):
        self.children.append(child_node)


    def is_subquery(self) -> bool:
        """
        判断是否是子查询节点（如 SELECT、SUBQUERY、UNION、CTE）
        """
        if isinstance(self.expression, (exp.Select, exp.Union)):
            return True
        if isinstance(self.expression, exp.CTE):
            expressions = self.expression.args.get("expressions")
            return bool(expressions)
        return False

    def to_sql(self) -> str:
        """
        返回当前节点的 SQL 表达
        """
        return self.expression.sql()

    def __repr__(self):
        return f"SyntaxTreeNode({type(self.expression).__name__}, sql={self.to_sql()})"


class SubqueryFixer:
    """
    子查询修复器，用于修复子查询使其能够独立执行
    """
    
    def __init__(self, db_id: str = DEFAULT_DB_ID):
        self.parser = SQLParser()
        self.db_id = str(db_id or DEFAULT_DB_ID).strip()
    
    def extract_outer_context_tables(self, main_sql: str) -> Dict[str, str]:
        """
        从主查询中提取外层上下文表信息
        返回: {table_alias: table_name}
        """
        # 直接使用 SQLParser 的方法
        return self.parser.extract_table_aliases(main_sql)
    
    def find_external_column_references(self, subquery_sql: str, context_tables: Dict[str, str]) -> Set[str]:
        """
        找到子查询中引用的外部表别名
        """
        prep = self.prepare_subquery_for_standalone(subquery_sql, context_tables)
        return set(prep.external_aliases)

    def _aliases_for_table(self, table_name: str, context_tables: Dict[str, str]) -> List[str]:
        return [alias for alias, tname in context_tables.items() if tname.lower() == table_name.lower()]

    def _extract_local_table_aliases(self, parsed: exp.Expression) -> Dict[str, str]:
        aliases: Dict[str, str] = {}
        for table in parsed.find_all(exp.Table):
            aliases[table.alias_or_name] = table.name
        return aliases

    def _resolve_outer_reference(
        self,
        column: exp.Column,
        local_tables: Dict[str, str],
        context_tables: Dict[str, str],
        schema_types: Dict[str, Dict[str, str]],
    ) -> Optional[Tuple[str, str]]:
        table_alias = (column.table or "").strip()
        column_name = (column.name or "").strip()
        if not column_name:
            return None

        if table_alias:
            if table_alias not in local_tables and table_alias in context_tables:
                return table_alias, context_tables[table_alias]
            return None

        if "_" not in column_name:
            return None

        # If any local table can legally provide this unqualified column, treat it as local.
        lowered_col = column_name.lower()
        for table_name in local_tables.values():
            if lowered_col in schema_types.get(str(table_name).lower(), {}):
                return None

        prefix = column_name.split("_", 1)[0].lower()
        table_name = TPCH_PREFIX_TO_TABLE.get(prefix)
        if not table_name:
            return None

        for alias in self._aliases_for_table(table_name, context_tables):
            if alias not in local_tables:
                return alias, context_tables[alias]
        return None

    def _collect_correlated_replacements(
        self, parsed: exp.Expression, context_tables: Dict[str, str]
    ) -> List[CorrelatedColumnReplacement]:
        local_tables = self._extract_local_table_aliases(parsed)
        schema_types = _load_schema_column_types(self.db_id)
        seen: Set[Tuple[str, str]] = set()
        replacements: List[CorrelatedColumnReplacement] = []

        for column in parsed.find_all(exp.Column):
            resolved = self._resolve_outer_reference(column, local_tables, context_tables, schema_types)
            if resolved is None:
                continue
            outer_alias, table_name = resolved
            dedupe_key = (column.sql(), outer_alias)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            idx = len(replacements)
            placeholder_column = f"__dg_corr_{idx}__"
            token = f"__DG_CORR_VALUE_{idx}__"
            col_type = schema_types.get(str(table_name).lower(), {}).get(column.name.lower(), "")
            placeholder_literal_sql = _placeholder_literal_for_type(col_type, token)
            replacements.append(
                CorrelatedColumnReplacement(
                    original_sql=column.sql(),
                    outer_alias=outer_alias,
                    table_name=table_name,
                    column_name=column.name,
                    column_type=col_type,
                    placeholder_column=placeholder_column,
                    placeholder_literal_sql=placeholder_literal_sql,
                    placeholder_match_sqls=_placeholder_match_sqls(placeholder_literal_sql, col_type),
                )
            )
        return replacements

    def prepare_subquery_for_standalone(
        self, subquery_sql: str, context_tables: Dict[str, str]
    ) -> StandaloneSubqueryPreparation:
        """
        将相关子查询改写成可独立送入 Calcite 的形式，但不引入真实外层表。

        方案：
        1. 识别子查询里引用的外层列；
        2. 直接用与列类型匹配的特殊常值替换这些外层列；
        3. 后续在拼回完整 SQL 前，再把这些特殊常值严格还原成原始外层列表达式。
        """
        try:
            parsed = parse_one(subquery_sql)
        except Exception:
            return StandaloneSubqueryPreparation(
                original_sql=subquery_sql,
                prepared_sql=subquery_sql,
            )

        if not isinstance(parsed, exp.Select):
            return StandaloneSubqueryPreparation(
                original_sql=subquery_sql,
                prepared_sql=subquery_sql,
            )

        replacements = self._collect_correlated_replacements(parsed, context_tables)
        if not replacements:
            return StandaloneSubqueryPreparation(
                original_sql=subquery_sql,
                prepared_sql=subquery_sql,
            )

        replacement_by_sql = {rep.original_sql: rep for rep in replacements}

        def visit(node: exp.Expression) -> exp.Expression:
            if isinstance(node, exp.Column):
                rep = replacement_by_sql.get(node.sql())
                if rep is not None:
                    return parse_one(rep.placeholder_literal_sql)
            return node

        prepared_expr = parsed.transform(visit)

        external_aliases = sorted({rep.outer_alias for rep in replacements})
        return StandaloneSubqueryPreparation(
            original_sql=subquery_sql,
            prepared_sql=prepared_expr.sql(),
            placeholder_context_alias="",
            replacements=tuple(replacements),
            external_aliases=tuple(external_aliases),
        )

    def _restore_subquery_from_standalone_fallback(
        self, rewritten_sql: str, prep: StandaloneSubqueryPreparation
    ) -> str:
        out = rewritten_sql
        for rep in prep.replacements:
            for match_sql in sorted(rep.placeholder_match_sqls, key=len, reverse=True):
                out = out.replace(match_sql, rep.original_sql)
        return " ".join(out.split())

    def restore_subquery_from_standalone(
        self, rewritten_sql: str, prep: StandaloneSubqueryPreparation
    ) -> str:
        """
        将独立重写阶段注入的占位上下文恢复成原始相关列语义。
        """
        if not prep.replacements:
            return rewritten_sql

        try:
            parsed = parse_one(rewritten_sql)
        except Exception:
            return self._restore_subquery_from_standalone_fallback(rewritten_sql, prep)

        match_to_rep: Dict[str, CorrelatedColumnReplacement] = {}
        for rep in prep.replacements:
            for match_sql in rep.placeholder_match_sqls:
                match_to_rep[" ".join(match_sql.split()).lower()] = rep

        def visit(node: exp.Expression) -> exp.Expression:
            node_sql = " ".join(node.sql().split()).lower()
            rep = match_to_rep.get(node_sql)
            if rep is None:
                return node
            return parse_one(rep.original_sql)

        restored_expr = parsed.transform(visit)

        restored_sql = restored_expr.sql()
        if any(rep.placeholder_literal_sql in restored_sql for rep in prep.replacements):
            restored_sql = self._restore_subquery_from_standalone_fallback(restored_sql, prep)
        return restored_sql
    
    def fix_subquery_syntax(self, subquery_sql: str, context_tables: Dict[str, str]) -> str:
        """
        修复子查询语法，使其可独立送入重写器，但不再引入真实外层表。
        """
        try:
            prep = self.prepare_subquery_for_standalone(subquery_sql, context_tables)
            return prep.prepared_sql
        except Exception as e:
            print(f"修复子查询时出错: {e}")
            return subquery_sql

    def fix_all_subqueries_in_tree(self, root: 'SyntaxTreeNode', main_sql: str) -> List[Tuple[str, str]]:
        """
        修复语法树中的所有子查询
        返回: [(原始子查询, 修复后子查询), ...]
        """
        # 提取外层上下文
        context_tables = self.extract_outer_context_tables(main_sql)
        
        # 获取所有子查询节点
        subqueries = find_subqueries(root)
        
        fixed_subqueries = []
        
        
        for subquery_node in subqueries[:]:
            original_sql = subquery_node.to_sql()
            
            # 修复子查询
            fixed_sql = self.fix_subquery_syntax(original_sql, context_tables)
            # 尝试对修复后的子查询应用 GROUP BY 别名 -> 原始表达式的替换
            try:
                aligned_sql = align_group_by_with_select(fixed_sql)
            except Exception:
                aligned_sql = fixed_sql
            fixed_subqueries.append((original_sql, aligned_sql))
        
        return fixed_subqueries
    
    def extract_cte_tables(self, sql_query: str) -> Dict[str, str]:
        """
        提取 WITH 语句中定义的 CTE 表名和其对应的 SQL
        返回: {cte_name: cte_sql}
        """
        result = {}
        try:
            parsed = parse_one(sql_query)
            cte = parsed.args.get("with")
            if cte:
                for cte_exp in cte.expressions:
                    if isinstance(cte_exp, exp.CTE):
                        alias = cte_exp.alias_or_name
                        subquery_sql = cte_exp.this.sql()
                        result[alias] = subquery_sql
        except Exception as e:
            print(f"提取 CTE 表时出错: {e}")
        return result








def build_syntax_tree(sql_query: str) -> SyntaxTreeNode:
    """
    构建 SQL 的语法树结构
    """
    root_exp = parse_one(sql_query)
    root_node = SyntaxTreeNode(root_exp)
    _build_tree_recursive(root_node, root_exp)
    return root_node


def _build_tree_recursive(node: SyntaxTreeNode, expression: Expression):
    for child in expression.args.values():
        if isinstance(child, list):
            for item in child:
                if isinstance(item, Expression):
                    child_node = SyntaxTreeNode(item, parent=node)
                    node.add_child(child_node)
                    _build_tree_recursive(child_node, item)
        elif isinstance(child, Expression):
            child_node = SyntaxTreeNode(child, parent=node)
            node.add_child(child_node)
            _build_tree_recursive(child_node, child)

        # 特别处理 CTE 中的每个子查询
        if isinstance(expression, exp.CTE):
            expressions = expression.args.get("expressions")
            if expressions:
                for cte in expressions:
                    if isinstance(cte, exp.CTE):
                        # cte.this 是子查询，cte.alias 是别名
                        sub_node = SyntaxTreeNode(cte.this, parent=node)
                        node.add_child(sub_node)
                        _build_tree_recursive(sub_node, cte.this)


def traverse_tree(node: SyntaxTreeNode):
    """
    先序遍历树
    """
    yield node
    for child in node.children:
        yield from traverse_tree(child)


def find_subqueries_dfs(root: SyntaxTreeNode):
    """
    使用深度优先搜索提取树中的所有子查询节点
    """
    return [node for node in traverse_tree(root) if node.is_subquery()]



def _clean_subquery_sql(sql: str) -> str:
    """
    清理子查询SQL，去除AS别名和处理括号包装
    """
    sql = sql.strip()
    
    # 检查是否以 ) AS xxx 结尾
    import re
    
    # 匹配模式：(...) AS identifier
    as_pattern = r'\)\s+AS\s+\w+\s*$'
    
    if re.search(as_pattern, sql, re.IGNORECASE):
        # 找到 AS 的位置
        as_match = re.search(r'\)\s+AS\s+', sql, re.IGNORECASE)
        if as_match:
            # 截取到 AS 之前的部分
            sql = sql[:as_match.end()-3].strip()  # -3 是为了去掉 " AS"
    
    # 如果整个查询被括号包装，去掉外层括号
    if sql.startswith('(') and sql.endswith(')'):
        # 检查是否是完整的括号包装
        if _is_complete_parentheses(sql):
            sql = sql[1:-1].strip()
    
    return sql

def _is_complete_parentheses(sql: str) -> bool:
    """
    检查是否是完整的括号包装（整个SQL被一对括号包围）
    """
    if not (sql.startswith('(') and sql.endswith(')')):
        return False
    
    paren_count = 0
    for i, char in enumerate(sql):
        if char == '(':
            paren_count += 1
        elif char == ')':
            paren_count -= 1
            # 如果在最后一个字符之前括号计数归零，说明不是完整包装
            if paren_count == 0 and i < len(sql) - 1:
                return False
    
    return paren_count == 0


def find_subqueries(root: SyntaxTreeNode):
    """
    使用广度优先搜索提取树中的所有子查询节点，删除括号包装的项，处理AS别名
    """
    # 第一阶段：收集所有子查询节点
    all_subqueries = []
    queue = deque([root])
    
    while queue:
        node = queue.popleft()
        
        if node.is_subquery():
            all_subqueries.append(node)
        
        for child in node.children:
            queue.append(child)
    
    # 第二阶段：过滤和清理子查询
    result = []
    
    for node in all_subqueries:
        sql = node.to_sql().strip()
        
        # 处理带有 AS 别名的情况
        cleaned_sql = _clean_subquery_sql(sql)
        
        # 如果清理后的SQL是括号包装的，跳过
        if cleaned_sql.startswith('(') and cleaned_sql.endswith(')'):
            continue
        else:
            # 创建一个新的节点包含清理后的SQL
            if cleaned_sql != sql:
                # 如果SQL被清理过，需要重新解析
                try:
                    new_expression = parse_one(cleaned_sql)
                    new_node = SyntaxTreeNode(new_expression, parent=node.parent)
                    result.append(new_node)
                except:
                    # 如果解析失败，使用原节点
                    result.append(node)
            else:
                result.append(node)
    
    return result

def print_tree(node: SyntaxTreeNode, indent: int = 0):
    """
    打印语法树结构
    """
    print("  " * indent + repr(node))
    for child in node.children:
        print_tree(child, indent + 1)

def extract_and_fix_subqueries(sql_query: str) -> Dict:
    """
    主要接口函数：提取并修复子查询
    """
    # 构建语法树
    root = build_syntax_tree(sql_query)
    
    # 创建修复器
    fixer = SubqueryFixer()
    
    # 修复所有子查询
    fixed_subqueries = fixer.fix_all_subqueries_in_tree(root, sql_query)
    
    # 提取外层上下文信息
    context_tables = fixer.extract_outer_context_tables(sql_query)

    cte_tables = fixer.extract_cte_tables(sql_query)

    # external_refs = fixer.find_external_column_references(sql_query, context_tables)
    
    return {
        "original_query": sql_query,
        "syntax_tree": root,
        "context_tables": context_tables,
        "fixed_subqueries": fixed_subqueries,
        "cte_tables": cte_tables,
        "fixer": fixer
    }









if __name__ == "__main__":

    sql_normal = """
    SELECT
      r.r_name,
      c.c_custkey,
      c.c_name,
      (
        SELECT SUM(o.o_totalprice)
        FROM orders o
        WHERE o.o_custkey = c.c_custkey
          AND EXISTS (
            SELECT 1
            FROM nation n2
            JOIN region r2 ON n2.n_regionkey = r2.r_regionkey
            WHERE n2.n_nationkey = c.c_nationkey
              AND r2.r_name = r.r_name
          )
      ) AS total_amount
    FROM customer c
    JOIN nation n ON c.c_nationkey = n.n_nationkey
    JOIN region r ON n.n_regionkey = r.r_regionkey
    GROUP BY r.r_name, c.c_custkey, c.c_name
    """

    # 测试UNION SQL
    sql_union = """
    SELECT COUNT(DISTINCT l_partkey), SUM(DISTINCT l_suppkey) 
    FROM lineitem 
    WHERE l_quantity > 10 
    UNION 
    SELECT COUNT(DISTINCT ps_partkey), SUM(DISTINCT ps_suppkey) 
    FROM partsupp 
    WHERE ps_availqty > 5
    """

    root = build_syntax_tree(sql_union)

    print("SQL语法树结构:")
    print_tree(root)

    print("原始查询:", sql_union)

    print("提取子查询节点:")
    subqueries = find_subqueries(root)
    for i, sub in enumerate(subqueries, 1):
        print(f"  子查询 {i}: {sub.to_sql()}")


    # 测试所有类型的SQL
    for sql_name, sql in [ ("普通SQL", sql_normal), ("UNION SQL", sql_union)]:
        print(f"\n{'='*50}")
        print(f"测试 {sql_name}")
        print(f"{'='*50}")
        
        result = extract_and_fix_subqueries(sql)
        
        if "error" in result:
            continue
        
        print(f"成功处理 {sql_name}")
        print(f"外层上下文表: {len(result['context_tables'])} 个")
        print(f"CTE表: {len(result['cte_tables'])} 个")
        print(f"子查询数量: {len(result['fixed_subqueries'])} 个")
        
        if result['fixed_subqueries']:
            print("\n修复的子查询:")
            for i, (original, fixed) in enumerate(result['fixed_subqueries'], 1):
                print(f"  {i}. 原始: {original}")
                print(f"     修复: {fixed}")