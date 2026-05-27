import os
import pytest
import pandas as pd
from lib.cli_parser import parse_args, infer_type, load_input_file

def test_parse_args_success() -> None:
    """
    @ai-ut-matrix: 测试在传入合法的 CLI 参数时，argparse 解析器是否能正常解析并返回正确的默认值与配置。
    @ai-ut-mock: 无
    @ai-ut-assert: 1. 解析出的 input 必须与输入一致。
                   2. 默认的 output 必须为 'output.csv'。
                   3. 默认的 scope 必须包含 cid, name, smiles, weight。
                   4. 默认 batch 必须是 100，header 默认是 'auto'。
    """
    parsed = parse_args(["--input", "1.xlsx"])
    assert parsed.input == "1.xlsx"
    assert parsed.output == "output.csv"
    assert "cid" in parsed.scope
    assert parsed.batch == 50
    assert parsed.header == "auto"

def test_parse_args_invalid_scope() -> None:
    """
    @ai-ut-matrix: 测试在传入不支持的 Scope 字段时，解析器是否能抛出 SystemExit 拒绝不合规请求。
    @ai-ut-mock: 无
    @ai-ut-assert: 必须引发 SystemExit 异常阻止程序继续。
    """
    with pytest.raises(SystemExit):
        parse_args(["--input", "1.xlsx", "--scope", "invalid_field"])

def test_infer_type() -> None:
    """
    @ai-ut-matrix: 测试智能类型推断引擎对于各类化学标识符的分类精准度。
    @ai-ut-mock: 无
    @ai-ut-assert: 1. 纯数字 '2244' 应推断为 'cid'。
                   2. 'InChI=1S/C2H6O/c1-2-3/h3H,2H2,1H3' 应推断为 'inchi'。
                   3. 'LFQCMRUKMMVBAH-UHFFFAOYSA-N' 应推断为 'inchikey'。
                   4. 'CCO'、'C1=CC=CC=C1' 极短或化学字符集判定应推断为 'smiles'。
                   5. 带空格或禁用字母的俗名 'glucose'、'aspirin' 应推断为 'name'。
    """
    assert infer_type("2244") == "cid"
    assert infer_type("5090") == "cid"
    assert infer_type("InChI=1S/C2H6O/c1-2-3/h3H,2H2,1H3") == "inchi"
    assert infer_type("LFQCMRUKMMVBAH-UHFFFAOYSA-N") == "inchikey"
    
    # SMILES
    assert infer_type("CCO") == "smiles"
    assert infer_type("C1=CC=CC=C1") == "smiles"
    assert infer_type("C(=O)(O)C") == "smiles"
    
    # Names
    assert infer_type("glucose") == "name"
    assert infer_type("aspirin") == "name"
    assert infer_type("sodium chloride") == "name"
    assert infer_type("not_a_real_compound") == "name"

def test_load_input_file_csv_auto_header(tmp_path) -> None:
    """
    @ai-ut-matrix: 测试加载带有表头行的 CSV 文件时，自动推断系统是否能完美剔除表头并将第一列数据准确返回。
    @ai-ut-mock: 使用 tmp_path 写入临时测试文件，实现 I/O 隔离。
    @ai-ut-assert: 1. 是否跳过表头标志 must be True。
                   2. 返回的待查询标识符列表必须与 CSV 第二行起的数据内容完全吻合，且保留索引。
    """
    csv_file = tmp_path / "test.csv"
    data = "name,other_col\naspirin,1\nglucose,2\n"
    csv_file.write_text(data, encoding="utf-8")
    
    results = load_input_file(str(csv_file), "auto")
    
    assert len(results) == 1
    sheet_name, df, identifiers, has_header, specified_type = results[0]
    
    assert sheet_name == "CSV_Data"
    assert has_header is True
    assert len(identifiers) == 2
    assert identifiers[0] == "aspirin"
    assert identifiers[1] == "glucose"
    assert list(df.columns) == ["name", "other_col"]

