from syntax_tree import extract_and_fix_subqueries
from subquery_masker import mask_all_but_one_subquery,split_and_conditions, get_string_column_from_from_clause, restore_placeholders
from pushdown_rules import apply_pushdown_rules,apply_pushdown_rules_batch_parallel
from flatten_rules import apply_flatten_rules, apply_flatten_rules_batch_parallel
import config
from config import DB_CONFIG
from llm_local_rules import apply_local_rules
from rewriter_interface import call_rewriter
from utils.cost_estimator import get_query_cost
from cte import extract_cte
import pandas as pd
import datetime
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from typing import List, Dict, Any, Tuple


print_lock = threading.Lock()



def replace_flatten_while_loop(sql_query: str, db_config: Dict, database: str, max_workers: int = 4) -> str:
    """
    parallelized flatten rules loop processing
    """

    while True:
        extracted_result = extract_and_fix_subqueries(sql_query)
        fixed_subqueries = extracted_result["fixed_subqueries"]
        original_cost = get_query_cost(db_config, sql_query)
        
        is_changed = False
        
        print("======")
        
        if not fixed_subqueries:
            break

        parallel_args = []
        for idx, (original, fixed) in enumerate(fixed_subqueries, 1):
            # if database != "tpch":
            #     fixed = original
            masked_sqls, sub_map = mask_all_but_one_subquery(fixed, db_config)
            if len(masked_sqls) <= 1:
                continue
            parallel_args.append((idx, original, fixed, masked_sqls, sub_map, sql_query, db_config))
        if not parallel_args:
            break

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            def process_single_flatten(args):
                idx, original, fixed, masked_sqls, sub_map, current_sql, db_config = args
                
                try:
                    with print_lock:
                        print(f"-----------Subquery {idx}---------")
                    # parallel processing flatten rules
                    flatten_sql = apply_flatten_rules_batch_parallel(
                        masked_sqls, 
                        db_config, 
                        sub_map, 
                        batch_size=40,
                        max_workers=4
                    )
                    
                    sql_query_new = current_sql.replace(original, flatten_sql)
                    if(idx == 1):
                        sql_query_new = flatten_sql
                    
                    if sql_query_new.strip() != current_sql.strip():
                        rewritten_cost = get_query_cost(db_config, sql_query_new)
                        cost_reduction = original_cost - rewritten_cost
                        
                        return {
                            'idx': idx,
                            'original': original,
                            'flatten_sql': flatten_sql,
                            'sql_query_new': sql_query_new,
                            'rewritten_cost': rewritten_cost,
                            'cost_reduction': cost_reduction,
                            'status': 'success'
                        }
                    
                    return {'idx': idx, 'status': 'no_change'}
                    
                except Exception as e:
                    with print_lock:
                        print(f"subquery {idx} do not rewrite")
                    return {'idx': idx, 'status': 'error', 'error': str(e)}
            
            futures = [executor.submit(process_single_flatten, args) for args in parallel_args]
            results = [future.result() for future in futures]
        
        # Greedy selection
        best_result = None
        best_cost_reduction = 0
        
        for result in results:
            if (result['status'] == 'success' and 
                result.get('cost_reduction', 0) > best_cost_reduction and
                result.get('cost_reduction', 0) > 0):
                best_cost_reduction = result['cost_reduction']
                best_result = result
        
        # greedy selection
        if best_result:
            sql_query = best_result['sql_query_new']
            is_changed = True
            print(f"[FLATTEN RULE APPLIED]: {sql_query}")
        
        if not is_changed:
            break
    
    return sql_query





