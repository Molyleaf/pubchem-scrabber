import pandas as pd

sheets = pd.read_excel("阳性样本爬smiles.xlsx", sheet_name=None, header=None)

for name, df in sheets.items():
    print(f"\nSheet '{name}':")
    # 模拟 cli_parser.py 中的 header 推断
    first_val = str(df.iloc[0, 0]).strip().lower()
    known_headers = [
        "name", "cid", "smiles", "inchi", "inchikey", "compound", 
        "名称", "化合物", "标识符", "输入", "input", "id", "chemical"
    ]
    has_header = False
    if first_val in known_headers:
        has_header = True
    
    if has_header:
        header_row = df.iloc[0].tolist()
        df_data = df.iloc[1:].copy()
        df_data.columns = header_row
        df_data.reset_index(drop=True, inplace=True)
    else:
        df_data = df.copy()
        df_data.columns = [f"Col_{i}" for i in range(df_data.shape[1])]
        
    print("df_data columns:", list(df_data.columns))
    
    # 智能列检测
    target_col = df_data.columns[0]
    if df_data.shape[1] > 1:
        first_col_unique = df_data[df_data.columns[0]].dropna().nunique()
        if first_col_unique <= 1:
            second_col_unique = df_data[df_data.columns[1]].dropna().nunique()
            if second_col_unique > first_col_unique:
                target_col = df_data.columns[1]
                
    print("Selected target column:", target_col)
    raw_identifiers = df_data[target_col].fillna("").astype(str).tolist()
    raw_identifiers = [item.strip() for item in raw_identifiers]
    print("First 3 selected identifiers:", raw_identifiers[:3])
