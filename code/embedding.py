import os
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from typing import List, Tuple, Dict, Any
from syntax_tree import extract_and_fix_subqueries
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import threading
from functools import lru_cache

_model = None
_model_lock = threading.Lock()
_embedding_cache = {}

def setup_embedding_model():

    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                cache_dir = ""
            
                _model = SentenceTransformer("all-MiniLM-L6-v2", cache_folder=cache_dir)
    return _model

def get_embedding_with_cache(text: str, model=None):
    # Get embedding for a single text, using cache if available
    if model is None:
        model = setup_embedding_model()
        
    # use a simple hash as cache key
    cache_key = hash(text)
    if cache_key in _embedding_cache:
        return _embedding_cache[cache_key]
    
    embedding = model.encode(text)
    _embedding_cache[cache_key] = embedding
    return embedding

def get_embeddings_batch(texts: List[str], model=None, max_workers: int = 4):
    # Get embeddings for a batch of texts, using cache if available
    if model is None:
        model = setup_embedding_model()
    
    cached_embeddings = {}
    uncached_texts = []
    uncached_indices = []
    
    # Check cache for each text
    for i, text in enumerate(texts):
        cache_key = hash(text)
        if cache_key in _embedding_cache:
            cached_embeddings[i] = _embedding_cache[cache_key]
        else:
            uncached_texts.append(text)
            uncached_indices.append(i)
    
    # If all texts are cached, return them directly
    if uncached_texts:
        batch_embeddings = model.encode(uncached_texts, batch_size=32, show_progress_bar=False)
        
        for text, embedding, idx in zip(uncached_texts, batch_embeddings, uncached_indices):
            cache_key = hash(text)
            _embedding_cache[cache_key] = embedding
            cached_embeddings[idx] = embedding
    
    return [cached_embeddings[i] for i in range(len(texts))]

def get_most_similar_sql_parallel(model, query, demo_queries, demo_rules, max_workers: int = 4):
    # Find the most similar SQL query to the input query using parallel processing

    query_emb = get_embedding_with_cache(query, model)

    demo_embeddings = get_embeddings_batch(demo_queries, model, max_workers)
    
    # Compute cosine similarity in parallel
    def compute_similarity(args):
        idx, demo_emb = args
        return idx, cosine_similarity([query_emb], [demo_emb])[0][0]
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        similarity_tasks = [(i, emb) for i, emb in enumerate(demo_embeddings)]
        similarity_results = list(executor.map(compute_similarity, similarity_tasks))
    

    best_idx = max(similarity_results, key=lambda x: x[1])[0]
    best_score = similarity_results[best_idx][1]
    
    return {
        "input_query": query,
        "most_similar_demo_query": demo_queries[best_idx],
        "demo_rule": demo_rules[best_idx],
        "score": best_score
    }

def process_single_subquery(args):
   # Process a single subquery to find the most similar demo SQL and its rule
    idx, original, fixed, demo_queries, demo_rules, model = args
    
    try:
        result = get_most_similar_sql_parallel(model, fixed, demo_queries, demo_rules)
        
        subquery_result = {
            "subquery_index": idx,
            "original_sql": original,
            "fixed_sql": fixed,
            "most_similar_demo_query": result["most_similar_demo_query"],
            "demo_rule": result["demo_rule"],
            "similarity_score": result["score"]
        }
        
        print(f"  subquery {idx}  - score: {result['score']:.4f}")
        return subquery_result
        
    except Exception as e:
        return {
            "subquery_index": idx,
            "original_sql": original,
            "fixed_sql": fixed,
            "most_similar_demo_query": None,
            "demo_rule": None,
            "similarity_score": 0.0,
            "error": str(e)
        }

def find_similar_demo_sql_for_subqueries_parallel(
    sql_query: str, 
    csv_path: str = '',
    max_workers: int = 4
) -> List[Dict[str, Any]]:
    """
    Parallel version: Given an input SQL query, extract all subqueries and find the most similar demo SQL and its rule for each subquery.

    Args:
        sql_query: Original SQL query string.
        csv_path: Path to the CSV file containing SQL templates and rules.
        max_workers: Maximum number of parallel worker threads.

    Returns:
        List[Dict]: List containing the matching result for each subquery.
    """

    model = setup_embedding_model()
    
    try:
        df = pd.read_csv(csv_path)
        demo_queries = df['sql_template'].tolist()
        demo_rules = df['rule_applied'].tolist()
    except Exception as e:
        return []
    

    get_embeddings_batch(demo_queries, model, max_workers)
    
    # Extract subqueries from the SQL query
    extracted_result = extract_and_fix_subqueries(sql_query)
    fixed_subqueries = extracted_result["fixed_subqueries"][1:]
    
    if not fixed_subqueries:
        return []
    
    print("======")
    
    parallel_args = [
        (idx, original, fixed, demo_queries, demo_rules, model)
        for idx, (original, fixed) in enumerate(fixed_subqueries, 1)
    ]
    
    # Use ThreadPoolExecutor to process subqueries in parallel
    matching_results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(process_single_subquery, args): args[0] 
            for args in parallel_args
        }
        
        for future in as_completed(future_to_idx):
            result = future.result()
            matching_results.append(result)
    
    # Sort results by subquery index
    matching_results.sort(key=lambda x: x['subquery_index'])
    
    # Print results for debugging
    for result in matching_results:
        idx = result['subquery_index']
        # print(f"-----------Subquery {idx}---------")
        # print(f"  Original: {result['original_sql']}")
        # print(f"  Fixed: {result['fixed_sql']}")
        
        if result.get('error'):
            print(f"  error: {result['error']}")
        else:
            print(f"  demo SQL: {result['most_similar_demo_query'][:100]}...")
            print(f"  rule: {result['demo_rule']}")
            print(f"  score: {result['similarity_score']:.4f}")
    
    return matching_results

