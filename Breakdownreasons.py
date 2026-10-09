"""
Build a short table of breakdown reasons (NHTSA COMPDESC) per make + model + year,
with a benchmark average per reason so models can be compared.

Input:  nhtsa_complaints_2000_2020.csv   (from the NHTSA filtering script)
Output: complaint_reasons_by_model_year.csv   one row per make/model/year/reason
        reason_benchmarks.csv                 one row per reason (the averages)
"""
import pandas as pd

NHTSA_PATH = "nhtsa_complaints_2000_2020.csv"
YEAR_MIN, YEAR_MAX = 2000, 2020

# "top"  -> group by the first part of COMPDESC ("ENGINE AND ENGINE COOLING:ENGINE" -> "ENGINE AND ENGINE COOLING"),
#           which gives ~20 reasons and a much shorter table
# "full" -> keep the complete COMPDESC text (hundreds of reasons)
REASON_LEVEL = "top"
MIN_COMPLAINTS = 1     # raise (e.g. 5) to drop thinly-supported rows


def key_series(s: pd.Series) -> pd.Series:
    """Uppercase and strip everything except letters/digits: 'F-150' -> 'F150'."""
    return s.fillna("").astype(str).str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)


nh = pd.read_csv(NHTSA_PATH, low_memory=False)
nh["year"] = pd.to_numeric(nh["YEARTXT"], errors="coerce")
nh = nh[nh["year"].between(YEAR_MIN, YEAR_MAX)].copy()
nh["year"] = nh["year"].astype(int)

# same join keys as clean_and_join.py, so this table joins to the other outputs
nh["make_key"] = key_series(nh["MAKETXT"]).replace({"VW": "VOLKSWAGEN", "CHEVY": "CHEVROLET", "MERCEDES": "MERCEDESBENZ"})
nh["model_key"] = key_series(nh["MODELTXT"])
nh = nh[(nh["make_key"] != "") & (nh["model_key"] != "")]

reason = nh["COMPDESC"].fillna("UNKNOWN").astype(str).str.upper().str.strip()
if REASON_LEVEL == "top":
    reason = reason.str.split(":").str[0].str.strip()
nh["reason"] = reason.replace("", "UNKNOWN")

KEYS = ["make_key", "model_key", "year"]

# complaints per make/model/year/reason
out = nh.groupby(KEYS + ["reason"]).size().rename("n_complaints").reset_index()

# share of that model-year's complaints that this reason makes up
total = nh.groupby(KEYS).size().rename("total_complaints").reset_index()
out = out.merge(total, on=KEYS)
out["share_of_model_year"] = out["n_complaints"] / out["total_complaints"]

# benchmark: average count per reason across ALL make/model/year combinations
# (combinations with zero complaints for that reason count as 0, so the benchmark isn't inflated)
n_cells = len(total)
bench = nh.groupby("reason").size().rename("total_complaints_all").reset_index()
bench["avg_count_per_model_year"] = bench["total_complaints_all"] / n_cells
present = out.groupby("reason")["n_complaints"].agg(
    avg_count_when_present="mean", n_model_years_with_reason="size"
).reset_index()
bench = bench.merge(present, on="reason")
bench["overall_share"] = bench["total_complaints_all"] / bench["total_complaints_all"].sum()
bench = bench.sort_values("total_complaints_all", ascending=False)

# compare each model-year to the benchmark
out = out.merge(bench[["reason", "avg_count_per_model_year", "overall_share"]], on="reason")
out["ratio_to_avg_count"] = out["n_complaints"] / out["avg_count_per_model_year"]
out["share_vs_overall"] = out["share_of_model_year"] / out["overall_share"]

out = out[out["n_complaints"] >= MIN_COMPLAINTS].sort_values(KEYS + ["n_complaints"], ascending=[True, True, True, False])

out.to_csv("complaint_reasons_by_model_year.csv", index=False)
bench.to_csv("reason_benchmarks.csv", index=False)

print(f"{len(out):,} rows across {n_cells:,} make/model/year combos, {bench['reason'].nunique()} reasons")
print(bench.head(10).to_string(index=False))
