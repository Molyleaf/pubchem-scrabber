import argparse
import os
import re
import pandas as pd
from typing import List, Tuple, Optional

# 可用 Scope 映射表
SCOPE_MAPPING = {
    "cid": "cid",
    "name": "iupac_name",
    "smiles": "isomeric_smiles",
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
    @ai-invariant: 命令行解析器必须至少包含 --input, --output 和 --scope，且 --scope 字段必须在支持的映射表中。
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
        description="PubChem 自动客户端 - 批量获取化合物属性并完美对齐导出",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument(
        "--input", 
        required=True, 
        help="输入文件的绝对路径或相对路径，支持 .xlsx 和 .csv 格式。"
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
        default=100,
        help="批量请求的 Chunk 大小，默认值为 100。"
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
      Flow: 输入原始标识符 -> 经过正则与词汇筛查 -> 输出 PubChem 查询的 namespace 类型
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
        # 我们一律将其视为 name。即便它是极简 SMILES（如 cco），作为 name 输入给 PubChem 也能 100% 查到正确结果。
        if value.isalpha() and value.islower():
            return "name"
            
        # SMILES 允许的字符以及常见元素大写/小写组合
        # 常见大写字母：C, H, O, N, S, P, F, B, I
        # 常见双字符元素：Cl, Br, Na, Li, Si, Se, As 等
        # 极罕见的非化学大写字母或小写字母（排除法）：j, q, z
        # SMILES 特有符号：=, #, @, [, ], (, ), +, -, /, \, %, $, :
        has_smiles_symbol = any(char in value for char in "=#[@]+-/\\%$:*")
        
        # 提取其中所有的纯英文字母
        letters = "".join(re.findall(r"[A-Za-z]", value))
        # 转换为小写后，检查是否包含化学中不可能出现的非化学保留字母（j, q, z）
        has_invalid_letters = any(bad in letters.lower() for bad in ["j", "q", "z"])
        
        # 如果包含 SMILES 特有符号且不含禁用字母，极大概率是 SMILES
        if has_smiles_symbol and not has_invalid_letters:
            return "smiles"
            
        # 即使没有符号，但如果字符完全由常见有机/无机元素构成且没有禁用字母，也可能是非常简单的 SMILES（如 CCO, CCCCC）
        # 并且我们要避免纯英文短单词（如 glucose, aspirin 等是 Name，它们一般包含大量的非化学常见连续字母，且长单词不含符号）
        # 如果长度较短（比如 <= 12 字符）且仅含化学元素符号，可认定为 SMILES
        if len(value) <= 12 and not has_invalid_letters:
            # 常见的有机/无机 SMILES 字母集
            # 移去可能在纯英文里大量出现的 p, r 等小写干扰，转而侧重于典型大写与常见配对
            valid_smiles_chars = set("cdehinosxclbfinasike@+-\[\]\(\)=\#\/\\%")
            if all(char.lower() in valid_smiles_chars or char.isdigit() for char in value):
                return "smiles"
                
    return "name"

def load_input_file(filepath: str, header_strategy: str = "auto") -> Tuple[pd.DataFrame, List[str], bool]:
    """
    @ai-intent: 加载输入文件（CSV 或 Excel），智能检测表头，并提取出第一列作为待查询的化学标识符列表，同时保留原始 DataFrame 用于最终的数据对齐。
    @ai-invariant: 返回的标识符列表长度必须与原始读取的 DataFrame 行数完全一致。
    @ai-boundary: 允许读取 filepath 指向的文件系统资源，返回元组 (原始DataFrame, 标识符列表, 是否跳过表头行)。入参 filepath 只读。
    @ai-directive: 保证支持 Windows Excel 常见的中文与格式兼容。
    @ai-observe:
      Event Logging: [读取输入文件/filepath] -> [行数, 推断得到的表头状态] -> [成功/失败]
    @ai-context:
      Topology: 模块 1: CLI 与智能推断器 / 数据加载层
      Flow: 读取文件 -> 检查首行 -> 提取第一列 -> 返回结构化数据与策略
      Blast Radius: 文件损坏或不存在会引发 IOError，需要上层捕获
      ADR: 无特殊妥协
      Ubiquitous Language: 原始 DataFrame 保留了输入的其他列和物理行顺序，用于生成 404 对齐的最终输出
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"找不到输入文件: {filepath}")
        
    _, ext = os.path.splitext(filepath.lower())
    
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
    elif ext in [".xlsx", ".xls"]:
        try:
            df = pd.read_excel(filepath, header=None)
        except Exception as e:
            raise IOError(f"无法读取 Excel 文件 {filepath}: {e}")
    else:
        raise ValueError("不支持的文件格式！仅支持 .csv, .xlsx, .xls 文件。")
        
    if df.empty:
        raise ValueError("输入文件内容为空！")
        
    has_header = False
    
    if header_strategy == "yes":
        has_header = True
    elif header_strategy == "no":
        has_header = False
    else:  # "auto"
        # 智能推断：如果第一行第一列的文本是已知的常规表头单词，或者是空值，或者包含明显的列标指示，则视其为表头
        first_val = str(df.iloc[0, 0]).strip().lower()
        known_headers = [
            "name", "cid", "smiles", "inchi", "inchikey", "compound", 
            "名称", "化合物", "标识符", "输入", "input", "id", "chemical"
        ]
        # 如果是纯数字，那肯定不是表头，而是真实的 CID
        if first_val.isdigit():
            has_header = False
        elif first_val in known_headers:
            has_header = True
        else:
            # 看看第一行其他列是否包含已知表头，或第一行都是文本而后面有数字等统计差异
            # 如果第一列的第一个元素推断出是 'name'（比如 "aspirin"），但看起来更像是实际数据，那不作为表头
            # 这里保守一点，如果第一行第一列包含在常见表头名中，就认为是表头，否则认为不是
            has_header = False
            
    if has_header:
        # 重新读取以第一行为表头，或者直接从 df 中切片并重设 index
        header_row = df.iloc[0].tolist()
        # 清洗 header_row 中的空值，确保列名唯一
        header_row = [str(col).strip() if pd.notna(col) else f"Unnamed_{i}" for i, col in enumerate(header_row)]
        df_data = df.iloc[1:].copy()
        df_data.columns = header_row
        df_data.reset_index(drop=True, inplace=True)
    else:
        # 无表头，自动分配列名
        df_data = df.copy()
        df_data.columns = [f"Col_{i}" for i in range(df_data.shape[1])]
        
    # 提取第一列，清洗空值（空值设为空字符串，保留索引以确保严格对齐）
    first_col_name = df_data.columns[0]
    raw_identifiers = df_data[first_col_name].fillna("").astype(str).tolist()
    # 清除首尾空白
    raw_identifiers = [item.strip() for item in raw_identifiers]
    
    return df_data, raw_identifiers, has_header
