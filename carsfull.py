"""
Clean the Kaggle Craigslist used-car listings (2000-2020) and join them to the
NHTSA complaints file on make + model + model year.

Inputs (put next to this script):
  vehicles.csv.zip                    Kaggle "craigslist-carstrucks-data" (zip is fine, never unzipped)
  nhtsa_complaints_2000_2020.csv      output of the NHTSA filtering script

Outputs:
  craigslist_clean_2000_2020.csv      cleaned listings, original header names kept
  listings_with_complaints.csv        every listing + complaint stats for its make/model/year
  model_summary.csv                   one row per make/model (for the reliability analysis)
  unmatched_models.csv                Craigslist models that found no NHTSA match (inspect these)
"""
import re
import pandas as pd

# ---------------------------------------------------------------- CONFIG
CRAIGSLIST_PATH = "vehicles.csv.zip"
NHTSA_PATH = "nhtsa_complaints_2000_2020.csv"

YEAR_MIN, YEAR_MAX = 2000, 2020
PRICE_MIN, PRICE_MAX = 300, 100_000      # drops $0 and joke prices
ODO_MIN, ODO_MAX = 1, 400_000            # drops 0 and absurd odometers
MIN_LISTINGS = 30                         # min listings per model for model_summary
CHUNK_ROWS = 200_000

# Big/unneeded columns skipped at read time. Every other original header is kept as-is.
DROP_COLS = {"url", "region_url", "image_url", "description", "county", "lat", "long"}

# Craigslist make spellings that differ from NHTSA's after punctuation is stripped
MAKE_ALIASES = {"VW": "VOLKSWAGEN", "CHEVY": "CHEVROLET", "MERCEDES": "MERCEDESBENZ"}


def key_series(s: pd.Series) -> pd.Series:
    """Uppercase and strip everything except letters/digits: 'F-150' -> 'F150'."""
    return (
        s.fillna("").astype(str).str.upper()
        .str.replace(r"[^A-Z0-9]", "", regex=True)
    )

# ------------------------------------------------ PART 1: stream + clean Craigslist
# Read the (zipped) CSV in chunks and keep only rows that pass the filters,
# so the full ~GB file is never held in memory.
kept = []
n_read = 0
for chunk in pd.read_csv(
    CRAIGSLIST_PATH,
    chunksize=CHUNK_ROWS,
    usecols=lambda c: c not in DROP_COLS,
    low_memory=False,
):
    n_read += len(chunk)
    for c in ["year", "price", "odometer"]:
        chunk[c] = pd.to_numeric(chunk[c], errors="coerce")
    keep = (
        chunk["year"].between(YEAR_MIN, YEAR_MAX)
        & chunk["price"].between(PRICE_MIN, PRICE_MAX)
        & chunk["odometer"].between(ODO_MIN, ODO_MAX)
        & chunk["manufacturer"].notna()
        & chunk["model"].notna()
    )
    kept.append(chunk[keep])

cl = pd.concat(kept, ignore_index=True)
cl["year"] = cl["year"].astype(int)
print(f"Craigslist: read {n_read:,} rows, kept {len(cl):,} after filters")

# Craigslist reposts the same car many times: drop duplicates
has_vin = cl["VIN"].notna()
cl = pd.concat([
    cl[has_vin].drop_duplicates(subset="VIN"),
    cl[~has_vin],
]).drop_duplicates(subset=["manufacturer", "model", "year", "price", "odometer"])
cl = cl.reset_index(drop=True)
print(f"Craigslist: {len(cl):,} rows after de-duplicating")

cl.to_csv("craigslist_clean_2000_2020.csv", index=False)

# ------------------------------------------------ PART 2: NHTSA complaints
nh = pd.read_csv(NHTSA_PATH, low_memory=False)
nh["year"] = pd.to_numeric(nh["YEARTXT"], errors="coerce")
nh = nh[nh["year"].between(YEAR_MIN, YEAR_MAX)].copy()
nh["year"] = nh["year"].astype(int)

