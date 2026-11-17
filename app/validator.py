"""SQL validation for the INGRES chatbot.

validate(sql, schema) -> safe SQL string, or raises ValidationError.
run_readonly(db_path, sql) -> (columns, rows), executed on a read-only connection.
"""
import re
import sqlite3
import time
from pathlib import Path

import sqlglot
from sqlglot import exp
from rapidfuzz import fuzz, process

NAME_COLUMNS = ("state_name", "district", "block")   # columns whose values we check
MAX_ROWS = 200

# Optional: map common spellings to the exact name used in your data, e.g.
# ALIASES = {"bangalore urban": "Bengaluru Urban"}.  Fill in after you see the real names.
ALIASES = {}


class ValidationError(Exception):
    """kind is one of: 'syntax', 'unsafe', 'schema', 'entity'."""

    def __init__(self, message, kind="syntax", suggestions=None):
        super().__init__(message)
        self.kind = kind
        self.suggestions = suggestions or []


def norm(s):
    """lower-case, letters and digits only: 'Chanditala -II' -> 'chanditalaii'."""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


class SchemaInfo:
    """Reads table/column names and the list of valid place names from the database."""

    def __init__(self, db_path):
        self.db_path = str(db_path)
        if not Path(self.db_path).exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}. Run build_db.py first.")
        con = sqlite3.connect(self.db_path)
        self.tables = {}
        for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            self.tables[t.lower()] = {r[1].lower() for r in con.execute(f'PRAGMA table_info("{t}")')}
        self.names = {c: {} for c in NAME_COLUMNS}
        for t, cols in self.tables.items():
            for c in NAME_COLUMNS:
                if c in cols:
                    for (v,) in con.execute(f'SELECT DISTINCT "{c}" FROM "{t}" WHERE "{c}" IS NOT NULL'):
                        self.names[c][norm(v)] = v
        con.close()


def _resolve(column, value, schema):
    """Return the exact stored spelling of a place name, or raise with suggestions."""
    known = schema.names.get(column, {})
    n = norm(value)
    n = norm(ALIASES.get(n, value))
    if n in known:
        return known[n]
    hits = process.extract(value, list(known.values()), scorer=fuzz.WRatio, limit=3, score_cutoff=70)
    raise ValidationError(f"{column} '{value}' was not found in the data.", "entity",
                          [h[0] for h in hits])


def validate(sql, schema):
    sql = sql.strip().rstrip(";").strip()
    try:
        parsed = sqlglot.parse(sql, read="sqlite")
    except sqlglot.errors.SqlglotError as e:
        raise ValidationError(f"The SQL could not be parsed: {e}", "syntax")
    parsed = [p for p in parsed if p is not None]
    if len(parsed) != 1:
        raise ValidationError("Exactly one SQL statement is allowed.", "unsafe")
    stmt = parsed[0]
    if not isinstance(stmt, (exp.Select, exp.Union)):
        raise ValidationError("Only SELECT statements are allowed.", "unsafe")

    # ---- tables ----
    ctes = {c.alias.lower() for c in stmt.find_all(exp.CTE)}
    alias_to_table, used = {}, set()
    for t in stmt.find_all(exp.Table):
        name = t.name.lower()
        if name in ctes:
            continue
        if name not in schema.tables:
            raise ValidationError(
                f"Unknown table '{t.name}'. Available tables: {', '.join(sorted(schema.tables))}.",
                "schema")
        used.add(name)
        alias_to_table[(t.alias or t.name).lower()] = name

    # ---- columns ----
    select_aliases = {a.alias.lower() for a in stmt.find_all(exp.Alias)}
    allowed = set().union(*(schema.tables[t] for t in used)) if used else set()
    for col in stmt.find_all(exp.Column):
        name = col.name.lower()
        if name in select_aliases:
            continue
        if col.table:
            tbl = alias_to_table.get(col.table.lower())
            if tbl and name not in schema.tables[tbl]:
                raise ValidationError(f"Table '{tbl}' has no column '{col.name}'.", "schema")
            continue
        if name not in allowed:
            raise ValidationError(
                f"Unknown column '{col.name}'. If it was meant as a text value, put it in single "
                f"quotes. Columns available: {', '.join(sorted(allowed))}.", "schema")

    # ---- place names: fix spelling/case, or ask the user ----
    def check(column_node, literal_nodes):
        if not isinstance(column_node, exp.Column):
            return
        col = column_node.name.lower()
        if col not in NAME_COLUMNS:
            return
        for lit in literal_nodes:
            if isinstance(lit, exp.Literal) and lit.is_string:
                lit.replace(exp.Literal.string(_resolve(col, lit.name, schema)))

    for node in list(stmt.find_all(exp.EQ, exp.NEQ)):
        check(node.this, [node.expression])
        check(node.expression, [node.this])
    for node in list(stmt.find_all(exp.In)):
        check(node.this, node.expressions)

    # ---- row limit ----
    if not stmt.args.get("limit"):
        stmt = stmt.limit(MAX_ROWS)
    return stmt.sql(dialect="sqlite")


def run_readonly(db_path, sql, timeout_s=10):
    """Execute on a read-only connection with a time limit."""
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    start = time.time()
    con.set_progress_handler(lambda: 1 if time.time() - start > timeout_s else 0, 100000)
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    finally:
        con.close()
    return cols, rows
