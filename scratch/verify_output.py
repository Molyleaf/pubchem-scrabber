import pandas as pd
import os

out_path = "scratch/test_output.xlsx"
if not os.path.exists(out_path):
    print("Output file does NOT exist!")
    exit(1)

try:
    xl = pd.ExcelFile(out_path)
    print("Sheets in output:", xl.sheet_names)
    for name in xl.sheet_names:
        df = xl.parse(name)
        print(f"\nSheet: {name}")
        print("Columns:", df.columns.tolist())
        print("Shape:", df.shape)
        print("First 3 rows:")
        print(df.head(3))
        print("Last 2 rows:")
        print(df.tail(2))
except Exception as e:
    print("Error:", e)