def find_similar_demo_sql_single_optimized(
    query: str, 
    csv_path: str = ''
) -> Tuple[str, str, float]:
    """
    Optimized single-query processing function.
    """

    model = setup_embedding_model()
    
    df = pd.read_csv(csv_path)
    demo_queries = df['sql_template'].tolist()
    demo_rules = df['rule_applied'].tolist()

    result = get_most_similar_sql_parallel(model, query, demo_queries, demo_rules)
    return result["most_similar_demo_query"], result["demo_rule"], result["score"]

def clear_embedding_cache():

    global _embedding_cache
    _embedding_cache.clear()


def find_similar_demo_sql_for_subqueries(
    sql_query: str, 
    csv_path: str = ''
) -> List[Dict[str, Any]]:

    return find_similar_demo_sql_for_subqueries_parallel(sql_query, csv_path, max_workers=4)

if __name__ == "__main__":
    import time
    
    csv_path = ''
    query = """SELECT l.l_shipDATE AS l_l_shipDATE, AVG(l.l_linenumber) AS avg_l_l_linenumber, MAX(l.l_commitDATE) AS max_l_l_commitDATE, MAX(p.p_brand) AS max_p_p_brand, COUNT(l.l_shipDATE) AS count_l_l_shipDATE, l.l_linestatus AS l_l_linestatus, MAX(l.l_shipDATE) AS max_l_l_shipDATE, MAX(p.p_container) AS max_p_p_container, COUNT(p.p_brand) AS count_p_p_brand, MAX(l.l_orderkey) AS max_l_l_orderkey FROM lineitem AS l, part AS p, partsupp AS ps WHERE EXISTS(SELECT MAX(c_acctbal) FROM (SELECT c_acctbal, c_mktsegment FROM customer WHERE c_nationkey BETWEEN 10 AND 20) AS t GROUP BY c_mktsegment ORDER BY c_mktsegment) AND l.l_suppkey > (SELECT COUNT(*) FROM (SELECT c_address FROM customer UNION ALL SELECT s_address FROM supplier) AS t) AND ps.ps_supplycost IN (SELECT DISTINCT ps_supplycost FROM partsupp UNION SELECT l_discount FROM lineitem UNION SELECT l_discount FROM (SELECT DISTINCT l_discount FROM lineitem AS l1_3 WHERE l_quantity < 15) AS subq_3) AND l.l_extendedprice = (SELECT (20 * 5) + COUNT(DISTINCT l_linenumber) FROM lineitem WHERE l_extendedprice IN (SELECT p_retailprice FROM part WHERE p_size < 15)) AND p.p_name IN (SELECT p_name FROM part WHERE p_partkey IN (SELECT l_partkey FROM lineitem WHERE l_shipdate > '1995-06-30' UNION SELECT p_partkey FROM part WHERE p_retailprice < 150) AND p_size IN (SELECT p_size FROM part JOIN partsupp ON p_partkey = ps_partkey WHERE ps_availqty < 50)) AND p.p_partkey = ps.ps_partkey AND l.l_partkey = ps.ps_partkey AND l.l_suppkey = ps.ps_suppkey AND p.p_container LIKE 'SM PKG%' AND l.l_suppkey < 9538 AND l.l_shipinstruct LIKE 'NONE%' AND l.l_shipdate > '1997-07-14' AND p.p_retailprice > 1697.2582838831686 AND ps.ps_partkey >= 67068 AND l.l_quantity <= 39.62003427125977 AND ps.ps_availqty >= 5064 AND p.p_size > 22 AND l.l_discount < 0.08084684396533358 GROUP BY l.l_shipDATE, l.l_linestatus LIMIT 50"""

    # test
    start_time = time.time()
    result = find_similar_demo_sql_for_subqueries_parallel(query, csv_path=csv_path, max_workers=4)
    end_time = time.time()
    
    
    # 清理缓存
    clear_embedding_cache()