def replace_pushdown_while_loop(sql_query: str, db_config: Dict, database: str, max_workers: int = 4) -> str:
    """
    parallelized pushdown rules loop processing
    """
    while True:
        extracted_result = extract_and_fix_subqueries(sql_query)
        fixed_subqueries = extracted_result["fixed_subqueries"]
        
        is_changed = False
        original_cost = get_query_cost(db_config, sql_query)

        print("======")
        
        if not fixed_subqueries:
            break
        
        parallel_args = []
        for idx, (original, fixed) in enumerate(fixed_subqueries, 1):
            # if database != "tpch":
            #     fixed = original
            
            masked_sqls, sub_map = mask_all_but_one_subquery(fixed, db_config)
            if len(masked_sqls) <= 1:
                continue
            
            parallel_args.append((idx, original, fixed, masked_sqls, sub_map, sql_query, db_config))
        
        if not parallel_args:
            break
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            def process_single_pushdown(args):
                idx, original, fixed, masked_sqls, sub_map, current_sql, db_config = args
                
                try:
                    with print_lock:
                        print(f"-----------Subquery {idx}---------")
                    
                    pushdown_sql = apply_pushdown_rules_batch_parallel(
                        masked_sqls, 
                        db_config, 
                        sub_map, 
                        batch_size=20,
                        max_workers=4
                    )
                    
                    if idx == 1:
                        sql_query_new = pushdown_sql
                    else:
                        sql_query_new = current_sql.replace(original, pushdown_sql)
                    
                    if sql_query_new.strip() != current_sql.strip():
                        rewritten_cost = get_query_cost(db_config, sql_query_new)
                        cost_reduction = original_cost - rewritten_cost
                        
                        return {
                            'idx': idx,
                            'original': original,
                            'pushdown_sql': pushdown_sql,
                            'sql_query_new': sql_query_new,
                            'rewritten_cost': rewritten_cost,
                            'cost_reduction': cost_reduction,
                            'status': 'success'
                        }
                    
                    return {'idx': idx, 'status': 'no_change'}
                    
                except Exception as e:
                    with print_lock:
                        print(f"subquery {idx} do not rewrite")
                    return {'idx': idx, 'status': 'error', 'error': str(e)}
            
            futures = [executor.submit(process_single_pushdown, args) for args in parallel_args]
            results = [future.result() for future in futures]
        
        best_result = None
        best_cost_reduction = 0
        
        #greedy selection
        for result in results:
            if (result['status'] == 'success' and 
                result.get('cost_reduction', 0) > best_cost_reduction and
                result.get('cost_reduction', 0) > 0):
                best_cost_reduction = result['cost_reduction']
                best_result = result
        
        # greedy selection
        if best_result:
            sql_query = best_result['sql_query_new']
            is_changed = True
        
        if not is_changed:
            break
    
    return sql_query



def replace_pushdown_while_loop2(sql_query: str, db_config: Dict, database: str, max_workers: int = 4) -> str:
    """
    parallelized pushdown rules loop processing
    """
    while True:
        extracted_result = extract_and_fix_subqueries(sql_query)
        fixed_subqueries = extracted_result["fixed_subqueries"]
        
        is_changed = False
        original_cost = get_query_cost(db_config, sql_query)

        print("======")
        
        if not fixed_subqueries:
            break
        
        parallel_args = []
        for idx, (original, fixed) in enumerate(fixed_subqueries, 1):
            # if database != "tpch":
            #     fixed = original
            
            masked_sqls, sub_map = mask_all_but_one_subquery(fixed, db_config)
            if len(masked_sqls) <= 2:
                continue
            
            parallel_args.append((idx, original, fixed, masked_sqls, sub_map, sql_query, db_config))
        
        if not parallel_args:
            break
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            def process_single_pushdown(args):
                idx, original, fixed, masked_sqls, sub_map, current_sql, db_config = args
                
                try:
                    with print_lock:
                        print(f"-----------Subquery {idx}---------")
                    
                    pushdown_sql = apply_pushdown_rules_batch_parallel(
                        masked_sqls, 
                        db_config, 
                        sub_map, 
                        batch_size=20,
                        max_workers=4
                    )
                    
                    if idx == 1:
                        sql_query_new = pushdown_sql
                    else:
                        sql_query_new = current_sql.replace(original, pushdown_sql)
                    
                    if sql_query_new.strip() != current_sql.strip():
                        rewritten_cost = get_query_cost(db_config, sql_query_new)
                        cost_reduction = original_cost - rewritten_cost
                        
                        return {
                            'idx': idx,
                            'original': original,
                            'pushdown_sql': pushdown_sql,
                            'sql_query_new': sql_query_new,
                            'rewritten_cost': rewritten_cost,
                            'cost_reduction': cost_reduction,
                            'status': 'success'
                        }
                    
                    return {'idx': idx, 'status': 'no_change'}
                    
                except Exception as e:
                    with print_lock:
                        print(f"subquery {idx} do not rewrite")
                    return {'idx': idx, 'status': 'error', 'error': str(e)}
            
            futures = [executor.submit(process_single_pushdown, args) for args in parallel_args]
            results = [future.result() for future in futures]
        
        best_result = None
        best_cost_reduction = 0
        
        #greedy selection
        for result in results:
            if (result['status'] == 'success' and 
                result.get('cost_reduction', 0) > best_cost_reduction and
                result.get('cost_reduction', 0) > 0):
                best_cost_reduction = result['cost_reduction']
                best_result = result
        
        # greedy selection
        if best_result:
            sql_query = best_result['sql_query_new']
            is_changed = True
        
        if not is_changed:
            break
    
    return sql_query




