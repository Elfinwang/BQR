# from vllm import LLM, SamplingParams
from rewriter_interface import call_rewriter
from utils.cost_estimator import get_query_cost
from sqlglot import parse_one, exp
from syntax_tree import build_syntax_tree, find_subqueries,extract_and_fix_subqueries
from embedding import find_similar_demo_sql_for_subqueries_parallel
from rewriter_interface import call_rewriter
from config import DB_CONFIG
import os
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed
import time


client = OpenAI(
    api_key=""
)

LOCAL_RULES = [
    "AGGREGATE_VALUES",
    "JOIN_REDUCE_EXPRESSIONS",

    # aggregate rules
    'AGGREGATE_EXPAND_DISTINCT_AGGREGATES',
    'AGGREGATE_PROJECT_MERGE', 
    'AGGREGATE_ANY_PULL_UP_CONSTANTS',
    'AGGREGATE_UNION_AGGREGATE',
    'AGGREGATE_REMOVE',
    
    # filter rules
    'FILTER_REDUCE_EXPRESSIONS',
    
    # project rules
    'PROJECT_REDUCE_EXPRESSIONS',
    'PROJECT_CALC_MERGE',
    'PROJECT_MERGE',
    'PROJECT_REMOVE',
    'PROJECT_TO_CALC',

    # sort rules
    'SORT_PROJECT_TRANSPOSE',
    'SORT_UNION_TRANSPOSE',
    'SORT_REMOVE_CONSTANT_KEYS',
    'SORT_REMOVE',
    'SORT_FETCH_ZERO_INSTANCE',
    
    # calc rules
    'CALC_MERGE',
    'CALC_REMOVE',
    
    'AGGREGATE_INSTANCE',
    'FILTER_INSTANCE', 
    'JOIN_LEFT_INSTANCE',
    'JOIN_RIGHT_INSTANCE',
    'PROJECT_INSTANCE',
    'SORT_INSTANCE',
    'UNION_INSTANCE',
    'INTERSECT_INSTANCE',
    'MINUS_INSTANCE'
]




def generate_prompt(query, demo_sql, demo_rule):
    prompt = [{'role': "system", 'content': 'You are an online SQL rewrite agent. You will be given a SQL query. You are required to propose rewriting rules to rewrite the query to improve the efficiency of running this query, using the given rewriting rules below. The rules are provided in form of ["rule name": "rule description"] and you should answer with a list of rewriting rule names, which if applied in sequence, will best rewrite the input SQL query into a new query, which is the most efficient. Return "Empty List" if from the previous chat and input query, no rule should be used. The rewriting rules you can adopt are defined as follows: ' +
            '[AGGREGATE_INSTANCE": "Rule that instantiates an Aggregate with a given input"], ' \
            '["AGGREGATE_EXPAND_DISTINCT_AGGREGATES": "Rule that expands a DISTINCT Aggregate into a Join with a Project, to allow for more general rewrites"], ' \
            '["AGGREGATE_PROJECT_MERGE": "Rule that recognizes an Aggregate on top of a Project and if possible aggregates through the Project or removes the Project"], ' \
            '["AGGREGATE_ANY_PULL_UP_CONSTANTS": "More general form of AGGREGATE_PROJECT_PULL_UP_CONSTANTS that matches any relational expression"], ' \
            '["AGGREGATE_UNION_AGGREGATE": "Rule that matches an Aggregate whose input is a Union one of whose inputs is an Aggregate"], ' \
            '["AGGREGATE_VALUES": "Rule that applies an Aggregate to a Values (currently just an empty Values)"], ' \
            '["AGGREGATE_REMOVE": "Rule that removes an Aggregate if it computes no aggregate functions (that is, it is implementing SELECT DISTINCT), or all the aggregate functions are splittable, and the underlying relational expression is already distinct"], '\
            '["FILTER_REDUCE_EXPRESSIONS": "Rule that reduces constants inside a LogicalFilter"], ' \
            '["FILTER_INSTANCE": "Rule that instantiates a Filter with a given input"], '\
            '["JOIN_LEFT_INSTANCE": "Rule that instantiates a Join with a left input"], ' \
            '["JOIN_RIGHT_INSTANCE": "Rule that instantiates a Join with a right input"], ' \
            '["JOIN_REDUCE_EXPRESSIONS": "Rule that reduces constants inside a Join"], ' \
            '["SORT_FETCH_ZERO_INSTANCE": "Rule that instantiates a Sort with a fetch of zero instances"], ' \
            '["SORT_PROJECT_TRANSPOSE": "Rule that pushes a Sort past a Project"], ' \
            '["SORT_UNION_TRANSPOSE": "Rule that pushes a Sort past a Union"], ' \
            '["SORT_REMOVE_CONSTANT_KEYS": "Rule that removes keys from a Sort if those keys are known to be constant, or removes the entire Sort if all keys are constant"], ' \
            '["SORT_REMOVE": "Rule that removes a Sort if its input is already sorted"], '\
            '["SORT_INSTANCE": "Rule that instantiates a Sort with a given input"], '\
            '["UNION_MERGE": "Rule that flattens a Union on a Union into a single Union"], ' \
            '["UNION_REMOVE": "Rule that removes a Union if it has only one input"], ' \
            '["UNION_TO_DISTINCT": "Rule that translates a distinct Union (all = false) into an Aggregate on top of a non-distinct Union (all = true)"], ' \
            '["UNION_PULL_UP_CONSTANTS": "Rule that pulls up constants through a Union operator"], '\
            '["UNION_INSTANCE": "Rule that instantiates a Union with a given input"], '\
            '["INTERSECT_INSTANCE": "Rule that instantiates an Intersect with a given input"], ' \
            '["MINUS_INSTANCE": "Rule that instantiates a Minus with a given input"], ' \
            '["CALC_MERGE": "Rule that merges consecutive Calc operators into a single Calc operator to eliminate redundant expression evaluation layers"], ' \
            '["CALC_REMOVE": "Rule that removes a Calc operator if it computes no expressions (that is, it is implementing SELECT *), or all the expressions are splittable, and the underlying relational expression is already distinct"]. ' \
            'You should return only a list of rewriting rule names provided above, in the form of "Rules selected: [rule names]".'}]

    demo = [{
        'role': "user",
        'content': "Query: " + demo_sql,
    },
        {
            'role': "assistant",
            'content': 'Rules selected: [' + demo_rule + ']' ,
        }]
    prompt = prompt + demo
    prompt.append({
        'role': "user",
        'content': "Query: " + query,
    })
    return prompt



