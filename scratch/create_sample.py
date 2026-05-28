import os

import pandas as pd

excel_path = "阳性样本爬smiles.xlsx"
out_dir = "scratch"
out_path = os.path.join(out_dir, "test_sample.xlsx")

if not os.path.exists(out_dir):
    os.makedirs(out_dir)

try:
    xl = pd.ExcelFile(excel_path)
    with pd.ExcelWriter(out_path) as writer:
        for sheet_name in xl.sheet_names:
            df = xl.parse(sheet_name)
            # 提取前 10 行，并且在 InChIKey 和 Name 中增加一个故意造假的 404 测试行，方便测试 404 填充
            sample_df = df.head(10).copy()
            
            # 在样本的尾部插入一行必为 404 的测试行
            if sheet_name == "InChIKey":
                # 造一个格式正确但完全不存在的 InChIKey，或者写个明显不存在的
                # InChIKey 格式通常是 14个大写字母 + 短横线 + 10个大写字母 + 短横线 + 1个大写字母
                fake_row = pd.DataFrame({"InchIkey": ["NOTEXISTINCHI-UHFFFAOYSA-N"]})
                sample_df = pd.concat([sample_df, fake_row], ignore_index=True)
            elif sheet_name == "Name":
                fake_row = pd.DataFrame({"Name": ["ThisIsAFakeChemicalNameXYZZY"]})
                sample_df = pd.concat([sample_df, fake_row], ignore_index=True)
            elif sheet_name == "Synon":
                col_name = df.columns[0]
                fake_row = pd.DataFrame({col_name: ["FakeSynonChemicalX"]})
                sample_df = pd.concat([sample_df, fake_row], ignore_index=True)
                
            sample_df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"Created sheet {sheet_name} with shape {sample_df.shape}")
            
    print(f"Successfully created test sample file: {out_path}")
except Exception as e:
    print(f"Failed to create sample: {e}")
