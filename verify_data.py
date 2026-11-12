import sqlite3
import pandas as pd

con = sqlite3.connect("ingres.db")
b = pd.read_sql("SELECT * FROM blocks", con)
pd.set_option("display.width", 200)

print("Rows:", len(b))
print("\n--- Missing values per column ---")
print(b.isna().sum().to_string())

print("\n--- Duplicate (state, district, block) ---")
dups = b[b.duplicated(["state_code", "district", "block"], keep=False)]
print(len(dups), "rows involved")
print(dups[["state_code", "district", "block", "category"]].head(10).to_string())

print("\n--- Blocks per state ---")
print(b.groupby("state_name").size().sort_values(ascending=False).to_string())

print("\n--- Category counts ---")
print(b["category"].value_counts(dropna=False).to_string())

# 1. total draft = irrigation + domestic/industrial
chk = b.dropna(subset=["draft_total", "draft_irrigation", "draft_domestic_industrial"]).copy()
chk["diff"] = (chk["draft_total"] - chk["draft_irrigation"] - chk["draft_domestic_industrial"]).abs()
bad = chk[chk["diff"] > 0.02 * chk["draft_total"].clip(lower=1)]
print(f"\n[1] draft_total != irrigation + dom/ind: {len(bad)} of {len(chk)}")
print(bad[["block", "district", "draft_total", "draft_irrigation", "draft_domestic_industrial"]].head(5).to_string())

# 2. stage % = draft_total / net availability * 100
chk = b.dropna(subset=["stage_pct", "draft_total", "net_annual_availability"])
chk = chk[chk["net_annual_availability"] > 0].copy()
chk["calc_stage"] = chk["draft_total"] / chk["net_annual_availability"] * 100
bad = chk[(chk["calc_stage"] - chk["stage_pct"]).abs() > 1]
print(f"\n[2] stage_pct differs from draft/availability*100 by >1 point: {len(bad)} of {len(chk)}")
print(bad[["block", "district", "stage_pct", "calc_stage"]].head(5).to_string())

# 3. net availability = recharge - natural discharge
chk = b.dropna(subset=["net_annual_availability", "annual_replenishable_resource", "natural_discharge_non_monsoon"]).copy()
chk["calc_net"] = chk["annual_replenishable_resource"] - chk["natural_discharge_non_monsoon"]
bad = chk[(chk["calc_net"] - chk["net_annual_availability"]).abs() > 0.02 * chk["net_annual_availability"].abs().clip(lower=1)]
print(f"\n[3] net availability != recharge - discharge: {len(bad)} of {len(chk)}")

# 4. category matches stage thresholds
def expected(p):
    if pd.isna(p): return None
    if p <= 70: return "Safe"
    if p <= 90: return "Semi-Critical"
    if p <= 100: return "Critical"
    return "Over-Exploited"
chk = b[b["category"].isin(["Safe", "Semi-Critical", "Critical", "Over-Exploited"])].copy()
chk["expected"] = chk["stage_pct"].apply(expected)
bad = chk[chk["expected"] != chk["category"]]
print(f"\n[4] category disagrees with stage thresholds: {len(bad)} of {len(chk)}")
print(bad[["block", "district", "stage_pct", "category", "expected"]].head(5).to_string())

# 5. outliers
print("\n[5] negative values:", int((b.select_dtypes("number").drop(columns=["lat", "lon"]) < 0).sum().sum()))
print("    stage_pct > 500:", int((b["stage_pct"] > 500).sum()))
print("    area_km2 == 0 or null:", int((b["area_km2"].fillna(0) == 0).sum()))

# 6. sample for manual checking against the portal
cats = ["Safe", "Semi-Critical", "Critical", "Over-Exploited"]
sample = pd.concat([b[b["category"] == c].sample(3, random_state=42) for c in cats])
# also include a few blocks the checks flagged, so you can see which side the portal agrees with
flagged = b[b["block"].isin(["Amta -I", "Pursura", "Bagda", "Chanditala -Ii"])]
sample = pd.concat([sample, flagged]).drop_duplicates()
cols = ["state_name", "district", "block", "category", "stage_pct",
        "annual_replenishable_resource", "net_annual_availability", "draft_total"]
sample[cols].to_csv("verification_sample.csv", index=False)
print("\nSaved verification_sample.csv with", len(sample), "blocks to check by hand.")
con.close()