def query_gpt_attempts(prompt, trys):
    try:
        output = query_turbo_model(prompt)
    except:
        print(trys)
        trys += 1
        if trys <= 3:
            output = query_gpt_attempts(prompt, trys)
        else:
            output = 'NA'
    return output


def query_turbo_model(prompt):
    chat_completion = client.chat.completions.create(
        messages=prompt,
        # model="gpt-3.5-turbo",
        model = "gpt-4-1106-preview",
        
        temperature=0,
    )
    return chat_completion.choices[0].message.content

def filter_gpt_output(gpt_output):
    rule_list = LOCAL_RULES
    if gpt_output == 'NA':
        return []
    out_rules = gpt_output.split('[')[-1].split(']')[0]
    out_rules = out_rules.replace('/', '').replace('"', '').replace("'", "")
    out_rules = [x.replace(' ', '').replace('\n', '').strip() for x in out_rules.split(',')]
    print('out_rules: ', out_rules)
    execute_rules = []
    for r in out_rules:
        if r in rule_list:
            execute_rules.append(r)

    return execute_rules




def query_multiple_prompts_parallel(prompts, max_workers=4):
    """
    Process multiple prompts in parallel
    
    Args:
        prompts: list, list containing all prompts
        max_workers: int, maximum number of parallel workers
    
    Returns:
        list, list containing all processing results
    """
    all_results = [None] * len(prompts)  
    
    def process_single_prompt(prompt_data):
        index, prompt = prompt_data
        try:
            print(f"Starting to process prompt {index+1}")
            generated_text = query_gpt_attempts(prompt, 0)
            execute_rules = filter_gpt_output(generated_text)
            print(f"Completed prompt {index+1}: {execute_rules}")
            return index, generated_text, execute_rules
        except Exception as e:
            print(f"Failed to process prompt {index+1}: {e}")
            return index, 'NA', []

    indexed_prompts = [(i, prompt) for i, prompt in enumerate(prompts)]
    
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(process_single_prompt, prompt_data): prompt_data[0] 
            for prompt_data in indexed_prompts
        }

        for future in as_completed(future_to_index):
            try:
                index, generated_text, rules = future.result()
                all_results[index] = {
                    'generated_text': generated_text,
                    'execute_rules': rules
                }
            except Exception as e:
                index = future_to_index[future]
                print(f"Failed to get result for prompt {index+1}: {e}")
                all_results[index] = {
                    'generated_text': 'NA',
                    'execute_rules': []
                }
    
    end_time = time.time()
    
    return all_results


def apply_local_rules(sql_query, db_config, local_rules=LOCAL_RULES):
    csv_path = './data/data_llmr2/embedding_data/sql_templates_with_rule_final.csv'
    database = db_config.get('database')
    if (database == 'tpch10g') or (database == 'tpch5g') or (database == 'tpch1g'):
        database = 'tpch'
    
    result = find_similar_demo_sql_for_subqueries_parallel(sql_query, csv_path=csv_path, max_workers=4)

    if not result:
        return sql_query
    
    # Collect all prompts and corresponding fixed_sql
    prompts = []
    fixed_sqls = []
    
    for item in result:
        fixed_sql = item.get('fixed_sql')
        most_similar_demo_query = item.get('most_similar_demo_query')
        demo_rule = item.get('demo_rule')
        prompt = generate_prompt(fixed_sql, most_similar_demo_query, demo_rule)
        prompts.append(prompt)
        fixed_sqls.append(fixed_sql)
    
    prompt_results = query_multiple_prompts_parallel(prompts, max_workers=4)
    
    original_cost = get_query_cost(db_config, sql_query)  # Calculate original cost 
    
    best_sql = sql_query
    best_cost = original_cost
    
    for i, (fixed_sql, prompt_result) in enumerate(zip(fixed_sqls, prompt_results)):
        execute_rules = prompt_result['execute_rules']
        
        if execute_rules:
            try:
                new_fixed_sql = call_rewriter(database, fixed_sql, execute_rules)
                print(f"Subquery {i+1} - Rewritten SQL Query: {new_fixed_sql}")
                
                # Replace subquery and calculate new cost
                sql_query_new = sql_query.replace(fixed_sql, new_fixed_sql)
                new_cost = get_query_cost(db_config, sql_query_new)
                
                print(f"Subquery {i+1} - New Cost: {new_cost}")
                
                # Update if this rewrite is better than current best result
                if new_cost < best_cost:
                    best_sql = sql_query_new
                    best_cost = new_cost
                    
            except Exception as e:
                print(f"Subquery {i+1} rewrite failed")

    
    print(f"Final SQL Query: {best_sql}")
    
    return best_sql

