"""
Abstract / anonymize SQL into a compact form.

Goal:
- Replace table names with table1, table2, ...
- Replace column names with col1, col2, ...
- Keep reference consistency across the query
- Compress redundant predicates in AND-chains: multiple (col op constant) or
  (col = constant), keep one representative; others become TRUE

Usage:
  python abstract_simplify_sql.py --in input.sql --out output.sql
  cat input.sql | python abstract_simplify_sql.py
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from sqlglot import exp, parse_one


@dataclass
class _Maps:
    table: Dict[str, str]
    column: Dict[str, str]


def _norm_ident(name: str) -> str:
    return name.strip().strip('"').lower()


def _is_literal(e: exp.Expression) -> bool:
    return isinstance(e, (exp.Literal, exp.Boolean, exp.Null))


def _is_literalish(e: exp.Expression) -> bool:
    """Literal, NULL, boolean, or CAST/TRY_CAST around a literalish expr."""
    if _is_literal(e):
        return True
    if isinstance(e, (exp.Cast, exp.TryCast)) and e.this is not None:
        return _is_literalish(e.this)
    return False


_COMPARISON_TYPES = (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)


def _is_col_op_literal(e: exp.Expression) -> bool:
    """col <op> constant (constant side may be CAST('x' AS DATE), etc.)."""
    if type(e) not in _COMPARISON_TYPES:
        return False
    a, b = e.left, e.right
    return (isinstance(a, exp.Column) and _is_literalish(b)) or (
        isinstance(b, exp.Column) and _is_literalish(a)
    )


def _is_col_between_literals(e: exp.Expression) -> bool:
    """col BETWEEN literalish AND literalish."""
    if not isinstance(e, exp.Between):
        return False
    low = e.args.get("low")
    high = e.args.get("high")
    return (
        isinstance(e.this, exp.Column)
        and low is not None
        and high is not None
        and _is_literalish(low)
        and _is_literalish(high)
    )


def _is_compressible_col_const_predicate(e: exp.Expression) -> bool:
    return _is_col_op_literal(e) or _is_col_between_literals(e)


def _unwrap_parens(e: exp.Expression) -> exp.Expression:
    while isinstance(e, exp.Paren):
        inner = e.this
        if inner is None:
            break
        e = inner
    return e


def _flatten_and(e: exp.Expression) -> List[exp.Expression]:
    out: List[exp.Expression] = []

    def rec(x: exp.Expression) -> None:
        x = _unwrap_parens(x)
        if isinstance(x, exp.And):
            rec(x.left)
            rec(x.right)
        else:
            out.append(x)

    rec(_unwrap_parens(e))
    return out


def _rebuild_and(terms: List[exp.Expression]) -> exp.Expression:
    if not terms:
        return exp.true()
    cur = terms[0]
    for t in terms[1:]:
        cur = exp.and_(cur, t)
    return cur


def _simplify_boolean(e: exp.Expression) -> exp.Expression:
    """
    Very small boolean simplifier:
    - TRUE AND x -> x
    - x AND TRUE -> x
    """
    if isinstance(e, exp.And):
        left = _simplify_boolean(e.left)
        right = _simplify_boolean(e.right)
        if isinstance(left, exp.Boolean) and left.this is True:
            return right
        if isinstance(right, exp.Boolean) and right.this is True:
            return left
        e.set("this", left)
        e.set("expression", right)
        return e
    return e


def compress_constant_predicates(where_expr: exp.Expression) -> exp.Expression:
    """
    In a single AND-chain (including under redundant parentheses), keep only ONE
    predicate of the form (col <cmp> constant) or (constant <cmp> col), including
    CAST(...) around the constant. Extra ones become TRUE.

    Example: (col >= d1 AND col < d2) -> keeps the first comparison only.
    This is for abstraction compactness, not semantic preservation.
    """
    terms = _flatten_and(where_expr)
    kept: List[exp.Expression] = []
    kept_one_col_const = False
    for t in terms:
        if _is_compressible_col_const_predicate(t):
            if not kept_one_col_const:
                kept.append(t)
                kept_one_col_const = True
            else:
                kept.append(exp.true())
        else:
            kept.append(t)
    return _simplify_boolean(_rebuild_and(kept))


def _collect_table_names(tree: exp.Expression) -> List[str]:
    """
    Collect base table identifiers (not aliases) in first-seen order.
    """
    seen: Set[str] = set()
    ordered: List[str] = []
    for t in tree.find_all(exp.Table):
        name = t.name
        if not name:
            continue
        n = _norm_ident(name)
        if n in seen:
            continue
        seen.add(n)
        ordered.append(name)
    return ordered


def _collect_column_names(tree: exp.Expression) -> List[str]:
    """
    Collect column identifiers in first-seen order.
    Uses only the column *name* (not the table qualifier) to produce col1/col2...
    """
    seen: Set[str] = set()
    ordered: List[str] = []
    for c in tree.find_all(exp.Column):
        name = c.name
        if not name:
            continue
        n = _norm_ident(name)
        if n in seen:
            continue
        seen.add(n)
        ordered.append(name)
    return ordered


def build_maps(sql: str) -> _Maps:
    tree = parse_one(sql)
    tables = _collect_table_names(tree)
    cols = _collect_column_names(tree)
    table_map = { _norm_ident(t): f"table{i+1}" for i, t in enumerate(tables) }
    col_map = { _norm_ident(c): f"col{i+1}" for i, c in enumerate(cols) }
    return _Maps(table=table_map, column=col_map)


def abstract_sql(sql: str) -> str:
    tree = parse_one(sql)
    maps = build_maps(sql)

    def transform(node: exp.Expression) -> exp.Expression:
        # Replace base table names, keep aliases untouched (alias is a separate node).
        if isinstance(node, exp.Table):
            name = node.name
            if name:
                key = _norm_ident(name)
                if key in maps.table:
                    node.set("this", exp.Identifier(this=maps.table[key]))
            return node

        # Replace column names; keep qualifiers as-is (could be alias).
        if isinstance(node, exp.Column):
            name = node.name
            if name:
                key = _norm_ident(name)
                if key in maps.column:
                    node.set("this", exp.Identifier(this=maps.column[key]))
            return node

        # Compress AND-chains inside WHERE
        if isinstance(node, exp.Where):
            inner = node.this
            if isinstance(inner, exp.Expression):
                node.set("this", compress_constant_predicates(inner))
            return node

        return node

    # sqlglot transform walks the tree and replaces nodes with returned value
    tree = tree.transform(transform)
    return tree.sql(pretty=False)


def _read_text(path: Optional[str]) -> str:
    if not path:
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_text(path: Optional[str], text: str) -> None:
    if not path:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
        if not text.endswith("\n"):
            f.write("\n")


def _default_anonymous_jsonl_path(input_path: str) -> str:
    p = Path(input_path).expanduser().resolve()
    stem = p.stem
    if stem.endswith("_anonymous"):
        out_name = f"{stem}.jsonl"
    else:
        out_name = f"{stem}_anonymous.jsonl"
    return str(p.with_name(out_name))


def _process_jsonl_sql_field(input_path: str, output_path: str, sql_field: str = "sql") -> None:
    in_path = Path(input_path).expanduser().resolve()
    out_path = Path(output_path).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    rewritten = 0
    with in_path.open("r", encoding="utf-8") as fin, out_path.open("w", encoding="utf-8") as fout:
        for line_no, line in enumerate(fin, 1):
            text = line.strip()
            if not text:
                continue
            total += 1
            obj = json.loads(text)
            if not isinstance(obj, dict):
                raise ValueError(f"{in_path}:{line_no}: each line must be a JSON object")
            sql_text = str(obj.get(sql_field, "") or "").strip()
            if sql_text:
                obj[sql_field] = abstract_sql(sql_text)
                rewritten += 1
            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")

    print(
        json.dumps(
            {
                "mode": "jsonl",
                "input_jsonl": str(in_path),
                "output_jsonl": str(out_path),
                "sql_field": sql_field,
                "total_rows": total,
                "rewritten_rows": rewritten,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="in_path", default=None, help="Input SQL file. If omitted, read stdin.")
    p.add_argument("--out", dest="out_path", default=None, help="Output file. If omitted, write to stdout.")
    p.add_argument("--jsonl-in", dest="jsonl_in", default=None, help="Input JSONL file path.")
    p.add_argument(
        "--jsonl-out",
        dest="jsonl_out",
        default=None,
        help="Output JSONL path. If omitted, auto-generate with suffix '_anonymous.jsonl'.",
    )
    p.add_argument(
        "--jsonl-sql-field",
        dest="jsonl_sql_field",
        default="sql",
        help="SQL field name in JSONL objects (default: sql).",
    )
    args = p.parse_args()

    if args.jsonl_in:
        jsonl_out = args.jsonl_out or _default_anonymous_jsonl_path(args.jsonl_in)
        _process_jsonl_sql_field(args.jsonl_in, jsonl_out, args.jsonl_sql_field)
        return

    sql = _read_text(args.in_path).strip()
    if not sql:
        raise SystemExit("Empty SQL input")
    out = abstract_sql(sql)
    _write_text(args.out_path, out)


if __name__ == "__main__":
    main()

