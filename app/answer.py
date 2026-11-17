"""Turn a query result into a short answer, and check it against the data.

make_answer(question, result, llm) -> dict with keys:
    answer    text to show the user (always safe: either LLM text that passed the checks, or plain text)
    verified  True if every number in the answer was found in the query result
    flags     what the checker found (for logging and for your evaluation)
    table     the result table (DataFrame) or None
    sql       the SQL that produced it
    llm_calls how many LLM calls were used (0 when no LLM was needed)
"""
import numbers
import re

import pandas as pd

MAX_ROWS_TO_LLM = 30
SOURCE = "Source: CGWB groundwater resource assessment 2020 (INGRES / India-WRIS)."
VOLUME_WORDS = ("recharge", "draft", "availability", "discharge", "resource", "demand", "ham")
NUM_RE = re.compile(r"(?<!\w)-?\d[\d,]*(?:\.\d+)?")

SYSTEM = """You write short answers about Indian groundwater data, using ONLY the table you are given.
Rules:
- Use only numbers that appear in the table. Never calculate new numbers
  (no totals, percentages, averages or differences).
- Do not add facts that are not in the table. Do not give advice or predictions.
- Name places exactly as written in the table.
- stage_pct is the stage of extraction, a percentage. Volumes are in ham (hectare-metres) per year.
- Write 1 to 4 plain sentences. Do not number or bullet anything.
- If the table has more rows than shown, say how many rows there are in total and describe only
  the rows shown.
- Output only the answer text."""


# ---------------- number checking ----------------
def _numbers(text):
    """All numbers in a piece of text as (value, decimals, raw_text)."""
    out = []
    for raw in NUM_RE.findall(str(text)):
        s = raw.replace(",", "").rstrip(".")
        try:
            out.append((float(s), len(s.split(".")[1]) if "." in s else 0, raw.strip(",")))
        except ValueError:
            pass
    return out


def _allowed_numbers(df, question):
    vals = {2020.0, float(len(df)), float(min(len(df), MAX_ROWS_TO_LLM))}
    for col in df.columns:
        for v in df[col].dropna():
            if isinstance(v, numbers.Real) and not isinstance(v, bool):
                vals.add(float(v))
            else:
                vals.update(x for x, _, _ in _numbers(v))
    vals.update(x for x, _, _ in _numbers(question))
    return vals


def unsupported_numbers(answer, df, question):
    """Numbers in `answer` that cannot be traced to the table (rounding is allowed)."""
    allowed = _allowed_numbers(df, question)
    bad = []
    for x, d, raw in _numbers(answer):
        tol = 0.5 * 10 ** (-d) + 1e-9
        if not any(abs(v - x) <= tol for v in allowed):
            bad.append(raw)
    return bad


# ---------------- plain (no-LLM) text ----------------
def _fmt(v):
    if isinstance(v, numbers.Integral):
        return f"{int(v):,}"
    if isinstance(v, numbers.Real):
        return f"{v:,.2f}"
    return str(v)


def _plain_answer(df):
    if df.shape == (1, 1):
        return f"The result is {_fmt(df.iloc[0, 0])}."
    n = len(df)
    return f"Found {n} matching row{'s' if n != 1 else ''}; see the table."


def _footer(df):
    notes = [SOURCE]
    if any(w in str(c).lower() for c in df.columns for w in VOLUME_WORDS):
        notes.append("Volumes are in ham (hectare-metres) per year.")
    if df.isna().any().any():
        notes.append("Blank values were not reported in the source data.")
    return " ".join(notes)


def _cap(text):
    text = str(text).strip()
    return text[:1].upper() + text[1:]


# ---------------- main entry ----------------
def make_answer(question, result, llm):
    status = result["status"]
    base = {"verified": True, "flags": [], "table": None, "sql": result.get("sql"), "llm_calls": 0}

    if status == "unsupported":
        base["answer"] = ("I can't answer that from the data I have. "
                          f"{_cap(result.get('message', '')).rstrip('.')}.")
        return base
    if status == "clarify":
        hint = result.get("suggestions") or []
        base["answer"] = _cap(result["message"]) + (f" Did you mean: {', '.join(hint)}?" if hint
                                              else " Please check the spelling.")
        return base
    if status != "ok":
        base["answer"] = "I couldn't build a reliable query for that question. Try rephrasing it."
        base["flags"].append(result.get("message", "failed"))
        base["verified"] = False
        return base

    df = result["data"]
    base["table"] = df
    if df.empty:
        base["answer"] = ("No records matched that question in the 2020 block assessment data. "
                          "Check the place name or try a broader question.")
        return base

    shown = df.head(MAX_ROWS_TO_LLM).round(2)
    first = (f"Question: {question}\nTotal rows: {len(df)} (showing {len(shown)})\n"
             f"Table (CSV):\n{shown.to_csv(index=False)}\nAnswer:")
    prompt, text, verified = first, None, False
    for _ in range(2):
        try:
            text = llm(SYSTEM, prompt).strip()
            base["llm_calls"] += 1
        except Exception as e:
            base["flags"].append(f"LLM error: {type(e).__name__}")
            text = None
            break
        bad = unsupported_numbers(text, df, question)
        if not bad:
            verified = True
            break
        base["flags"].append(f"numbers not found in data: {bad}")
        prompt = (first.rsplit("Answer:", 1)[0] +
                  f"Your previous answer used numbers that are not in the table: {bad}. "
                  f"Rewrite it using only numbers from the table.\nAnswer:")

    if not verified:                       # never show unchecked LLM text
        text = _plain_answer(df)
        base["flags"].append("used plain fallback answer")
    base["answer"] = f"{text}\n{_footer(df)}"
    base["verified"] = verified
    return base
