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
    处理单个flatten查询的函数（用于并行化）
    
    Args:
        args: (idx, sql, database, sub_map, db_config)
    
    Returns:
        Dict: 包含处理结果的字典
    """
    idx, sql, database, sub_map, db_config = args
    
    try:
        print(f"  🔄 开始处理 Masked SQL {idx} - flatten rules")
        
        # 调用rewriter
        rewritten = call_rewriter(database, sql, FLATTEN_RULES)
        rewritten = rewritten.replace("$", "")
        
        print(f"  📝 Masked SQL {idx} - before rewrite: {sql[:100]}...")
        print(f"  📝 Masked SQL {idx} - after rewrite: {rewritten[:100]}...")
        
        # 还原占位符
        restored = restore_placeholders(rewritten, sub_map, db_config)
        
        # 计算成本
        new_cost = get_query_cost(db_config, restored)
        if new_cost < 1:
            new_cost = float("inf")
        
        print(f"  ✅ Masked SQL {idx} 处理完成，成本: {new_cost:.2f}")
        
        return {
            'idx': idx,
            'sql': sql,
            'rewritten': rewritten,
            'restored': restored,
            'new_cost': new_cost,
            'status': 'success'
        }
        
    except Exception as e:
        print(f"  ❌ Masked SQL {idx} 处理失败: {e}")
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
    并行版本的apply_flatten_rules
    
    Args:
        masked_subqueries: 被masked的子查询列表
        db_config: 数据库配置
        sub_map: 子查询占位符映射
        max_workers: 最大并行工作线程数
    
    Returns:
        str: 最优的SQL查询
    """
    print("\n======step3: 并行应用 FLATTEN RULES======")
    
    original_sql = masked_subqueries[0]
    base_cost = get_query_cost(db_config, original_sql)
    
    # 准备数据库名称
    database = db_config["database"]
    if database == "tpch10g" or database == "tpch5g" or database == "tpch1g":
        database = "tpch"
    
    print(f"原始SQL成本: {base_cost:.2f}")
    print(f"开始并行处理 {len(masked_subqueries)} 个masked queries...")
    
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
            executor.submit(process_single_flatten_query, args): args[0]
            for args in parallel_args
        }
        
        # 收集结果
        for future in as_completed(future_to_idx):
            result = future.result()
            results.append(result)
    
    # 按索引排序
    results.sort(key=lambda x: x['idx'])
    
    processing_time = time.time() - start_time
    print(f"⏱️ 并行处理完成，耗时: {processing_time:.2f}秒")
    
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
        
        print(f"  Masked SQL {idx} 应用 FLATTEN RULES：成本 {base_cost:.2f} → {new_cost:.2f}，降低 {delta:.2f}")
        print("-------")
        
        if delta > best_delta:
            best_delta = delta
            best_sql = result['sql']
            best_idx = idx
            best_new_sql = result['restored']
    
    # 输出最终结果
    if best_delta > 0 and best_new_sql:
        print(f"[选择] Masked SQL {best_idx} 应用FLATTEN_RULES，成本降低 {best_delta:.2f}")
    else:
        best_new_sql = original_sql
        print("[终止] 没有进一步成本降低")
    
    print(f"  最终子查询 SQL: {best_new_sql}")
    return best_new_sql

