import os
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from lib.cache_manager import CacheManager
from lib.batch_dispatcher import serialize_compound, dispatch_processing, UserInterruptError

def test_serialize_compound() -> None:
    """
    @ai-ut-matrix: 测试将 pubchempy Compound 转换为本地持久化字典的方法是否具备鲁棒性且能补充缺省属性。
    @ai-ut-mock: 使用 MagicMock 模拟 Compound 对象。
    @ai-ut-assert: 1. 字典中包含 cid, inchikey 核心键值。
                   2. 转换成 float 类型的分子量应准确无误。
    """
    mock_comp = MagicMock()
    mock_comp.cid = 2244
    mock_comp.iupac_name = "Aspirin"
    mock_comp.isomeric_smiles = "CC(=O)OC1=CC=CC=C1C(=O)O"
    mock_comp.inchi = "InChI=1"
    mock_comp.inchikey = "BSYNRPNEBBAWKU-UHFFFAOYSA-N"
    mock_comp.molecular_weight = "180.16"
    mock_comp.molecular_formula = "C9H8O4"
    mock_comp.xlogp = 1.3
    mock_comp.tpsa = 63.6
    mock_comp.charge = 0
    
    # 模拟 to_dict 行为
    mock_comp.to_dict.return_value = {
        "cid": 2244,
        "inchikey": "BSYNRPNEBBAWKU-UHFFFAOYSA-N",
        "molecular_weight": "180.16"
    }
    
    res = serialize_compound(mock_comp)
    assert res["cid"] == 2244
    assert res["inchikey"] == "BSYNRPNEBBAWKU-UHFFFAOYSA-N"
    assert res["molecular_weight"] == 180.16
    assert res["iupac_name"] == "Aspirin"

def test_dispatch_processing_alignment(tmp_path) -> None:
    """
    @ai-ut-matrix: 测试调度器在读取包含 CID、名称、空行、无效化合物的混合输入时，是否能完美重组并严格保持输出行对齐，同时将无效字段填充 404 Not Found。
    @ai-ut-mock: patch 网络获取层 _fetch_by_cids_network 和 _fetch_single_network。
    @ai-ut-assert: 1. 导出的 excel/csv 物理行数必须与原始 DataFrame 的行数一致。
                   2. 缺失的、无效的、或空数据列必须填充为 "404 Not Found"。
    """
    cache_file = tmp_path / "cache.json"
    cache_manager = CacheManager(str(cache_file))
    
    # 构造输入 DataFrame（4行）
    raw_identifiers = ["2244", "glucose", "not_real_compound", ""]
    df_original = pd.DataFrame({
        "input_col": raw_identifiers,
        "extra_info": ["val1", "val2", "val3", "val4"]
    })
    
    # 模拟 CID 网络返回
    mock_comp_cid = MagicMock()
    mock_comp_cid.cid = 2244
    mock_comp_cid.inchikey = "CID_KEY_2244"
    mock_comp_cid.iupac_name = "Aspirin"
    mock_comp_cid.isomeric_smiles = "SMILES_2244"
    mock_comp_cid.molecular_weight = 180.1
    mock_comp_cid.to_dict.return_value = {"cid": 2244, "inchikey": "CID_KEY_2244"}
    
    # 模拟 Name 网络返回
    mock_comp_name = MagicMock()
    mock_comp_name.cid = 5793
    mock_comp_name.inchikey = "GLUCOSE_KEY"
    mock_comp_name.iupac_name = "D-Glucose"
    mock_comp_name.isomeric_smiles = "SMILES_GLUCOSE"
    mock_comp_name.molecular_weight = 180.16
    mock_comp_name.to_dict.return_value = {"cid": 5793, "inchikey": "GLUCOSE_KEY"}
    
    output_path = tmp_path / "output.csv"
    
    with patch("lib.batch_dispatcher._fetch_by_cids_network", return_value=[mock_comp_cid]) as mock_batch, \
         patch("lib.batch_dispatcher._fetch_single_network") as mock_single:
         
        # mock_single 返回结果列表
        def side_effect(query, q_type):
            if query == "glucose":
                return [mock_comp_name]
            return []  # 找不到则返回空
            
        mock_single.side_effect = side_effect
        
        sheets = [("CSV_Data", df_original, raw_identifiers, False)]
        stats = dispatch_processing(
            sheets=sheets,
            scope=["cid", "name", "smiles", "weight"],
            output_path=str(output_path),
            batch_size=10,
            cache_manager=cache_manager
        )
        
    total, hits, net, not_found = stats
    assert total == 4
    
    # 验证输出文件物理结构
    assert os.path.exists(str(output_path))
    df_res = pd.read_csv(str(output_path))
    
    assert len(df_res) == 4
    # 首列和附加列必须与原文件一致
    assert list(df_res["input_col"].fillna("")) == raw_identifiers
    assert list(df_res["extra_info"]) == ["val1", "val2", "val3", "val4"]
    
    # 验证 Scope 对齐字段值
    # 2244 成功匹配
    assert df_res.at[0, "cid"] == "2244"
    assert df_res.at[0, "name"] == "Aspirin"
    
    # glucose 成功匹配
    assert df_res.at[1, "cid"] == "5793"
    assert df_res.at[1, "name"] == "D-Glucose"
    
    # not_real_compound 填充 404
    assert df_res.at[2, "cid"] == "404 Not Found"
    assert df_res.at[2, "name"] == "404 Not Found"
    assert df_res.at[2, "smiles"] == "404 Not Found"
    
    # 空行填充 404
    assert df_res.at[3, "cid"] == "404 Not Found"
    assert df_res.at[3, "name"] == "404 Not Found"