nh["make_key"] = key_series(nh["MAKETXT"]).replace(MAKE_ALIASES)
nh["model_key"] = key_series(nh["MODELTXT"])
nh["MILES"] = pd.to_numeric(nh["MILES"], errors="coerce")
nh["miles_pos"] = nh["MILES"].where(nh["MILES"] > 0)      # 0 means "not reported"
nh["towed"] = (nh["VEHICLES_TOWED_YN"] == "Y").astype(int)
nh["engine_pt"] = (
    nh["COMPDESC"].fillna("").str.contains("ENGINE|POWER TRAIN", regex=True).astype(int)
)

AGG = dict(
    n_complaints=("CMPLID", "count"),
    median_fail_miles=("miles_pos", "median"),
    pct_towed=("towed", "mean"),
    n_engine_powertrain=("engine_pt", "sum"),
)
comp_year = nh.groupby(["make_key", "model_key", "year"]).agg(**AGG).reset_index()
comp_model = nh.groupby(["make_key", "model_key"]).agg(**AGG).reset_index()

# ------------------------------------------------ PART 3: match model names
# Craigslist 'model' is free text ("f-150 xlt supercrew"); NHTSA's is clean ("F-150").
# For each make, find the longest NHTSA model name that the Craigslist text starts with.
cl["make_key"] = key_series(cl["manufacturer"]).replace(MAKE_ALIASES)
cl["cl_model_key"] = key_series(cl["model"])
cl["cl_model_key"] = [      # drop a leading make name: "hondaaccord" -> "accord"
    m[len(k):] if m.startswith(k) and len(m) > len(k) else m
    for k, m in zip(cl["make_key"], cl["cl_model_key"])
]

nh_models = nh[["make_key", "model_key"]].drop_duplicates()
nh_models = nh_models[(nh_models["make_key"] != "") & (nh_models["model_key"] != "")]
models_by_make = {
    mk: sorted(g["model_key"], key=len, reverse=True)
    for mk, g in nh_models.groupby("make_key")
}


def match_model(make_key, cl_key):
    for k in models_by_make.get(make_key, []):
        if cl_key == k or (len(k) >= 3 and cl_key.startswith(k)):
            return k
    return None


pairs = cl[["make_key", "cl_model_key"]].drop_duplicates().copy()
pairs["nhtsa_key"] = [match_model(a, b) for a, b in zip(pairs["make_key"], pairs["cl_model_key"])]
pairs["matched_to_nhtsa"] = pairs["nhtsa_key"].notna()
pairs["model_key"] = pairs["nhtsa_key"].fillna(pairs["cl_model_key"])

cl = cl.merge(pairs, on=["make_key", "cl_model_key"], how="left")
print(f"Listings matched to an NHTSA model name: {cl['matched_to_nhtsa'].mean():.1%}")

unmatched = (
    cl[~cl["matched_to_nhtsa"]]
    .groupby(["make_key", "cl_model_key"]).size()
    .sort_values(ascending=False).rename("n_listings").reset_index()
)
unmatched.to_csv("unmatched_models.csv", index=False)

# ------------------------------------------------ PART 4: join on make + model + year
joined = cl.merge(comp_year, on=["make_key", "model_key", "year"], how="left")
joined["n_complaints"] = joined["n_complaints"].fillna(0).astype(int)
joined["n_engine_powertrain"] = joined["n_engine_powertrain"].fillna(0).astype(int)
joined.to_csv("listings_with_complaints.csv", index=False)
print(f"Joined table: {len(joined):,} rows")

# ------------------------------------------------ PART 5: model-level summary
listings_model = (
    cl[cl["matched_to_nhtsa"]]
    .groupby(["make_key", "model_key"])
    .agg(
        n_listings=("price", "size"),
        median_price=("price", "median"),
        median_odometer=("odometer", "median"),
    )
    .reset_index()
)
summary = listings_model.merge(comp_model, on=["make_key", "model_key"], how="left")
summary["n_complaints"] = summary["n_complaints"].fillna(0).astype(int)
summary["complaints_per_1000_listings"] = summary["n_complaints"] / summary["n_listings"] * 1000
summary = summary[summary["n_listings"] >= MIN_LISTINGS].sort_values(
    "complaints_per_1000_listings"
)
summary.to_csv("model_summary.csv", index=False)
print(f"Model summary: {len(summary):,} models with >= {MIN_LISTINGS} listings")
print(summary.head(10).to_string(index=False))
