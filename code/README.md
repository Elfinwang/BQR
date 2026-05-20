# BQR

## Overview

This project provides a pipeline for:

* Building training datasets for Pointer Network based cut-edge selection
* Training and evaluating PointerNet models
* Predicting SQL cut edges using trained checkpoints
* Applying predicted cut edges for SQL rewriting
* Anonymous SQL abstraction preprocessing
* Supporting multiple rewrite backends:
    * Calcite Rule-based Rewriter
    * LLM-R2 Rewriter
    * QUITE Rewriter
    * R-Bot Rewriter

## PointerNet Training

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

## Predicting Cut Edges
Use a trained PointerNet checkpoint to predict SQL cut edges.
```
python BQR/pointer_net_cut_selector/predict_pointer_net.py \
  --checkpoint [BEST_CHECKPOINT_PATH] \
  --input-jsonl [INPUT_JSONL_PATH] \
  --output-jsonl [OUTPUT_JSONL_PATH]
  ```

  ## Apply Predicted Cut Edges for SQL Rewriting
  Apply predicted cut edges and generate rewritten SQL queries.
  ```
python BQR/submodular_cut_validation/apply_predicted_cut_rewrite.py \
  --jsonl [CUT_EDGE_JSONL_PATH] \
  [--rewrite-backend [llmr2/quite/rbot]] \
  --output [OUTPUT_JSONL_PATH] 
  ```




## Supported Rewrite Backends
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

### 2. QuiteBackend

Integration with the QUITE SQL rewriting framework.

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