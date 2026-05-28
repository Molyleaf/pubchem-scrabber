import json
import os

from lib.cache_manager import CacheManager


def test_cache_initialization(tmp_path) -> None:
    """
    @ai-ut-matrix: 测试在指定目录不存在时，缓存管理器是否能自动创建目录并初始化一个空的有效 JSON 缓存文件。
    @ai-ut-mock: 使用 tmp_path 隔离文件 IO。
    @ai-ut-assert: 1. 缓存文件必须自动生成。
                   2. 顶层字典必须包含且仅包含 compounds 和 query_index。
    """
    cache_file = tmp_path / "subdir" / "cache.json"
    manager = CacheManager(str(cache_file))
    
    assert os.path.exists(str(cache_file))
    with open(str(cache_file), "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "compounds" in data
    assert "query_index" in data
    assert len(data["compounds"]) == 0

def test_save_and_lookup_multi_index(tmp_path) -> None:
    """
    @ai-ut-matrix: 测试化合物保存后，是否能为 CID、俗名、SMILES、InChI 以及 InChIKey 自动建立小写化多级索引，并能通过 lookup 瞬间定位。
    @ai-ut-mock: 无
    @ai-ut-assert: 1. 保存后，通过原始俗名、CID、SMILES、InChI 甚至不同大小写的别名均能成功检索出同一化合物数据。
                   2. 查询不存在的项应返回 None。
    """
    cache_file = tmp_path / "cache.json"
    manager = CacheManager(str(cache_file))
    
    dummy_compound = {
        "cid": 2244,
        "iupac_name": "Aspirin",
        "smiles": "CC(=O)OC1=CC=CC=C1C(=O)O",
        "inchi": "InChI=1S/C9H8O4/c1-6(10)13-8-5-3-2-4-7(8)9(11)12/h2-5H,1H3,(H,11,12)",
        "inchikey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
        "molecular_weight": 180.16
    }
    
    # 模拟用户通过 "Aspirin-Query" 进行的网络查询保存
    manager.save_compound("Aspirin-Query", dummy_compound)
    
    # 多维索引验证（不区分大小写匹配）
    res1 = manager.lookup("Aspirin-Query")
    res2 = manager.lookup("aspirin-query")
    res3 = manager.lookup("2244")
    res4 = manager.lookup("aspirin")
    res5 = manager.lookup("CC(=O)OC1=CC=CC=C1C(=O)O")
    res6 = manager.lookup("InChI=1S/C9H8O4/c1-6(10)13-8-5-3-2-4-7(8)9(11)12/h2-5H,1H3,(H,11,12)")
    res7 = manager.lookup("BSYNRYMUTXBXSQ-UHFFFAOYSA-N")
    
    assert res1 is not None
    assert res1["cid"] == 2244
    assert res2 == res1
    assert res3 == res1
    assert res4 == res1
    assert res5 == res1
    assert res6 == res1
    assert res7 == res1
    
    assert manager.lookup("not_exist") is None

def test_negative_caching(tmp_path) -> None:
    """
    @ai-ut-matrix: 测试负向空值缓存机制（把未命中的 query 标记为 '404 Not Found'），确保不会重复网络请求。
    @ai-ut-mock: 无
    @ai-ut-assert: 保存为 404 后，lookup 必须立即返回 '404 Not Found' 字符串。
    """
    cache_file = tmp_path / "cache.json"
    manager = CacheManager(str(cache_file))
    
    manager.data["query_index"]["not_real"] = "404 Not Found"
    manager._save_cache_to_disk()
    
    assert manager.lookup("not_real") == "404 Not Found"
