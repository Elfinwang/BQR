from syntax_tree import extract_and_fix_subqueries
from sqlglot import parse_one, exp
from utils.cost_estimator import get_query_cost
import re


def extract_cte(sql_query, db_config):
    """
    Extracts a CTE from the SQL query and returns the rewritten query.
    Only replaces the longest subquery with a single CTE.

    Args:
        sql_query (str): The original SQL query.
        db_config (dict): Database configuration.

    Returns:
        str: The rewritten SQL query.
    """
    try:
        
        result = extract_and_fix_subqueries(sql_query)
        if len(result['fixed_subqueries']) < 1:
            return sql_query
        
        # get subqueries
        subqueries = []
        for i, (original, fixed) in enumerate(result['fixed_subqueries']):
            print(f"subquery {i}: original: {original}, fixed: {fixed}\n\n")
            if(i==0):
                continue
            subqueries.append({
                'id': i,
                'original': original,
                'fixed': fixed,
                'sql': original
            })
        print(f" {len(subqueries)} ")

        
        terminal_nodes = []
        
        for subquery in subqueries:
            if is_worth_materializing(subquery['sql'], db_config):
                try:
                    cost = get_query_cost(db_config, subquery['fixed'])
                    terminal_nodes.append({
                        'subquery': subquery,
                        'cost': cost,
                        'length': len(subquery['original'])  
                    })
                except Exception as e:
                    print(f"can not get cost: {e}")
                    terminal_nodes.append({
                        'subquery': subquery,
                        'cost': len(subquery['original']) * 10,  
                        'length': len(subquery['original'])
                    })
        
        if not terminal_nodes:
            return sql_query
        
        # find subquery to construct CTE
        terminal_nodes.sort(key=lambda x: x['length'], reverse=True)
        best_node = terminal_nodes[0]
        
        cte_name = "cte"
        cte_sql = clean_subquery_for_cte(best_node['subquery']['sql'])
        
        # construct CTE with clause
        with_clause = f"{cte_name} AS ({cte_sql})"
        
        # replace subquery in main query
        rewritten_main_query = sql_query
        original_subquery = best_node['subquery']['original']
        
        # method 1: direct match
        if original_subquery in rewritten_main_query:
            rewritten_main_query = rewritten_main_query.replace(
                original_subquery, cte_name, 1
            )
        else:
            # method 2: structured match
            
            normalized_query = parse_one(sql_query).sql()
            
            if original_subquery in normalized_query:
                normalized_rewritten = normalized_query.replace(
                    original_subquery, cte_name, 1
                )
                rewritten_main_query = normalized_rewritten
            else:
                # method 3: fuzzy match
                
                fuzzy_pattern = create_fuzzy_pattern(original_subquery)
                
                match = re.search(fuzzy_pattern, sql_query, re.IGNORECASE | re.DOTALL)
                if match:
                    rewritten_main_query = sql_query.replace(match.group(0), cte_name, 1)
                else:
                    return sql_query
        
        # clean up CTE name in rewritten query
        rewritten_main_query = re.sub(r'\(\s*cte_\d+\s*\)', cte_name, rewritten_main_query)
        
        # final query
        final_query = f"WITH {with_clause} {rewritten_main_query}"
        
        # cost estimation
        try:
            original_cost = get_query_cost(db_config, sql_query)
            rewritten_cost = get_query_cost(db_config, final_query)
            
            if rewritten_cost <= original_cost:
                print(f"cost: {original_cost:.2f} ->  {rewritten_cost:.2f}")
                return final_query
            else:
                print(f"cost: {original_cost:.2f} ->  {rewritten_cost:.2f}")
                return sql_query
        except Exception as e:
            return final_query
        
    except Exception as e:
        print(f"CTE fail: {e}")
        return sql_query


def create_fuzzy_pattern(subquery_sql):
    """
    Create a fuzzy matching pattern to handle differences in DATE formats.
    """
    pattern = re.escape(subquery_sql)
    
    pattern = pattern.replace(r"CAST\(\'([^\']+)\'\s+AS\s+DATE\)", r"(?:CAST\('\1' AS DATE|DATE '\1')")
    
    pattern = pattern.replace(r"CAST\(\'", r"(?:CAST\('|DATE ')")
    pattern = pattern.replace(r"\'\s+AS\s+DATE\)", r"'(?:\s+AS\s+DATE)?)")
    
    return pattern


def normalize_date_formats(sql):

    sql = re.sub(r"DATE\s+'([^']+)'", r"CAST('\1' AS DATE)", sql, flags=re.IGNORECASE)
    return sql



def is_worth_materializing(sql, db_config):
    """
    Determine whether a subquery is worth materializing as a CTE.
    Uses cost estimation as the metric.
    """
    # cost estimation
    cost = get_query_cost(db_config, sql)
    
    MATERIALIZATION_THRESHOLD = 1000 
    
    return cost > MATERIALIZATION_THRESHOLD

def is_similar_subquery(sql1, sql2):
    """
    Check if two subqueries are similar (can share materialization)
    """
    # simple check
    if sql1.strip() == sql2.strip():
        return True

    # further check: whether sqls rewritten after rules are the same...
    
    return False


def clean_subquery_for_cte(sql):
  
    try:
 
        sql = sql.strip()
        if sql.startswith('(') and sql.endswith(')'):
            paren_count = 0
            for i, char in enumerate(sql):
                if char == '(':
                    paren_count += 1
                elif char == ')':
                    paren_count -= 1
                    if paren_count == 0 and i == len(sql) - 1:
                        sql = sql[1:-1].strip()
                        break
        
        # clean up trailing AS clause
        sql = re.sub(r'\s+AS\s+\w+\s*$', '', sql, flags=re.IGNORECASE)
        
        return sql
        
    except Exception:
        return sql



if __name__ == "__main__":
    from config import DB_CONFIG
    
    test_sql_1 = """
    SELECT * FROM (SELECT * FROM orders WHERE o_orderdate >= DATE '1995-01-01' UNION ALL SELECT * FROM orders WHERE o_orderdate < DATE '1997-01-01') AS o JOIN customer c ON o.o_custkey = c.c_custkey AND c_custkey > 100;
    """
    

    test_cases = [
        ("UNION sql", test_sql_1)
    ]
    
    print("="*80)
    print("CTE test")
    print("="*80)
    
    for test_name, sql in test_cases:
        print(f"\n{'='*60}")
        print(f"test: {test_name}")
        print(f"{'='*60}")
        
        print(f"original sql:")
        print(sql.strip())
        
        try:
            # original cost estimation
            original_cost = get_query_cost(DB_CONFIG, sql)
            print(f"\noriginal cost: {original_cost:.2f}")
            
            # cte
            result = extract_cte(sql, DB_CONFIG)
            
            print(f"\nafter rewrite:")
            print(result.strip())
            
            if result.strip() != sql.strip():
                new_cost = get_query_cost(DB_CONFIG, result)
                print(f"new cost: {new_cost:.2f}")
                print(f" {((new_cost - original_cost) / original_cost * 100):+.1f}%")
                
            
            else:
                print("ℹ  No cte applied")
                
        except Exception as e:
            print(f"fail: {e}")
    
    print(f"\n{'='*80}")
    print("finished")
    print("="*80)
