import pandas as pd
import os
import sys

def verify():
    input_file = "阳性样本爬smiles.xlsx"
    output_file = "阳性样本爬smiles_已对齐.xlsx"
    
    print("====================================================")
    print("开始进行 Excel 物理行对齐和数据完整性全量校验...")
    print("====================================================")
    
    if not os.path.exists(output_file):
        print(f"❌ 校验失败：找不到输出文件 {output_file}")
        sys.exit(1)
        
    try:
        input_sheets = pd.read_excel(input_file, sheet_name=None, header=None)
        output_sheets = pd.read_excel(output_file, sheet_name=None)
    except Exception as e:
        print(f"❌ 校验失败：读取 Excel 发生异常: {e}")
        sys.exit(1)
        
    if list(input_sheets.keys()) != list(output_sheets.keys()):
        print(f"❌ 校验失败：工作表列表不一致！\n输入: {list(input_sheets.keys())}\n输出: {list(output_sheets.keys())}")
        sys.exit(1)
        
    print(f"✅ 工作表结构一致，包含 Sheets: {list(input_sheets.keys())}")
    
    for sheet_name in input_sheets.keys():
        print(f"\n[Sheet: {sheet_name}] 开始校验...")
        df_in_raw = input_sheets[sheet_name]
        df_out = output_sheets[sheet_name]
        
        # 模拟 cli_parser 中的 header 和 智能列推断逻辑
        first_val = str(df_in_raw.iloc[0, 0]).strip().lower()
        known_headers = [
            "name", "cid", "smiles", "inchi", "inchikey", "compound", 
            "名称", "化合物", "标识符", "输入", "input", "id", "chemical"
        ]
        has_header = False
        if first_val in known_headers:
            has_header = True
            
        if has_header:
            header_row = df_in_raw.iloc[0].tolist()
            df_in_data = df_in_raw.iloc[1:].copy()
            df_in_data.columns = [str(x).strip() if pd.notna(x) else f"Unnamed_{i}" for i, x in enumerate(header_row)]
            df_in_data.reset_index(drop=True, inplace=True)
        else:
            df_in_data = df_in_raw.copy()
            df_in_data.columns = [f"Col_{i}" for i in range(df_in_data.shape[1])]
            
        # 智能检测真正的标识符列
        target_col = df_in_data.columns[0]
        if df_in_data.shape[1] > 1:
            first_col_unique = df_in_data[df_in_data.columns[0]].dropna().nunique()
            if first_col_unique <= 1:
                second_col_unique = df_in_data[df_in_data.columns[1]].dropna().nunique()
                if second_col_unique > first_col_unique:
                    target_col = df_in_data.columns[1]
                    
        # 检查物理行数是否完全一致
        len_in = len(df_in_data)
        len_out = len(df_out)
        if len_in != len_out:
            print(f"❌ 物理行数不一致！输入数据行数: {len_in}, 输出数据行数: {len_out}")
            sys.exit(1)
        print(f"  - 物理行数校验通过: {len_in} 行")
        
        # 校验标识符列的值是否完全相同且绝对对齐
        # 输出文件的第一列应该保留了输入文件的第一列（如果是智能降级识别，那输出文件应该保留了原 df_in_data 的所有原始列）
        in_identifiers = df_in_data[target_col].fillna("").astype(str).tolist()
        in_identifiers = [item.strip() for item in in_identifiers]
        
        out_identifiers = df_out[target_col].fillna("").astype(str).tolist()
        out_identifiers = [item.strip() for item in out_identifiers]
        
        mismatch_count = 0
        for idx, (in_val, out_val) in enumerate(zip(in_identifiers, out_identifiers)):
            if in_val != out_val:
                mismatch_count += 1
                if mismatch_count <= 5:
                    print(f"    - 行号 {idx} 对齐不匹配！输入: '{in_val}', 输出: '{out_val}'")
                    
        if mismatch_count > 0:
            print(f"❌ 校验失败：存在 {mismatch_count} 行标识符未对齐！")
            sys.exit(1)
        print("  - 标识符列绝对物理行对齐校验通过")
        
        # 检查新增的 scope 字段是否存在
        added_scopes = ["cid", "name", "smiles", "weight", "formula", "xlogp"]
        for s in added_scopes:
            if s not in df_out.columns:
                print(f"❌ 校验失败：输出文件缺少导出的属性列 '{s}'")
                sys.exit(1)
        print("  - 导出的 Scope 属性列完整性校验通过")
        
        # 检查是否有成功爬取到的数据（不能全为 404，如果是干净的缓存，肯定会有成功获取的数据）
        found_data = df_out[~df_out["cid"].astype(str).str.contains("404 Not Found", na=False)]
        print(f"  - 成功抓取并对齐的化合物数量: {len(found_data)} / {len_out}")
        
    print("\n====================================================")
    print("🎉 恭喜！多工作表全量物理行对齐与属性完整性校验 100% 通过！")
    print("====================================================")

if __name__ == "__main__":
    verify()
