import json
import subprocess

def call_rewriter(db_id, sql_input, rule_input):
    # Provide a list of strings as input
    input_list = [db_id, sql_input, rule_input]
    # Convert the input list to a JSON string
    input_string = json.dumps(input_list)
    command = 'java -cp rewriter_java.jar src/rule_rewriter.java'

    process = subprocess.Popen(command, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True)
    # process.stdin.write(.encode())
    # Wait for the subprocess to finish and capture the output
    output, error = process.communicate(input=input_string)

    output = output.replace("\u001B[32m", '').replace("\u001B[0m", '').split('\n')
    ind = 0
    for i in output:
        if not i.startswith('SELECT') and not i.startswith('select') and not i.startswith('with '):
            pass
        else:
            ind = output.index(i)
            break
    queries = output[ind+1:-3]
    # print(' '.join(queries))
    output = ' '.join(queries).replace('"', '')
    if 'select' in output or 'SELECT' in output or 'Select' in output:
        # change the functions edited to fit calcite back to original ones
        output = output.replace('SUBSTRING', 'SUBSTR')
        return output
    else:
        print(db_id)
        print(sql_input)
        # print("Output:\n", output)
        # print("Error:\n", error)
        with open('error_logs_gpt_rewrite.txt', 'a+') as f:
            f.write(sql_input)
            f.write('\n')
            f.write(error)
            f.write('\n')
            f.write('\n')
            f.write('\n')
            f.close()
        return 'NA'



if __name__ == "__main__":
    
    sql_input0 = """SELECT * FROM (SELECT o.* FROM orders o, lineitem l WHERE o.o_orderkey > l.l_orderkey and o.o_orderkey < 200000 AND l.l_orderkey < 50000 AND l.l_quantity > 5 AND l.l_shipdate BETWEEN DATE '1995-01-01' AND DATE '1995-12-31' UNION ALL SELECT o.* FROM orders o JOIN nation n ON o.o_custkey + 25 = n.n_nationkey WHERE o.o_orderkey > 1000 AND n.n_name IN ('UNITED STATES', 'CANADA', 'GERMANY') AND o.o_orderkey > 1000000) AS o JOIN customer c ON o.o_custkey = c.c_custkey WHERE c.c_custkey > 2000;"""
    rule_input0 =  ["JOIN_LEFT_UNION_TRANSPOSE","JOIN_RIGHT_UNION_TRANSPOSE"] 

    db_id = "tpch"
    print(call_rewriter(db_id, sql_input0, rule_input0).replace("$",""))