def test_dispatch_processing_interrupt_recovery(tmp_path) -> None:
    """
    @ai-ut-matrix: 测试键盘中断保护机制。若在网络轮询时触发 KeyboardInterrupt，系统必须拦截并把当前已查询好的数据对齐写入磁盘，再重新上抛退出。
    @ai-ut-mock: patch 网络层以使其抛出 UserInterruptError。
    @ai-ut-assert: 1. 必须捕获并重新抛出 UserInterruptError。
                   2. 已经查出的第一行数据必须被保存，未处理的数据应填充为 404。
    """
    cache_file = tmp_path / "cache.json"
    cache_manager = CacheManager(str(cache_file))
    
    raw_identifiers = ["2244", "glucose"]
    df_original = pd.DataFrame({"input": raw_identifiers})
    
    # 模拟 2244 在第一步批量查询时就成功
    mock_comp_cid = MagicMock()
    mock_comp_cid.cid = 2244
    mock_comp_cid.inchikey = "KEY_2244"
    mock_comp_cid.iupac_name = "Aspirin"
    mock_comp_cid.to_dict.return_value = {"cid": 2244, "inchikey": "KEY_2244"}
    
    output_path = tmp_path / "interrupt_output.csv"
    
    with patch("lib.batch_dispatcher._fetch_by_cids_network", return_value=[mock_comp_cid]), \
         patch("lib.batch_dispatcher._fetch_single_network", side_effect=UserInterruptError("Keyboard Interrupt")):
         
         with pytest.raises(UserInterruptError):
             sheets = [("CSV_Data", df_original, raw_identifiers, False)]
             dispatch_processing(
                 sheets=sheets,
                 scope=["cid", "name"],
                 output_path=str(output_path),
                 batch_size=10,
                 cache_manager=cache_manager
             )
             
    # 中断保护验证：文件必须仍然生成，且已查询好的 2244 有数据，glucose 因为中断应填充 404
    assert os.path.exists(str(output_path))
    df_res = pd.read_csv(str(output_path))
    assert len(df_res) == 2
    assert df_res.at[0, "name"] == "Aspirin"
    assert df_res.at[1, "name"] == "404 Not Found"