def BQR_rewrite(sql_query: str, db_config=DB_CONFIG) -> str:

    before_rewrite_sql_query = sql_query.strip()

    database = DB_CONFIG["database"]
    if database == "tpch10g" or database == "tpch5g" or database == "tpch1g":
        database = "tpch"

    # parallel processing for pushdown rules
    sql_query = replace_pushdown_while_loop(sql_query, db_config, database, max_workers=4)

    # Serial

    # while True:
    #     extracted_result = extract_and_fix_subqueries(sql_query)
    #     fixed_subqueries = extracted_result["fixed_subqueries"]
    #     print(fixed_subqueries)
        
    #     is_changed = False
    #     original_cost = get_query_cost(db_config, sql_query)

    #     print("======")
    #     for idx, (original, fixed) in enumerate(fixed_subqueries, 1):
            
    #         # print(f"-----------Subquery {idx}---------")
    #         # print(f"  Original: {original}")
    #         # print(f"  Fixed: {fixed}")
    #         masked_sqls, sub_map = mask_all_but_one_subquery(sql = fixed, db_config = db_config)
    #         # if(len(masked_sqls) <= 2):
    #         #     continue

    #         print(f"  Masked SQLs: {masked_sqls}")

            
    #         # pushdown_sql = apply_pushdown_rules(masked_sqls, db_config, sub_map)

    #         #parallel processing for pushdown rules
    #         pushdown_sql = apply_pushdown_rules_batch_parallel(
    #             masked_sqls, 
    #             db_config, 
    #             sub_map, 
    #             batch_size=20,
    #             max_workers=4
    #         )

    #         if(idx==1):
    #             sql_query_new = pushdown_sql
    #         else:
    #             sql_query_new = sql_query.replace(original, pushdown_sql)
    #         if sql_query_new.strip() != sql_query.strip():
    #             # print(f"[Pushdown SQL]: {pushdown_sql}")
    #             rewritten_cost = get_query_cost(db_config, sql_query_new)
    #             if(rewritten_cost < original_cost):
    #                 sql_query = sql_query_new
    #                 is_changed = True
    #                 # sql_query = call_rewriter(database,sql_query,["UNION_TO_DISTINCT"]).replace("$", "")
    #     
    #                 break

    #         # if pushdown_sql.strip() != fixed.strip():
    #         #     print(f"[Pushdown SQL]: {pushdown_sql}")
                
    #         #     sql_query = sql_query.replace(original, pushdown_sql)
    #         #     is_changed = True
    #         
    #         #     break
        
    #     if not is_changed:
    #         break

    # parallel processing for flatten rules
    sql_query = replace_flatten_while_loop(sql_query, db_config, database, max_workers=4)

    # Serial

    # while True:
    #     extracted_result = extract_and_fix_subqueries(sql_query)
    #     fixed_subqueries = extracted_result["fixed_subqueries"]
    #     original_cost = get_query_cost(db_config, sql_query)
        
    #     is_changed = False
        
    #     print("======")
    #     for idx, (original, fixed) in enumerate(fixed_subqueries, 1):
    #         print(f"-----------Subquery {idx}---------")
    #         # print(f"  Original: {original}")
    #         # print(f"  Fixed: {fixed}")

    #         if(database !="tpch"):
    #             fixed = original
    #         masked_sqls, sub_map = mask_all_but_one_subquery(fixed, db_config)
    #         if(len(masked_sqls) <= 2):
    #             continue

    #         # serial
    #         # flatten_sql = apply_flatten_rules(masked_sqls, db_config, sub_map)

    #         # parallel
    #         flatten_sql = apply_flatten_rules_batch_parallel(
    #             masked_sqls, 
    #             db_config, 
    #             sub_map, 
    #             batch_size=20,
    #             max_workers=4
    #         )


    #         sql_query_new = sql_query.replace(original, flatten_sql)
    #         
    #         rewritten_cost = get_query_cost(db_config, sql_query_new)
    #         if (sql_query_new.strip() != sql_query.strip()) :
    #             if (rewritten_cost < original_cost):
    #                 # print(f"[Flatten SQL]: {flatten_sql}")
    #                 sql_query = sql_query_new
    #                 is_changed = True
    #                
    #                 break
    #         
    #         # if flatten_sql.strip() != fixed.strip():
    #         #     print(f"[Flatten SQL]: {flatten_sql}")

    #         #     sql_query = sql_query.replace(original, flatten_sql)
    #         #     is_changed = True
    #         #     
    #         #     break
        
    #     if not is_changed:
    #         break

    # parallel processing for pushdown rules
    sql_query = replace_pushdown_while_loop2(sql_query, db_config, database, max_workers=4)

    # serial

    # while True:
    #     extracted_result = extract_and_fix_subqueries(sql_query)
    #     fixed_subqueries = extracted_result["fixed_subqueries"][1:]
    #     original_cost = get_query_cost(db_config, sql_query)
    #     is_changed = False
    #     print("======")
    #     for idx, (original, fixed) in enumerate(fixed_subqueries, 1):

    #         if(database !="tpch"):
    #             fixed = original

    #         print(f"-----------Subquery {idx}---------")
    #         # print(f"  Original: {original}")
    #         # print(f"  Fixed: {fixed}")
    #         masked_sqls, sub_map = mask_all_but_one_subquery(fixed, db_config)
    #         # if(len(masked_sqls) <= 2):
    #         #     continue

    #         # parallel
    #         # pushdown_sql = apply_pushdown_rules(masked_sqls, db_config, sub_map)


    #         # serial
    #         pushdown_sql = apply_pushdown_rules_batch_parallel(
    #             masked_sqls, 
    #             DB_CONFIG, 
    #             sub_map, 
    #             batch_size=20,
    #             max_workers=4
    #         )


    #         sql_query_new = sql_query.replace(original, pushdown_sql)
    #         if sql_query_new.strip() != sql_query.strip():
    #             rewritten_cost = get_query_cost(db_config, sql_query_new)
    #             if(rewritten_cost < original_cost):
    #                 # print(f"[Pushdown SQL]: {pushdown_sql}")
    #                 sql_query = sql_query_new
    #                 is_changed = True
    #                 
    #                 break
        
    #     if not is_changed:
    #         break
    

    sql_query = apply_local_rules(sql_query, db_config, max_workers=8)


    # CTE extraction
    # print("before_cte: " ,sql_query)
    # sql_query = extract_cte(sql_query, db_config)
    
    print("=============================================")
    print("After Rewrite:", sql_query)

    return sql_query




