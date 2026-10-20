# BQR: Efficient Query Rewriting via Fine-Grained Sub-Query Decomposition


## Install

```bash
pip install -r requirements.txt
```

## Config

Update the database configuration in ```config.py```.

---

## I. BQR

### 1. Pointer Network Training Dataset Construction (Optional)

(Optional) Build the training and validation datasets for the Pointer Network.

```
python BQR/pointer_net_cut_selector/build_dataset.py \
  --csv data/queries/tpch/queries_tpch_test.csv \
  --output-train data/pointer_net/tpch_pointer_network_train.jsonl \
  --output-test data/pointer_net/tpch_pointer_network_test.jsonl \
  --train-ratio 0.9 \
  --seed 42
```

Alternatively, prebuilt datasets are available in ```./data/pointer_net/```.

### 2. Pointer Network Training (Optional)

Train the Pointer Network model for cut-edge prediction.

```
python BQR/pointer_net_cut_selector/train_pointer_net.py \
  --train-jsonl [TRAIN_JSONL_PATH] \
  --valid-jsonl [VALID_JSONL_PATH] \
  --output-dir [OUTPUT_PATH] \
  --batch-size 8 \
  --epochs 500 \
  --lr 1e-4
```

Pretrained model checkpoints are available in ```./checkpoint/```


### 3.1 Predicting Cut Edges

Use a trained Pointer Network checkpoint to predict SQL cut edges.

```
python BQR/pointer_net_cut_selector/predict_pointer_net.py \
  --checkpoint [BEST_CHECKPOINT_PATH] \
  --input-jsonl [INPUT_JSONL_PATH] \
  --output-jsonl [OUTPUT_JSONL_PATH]
```

For the ```checkpoint``` argument, use a model from Step 2. For ```input-jsonl```, you can use:

```
./data/pointer_net/dsb_csv_test_500.jsonl
./data/pointer_net/tpch_csv_test_500.jsonl
./data/pointer_net/sqlstorm_csv_250.jsonl
```

(These JSONL files correspond one-to-one with the CSV files in ```./data/queries/```)

### 3.2 Apply Predicted Cut Edges for SQL Rewriting

Apply predicted cut edges and generate rewritten SQL queries.

  ```
python BQR/submodular_cut_validation/apply_predicted_cut_rewrite.py \
  --jsonl [STEP3-1_GENERATED_CUT_EDGE_JSONL_PATH] \
  [--rewrite-backend [llmr2/quite]] \
  --output [OUTPUT_JSONL_PATH] 
  ```


---

## II. BQR (heuristic)

```
python BQR/submodular_cut_validation/double_greedy_cut_search.py \
  --jsonl-file [JSONL_PATH] \
  --jsonl-sql-field sql \
  --strategy double_greedy \
  --restarts 2 \
  --seed 0 \
  --rewrite-trace \
  --dump-evaluations \
  --rewrite-backend llmr2 \
  --output-jsonl [OUTPUT_JSONL_PATH]
```

For the ```jsonl-file``` argument, you can use:

```
./data/pointer_net/dsb_csv_test_500.jsonl
./data/pointer_net/tpch_csv_test_500.jsonl
./data/pointer_net/sqlstorm_csv_250.jsonl
```

(These JSONL files correspond one-to-one with the CSV files in ```./data/queries/```)



## III. Supported Rewrite Backends

### 1. [LLMR2](https://github.com/DAMO-NLP-SG/LLM-R2.git) Backend

LLM-guided SQL rewrite rule selection.

Features

* Uses semantic retrieval with SentenceTransformer
* Uses OpenAI models (default: gpt-4o)
* Dynamically selects Calcite rules

Required Environment Variables

```
export OPENAI_API_KEY=YOUR_KEY
export LLMR2_MODEL=gpt-4o
export LLMR2_NUM_PROMOS=1
```

 And add your OPENAI API KEY in ```./LLM-R2/src/LLM_R2.py```

### 2. QuiteBackend

Integration with the QUITE SQL rewriting framework.
QUITE must be deployed separately. Add the project path to the corresponding location in ```./BQR/rewrite_backends.py```.

Features

* FSM-based iterative query rewriting
* Multi-agent optimization pipeline
* Schema-aware rewriting

Required Environment Variables

```
export QUITE_ROOT=/path/to/QUITE
export QUITE_SCHEMA_FILE=/path/to/schema.sql
export QUITE_MAX_ITERATIONS=2
```


## IV. Test

1. To test query execution times before and after rewriting, update the database configuration and the corresponding input and output file paths in ```./test/test_sql_excution_time_parallel.py```, then run the script.
2. To calculate evaluation metrics, update the file path in ```./test/get_statistic_result.py``` to point to the output file generated in Step 1, then run the script.