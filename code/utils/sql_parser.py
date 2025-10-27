from sqlglot import parse_one, parse, exp
from sqlglot.errors import ParseError
from typing import Dict, List, Set, Tuple
import re
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DB_CONFIG
from utils.cost_estimator import get_query_cost

class SQLParser:

    def __init__(self, db_config: dict = None):

        self.db_config = db_config if db_config else DB_CONFIG
    
    @staticmethod
    def extract_table_aliases(sql: str) -> Dict[str, str]:
        """
        return: {alias: table_name}
        """
        parsed = parse_one(sql)
        aliases = {}
        
        for table in parsed.find_all(exp.Table):
            table_name = table.name
            alias = table.alias_or_name
            aliases[alias] = table_name
            
        return aliases
    
    @staticmethod
    def extract_column_references(sql: str) -> Set[Tuple[str, str]]:
        """
        return: {(table_alias, column_name), ...}
        """
        parsed = parse_one(sql)
        references = set()
        
        for column in parsed.find_all(exp.Column):
            table_alias = column.table or ""
            column_name = column.name
            references.add((table_alias, column_name))
            
        return references
    

    def is_valid_sql(self, sql: str) -> bool:
        """
        Check whether the SQL is syntactically correct and executable.
        Use the database's EXPLAIN functionality for validation.
        """
        if not self.db_config:
            try:
                parse_one(sql)
                return True
            except Exception:
                return False
        
        try:
            cost = get_query_cost(self.db_config, sql)
            print("cost:", cost)
            return cost != float("inf")
        except Exception:
            return False



    def normalize_sql(sql: str) -> str:
        """
        Normalize the SQL to ensure consistent logical formatting.
        """
        try:
            parsed = parse_one(sql)
            return parsed.sql(pretty=True)
        except ParseError:
            return sql




    def is_subquery_expression(expr: exp.Expression) -> bool:

        return isinstance(expr, (exp.Subquery, exp.Select, exp.CTE, exp.Union))


    def pretty_print_subqueries(sql: str):

        parsed = parse_one(sql)
        subqueries = parsed.find_all(lambda e: is_subquery_expression(e))
        for i, sq in enumerate(subqueries, 1):
            print(f"[Subquery {i}] {sq.sql(pretty=True)}")



if __name__ == "__main__":
    test_sql = """
   SELECT SUM(l.l_extendedprice * (1 - l.l_discount))
    FROM lineitem l
    WHERE l.l_orderkey IN (
      SELECT o.o_orderkey
      FROM orders o
      WHERE o.o_custkey = c.c_custkey
        AND EXISTS (
          SELECT 1
          FROM nation n
          JOIN region r2 ON n.n_regionkey = r2.r_regionkey
          WHERE n.n_nationkey = c.c_nationkey
            AND r2.r_name = r.r_name 
        )
    )
    """
    
    parser = SQLParser()

    print("aliases:", parser.extract_table_aliases(test_sql))
    print("references:", parser.extract_column_references(test_sql))
    print(parser.is_valid_sql(test_sql))
