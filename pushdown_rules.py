from rewriter_interface import call_rewriter
from utils.cost_estimator import get_query_cost
from sqlglot import parse_one, exp
from syntax_tree import build_syntax_tree, find_subqueries
from subquery_masker import restore_placeholders
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from typing import List, Dict, Any, Tuple



PUSHDOWN_RULES = [
"AGGREGATE_EXPAND_DISTINCT_AGGREGATES_TO_JOIN",
"FILTER_PROJECT_TRANSPOSE",
"FILTER_TABLE_FUNCTION_TRANSPOSE",
"FILTER_AGGREGATE_TRANSPOSE",
"FILTER_SCAN",
"PROJECT_CORRELATE_TRANSPOSE",
"SORT_JOIN_TRANSPOSE",
"SORT_PROJECT_TRANSPOSE",
"SORT_UNION_TRANSPOSE",
"AGGREGATE_UNION_TRANSPOSE",
"UNION_MERGE",
"UNION_REMOVE",
"UNION_PULL_UP_CONSTANTS",
"AGGREGATE_UNION_AGGREGATE",
"AGGREGATE_UNION_TRANSPOSE",
"JOIN_EXTRACT_FILTER",
"JOIN_LEFT_UNION_TRANSPOSE",
"JOIN_RIGHT_UNION_TRANSPOSE", 
"JOIN_PROJECT_BOTH_TRANSPOSE",
"JOIN_PROJECT_LEFT_TRANSPOSE",
"JOIN_PROJECT_RIGHT_TRANSPOSE", 
"SEMI_JOIN_REMOVE",
"JOIN_REDUCE_EXPRESSIONS",
"JOIN_CONDITION_PUSH"
] 

UNION_RULES = ["UNION_TO_DISTINCT"]




def process_single_masked_query(args: Tuple[int, str, str, Dict, Dict]) -> Dict[str, Any]:
    """
    Function to process a single masked query (for parallelization)
    
    Args:
        args: (idx, sql, database, sub_map, db_config)
    
    Returns:
        Dict: Dictionary containing the processing result
    """
    idx, sql, database, sub_map, db_config = args
    
    try:
        rules = []

        # for rule in PUSHDOWN_RULES:
        #     apply_single_rule = call_rewriter(database, sql, [rule]).replace("$", "")
        #     if apply_single_rule != sql:
        #         rules.append(rule)
  
        def check_single_rule(rule):
            """check if a single rule can be applied"""
            try:
                apply_single_rule = call_rewriter(database, sql, [rule]).replace("$", "")
                if apply_single_rule != sql:
                    return rule
                return None
            except Exception as e:
                print(f"      rule {rule} fail: {e}")
                return None

    
        # check all rules in parallel
        with ThreadPoolExecutor(max_workers=min(len(PUSHDOWN_RULES), 8)) as executor:
            future_to_rule = {
                executor.submit(check_single_rule, rule): rule 
                for rule in PUSHDOWN_RULES
            }
            
            for future in as_completed(future_to_rule):
                result = future.result()
                if result is not None:
                    rules.append(result)

        if not rules:
            return {
                'idx': idx,
                'sql': sql,
                'rewritten': sql,
                'restored': sql,
                'new_cost': float("inf"),
                'status': 'skipped'
            }

        print("FINAL PUSHDOWN_RULES:", rules)
        
        rewritten = call_rewriter(database, sql, rules).replace("$", "")
        
        print(f"  Masked SQL {idx} - before rewrite: {sql}...")
        print(f"  Masked SQL {idx} - after rewrite: {rewritten}...")

        restored = restore_placeholders(rewritten, sub_map, db_config)
        
        new_cost = get_query_cost(db_config, restored)
        
        after_union_rule_sql = call_rewriter(database, restored, UNION_RULES).replace("$", "")
        if after_union_rule_sql != restored:
            after_union_rule_cost = get_query_cost(db_config, after_union_rule_sql)
            if after_union_rule_cost < new_cost:
                restored = after_union_rule_sql
                new_cost = after_union_rule_cost
        
        if new_cost < 1:
            new_cost = float("inf")
        
        print(f"  Masked SQL {idx} finish, cost: {new_cost:.2f}")
        
        return {
            'idx': idx,
            'sql': sql,
            'rewritten': rewritten,
            'restored': restored,
            'new_cost': new_cost,
            'status': 'success'
        }
        
    except Exception as e:
        return {
            'idx': idx,
            'sql': sql,
            'rewritten': sql,
            'restored': sql,
            'new_cost': float("inf"),
            'status': 'error',
            'error': str(e)
        }