def apply_flatten_rules_batch_parallel(
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
    print("\n======step3: 分批并行应用 FLATTEN RULES======")
    
    original_sql = masked_subqueries[0]
    base_cost = get_query_cost(db_config, original_sql)
    
    # 准备数据库名称
    database = db_config["database"]
    if database == "tpch10g" or database == "tpch5g" or database == "tpch1g":
        database = "tpch"
    
    print(f"原始SQL成本: {base_cost:.2f}")
    print(f"开始分批并行处理 {len(masked_subqueries)} 个masked queries...")
    
    all_results = []
    total_batches = (len(masked_subqueries) + batch_size - 1) // batch_size
    
    for batch_idx in range(0, len(masked_subqueries), batch_size):
        batch_queries = masked_subqueries[batch_idx:batch_idx + batch_size]
        batch_num = batch_idx // batch_size + 1
        
        print(f"\n--- 处理第 {batch_num}/{total_batches} 批 ({len(batch_queries)} 个queries) ---")
        
        # 准备当前批次的参数
        parallel_args = [
            (batch_idx + i, sql, database, sub_map, db_config)
            for i, sql in enumerate(batch_queries)
        ]
        
        # 并行处理当前批次
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(process_single_flatten_query, args): args[0]
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
        
        print(f"  Masked SQL {idx} 应用 FLATTEN RULES：成本 {base_cost:.2f} → {new_cost:.2f}，降低 {delta:.2f}")
        
        if delta > best_delta:
            best_delta = delta
            best_sql = result['sql']
            best_idx = idx
            best_new_sql = result['restored']
    
    # 输出最终结果
    if best_delta > 0 and best_new_sql:
        print(f"[选择] Masked SQL {best_idx} 应用FLATTEN_RULES，成本降低 {best_delta:.2f}")
    else:
        best_new_sql = original_sql
        print("[终止] 没有进一步成本降低")
    
    print(f"  最终子查询 SQL: {best_new_sql}")
    return best_new_sql

# 为了保持向后兼容，可以保留原函数名
def apply_flatten_rules(masked_subqueries, db_config, sub_map):
    """
    兼容性函数：默认使用并行版本
    """
    return apply_flatten_rules_parallel(
        masked_subqueries, 
        db_config, 
        sub_map, 
        max_workers=4
    )







# def apply_flatten_rules(masked_subqueries, db_config, sub_map):
#     """
#     Algorithm 3: 贪心推导扁平化规则

#     参数:
#     - fixed_subqueries: List of (original_sql, fixed_sql)
#     - db_config: dict 类型，包含数据库连接信息
#     - sub_map: 包含子查询占位符与原始子查询的映射关系
#     """

#     print("\n======step3: 应用 FLATTEN RULES======")

#     original_sql = masked_subqueries[0]
#     base_cost = get_query_cost(db_config, original_sql)

#     idx = 0
#     best_delta = 0
#     best_sql = None
#     best_idx = -1
#     best_new_sql = None
    

#     for sql in masked_subqueries:
#     # for sql in masked_subqueries[1:]:
#         print(f"Masked SQL {idx}: flatten rules")
#         current_sql = sql

    
#         # base_cost = get_query_cost(db_config, current_sql)

#         try:
#             # rule_list = [rule]
#             database = db_config["database"]
#             if database == "tpch10g":
#                 database = "tpch"
#             rewritten = call_rewriter(database, sql, FLATTEN_RULES)
#             rewritten = rewritten.replace("$", "")
#             print("before rewrite:", sql) 
#             print("\n") 
#             print("after rewrite:", rewritten)
#             # 还原占位符
#             restored = restore_placeholders(rewritten, sub_map,db_config)

#             # restored = restore_masked_subqueries(rewritten, subqueries)
#             # print("restored:", restored)
#             # new_cost = get_query_cost(db_config, restored)
#             new_cost = get_query_cost(db_config, restored)
#             if(new_cost < 1):
#                 new_cost = float("inf")
#             delta = base_cost - new_cost
#             print(f"\n  Masked SQL{idx} 应用 FLATTEN RULES：成本 {base_cost:.2f} → {new_cost:.2f}，降低 {delta:.2f}")
#             print("-------")
#             if delta > best_delta:
#                 best_delta = delta
#                 best_sql = sql
#                 best_idx = idx
#                 best_new_sql = restored
#         except Exception as e:
#             print(f"    [跳过] 规则应用失败: {e}")
#         idx += 1


#     if best_delta > 0 and best_new_sql:
#         print(f"[选择] Masked SQL {best_idx} 应用FLATTEN_RULES，成本降低 {best_delta:.2f}")
#         # current_sql = best_new_sql
#     else:
#         best_new_sql = original_sql
#         print("[终止] 没有进一步成本降低")


#     print(f"  最终子查询 SQL: {best_new_sql}")
    
#     return best_new_sql

