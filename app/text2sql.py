"""Question -> validated SQL -> rows.   ask(question) is the main entry point."""
import re
from pathlib import Path

import pandas as pd

from validator import SchemaInfo, ValidationError, run_readonly, validate

DB_PATH = Path(__file__).resolve().parent.parent / "ingres.db"
FOUR = "('Safe','Semi-Critical','Critical','Over-Exploited')"

RULES = f"""You convert questions about Indian groundwater assessment data into ONE SQLite SELECT query.

Output rules
- Output only the SQL. No explanation, no markdown fences.
- If the question cannot be answered from the tables below (for example water levels, rainfall,
  forecasts, or places outside India), output exactly: UNSUPPORTED: <short reason>
- Use single quotes for text values.

Data rules
- blocks has one row per assessment unit (block/mandal/taluk) from the 2020 assessment.
- Volumes are in ham (hectare-metres) per year.
- stage_pct = draft_total / net_annual_availability * 100.
- category is one of 'Safe','Semi-Critical','Critical','Over-Exploited','Saline','Not Assessed'.
  Use the category column as stored. Never derive a category from stage_pct.
- For rankings, averages, sums and category counts of assessed blocks, add
  category IN {FOUR}.
- NULL means not assessed or not reported. Never treat NULL as zero.
  natural_discharge_non_monsoon is NULL for some assessed blocks.
- Block names repeat across districts and states (for example 'Reserved Forest'),
  so filter by state_name and district. state_name holds full names such as 'Karnataka';
  state_code holds two-letter codes.
- lat/lon is a point inside the block; area_km2 is in square kilometres.
"""

EXAMPLES = f"""Examples
Q: Which blocks in Karnataka are over-exploited?
SQL: SELECT district, block, stage_pct FROM blocks WHERE state_name = 'Karnataka' AND category = 'Over-Exploited' ORDER BY stage_pct DESC

Q: How many blocks are in each category in Tamil Nadu?
SQL: SELECT category, COUNT(*) AS blocks FROM blocks WHERE state_name = 'Tamil Nadu' GROUP BY category ORDER BY blocks DESC

Q: Top 5 districts in Punjab by average stage of extraction
SQL: SELECT district, ROUND(AVG(stage_pct), 1) AS avg_stage_pct FROM blocks WHERE state_name = 'Punjab' AND category IN {FOUR} GROUP BY district ORDER BY avg_stage_pct DESC LIMIT 5

Q: Total annual recharge in Kerala
SQL: SELECT SUM(annual_replenishable_resource) AS total_recharge_ham FROM blocks WHERE state_name = 'Kerala' AND category IN {FOUR}

Q: What is the groundwater level in Pune?
SQL: UNSUPPORTED: this data has assessment figures, not water level measurements
"""


def build_system_prompt(schema):
    tables = "\n".join(f"{t}({', '.join(sorted(c))})" for t, c in sorted(schema.tables.items()))
    return f"{RULES}\nTables\n{tables}\n\n{EXAMPLES}"


def clean(text):
    text = re.sub(r"^```(?:sql)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    return re.sub(r"^SQL:\s*", "", text, flags=re.IGNORECASE)


def ask(question, llm, schema=None, max_tries=3, db_path=DB_PATH):
    """Returns a dict with status: ok | clarify | unsupported | failed."""
    schema = schema or SchemaInfo(db_path)
    system = build_system_prompt(schema)
    prompt, history = f"Q: {question}\nSQL:", []
    for attempt in range(1, max_tries + 1):
        raw = clean(llm(system, prompt))
        history.append(raw)
        if raw.upper().startswith("UNSUPPORTED"):
            return {"status": "unsupported", "message": raw.split(":", 1)[-1].strip(), "tries": attempt}
        try:
            sql = validate(raw, schema)
            cols, rows = run_readonly(db_path, sql)
            return {"status": "ok", "sql": sql, "data": pd.DataFrame(rows, columns=cols), "tries": attempt}
        except ValidationError as e:
            if e.kind == "entity":        # ask the user instead of guessing
                return {"status": "clarify", "message": str(e), "suggestions": e.suggestions}
            error = str(e)
        except Exception as e:            # database error (e.g. timeout)
            error = f"Database error: {e}"
        prompt = (f"Q: {question}\nYour previous SQL:\n{raw}\nIt failed: {error}\n"
                  f"Write a corrected SQL query.\nSQL:")
    return {"status": "failed", "message": error, "attempts": history}