if __name__ == "__main__":
    input_csv_path = ""
    output_csv_path = ""
    execution_time_file = "./execution_time.txt"
    
    try:
        df = pd.read_csv(input_csv_path)
    except Exception as e:
        exit(1)
    
    success_count = 0
    error_count = 0
    
    with open(execution_time_file, 'w') as f:
        f.write(f"BQR - {datetime.datetime.now()}\n")
        f.write("="*50 + "\n")
    
    try:
        header_df = pd.DataFrame(columns=['idx', 'db_id', 'original_sql', 'rewritten_sql'])
        header_df.to_csv(output_csv_path, index=False, encoding='utf-8')
    except Exception as e:
        exit(1)
    
    for index, row in df.iterrows():
        idx = index + 1 
        db_id = row['db_id']
        original_sql = row['original_sql']
        
        print(f"\n{'='*50}")
        print(f" {idx} sql (db_id: {db_id})")
        print(f"original SQL: {original_sql[:100]}...")
        
        try:
            rewritten_sql = BQR_rewrite(original_sql)
        
            current_result = {
                'idx': idx,
                'db_id': db_id,
                'original_sql': original_sql,
                'rewritten_sql': rewritten_sql
            }
            
            success_count += 1
            print(f"Rewritten SQL: {rewritten_sql}")
            
        except Exception as e:
            current_result = {
                'idx': idx,
                'db_id': db_id,
                'original_sql': original_sql,
                'rewritten_sql': f"ERROR: {str(e)}"
            }
            error_count += 1
        
        try:
            current_df = pd.DataFrame([current_result])
            current_df.to_csv(output_csv_path, mode='a', header=False, index=False, encoding='utf-8')
        except Exception as e:
            print(f" ")
        
        try:
            with open(execution_time_file, 'a') as f:
                f.write(f"\nQuery {idx} completed at: {datetime.datetime.now()}\n")
                f.write("=============================\n")
        except Exception as e:
            print(f"write failed")
    


