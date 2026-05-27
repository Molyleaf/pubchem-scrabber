import pandas as pd

file_path = "阳性样本爬smiles.xlsx"
try:
    xl = pd.ExcelFile(file_path)
    print("Sheet names:", xl.sheet_names)
    for name in xl.sheet_names:
        df = xl.parse(name)
        print(f"\nSheet: {name}")
        print("Columns:", df.columns.tolist())
        print("Shape:", df.shape)
        print("First 5 rows:")
        print(df.head(5))
except Exception as e:
    print("Error reading Excel:", e)
