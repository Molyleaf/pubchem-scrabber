import os
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from lib.cache_manager import CacheManager
from lib.batch_dispatcher import serialize_compound, dispatch_processing, UserInterruptError

def test_serialize_compound() -> None:
    """
    @ai-ut-matrix: 测试将 pubchempy Compound 转换为本地持久化字典的方法是否具备鲁棒性且能补充提倡字段。
    @ai-ut-mock: 使用 MagicMock 模拟 Compound 对象。
    @ai-ut-assert: 1. 字典中包含 cid, inchikey, smiles 核心键值。
                   2. 转换成 float 类型的分子量应准确无误。
    """
    mock_comp = MagicMock()
    mock_comp.cid = 2244
    mock_comp.iupac_name = "Aspirin"
    mock_comp.smiles = "CC(=O)OC1=CC=CC=C1C(=O)O"
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
    assert res["smiles"] == "CC(=O)OC1=CC=CC=C1C(=O)O"

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
    
    sheets_results = [("Sheet1", df_original, raw_identifiers, False)]
    
    mock_comp_cid = MagicMock()
    mock_comp_cid.cid = 2244
    mock_comp_cid.inchikey = "CID_KEY_2244"
    mock_comp_cid.iupac_name = "Aspirin"
    mock_comp_cid.smiles = "SMILES_2244"
    mock_comp_cid.molecular_weight = 180.1
    mock_comp_cid.to_dict.return_value = {"cid": 2244, "inchikey": "CID_KEY_2244"}
    
    mock_comp_name = MagicMock()
    mock_comp_name.cid = 5793
    mock_comp_name.inchikey = "GLUCOSE_KEY"
    mock_comp_name.iupac_name = "D-Glucose"
    mock_comp_name.smiles = "SMILES_GLUCOSE"
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
    assert df_res.at[0, "smiles"] == "SMILES_2244"
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

def test_fetch_by_inchikeys_network() -> None:
    """
    @ai-ut-matrix: 测试 _fetch_by_inchikeys_network 批量获取 InChIKey 属性的网络接口。
    @ai-ut-mock: 使用 MagicMock 模拟 urllib.request.urlopen 及其返回值。
    @ai-ut-assert: 1. 验证接口调用成功并正确解析返回数据。
                   2. 严格验证批量发送的 InChIKeys 在 POST 请求体中是由换行符（编码后为 %0A）分隔。
    """
    import json
    from lib.batch_dispatcher import _fetch_by_inchikeys_network
    
    mock_response = {
        "PropertyTable": {
            "Properties": [
                {
                    "CID": 180,
                    "MolecularFormula": "C3H6O",
                    "ConnectivitySMILES": "CC(=O)C",
                    "InChIKey": "CSCPPACGZOOCGX-UHFFFAOYSA-N"
                }
            ]
        }
    }
    
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_res_obj = MagicMock()
        mock_res_obj.__enter__.return_value = mock_res_obj
        mock_res_obj.read.return_value = json.dumps(mock_response).encode("utf-8")
        mock_urlopen.return_value = mock_res_obj
        
        res = _fetch_by_inchikeys_network(
            ["CSCPPACGZOOCGX-UHFFFAOYSA-N", "AICJARHUOUQZSH-UHFFFAOYSA-N"], 
            ["formula", "smiles"]
        )
        assert res == mock_response
        mock_urlopen.assert_called_once()
        
        # 深度契约断言：验证 payload 是否严格按照 PubChem 要求的换行符分割并编码发送
        args, _ = mock_urlopen.call_args
        req = args[0]
        assert req.data == b"inchikey=CSCPPACGZOOCGX-UHFFFAOYSA-N%0AAICJARHUOUQZSH-UHFFFAOYSA-N"

def test_dispatch_processing_inchikey_batch(tmp_path) -> None:
    """
    测试对于 InChIKey 标识符，dispatch_processing 是否能正确走批量 POST 并缓存。
    """
    cache_file = tmp_path / "cache.json"
    cache_manager = CacheManager(str(cache_file))
    
    raw_identifiers = ["CSCPPACGZOOCGX-UHFFFAOYSA-N", "INVALIDINCHIKEY-UHFFFAOYSA-N"]
    df_original = pd.DataFrame({"input": raw_identifiers})
    sheets_results = [("Sheet1", df_original, raw_identifiers, False)]
    
    mock_batch_response = {
        "PropertyTable": {
            "Properties": [
                {
                    "CID": 180,
                    "MolecularFormula": "C3H6O",
                    "CanonicalSMILES": "CC(=O)C",
                    "InChIKey": "CSCPPACGZOOCGX-UHFFFAOYSA-N"
                }
            ]
        }
    }
    
    output_path = tmp_path / "inchikey_batch_output.csv"
    
    with patch("lib.batch_dispatcher._fetch_by_inchikeys_network", return_value=mock_batch_response) as mock_fetch:
        stats = dispatch_processing(
            sheets_results=sheets_results,
            scope=["cid", "smiles", "formula"],
            output_path=str(output_path),
            batch_size=10,
            cache_manager=cache_manager
        )
        
    total, hits, net, not_found = stats
    assert total == 2
    assert os.path.exists(str(output_path))
    
    df_res = pd.read_csv(str(output_path))
    assert len(df_res) == 2
    assert df_res.at[0, "formula"] == "C3H6O"
    assert df_res.at[0, "smiles"] == "CC(=O)C"
    assert df_res.at[1, "formula"] == "404 Not Found"
    mock_fetch.assert_called_once()

def test_dispatch_processing_inchikey_fallback(tmp_path) -> None:
    """
    测试当批量 InChIKey 查询发生异常时，是否能智能无感地自动降级为串行逐个查询。
    """
    cache_file = tmp_path / "cache.json"
    cache_manager = CacheManager(str(cache_file))
    
    raw_identifiers = ["CSCPPACGZOOCGX-UHFFFAOYSA-N"]
    df_original = pd.DataFrame({"input": raw_identifiers})
    sheets_results = [("Sheet1", df_original, raw_identifiers, False)]
    
    mock_comp = MagicMock()
    mock_comp.cid = 180
    mock_comp.iupac_name = "Acetone"
    mock_comp.smiles = "CC(=O)C"
    mock_comp.inchikey = "CSCPPACGZOOCGX-UHFFFAOYSA-N"
    mock_comp.to_dict.return_value = {"cid": 180, "inchikey": "CSCPPACGZOOCGX-UHFFFAOYSA-N"}
    
    output_path = tmp_path / "inchikey_fallback_output.csv"
    
    with patch("lib.batch_dispatcher._fetch_by_inchikeys_network", side_effect=Exception("Network error")), \
         patch("lib.batch_dispatcher._fetch_single_network", return_value=[mock_comp]) as mock_single:
         
        stats = dispatch_processing(
            sheets_results=sheets_results,
            scope=["cid", "name", "smiles"],
            output_path=str(output_path),
            batch_size=10,
            cache_manager=cache_manager
        )
        
    total, hits, net, not_found = stats
    assert total == 1
    df_res = pd.read_csv(str(output_path))
    assert df_res.at[0, "name"] == "Acetone"
    mock_single.assert_called_once_with("CSCPPACGZOOCGX-UHFFFAOYSA-N", "inchikey")