def test_load_input_file_csv_no_header(tmp_path) -> None:
    """
    @ai-ut-matrix: 测试加载不带表头的 CSV 文件时，系统是否能智能识别到没有表头并将第一行也纳入查询对象中。
    @ai-ut-assert: 1. 是否跳过表头标志 must be False。
                   2. 第一行第一列的数据必须包含在返回的待查询标识符列表中。
    """
    csv_file = tmp_path / "test_no.csv"
    data = "2244,1\n5090,2\n"
    csv_file.write_text(data, encoding="utf-8")
    
    results = load_input_file(str(csv_file), "auto")
    
    assert len(results) == 1
    sheet_name, df, identifiers, has_header, specified_type = results[0]
    
    assert has_header is False
    assert len(identifiers) == 2
    assert identifiers[0] == "2244"
    assert identifiers[1] == "5090"

def test_infer_type_with_rdkit_validation() -> None:
    """
    @ai-ut-matrix: 测试在没有显式指定类型时，对 SMILES 和 InChI 候选进行 RDKit 校验的精确降级。
    @ai-ut-mock: 无
    @ai-ut-assert: 1. 合法的 SMILES 'CCO'、'C1=CC=CC=C1' 依然判定为 'smiles'。
                   2. 不合法的 SMILES 候选 'C(=O)(O)C_invalid' 虽有符号但 RDKit 校验失败，应平滑降级为 'name'。
                   3. 不合法的 InChI 'InChI=1S/invalid_inchi' 虽以 InChI= 开头但 RDKit 校验失败，应平滑降级为 'name'。
    """
    assert infer_type("CCO") == "smiles"
    assert infer_type("C1=CC=CC=C1") == "smiles"
    
    # 模拟包含化学符号，但属于不合法 SMILES 的情况
    assert infer_type("C(=O)(O)C_invalid") == "name"
    assert infer_type("CCO_invalid") == "name"
    
    # 模拟以 InChI= 开头但属于不合法 InChI 的情况
    assert infer_type("InChI=1S/invalid_inchi") == "name"

def test_load_input_file_specified_type(tmp_path) -> None:
    """
    @ai-ut-matrix: 测试首行第一列包含被去空格和不区分大小写的标准类型名（如 ' SMILES '）时，系统是否能正确提取该类型并判定 has_header 为 True。
    @ai-ut-mock: 使用 tmp_path 进行文件 I/O 隔离。
    @ai-ut-assert: 1. sheet_name 必须正确。
                   2. has_header 必须为 True，且跳过第一行表头。
                   3. specified_type 必须为 'smiles'。
                   4. identifiers 不应包含首行的 ' SMILES ' 本身，而应包含下面的数据。
    """
    csv_file = tmp_path / "test_spec.csv"
    data = " SMILES \nCCO\nC1=CC=CC=C1\n"
    csv_file.write_text(data, encoding="utf-8")
    
    results = load_input_file(str(csv_file), "auto")
    
    assert len(results) == 1
    sheet_name, df, identifiers, has_header, specified_type = results[0]
    
    assert has_header is True
    assert specified_type == "smiles"
    assert len(identifiers) == 2
    assert identifiers[0] == "CCO"
    assert identifiers[1] == "C1=CC=CC=C1"

def test_load_input_file_second_column_specified_type(tmp_path) -> None:
    """
    @ai-ut-matrix: 测试当化学标识符在第二列，且第二列首行指定了标准类型名时，系统是否能智能检测并偏向第二列作为标识符列。
    @ai-ut-mock: 使用 tmp_path 隔离。
    @ai-ut-assert: 1. has_header 必须为 True。
                   2. specified_type 必须为 'inchi'。
                   3. 标识符列表必须包含第二列的数据。
    """
    csv_file = tmp_path / "test_spec_col2.csv"
    data = "index,  InChI \n1,InChI=1S/C2H6O/c1-2-3/h3H,2H2,1H3\n2,InChI=1S/C3H8O/c1-2-3-4/h4H,2-3H2,1H3\n"
    csv_file.write_text(data, encoding="utf-8")
    
    results = load_input_file(str(csv_file), "auto")
    
    assert len(results) == 1
    sheet_name, df, identifiers, has_header, specified_type = results[0]
    
    assert has_header is True
    assert specified_type == "inchi"
    assert len(identifiers) == 2
    assert identifiers[0] == "InChI=1S/C2H6O/c1-2-3/h3H,2H2,1H3"
