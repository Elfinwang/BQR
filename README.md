# BQR: Efficient Query Rewriting via Fine-Grained Sub-Query Decomposition

BQR selects cut edges in a SQL subquery graph, rewrites the resulting query blocks, and reconstructs the full query. The repository provides two workflows:

- **BQR(HEU):** search for cut-edge sets using database cost estimates.
- **BQR(Learned):** train a Pointer Network on cut-edge labels produced by BQR(HEU), then predict cut edges for new queries.

Cut-edge selection and SQL rewriting are separate steps. Both workflows use the backend selected by `--rewrite-backend` to perform rewriting.

## Installation and Configuration

Run the commands below from the repository root, then keep `code/` as the working directory for the remaining examples:

```bash
cd code
pip install -r requirements.txt
```

Configure the following before running search or rewriting:

- Update `DB_CONFIG` in `code/config.py` with the target database connection. The default cost strategy is `pg_explain`.
- Ensure the target database and the schema metadata used by the SQL graph utilities correspond to the workload. Schema files are stored under `code/data/schemas/`.
- For Calcite-based rewriting, make Java available on `PATH` and ensure `code/rewriter_java.jar` is present. The Python interface launches Java using a relative JAR path, so the working directory matters.
- Complete the selected backend's setup in [Rewrite Backends](#rewrite-backends).

Paths in the commands below are relative to `code/`. Directory names are case-sensitive; for example, the TPCH query directory is `data/queries/TPCH/`.

## I. BQR(HEU): Search for Cut Edges

The heuristic workflow evaluates candidate cut sets using the cost objective `C(original) - C(rewritten)`. It supports `double_greedy` search. 

For batch input, provide one JSON object per line with a SQL field:

```json
{"sql": "SELECT ..."}
```

Run double-greedy search:

```bash
python BQR/submodular_cut_validation/double_greedy_cut_search.py \
  --jsonl-file data/pointer_net/tpch_csv_test_500.jsonl \
  --jsonl-sql-field sql \
  --strategy double_greedy \
  --restarts 2 \
  --seed 0 \
  --rewrite-backend llmr2 \
  --output-jsonl experiments/bqr_heu/tpch_results.jsonl
```

Existing query JSONL examples include `data/pointer_net/dsb_csv_test_500.jsonl`, `data/pointer_net/tpch_csv_test_500.jsonl`, and `data/pointer_net/sqlstorm_sql.jsonl`. Check their SQL field and query coverage before using them with a different CSV.
(These JSONL files correspond one-to-one with the CSV files in ```data/queries/```)

Each batch result includes:

- `original_sql` and `rewritten_sql`.
- `applied_cut_edge_ids`: the cut-edge labels used to supervise the Pointer Network.
- `original_query_cost` and `rewritten_query_cost`.
- `variant_fatal_error`: a failure description when applicable.


For a single query, use `--sql-file` or `--sql` instead of `--jsonl-file`. Use `--output-json` to save the detailed search result. 



## II. BQR(Learned): Predict Cut Edges

### 1. Pointer Network Training Dataset Construction (Optional)

**Training requires BQR(HEU) cutting-edge labels for each SQL query.**

First run BQR(HEU) on the queries intended for dataset construction. Its batch result contains `original_sql` and `applied_cut_edge_ids`. Then match those results to the source CSV:

```bash
python BQR/pointer_net_cut_selector/build_dataset.py \
  --csv data/queries/TPCH/queries_tpch_test.csv \
  --labels-jsonl experiments/bqr_heu/tpch_results.jsonl \
  --output-train [TRAIN_JSONL_PATH] \
  --output-test [VALID_JSONL_PATH] \
  --train-ratio 0.9 \
  --seed 42
```


Alternatively, merge the BQR(HEU) labels into the CSV itself and omit `--labels-jsonl`. The CSV must contain `original_sql` and one of these label columns: `target_cut_edge_ids`, `applied_cut_edge_ids`, or `cut_edge_ids`. Each label cell must contain a JSON array, such as `["E0", "E2"]` or `[]`. These must be labels obtained from BQR(HEU); the builder does not run the search or infer missing labels.



The output format is compatible with the training script:

```json
{"sql": "SELECT ...", "target_cut_edge_ids": ["E0", "E2"], "metadata": {"label_source": "bqr_heu"}}
```


### 2. Pointer Network Training (Optional)

Train the selector using the labeled JSONL files:

```bash
python BQR/pointer_net_cut_selector/train_pointer_net.py \
  --train-jsonl [TRAIN_JSONL_PATH] \
  --valid-jsonl [VALID_JSONL_PATH] \
  --output-dir [OUTPUT_CHECKPOINT_DIR_PATH] \
  --batch-size 8 \
  --epochs 500 \
  --lr 1e-4
```


Training writes `best.pt`, `last.pt`, and `history.json` to the output directory. To skip training, supply an existing compatible checkpoint whose label source and workload are appropriate for your experiment.

Pretrained model checkpoints are available in ```checkpoint/```


### 3. Predict Cut Edges

```bash
python BQR/pointer_net_cut_selector/predict_pointer_net.py \
  --checkpoint [BEST_CHECKPOINT_PATH] \
  --input-jsonl [INPUT_JSONL_PATH] \
  --output-jsonl [OUTPUT_JSONL_PATH]
```

Prediction accepts query JSONL with `sql` or `sql_text` fields. The output includes `predicted_cut_edge_ids`, which the next step consumes. 


### 4. Apply Predicted Cut Edges

```bash
python BQR/submodular_cut_validation/apply_predicted_cut_rewrite.py \
  --jsonl [INPUT_JSONL_PATH] \
  --rewrite-backend llmr2 \
  --output [OUTPUT_JSONL_PATH]
```

This step applies the predicted cut set and runs the rewrite pipeline.



## Rewrite Backends

### 1. [LLM-R2](https://github.com/DAMO-NLP-SG/LLM-R2) (`llmr2`)

The rewriter asks an OpenAI model to select rewrite rules, and passes those rules to the Calcite rewriter.

Clone the upstream repository under `code/`:

```bash
git clone https://github.com/DAMO-NLP-SG/LLM-R2.git LLM-R2
```

The adapter expects `code/LLM-R2/src/LLM_R2.py`. It extracts rule descriptions and the prompt/output parsing helpers from this file.

Set the API key and optional model/retrieval settings:

```bash
export OPENAI_API_KEY=YOUR_KEY
export LLMR2_MODEL=gpt-4o
export LLMR2_NUM_PROMOS=1
```

`OPENAI_API_KEY` is required for LLM inference. The model defaults to `gpt-4o`; the number of retrieved demonstrations defaults to one. The adapter reads the key from the environment.


### 2. QUITE (`quite`)

QUITE runs a schema-aware query rewriter with a finite-state-machine workflow. Install and configure QUITE separately, then point the adapter to its project and schema file:

```bash
export QUITE_ROOT=/path/to/QUITE
export QUITE_SCHEMA_FILE=/path/to/schema.sql
export QUITE_MAX_ITERATIONS=2
```

Set the environment variable for your installation.

Use `--rewrite-backend quite` in the search or application command. Both entry points also accept `--quite-schema-file /path/to/schema.sql` as a schema override. If the schema is missing or QUITE fails, the adapter returns the original SQL with error metadata.


### 3. [R-Bot](https://github.com/curtis-sun/LLM4Rewrite) 

R-Bot retrieves rewrite evidence from documents and code to guide LLM selection and ordering of rewrite rules. Its upstream repository includes a Calcite rewriting component.


