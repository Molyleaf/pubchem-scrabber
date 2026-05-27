import argparse
import os
import re
import pandas as pd
from typing import List, Tuple, Optional

# 可用 Scope 映射表
SCOPE_MAPPING = {
    "cid": "cid",
    "name": "iupac_name",
    "smiles": "smiles",
    "inchi": "inchi",
    "inchikey": "inchikey",
    "weight": "molecular_weight",
    "formula": "molecular_formula",
    "xlogp": "xlogp",
    "tpsa": "tpsa",
    "charge": "charge"
}

def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """
    @ai-intent: 解析用户输入的命令行参数，验证输入输出路径及 Scope 参数的合法性。
    @ai-invariant: 命令行解析器必须至少包含 --input，且 --scope 字段必须在支持的映射表中。
    @ai-boundary: 从命令行参数读取输入，返回解析后的 Namespace 对象，属于无副作用的纯参数解析。
    @ai-directive: 使用标准 argparse 实现，确保参数的合理提示。
    @ai-observe:
      Event Logging: [命令行解析/args] -> [成功解析的参数详情] -> [状态: 成功/失败]
    @ai-context:
      Topology: 模块 1: CLI 与智能推断器 / 边界输入层
      Flow: 接收命令行字符串 -> 转换为结构化 Namespace -> 传递给调度器
      Blast Radius: 参数解析失败会导致程序终止，属于进程级别的边界防守
      ADR: 无特殊妥协
      Ubiquitous Language: Scope 代表用户期望导出的 PubChem 化合物属性字段列表
    """
    parser = argparse.ArgumentParser(
        description="PubChem 批量自动数据获取客户端 - 批量获取化合物属性并完美对齐导出",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument(
        "--input", 
        required=True, 
        help="输入文件的绝对路径或相对路径，支持 .xlsx、.xls 和 .csv 格式。"
    )
    
    # 构造 Scope 的帮助说明
    scope_help = "需要导出的字段列表（空格分隔），可用值如下：\n"
    for k, v in SCOPE_MAPPING.items():
        scope_help += f"  - {k:<10} : 对应 PubChem 中的 {v}\n"
        
    parser.add_argument(
        "--scope",
        nargs="+",
        default=["cid", "name", "smiles", "weight"],
        help=scope_help
    )
    
    parser.add_argument(
        "--output",
        default="output.csv",
        help="输出文件的绝对路径或相对路径，支持 .xlsx 和 .csv 格式。默认值为 output.csv。"
    )
    
    parser.add_argument(
        "--batch",
        type=int,
        default=50,
        help="批量请求的 Chunk 大小，默认值为 50。"
    )
    
    parser.add_argument(
        "--header",
        choices=["auto", "yes", "no"],
        default="auto",
        help="表头处理策略：\n"
             "  - auto : 智能自动检测首行是否为表头（默认）\n"
             "  - yes  : 强制第一行为表头，从第二行读取数据\n"
             "  - no   : 强制无表头，第一行即为数据"
    )
    
    parsed = parser.parse_args(args)
    
    # 校验 scope 是否合法
    invalid_scopes = [s for s in parsed.scope if s not in SCOPE_MAPPING]
    if invalid_scopes:
        parser.error(f"不支持的 Scope 字段: {invalid_scopes}。可用字段包括: {list(SCOPE_MAPPING.keys())}")
        
    return parsed

def infer_type(value: str) -> str:
    """
    @ai-intent: 根据输入的化学标识符文本特征，智能推断其在 PubChem 查询时所采用的 namespace 类型。
    @ai-invariant: 返回值必须是 'cid', 'inchi', 'inchikey', 'smiles', 'name' 之一，绝不可产生其他值。
    @ai-boundary: 入参 value 为只读字符串。无外部 I/O 依赖。
    @ai-directive: 保证 O(1) 的正则与文本扫描性能。
    @ai-observe:
      Event Logging: [类型推断/value] -> [推断得到的化学类型] -> [成功]
    @ai-context:
      Topology: 模块 1: CLI 与智能推断器 / 核心推断算法
      Flow: 输入原始标识符 -> 经过正则与词汇筛查 -> 输出 PubChem 查询 of namespace 类型
      Blast Radius: 推断错误会导致向 PubChem 发送错误的 namespace 查询，引发 404 填充
      ADR: SMILES 推断规则经过了化学元素集的正向筛查与非化学字母（j, q, z）的反向排除，从而最大限度避免与普通俗名（Name）发生重叠
      Ubiquitous Language: namespace 是 PubChemPy 中用于区分输入查询种类的参数（如 'cid', 'name', 'smiles'）
    """
    if not isinstance(value, str):
        value = str(value).strip()
    else:
        value = value.strip()
        
    if not value:
        return "name"
        
    # 1. 纯数字 -> cid
    if value.isdigit():
        return "cid"
        
    # 2. 以 InChI= 开头 -> inchi
    if value.lower().startswith("inchi="):
        return "inchi"
        
    # 3. 27位双横线哈希 -> inchikey
    # 标准格式为 14位大写字母 - 10位大写字母 - 1位字母/数字，共27位
    if len(value) == 27 and value[14] == '-' and value[25] == '-':
        parts = value.split('-')
        if len(parts) == 3 and parts[0].isalpha() and parts[1].isalpha() and len(parts[2]) == 1:
            return "inchikey"
            
    # 4. SMILES 规则筛选
    # SMILES 绝对不能包含空格
    if " " not in value:
        # 如果是纯字母单词且全是小写，为了防止将俗名（如 aspirin, glucose, benzene 等）误判为 SMILES，
        # 一律将其视为 name。即便它是极简 SMILES（如 cco），作为 name 输入给 PubChem 也能 100% 查到正确结果。
        if value.isalpha() and value.islower():
            return "name"
            
        # SMILES 允许的字符以及常见元素大写/小写组合
        has_smiles_symbol = any(char in value for char in "=#[@]+-/\\%$:*")
        
        # 提取其中所有的纯英文字母
        letters = "".join(re.findall(r"[A-Za-z]", value))
        has_invalid_letters = any(bad in letters.lower() for bad in ["j", "q", "z"])
        
        if has_smiles_symbol and not has_invalid_letters:
            return "smiles"
            
        if len(value) <= 12 and not has_invalid_letters:
            # 常见的有机/无机 SMILES 字母集
            # 添加 r 前缀成为原始字符串，彻底杜绝 SyntaxWarning
            valid_smiles_chars = set(r"cdehinosxclbfinasike@+-\[\]\(\)=\#\/\\%")
            if all(char.lower() in valid_smiles_chars or char.isdigit() for char in value):
                return "smiles"
                
    return "name"

def load_input_file(filepath: str, header_strategy: str = "auto") -> List[Tuple[str, pd.DataFrame, List[str], bool]]:
    """
    @ai-intent: 加载输入文件，支持多工作表读取。对于 Excel 将按顺序提取所有工作表，对于 CSV 仅包含单表。
    @ai-invariant: 返回值必须是一个列表，每个元素是一个四元组：(工作表名称, 数据DataFrame, 第一列标识符列表, 是否跳过表头标志)。
    @ai-boundary: 允许读取 filepath 指向的文件系统资源。入参 filepath 只读。
    @ai-directive: 保证多 Sheet 读取时物理行对齐的自洽性。
    @ai-observe:
      Event Logging: [加载输入文件/filepath] -> [读取到的 Sheet 数量和详情] -> [成功/失败]
    @ai-context:
      Topology: 模块 1: CLI 与智能推断器 / 数据加载层
      Flow: 读取文件 -> 分工作表解析 -> 表头智能分类 -> 提取第一列 -> 汇总返回元组列表
      Blast Radius: 文件损坏或空工作表会引发 IOError/ValueError
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"找不到输入文件: {filepath}")
        
    _, ext = os.path.splitext(filepath.lower())
    results: List[Tuple[str, pd.DataFrame, List[str], bool]] = []
    
    if ext == ".csv":
        # 优先用 utf-8-sig，兼容 Windows Excel 生成的带 BOM 的 CSV，再尝试 utf-8，最后尝试 gbk
        try:
            df = pd.read_csv(filepath, header=None, encoding="utf-8-sig")
        except Exception:
            try:
                df = pd.read_csv(filepath, header=None, encoding="utf-8")
            except Exception:
                try:
                    df = pd.read_csv(filepath, header=None, encoding="gbk")
                except Exception:
                    # 终极防弹降级：如果因为某些行有过多逗号等不规范格式引发 pandas.errors.ParserError，
                    # 我们退回到逐行纯文本读取，仅分割第一个逗号，确保 100% 物理行严格对齐绝不崩溃！
                    try:
                        lines = []
                        with open(filepath, "r", encoding="utf-8-sig") as f:
                            for line in f:
                                parts = line.strip().split(",", 1)
                                if len(parts) < 2:
                                    parts.append("")
                                lines.append(parts)
                        df = pd.DataFrame(lines)
                    except Exception:
                        try:
                            lines = []
                            with open(filepath, "r", encoding="gbk") as f:
                                for line in f:
                                    parts = line.strip().split(",", 1)
                                    if len(parts) < 2:
                                        parts.append("")
                                    lines.append(parts)
                            df = pd.DataFrame(lines)
                        except Exception as e:
                            raise IOError(f"无法读取 CSV 文件 {filepath}: {e}")
                            
        if df.empty:
            raise ValueError("输入文件内容为空！")
            
        has_header = False
        if header_strategy == "yes":
            has_header = True
        elif header_strategy == "no":
            has_header = False
        else:
            first_val = str(df.iloc[0, 0]).strip().lower()
            known_headers = [
                "name", "cid", "smiles", "inchi", "inchikey", "compound", 
                "名称", "化合物", "标识符", "输入", "input", "id", "chemical"
            ]
            if first_val.isdigit():
                has_header = False
            elif first_val in known_headers:
                has_header = True
            else:
                has_header = False
                
        if has_header:
            header_row = df.iloc[0].tolist()
            header_row = [str(col).strip() if pd.notna(col) else f"Unnamed_{i}" for i, col in enumerate(header_row)]
            df_data = df.iloc[1:].copy()
            df_data.columns = header_row
            df_data.reset_index(drop=True, inplace=True)
        else:
            df_data = df.copy()
            df_data.columns = [f"Col_{i}" for i in range(df_data.shape[1])]
            
        # 智能检测真正的标识符列（若第一列为常数标签，且第二列唯一值更多，则自动识别为第二列）
        target_col = df_data.columns[0]
        if df_data.shape[1] > 1:
            first_col_unique = df_data[df_data.columns[0]].dropna().nunique()
            if first_col_unique <= 1:
                second_col_unique = df_data[df_data.columns[1]].dropna().nunique()
                if second_col_unique > first_col_unique:
                    target_col = df_data.columns[1]
                    
        raw_identifiers = df_data[target_col].fillna("").astype(str).tolist()
        raw_identifiers = [item.strip() for item in raw_identifiers]
        
        results.append(("CSV_Data", df_data, raw_identifiers, has_header))
        
    elif ext in [".xlsx", ".xls"]:
        try:
            # sheet_name=None 一次性读入所有工作表，返回字典 {sheet_name: df}
            sheets_dict = pd.read_excel(filepath, sheet_name=None, header=None)
        except Exception as e:
            raise IOError(f"无法读取 Excel 文件 {filepath}: {e}")
            
        if not sheets_dict:
            raise ValueError("输入 Excel 文件中没有工作表！")
            
        for sheet_name, df in sheets_dict.items():
            if df.empty:
                # 忽略空工作表
                continue
                
            has_header = False
            if header_strategy == "yes":
                has_header = True
            elif header_strategy == "no":
                has_header = False
            else:
                first_val = str(df.iloc[0, 0]).strip().lower()
                known_headers = [
                    "name", "cid", "smiles", "inchi", "inchikey", "compound", 
                    "名称", "化合物", "标识符", "输入", "input", "id", "chemical"
                ]
                if first_val.isdigit():
                    has_header = False
                elif first_val in known_headers:
                    has_header = True
                else:
                    has_header = False
                    
            if has_header:
                header_row = df.iloc[0].tolist()
                header_row = [str(col).strip() if pd.notna(col) else f"Unnamed_{i}" for i, col in enumerate(header_row)]
                df_data = df.iloc[1:].copy()
                df_data.columns = header_row
                df_data.reset_index(drop=True, inplace=True)
            else:
                df_data = df.copy()
                df_data.columns = [f"Col_{i}" for i in range(df_data.shape[1])]
                
            # 智能检测真正的标识符列（若第一列为常数标签，且第二列唯一值更多，则自动识别为第二列）
            target_col = df_data.columns[0]
            if df_data.shape[1] > 1:
                first_col_unique = df_data[df_data.columns[0]].dropna().nunique()
                if first_col_unique <= 1:
                    second_col_unique = df_data[df_data.columns[1]].dropna().nunique()
                    if second_col_unique > first_col_unique:
                        target_col = df_data.columns[1]
                        
            raw_identifiers = df_data[target_col].fillna("").astype(str).tolist()
            raw_identifiers = [item.strip() for item in raw_identifiers]
            
            results.append((sheet_name, df_data, raw_identifiers, has_header))
            
        if not results:
            raise ValueError("输入 Excel 中的所有工作表均为空！")
            
    else:
        raise ValueError("不支持的文件格式！仅支持 .csv, .xlsx, .xls 文件。")
        
    return results