def apply_pushdown_rules_parallel(
    masked_subqueries: List[str], 
    db_config: Dict[str, Any], 
    sub_map: Dict[str, str],
    max_workers: int = 4
) -> str:
    """
    Parallel version of apply_pushdown_rules

    Args:
        masked_subqueries: List of masked subqueries
        db_config: Database configuration
        sub_map: Subquery placeholder mapping
        max_workers: Maximum number of parallel worker threads

    Returns:
        str: The optimal SQL query
    """
    print("\n======PUSHDOWN RULES======")
    
    original_sql = masked_subqueries[0]
    base_cost = get_query_cost(db_config, original_sql)
    
    # prepare
    database = db_config["database"]
    if database == "tpch10g" or database == "tpch5g" or database == "tpch1g":
        database = "tpch"
    
    
    parallel_args = [
        (idx, sql, database, sub_map, db_config)
        for idx, sql in enumerate(masked_subqueries)
    ]
    
    results = []
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(process_single_masked_query, args): args[0]
            for args in parallel_args
        }
        
        for future in as_completed(future_to_idx):
            result = future.result()
            results.append(result)
    
    results.sort(key=lambda x: x['idx'])
    
    processing_time = time.time() - start_time
    
    # greedy selection of the best result
    best_delta = 0
    best_sql = None
    best_idx = -1
    best_new_sql = None
    
    for result in results:
        idx = result['idx']
        
        if result['status'] == 'error':
            print(f"  Masked SQL {idx} : {result.get('error', 'Unknown error')}")
            continue
        
        new_cost = result['new_cost']
        delta = base_cost - new_cost
        
        print(f"  Masked SQL {idx} uses PUSHDOWN RULES: cost {base_cost:.2f} → {new_cost:.2f}, decline {delta:.2f}")
        print("-------")
        
        if delta > best_delta:
            best_delta = delta
            best_sql = result['sql']
            best_idx = idx
            best_new_sql = result['restored']
    
 
    if best_delta > 0 and best_new_sql:
        print(f" Masked SQL {best_idx} uses PUSHDOWN_RULES, cost decline {best_delta:.2f}")
    else:
        best_new_sql = original_sql
        print("no further cost decline, stop")
    
    print(f"  final SQL: {best_new_sql}")
    return best_new_sql

def apply_pushdown_rules_batch_parallel(
    masked_subqueries: List[str], 
    db_config: Dict[str, Any], 
    sub_map: Dict[str, str],
    batch_size: int = 50,
    max_workers: int = 4
) -> str:
    """
    Batch parallel processing for a large number of masked queries

    Args:
        masked_subqueries: List of masked subqueries
        db_config: Database configuration
        sub_map: Subquery placeholder mapping
        batch_size: Number of queries per batch
        max_workers: Maximum number of parallel worker threads per batch

    Returns:
        str: The optimal SQL query
    """
    print("\n======PUSHDOWN RULES======")
    
    original_sql = masked_subqueries[0]
    base_cost = get_query_cost(db_config, original_sql)
    
    database = db_config["database"]
    if database == "tpch10g" or database == "tpch5g" or database == "tpch1g":
        database = "tpch"
    

    
    all_results = []
    total_batches = (len(masked_subqueries) + batch_size - 1) // batch_size
    
    for batch_idx in range(0, len(masked_subqueries), batch_size):
        batch_queries = masked_subqueries[batch_idx:batch_idx + batch_size]
        batch_num = batch_idx // batch_size + 1
        

        parallel_args = [
            (batch_idx + i, sql, database, sub_map, db_config)
            for i, sql in enumerate(batch_queries)
        ]
        

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(process_single_masked_query, args): args[0]
                for args in parallel_args
            }
            
            batch_results = []
            for future in as_completed(future_to_idx):
                result = future.result()
                batch_results.append(result)
            
            batch_results.sort(key=lambda x: x['idx'])
            all_results.extend(batch_results)
    
    best_delta = 0
    best_sql = None
    best_idx = -1
    best_new_sql = None
    
    for result in all_results:
        idx = result['idx']
        
        if result['status'] == 'error':
            print(f"  Masked SQL {idx} fail: {result.get('error', 'Unknown error')}")
            continue
        
        new_cost = result['new_cost']
        delta = base_cost - new_cost
        
        print(f"  Masked SQL {idx} uses PUSHDOWN RULES: cost {base_cost:.2f} → {new_cost:.2f}, decline {delta:.2f}")
        
        if delta > best_delta:
            best_delta = delta
            best_sql = result['sql']
            best_idx = idx
            best_new_sql = result['restored']
    

    if best_delta > 0 and best_new_sql:
        print(f" Masked SQL {best_idx} uses PUSHDOWN_RULES, cost decline {best_delta:.2f}")
    else:
        best_new_sql = original_sql
        print("no further cost decline, stop")
    
    print(f"  final SQL: {best_new_sql}")
    return best_new_sql


def apply_pushdown_rules(masked_subqueries, db_config, sub_map):
    
    return apply_pushdown_rules_parallel(
        masked_subqueries, 
        db_config, 
        sub_map, 
        max_workers=4
    )


if __name__ == "__main__":

    from config import DB_CONFIG
    from syntax_tree import extract_and_fix_subqueries
    from subquery_masker import mask_all_but_one_subquery

    
    sql_query = """
    SELECT * FROM (SELECT * FROM orders WHERE o_orderdate >= CAST('1995-01-01' AS DATE) UNION ALL SELECT * FROM orders WHERE o_orderdate < CAST('1997-01-01' AS DATE)) AS o JOIN customer AS c ON o.o_custkey = c.c_custkey AND c.c_nationkey = 1
    """
    

    extraction_result = extract_and_fix_subqueries(sql_query)
    fixed_subqueries = extraction_result["fixed_subqueries"]
    
    # masked queries
    masked_sqls, sub_map = mask_all_but_one_subquery(fixed_subqueries[0][1])
    
    
    result2 = apply_pushdown_rules_parallel(
        masked_sqls, 
        DB_CONFIG, 
        sub_map, 
        max_workers=8
    )
    print(result2)