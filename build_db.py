import sqlite3
import numpy as np
import pandas as pd
import geopandas as gpd
from pathlib import Path
from shapely.ops import transform

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DB = BASE / "ingres.db"

# ---- find the block file ----
print("Looking in:", DATA)
print("Files found:", [p.name for p in DATA.iterdir()] if DATA.exists() else "folder missing")

block_hits = [p for p in DATA.glob("*.geojson")
              if "AU2020" in p.name.upper()]
BLOCK_FILE = block_hits[0] if block_hits else None

print("Block file   :", BLOCK_FILE)
if BLOCK_FILE is None:
    raise SystemExit("No block file found in data/. Check the file name and folder.")

STATES = {"AN":"Andaman and Nicobar Islands","AP":"Andhra Pradesh","AR":"Arunachal Pradesh",
 "AS":"Assam","BR":"Bihar","CG":"Chhattisgarh","CH":"Chandigarh","DD":"Daman and Diu",
 "DL":"Delhi","DN":"Dadra and Nagar Haveli","GA":"Goa","GJ":"Gujarat","HP":"Himachal Pradesh",
 "HR":"Haryana","JH":"Jharkhand","JK":"Jammu and Kashmir","KA":"Karnataka","KL":"Kerala",
 "LD":"Lakshadweep","LK":"Ladakh","MH":"Maharashtra","ML":"Meghalaya","MN":"Manipur",
 "MP":"Madhya Pradesh","MZ":"Mizoram","NL":"Nagaland","OD":"Odisha","PB":"Punjab",
 "PY":"Puducherry","RJ":"Rajasthan","SK":"Sikkim","TN":"Tamil Nadu","TR":"Tripura",
 "TS":"Telangana","UK":"Uttarakhand","UP":"Uttar Pradesh","WB":"West Bengal"}

con = sqlite3.connect(DB)

# ================= BLOCKS =================
print("\nReading block file (takes a minute)...")
g = gpd.read_file(BLOCK_FILE)
print("Columns in file:", list(g.columns))

# coordinates are stored as (lat, lon); GeoJSON expects (lon, lat) -> swap
g["geometry"] = g.geometry.apply(lambda geom: transform(lambda x, y: (y, x), geom))
bd = g.geometry.bounds
print("lon range:", round(bd.minx.min(), 1), "to", round(bd.maxx.max(), 1), "(expect about 68 to 98)")
print("lat range:", round(bd.miny.min(), 1), "to", round(bd.maxy.max(), 1), "(expect about 6 to 37)")

g.insert(0, "block_id", range(1, len(g) + 1))

# lightweight map file
m = g[["block_id", "geometry"]].copy()
m["geometry"] = m.geometry.simplify(0.005, preserve_topology=True)
m.to_file(DATA / "blocks_map.geojson", driver="GeoJSON")

# one point inside each block
pts = g.geometry.representative_point()
g["lat"], g["lon"] = pts.y.round(5), pts.x.round(5)

b = pd.DataFrame(g.drop(columns="geometry")).drop(
    columns=["TEHSIL", "GWR_2011_2", "GmlID", "objectid", "st_length_shape_"], errors="ignore")
b = b.rename(columns={
    "BLOCK": "block", "DISTRICT": "district", "State_Name": "state_code",
    "CLASS": "category", "CODE": "category_code",
    "Net_Annual_Ground_Water_Availability": "net_annual_availability",
    "Annual_Ground_Water_Draft_Irrigation": "draft_irrigation",
    "Stage_of_Ground_Water__Development____": "stage_pct",
    "Annual_Ground_Water_Draft_Domestic_and_industrial_uses": "draft_domestic_industrial",
    "Annual_Ground_Water_Draft_Total": "draft_total",
    "Annual_Replenishable_Ground_Water_Resource_Total": "annual_replenishable_resource",
    "Natural_Discharge_during_non-monsoon_season": "natural_discharge_non_monsoon"})

num = ["stage_pct", "annual_replenishable_resource", "natural_discharge_non_monsoon",
       "net_annual_availability", "draft_irrigation", "draft_domestic_industrial", "draft_total"]
for c in num:
    b.loc[b[c] <= -999, c] = np.nan

print("\nSaline sample (do the numbers look real?):")
print(b[b["category"] == "Saline"][["block", "district", "stage_pct", "draft_total"]].head(5).to_string())

# Not Assessed / Saline rows with no real numbers -> NULL
empty = b["category"].isin(["Not Assessed", "Saline"]) & (b[num].fillna(0).abs().sum(axis=1) == 0)
b.loc[empty, num] = np.nan
print("Rows nulled (no real numbers):", int(empty.sum()))

for c in ["block", "district", "state_code", "category"]:
    b[c] = b[c].astype(str).str.strip()
b["block"], b["district"] = b["block"].str.title(), b["district"].str.title()
b["category"] = b["category"].replace({"Over Exploited": "Over-Exploited"})
b["state_name"] = b["state_code"].map(STATES)
b["area_km2"] = (b["st_area_shape_"] / 1e6).round(1)
b = b.drop(columns="st_area_shape_")
b["year"] = 2020

b.to_sql("blocks", con, if_exists="replace", index=False)
print(f"\nblocks: {len(b)} rows; unmapped state codes:",
      list(b.loc[b.state_name.isna(), "state_code"].unique()))

con.close()
print("\nDone. Created", DB)