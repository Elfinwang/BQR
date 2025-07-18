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
            """检查单个规则是否适用"""
            try:
                apply_single_rule = call_rewriter(database, sql, [rule]).replace("$", "")
                if apply_single_rule != sql:
                    return rule
                return None
            except Exception as e:
                print(f"      规则 {rule} 检查失败: {e}")
                return None

    
        # 使用ThreadPoolExecutor并行检查所有规则
        with ThreadPoolExecutor(max_workers=min(len(PUSHDOWN_RULES), 8)) as executor:
            # 提交所有规则检查任务
            future_to_rule = {
                executor.submit(check_single_rule, rule): rule 
                for rule in PUSHDOWN_RULES
            }
            
            # 收集结果
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
        
        # 计算成本
        new_cost = get_query_cost(db_config, restored)
        
        # 单独应用union规则
        after_union_rule_sql = call_rewriter(database, restored, UNION_RULES).replace("$", "")
        if after_union_rule_sql != restored:
            after_union_rule_cost = get_query_cost(db_config, after_union_rule_sql)
            if after_union_rule_cost < new_cost:
                restored = after_union_rule_sql
                new_cost = after_union_rule_cost
        
        if new_cost < 1:
            new_cost = float("inf")
        
        print(f"  Masked SQL {idx} 处理完成，成本: {new_cost:.2f}")
        
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
    并行版本的apply_pushdown_rules
    
    Args:
        masked_subqueries: 被masked的子查询列表
        db_config: 数据库配置
        sub_map: 子查询占位符映射
        max_workers: 最大并行工作线程数
    
    Returns:
        str: 最优的SQL查询
    """
    print("\n======PUSHDOWN RULES======")
    
    original_sql = masked_subqueries[0]
    base_cost = get_query_cost(db_config, original_sql)
    
    # 准备数据库名称
    database = db_config["database"]
    if database == "tpch10g" or database == "tpch5g" or database == "tpch1g":
        database = "tpch"
    
    
    # 准备并行处理的参数
    parallel_args = [
        (idx, sql, database, sub_map, db_config)
        for idx, sql in enumerate(masked_subqueries)
    ]
    
    # 并行处理所有masked queries
    results = []
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_idx = {
            executor.submit(process_single_masked_query, args): args[0]
            for args in parallel_args
        }
        
        # 收集结果
        for future in as_completed(future_to_idx):
            result = future.result()
            results.append(result)
    
    # 按索引排序
    results.sort(key=lambda x: x['idx'])
    
    processing_time = time.time() - start_time
    
    # 找到最佳结果
    best_delta = 0
    best_sql = None
    best_idx = -1
    best_new_sql = None
    
    for result in results:
        idx = result['idx']
        
        if result['status'] == 'error':
            print(f"  [跳过] Masked SQL {idx} 规则应用失败: {result.get('error', 'Unknown error')}")
            continue
        
        new_cost = result['new_cost']
        delta = base_cost - new_cost
        
        print(f"  Masked SQL {idx} 应用 PUSHDOWN RULES: 成本 {base_cost:.2f} → {new_cost:.2f}，降低 {delta:.2f}")
        print("-------")
        
        if delta > best_delta:
            best_delta = delta
            best_sql = result['sql']
            best_idx = idx
            best_new_sql = result['restored']
    
    # 输出最终结果
    if best_delta > 0 and best_new_sql:
        print(f"[选择] Masked SQL {best_idx} 应用PUSHDOWN_RULES，成本降低 {best_delta:.2f}")
    else:
        best_new_sql = original_sql
        print("[终止] 没有进一步成本降低")
    
    print(f"  最终子查询 SQL: {best_new_sql}")
    return best_new_sql

def apply_pushdown_rules_batch_parallel(
    masked_subqueries: List[str], 
    db_config: Dict[str, Any], 
    sub_map: Dict[str, str],
    batch_size: int = 50,
    max_workers: int = 4
) -> str:
    """
    分批并行处理大量masked queries
    
    Args:
        masked_subqueries: 被masked的子查询列表
        db_config: 数据库配置
        sub_map: 子查询占位符映射
        batch_size: 每批处理的数量
        max_workers: 每批的最大并行工作线程数
    
    Returns:
        str: 最优的SQL查询
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
        
        
        # 准备当前批次的参数
        parallel_args = [
            (batch_idx + i, sql, database, sub_map, db_config)
            for i, sql in enumerate(batch_queries)
        ]
        
        # 并行处理当前批次
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(process_single_masked_query, args): args[0]
                for args in parallel_args
            }
            
            batch_results = []
            for future in as_completed(future_to_idx):
                result = future.result()
                batch_results.append(result)
            
            # 按索引排序
            batch_results.sort(key=lambda x: x['idx'])
            all_results.extend(batch_results)
    
    # 找到全局最佳结果
    best_delta = 0
    best_sql = None
    best_idx = -1
    best_new_sql = None
    
    for result in all_results:
        idx = result['idx']
        
        if result['status'] == 'error':
            print(f"  [跳过] Masked SQL {idx} 规则应用失败: {result.get('error', 'Unknown error')}")
            continue
        
        new_cost = result['new_cost']
        delta = base_cost - new_cost
        
        print(f"  Masked SQL {idx} 应用 PUSHDOWN RULES：成本 {base_cost:.2f} → {new_cost:.2f}，降低 {delta:.2f}")
        
        if delta > best_delta:
            best_delta = delta
            best_sql = result['sql']
            best_idx = idx
            best_new_sql = result['restored']
    
    # 输出最终结果
    if best_delta > 0 and best_new_sql:
        print(f"[选择] Masked SQL {best_idx} 应用PUSHDOWN_RULES，成本降低 {best_delta:.2f}")
    else:
        best_new_sql = original_sql
        print("[终止] 没有进一步成本降低")
    
    print(f"  最终子查询 SQL: {best_new_sql}")
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
    
    # 提取并修复子查询
    extraction_result = extract_and_fix_subqueries(sql_query)
    fixed_subqueries = extraction_result["fixed_subqueries"]
    
    # 生成masked queries
    masked_sqls, sub_map = mask_all_but_one_subquery(fixed_subqueries[0][1])
    
    
    result2 = apply_pushdown_rules_parallel(
        masked_sqls, 
        DB_CONFIG, 
        sub_map, 
        max_workers=8
    )
    print(result2)