import pandas as pd

# All 51 columns, in file order (from https://static.nhtsa.gov/odi/ffdd/cmpl/CMPL.txt)
ALL_COLS = [
    "CMPLID", "ODINO", "MFR_NAME", "MAKETXT", "MODELTXT", "YEARTXT",
    "CRASH", "FAILDATE", "FIRE", "INJURED", "DEATHS", "COMPDESC",
    "CITY", "STATE", "VIN", "DATEA", "LDATE", "MILES", "OCCURENCES",
    "CDESCR", "CMPL_TYPE", "POLICE_RPT_YN", "PURCH_DT", "ORIG_OWNER_YN",
    "ANTI_BRAKES_YN", "CRUISE_CONT_YN", "NUM_CYLS", "DRIVE_TRAIN",
    "FUEL_SYS", "FUEL_TYPE", "TRANS_TYPE", "VEH_SPEED", "DOT", "TIRE_SIZE",
    "LOC_OF_TIRE", "TIRE_FAIL_TYPE", "ORIG_EQUIP_YN", "MANUF_DT",
    "SEAT_TYPE", "RESTRAINT_TYPE", "DEALER_NAME", "DEALER_TEL",
    "DEALER_CITY", "DEALER_STATE", "DEALER_ZIP", "PROD_TYPE",
    "REPAIRED_YN", "MEDICAL_ATTN", "VEHICLES_TOWED_YN",
    "STATE_OF_INCIDENT", "VEHICLE_OPERATOR",
]

# Columns to keep. Skipping CDESCR (huge free text) and personal/dealer info
KEEP = [
    "CMPLID", "MFR_NAME", "MAKETXT", "MODELTXT", "YEARTXT",
    "CRASH", "FAILDATE", "FIRE", "INJURED", "DEATHS", "COMPDESC",
    "STATE", "MILES", "NUM_CYLS", "DRIVE_TRAIN", "FUEL_TYPE",
    "TRANS_TYPE", "VEHICLES_TOWED_YN", "PROD_TYPE",
]

df = pd.read_csv(
    "FLAT_CMPL.zip",        # pandas reads the zip directly
    sep="\t",
    header=None,
    names=ALL_COLS,         # assigns the names above to the 51 columns
    usecols=KEEP,           # only loads the ones in KEEP
    encoding="latin-1",
    quoting=3,              # no quote handling; the file has stray quote characters
    dtype=str,
    on_bad_lines="skip",
)

# Filter: vehicles only, model years 2000-2020
df = df[df["PROD_TYPE"] == "V"]
df["YEARTXT"] = pd.to_numeric(df["YEARTXT"], errors="coerce")   # 9999 = unknown
df = df[df["YEARTXT"].between(2000, 2020)]

# Clean numerics and join keys
for c in ["MILES", "INJURED", "DEATHS", "NUM_CYLS"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")
for c in ["MAKETXT", "MODELTXT", "COMPDESC"]:
    df[c] = df[c].str.strip().str.upper()

df.to_csv("nhtsa_complaints_2000_2020.csv", index=False)
print(df.shape)
print(df.head())
