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
    mock_comp.inchikey = "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
    mock_comp.molecular_weight = "180.16"
    mock_comp.molecular_formula = "C9H8O4"
    mock_comp.xlogp = 1.3
    mock_comp.tpsa = 63.6
    mock_comp.charge = 0
    
    mock_comp.to_dict.return_value = {
        "cid": 2244,
        "inchikey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
        "molecular_weight": "180.16"
    }
    
    res = serialize_compound(mock_comp)
    assert res["cid"] == 2244
    assert res["inchikey"] == "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
    assert res["molecular_weight"] == 180.16
    assert res["iupac_name"] == "Aspirin"

def test_dispatch_processing_alignment(tmp_path) -> None:
    """
    @ai-ut-matrix: 测试调度器在读取包含工作表列表的混合输入时，是否能全局去重并完美重组，严格保持多 Sheet 的行对齐，同时将无效字段填充 404 Not Found。
    @ai-ut-mock: patch 网络获取层 _fetch_by_cids_network 和 _fetch_single_network。
    @ai-ut-assert: 1. 导出的 CSV/Excel 物理结构和行数与原始 DataFrame 的行数一致。
                   2. 缺失列必须填充为 "404 Not Found"。
    """
    cache_file = tmp_path / "cache.json"
    cache_manager = CacheManager(str(cache_file))
    
    raw_identifiers = ["2244", "glucose", "not_real_compound", ""]
    df_original = pd.DataFrame({
        "input_col": raw_identifiers,
        "extra_info": ["val1", "val2", "val3", "val4"]
    })
    
    # 构造 sheets_results 的 List 格式
    sheets_results = [("Sheet1", df_original, raw_identifiers, False)]
    
    mock_comp_cid = MagicMock()
    mock_comp_cid.cid = 2244
    mock_comp_cid.inchikey = "CID_KEY_2244"
    mock_comp_cid.iupac_name = "Aspirin"
    mock_comp_cid.isomeric_smiles = "SMILES_2244"
    mock_comp_cid.molecular_weight = 180.1
    mock_comp_cid.to_dict.return_value = {"cid": 2244, "inchikey": "CID_KEY_2244"}
    
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
         
        def side_effect(query, q_type):
            if query == "glucose":
                return [mock_comp_name]
            return []
            
        mock_single.side_effect = side_effect
        
        stats = dispatch_processing(
            sheets_results=sheets_results,
            scope=["cid", "name", "smiles", "weight"],
            output_path=str(output_path),
            batch_size=10,
            cache_manager=cache_manager
        )
        
    total, hits, net, not_found = stats
    assert total == 4
    
    assert os.path.exists(str(output_path))
    df_res = pd.read_csv(str(output_path))
    
    assert len(df_res) == 4
    assert list(df_res["input_col"].fillna("")) == raw_identifiers
    assert df_res.at[0, "cid"] == "2244"
    assert df_res.at[0, "name"] == "Aspirin"
    assert df_res.at[1, "cid"] == "5793"
    assert df_res.at[2, "cid"] == "404 Not Found"

def test_dispatch_processing_interrupt_recovery(tmp_path) -> None:
    """
    @ai-ut-matrix: 测试键盘中断保护机制。
    @ai-ut-mock: patch 网络层以使其抛出 UserInterruptError。
    @ai-ut-assert: 1. 必须捕获并重新抛出 UserInterruptError。
                   2. 已经查出的数据必须被保存，未处理的数据应填充为 404。
    """
    cache_file = tmp_path / "cache.json"
    cache_manager = CacheManager(str(cache_file))
    
    raw_identifiers = ["2244", "glucose"]
    df_original = pd.DataFrame({"input": raw_identifiers})
    sheets_results = [("Sheet1", df_original, raw_identifiers, False)]
    
    mock_comp_cid = MagicMock()
    mock_comp_cid.cid = 2244
    mock_comp_cid.inchikey = "KEY_2244"
    mock_comp_cid.iupac_name = "Aspirin"
    mock_comp_cid.to_dict.return_value = {"cid": 2244, "inchikey": "KEY_2244"}
    
    output_path = tmp_path / "interrupt_output.csv"
    
    with patch("lib.batch_dispatcher._fetch_by_cids_network", return_value=[mock_comp_cid]), \
         patch("lib.batch_dispatcher._fetch_single_network", side_effect=UserInterruptError("Keyboard Interrupt")):
         
         with pytest.raises(UserInterruptError):
             dispatch_processing(
                 sheets_results=sheets_results,
                 scope=["cid", "name"],
                 output_path=str(output_path),
                 batch_size=10,
                 cache_manager=cache_manager
             )
             
    assert os.path.exists(str(output_path))
    df_res = pd.read_csv(str(output_path))
    assert len(df_res) == 2
    assert df_res.at[0, "name"] == "Aspirin"
    assert df_res.at[1, "name"] == "404 Not Found"
