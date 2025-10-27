#构建语法树
from sqlglot import parse_one, exp
from sqlglot.expressions import Expression
from collections import deque
from utils.sql_parser import SQLParser
from typing import Dict, Set, Tuple, List


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
    
    def __init__(self):
        self.parser = SQLParser()
    
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
        # 使用 SQLParser 获取子查询内部的表别名
        subquery_tables = set(self.parser.extract_table_aliases(subquery_sql).keys())
        
        # 使用 SQLParser 获取子查询中的所有列引用
        column_refs = self.parser.extract_column_references(subquery_sql)
        
        external_table_refs = set()
        
        for table_alias, column_name in column_refs:
            if table_alias:  # 有表别名的列引用
                # 如果引用的表不在子查询内部定义，且在外层上下文中存在
                if table_alias not in subquery_tables and table_alias in context_tables:
                    external_table_refs.add(table_alias)
        
        return external_table_refs
    
    def fix_subquery_syntax(self, subquery_sql: str, context_tables: Dict[str, str]) -> str:
        """
        修复子查询语法，添加缺失的外部表引用
        """
        external_refs = self.find_external_column_references(subquery_sql, context_tables)
        
        if not external_refs:
            return subquery_sql
        
        try:
            parsed = parse_one(subquery_sql)
            
            # 确保是 SELECT 语句
            if not isinstance(parsed, exp.Select):
                return subquery_sql
            
            # 获取现有的 FROM 子句
            from_clause = parsed.find(exp.From)
            
            if from_clause:
                # 在现有 FROM 子句基础上添加外部表
                for table_alias in external_refs:
                    table_name = context_tables[table_alias]
                    
                    # 创建新的表引用
                    new_table = exp.Table(this=table_name)
                    if table_alias != table_name:
                        new_table = exp.Alias(this=new_table, alias=table_alias)
                    
                    # 使用 CROSS JOIN 添加表
                    parsed = parsed.join(new_table, join_type="CROSS", copy=False)
            else:
                # 如果没有 FROM 子句，创建一个
                if external_refs:
                    # 取第一个外部表作为主表
                    first_ref = list(external_refs)[0]
                    table_name = context_tables[first_ref]
                    
                    new_table = exp.Table(this=table_name)
                    if first_ref != table_name:
                        new_table = exp.Alias(this=new_table, alias=first_ref)
                    parsed = parsed.from_(new_table, copy=False)
                    
                    # 添加其余的表
                    for table_alias in list(external_refs)[1:]:
                        table_name = context_tables[table_alias]
                        add_table = exp.Table(this=table_name)
                        if table_alias != table_name:
                            add_table = exp.Alias(this=add_table, alias=table_alias)
                        parsed = parsed.join(add_table, join_type="CROSS", copy=False)
            
            return parsed.sql()
            
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
            
            fixed_subqueries.append((original_sql, fixed_sql))
        
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