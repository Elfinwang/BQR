# #algorithm 3
from rewriter_interface import call_rewriter
from utils.cost_estimator import get_query_cost
from sqlglot import parse_one, exp
from syntax_tree import build_syntax_tree, find_subqueries
from subquery_masker import mask_all_but_one_subquery, restore_placeholders
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading
from typing import List, Dict, Any, Tuple


FLATTEN_RULES = [
    "FILTER_INTO_JOIN",
    "FILTER_CORRELATE",
]



def process_single_flatten_query(args: Tuple[int, str, str, Dict, Dict]) -> Dict[str, Any]:
    """
    Function to process a single flatten query (for parallelization)
    
    Args:
        args: (idx, sql, database, sub_map, db_config)
    
    Returns:
        Dict: Dictionary containing the processing result
    """
    idx, sql, database, sub_map, db_config = args
    
    try:
        
        rewritten = call_rewriter(database, sql, FLATTEN_RULES)
        rewritten = rewritten.replace("$", "")
        
        print(f"  Masked SQL {idx} - before rewrite: {sql[:100]}...")
        print(f"  Masked SQL {idx} - after rewrite: {rewritten[:100]}...")
        

        restored = restore_placeholders(rewritten, sub_map, db_config)
        

        new_cost = get_query_cost(db_config, restored)
        if new_cost < 1:
            new_cost = float("inf")
        
        print(f"  Masked SQL {idx} finished, cost: {new_cost:.2f}")
        
        return {
            'idx': idx,
            'sql': sql,
            'rewritten': rewritten,
            'restored': restored,
            'new_cost': new_cost,
            'status': 'success'
        }
        
    except Exception as e:
        print(f"   Masked SQL {idx} fail: {e}")
        return {
            'idx': idx,
            'sql': sql,
            'rewritten': None,
            'restored': None,
            'new_cost': float("inf"),
            'status': 'error',
            'error': str(e)
        }

def apply_flatten_rules_parallel(
    masked_subqueries: List[str], 
    db_config: Dict[str, Any], 
    sub_map: Dict[str, str],
    max_workers: int = 4
) -> str:
    """
    Parallel version of apply_flatten_rules

    Args:
        masked_subqueries: List of masked subqueries
        db_config: Database configuration
        sub_map: Mapping of subquery placeholders
        max_workers: Maximum number of parallel worker threads

    Returns:
        str: The optimal SQL query
    """
    print("\n======FLATTEN RULES======")
    
    original_sql = masked_subqueries[0]
    base_cost = get_query_cost(db_config, original_sql)
    
    database = db_config["database"]
    if database == "tpch10g" or database == "tpch5g" or database == "tpch1g":
        database = "tpch"
    
    print(f"original cost: {base_cost:.2f}")
    print(f"start to process {len(masked_subqueries)} masked queries...")
    
    # prepare parallel arguments
    parallel_args = [
        (idx, sql, database, sub_map, db_config)
        for idx, sql in enumerate(masked_subqueries)
    ]
    
    # parallel processing
    results = []
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(process_single_flatten_query, args): args[0]
            for args in parallel_args
        }
        

        for future in as_completed(future_to_idx):
            result = future.result()
            results.append(result)

    results.sort(key=lambda x: x['idx'])
    
    processing_time = time.time() - start_time
    
    # greddy selection of the best result
    best_delta = 0
    best_sql = None
    best_idx = -1
    best_new_sql = None
    
    for result in results:
        idx = result['idx']
        
        if result['status'] == 'error':
            continue
        
        new_cost = result['new_cost']
        delta = base_cost - new_cost
        
        
        if delta > best_delta:
            best_delta = delta
            best_sql = result['sql']
            best_idx = idx
            best_new_sql = result['restored']
    
    # output final result
    if best_delta > 0 and best_new_sql:
        print(f"Masked SQL {best_idx} uses FLATTEN_RULES, cost decline {best_delta:.2f}")
    else:
        best_new_sql = original_sql
        print("no more cost reduction, stop applying FLATTEN_RULES")
    
    print(f"  final SQL: {best_new_sql}")
    return best_new_sql

def apply_flatten_rules_batch_parallel(
    masked_subqueries: List[str], 
    db_config: Dict[str, Any], 
    sub_map: Dict[str, str],
    batch_size: int = 50,
    max_workers: int = 4
) -> str:
    """
    Batch parallel processing of large numbers of masked queries

    Args:
        masked_subqueries: List of masked subqueries
        db_config: Database configuration
        sub_map: Mapping of subquery placeholders
        batch_size: Number of queries per batch
        max_workers: Maximum number of parallel worker threads per batch

    Returns:
        str: The optimal SQL query
    """
    print("\n======FLATTEN RULES======")
    
    original_sql = masked_subqueries[0]
    base_cost = get_query_cost(db_config, original_sql)
    
    # prepare database config
    database = db_config["database"]
    if database == "tpch10g" or database == "tpch5g" or database == "tpch1g":
        database = "tpch"
    
    
    all_results = []
    total_batches = (len(masked_subqueries) + batch_size - 1) // batch_size
    
    for batch_idx in range(0, len(masked_subqueries), batch_size):
        batch_queries = masked_subqueries[batch_idx:batch_idx + batch_size]
        batch_num = batch_idx // batch_size + 1
        
        
        # prepare parallel arguments for the current batch
        parallel_args = [
            (batch_idx + i, sql, database, sub_map, db_config)
            for i, sql in enumerate(batch_queries)
        ]
        
        # process
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(process_single_flatten_query, args): args[0]
                for args in parallel_args
            }
            
            batch_results = []
            for future in as_completed(future_to_idx):
                result = future.result()
                batch_results.append(result)
            
            # sort results by index
            batch_results.sort(key=lambda x: x['idx'])
            all_results.extend(batch_results)
    
    # greedy selection of the best result
    best_delta = 0
    best_sql = None
    best_idx = -1
    best_new_sql = None
    
    for result in all_results:
        idx = result['idx']
        
        if result['status'] == 'error':
            continue
        
        new_cost = result['new_cost']
        delta = base_cost - new_cost
        
        print(f"  Masked SQL {idx} uses FLATTEN RULES: cost {base_cost:.2f} → {new_cost:.2f}, decline {delta:.2f}")
        
        if delta > best_delta:
            best_delta = delta
            best_sql = result['sql']
            best_idx = idx
            best_new_sql = result['restored']
    
    if best_delta > 0 and best_new_sql:
        print(f"Masked SQL {best_idx} uses FLATTEN_RULES, cost decline {best_delta:.2f}")
    else:
        best_new_sql = original_sql
        print("no more cost reduction, stop applying FLATTEN_RULES")
    
    print(f"  final SQL: {best_new_sql}")
    return best_new_sql


def apply_flatten_rules(masked_subqueries, db_config, sub_map):

    return apply_flatten_rules_parallel(
        masked_subqueries, 
        db_config, 
        sub_map, 
        max_workers=4
    )



