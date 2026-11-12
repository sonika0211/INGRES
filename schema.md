# Database: ingres.db (SQLite)

## Table: blocks
One row per groundwater assessment block in India, from the 2020 assessment.

| Column | Type | Meaning |
|---|---|---|
| block_id | INTEGER | Unique row id |
| block | TEXT | Block (taluk/mandal) name, Title Case |
| district | TEXT | District name, Title Case |
| state_code | TEXT | Two-letter state code, e.g. KA |
| state_name | TEXT | Full state name, e.g. Karnataka |
| category | TEXT | Official status: Safe, Semi-Critical, Critical, Over-Exploited, Saline, Not Assessed |
| category_code | TEXT | Short code for category |
| stage_pct | REAL | Stage of groundwater development (%): draft / net availability x 100 |
| annual_replenishable_resource | REAL | Annual groundwater recharge. Unit: TO CONFIRM (likely ham) |
| natural_discharge_non_monsoon | REAL | Natural discharge in non-monsoon season. Same unit |
| net_annual_availability | REAL | Recharge minus natural discharge. Same unit |
| draft_irrigation | REAL | Annual extraction for irrigation. Same unit |
| draft_domestic_industrial | REAL | Annual extraction for domestic and industrial use. Same unit |
| draft_total | REAL | Total annual extraction (irrigation + domestic/industrial) |
| area_km2 | REAL | Block area in square km |
| lat, lon | REAL | A point inside the block (for maps) |
| year | INTEGER | Assessment year (2020) |

## Rules
- NULL in any numeric column means "not assessed / no data", never zero.
- `category` is the official label. Never recompute it from stage_pct, because the official method also uses water-level trends.
- Stage thresholds for reference only: Safe <=70, Semi-Critical 70-90, Critical 90-100, Over-Exploited >100.
- Use `category = 'Over-Exploited'` with a hyphen. Names are Title Case, so match case-insensitively with LIKE or LOWER().
- District-level figures must be computed from sums: SUM(draft_total) / SUM(net_annual_availability) * 100. Never average stage_pct.
- Only the 2020 assessment exists. There is no historical data and no water-level (depth) data.
- Place names vary (Bangalore/Bengaluru); the database uses the official spelling.

## Example questions and SQL
Q: How many over-exploited blocks are in Karnataka?
SELECT COUNT(*) FROM blocks WHERE state_name = 'Karnataka' AND category = 'Over-Exploited';

Q: Top 5 districts in Punjab by total groundwater draft
SELECT district, SUM(draft_total) AS total_draft FROM blocks WHERE state_name = 'Punjab' GROUP BY district ORDER BY total_draft DESC LIMIT 5;