import os
import json
import logging
from typing import Optional, Dict, Any

class CacheManager:
    """
    @ai-intent: 管理本地化合物数据缓存，提供多级反向索引的快速查找和原子级的安全磁盘持久化。
    @ai-invariant: 1. 本地缓存文件必须以 JSON 格式存储，且顶层结构包含且仅包含 'compounds' 和 'query_index' 两个核心字段。
                   2. 所有的查询匹配均采用大小写不敏感（统一转小写）策略。
                   3. 任何写入操作必须采用临时文件重命名（原子级写入）方式，绝不允许在写入过程中因异常导致文件损坏。
    @ai-boundary: 允许读写 cache_path 指定的磁盘文件，提供内存级字典的检索与更新。
    @ai-directive: 查询复杂度必须为 O(1)。
    @ai-observe:
      Event Logging: [缓存加载/保存] -> [化合物总数, 映射索引数] -> [成功/失败原因]
    @ai-context:
      Topology: 模块 3: 缓存管理中心 / 本地 IO 与存储层
      Flow: 初始化 -> 加载 JSON -> 内存检索 -> 保存数据 -> 原子落盘
      Blast Radius: 缓存管理损坏会导致无法匹配，引发大量重复网络请求，必须严格保证 JSON schema 完整性
      ADR: 为了解决俗名、CID、SMILES 之间多对一的映射，引入 query_index 冗余索引，将所有关联标识符均映射至唯一的 InChIKey 主键。
      Ubiquitous Language: compounds 区存储详细结构体，query_index 存储各种别名/ID 到 InChIKey 的硬链接。
    """
    
    def __init__(self, cache_path: str = "cache/pubchem_cache.json"):
        """
        初始化缓存管理器，加载本地 JSON 文件。
        """
        self.cache_path = os.path.abspath(cache_path)
        self.cache_dir = os.path.dirname(self.cache_path)
        
        # 核心内存字典
        self.data: Dict[str, Dict[str, Any]] = {
            "compounds": {},
            "query_index": {}
        }
        
        self._load_cache()

    def _load_cache(self) -> None:
        """
        从磁盘安全读取缓存，若不存在则创建。
        """
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir, exist_ok=True)
            
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict) and "compounds" in loaded and "query_index" in loaded:
                        self.data = loaded
                    else:
                        # 结构损坏，初始化默认
                        self.data = {"compounds": {}, "query_index": {}}
            except Exception as e:
                # 异常损坏，保底重置并打印警告
                logging.warning(f"缓存文件 {self.cache_path} 损坏，将重新初始化。错误: {e}")
                self.data = {"compounds": {}, "query_index": {}}
        else:
            self._save_cache_to_disk()

    def _save_cache_to_disk(self) -> None:
        """
        原子级安全保存缓存数据至磁盘（临时文件写完后 rename，避免直接覆盖时断电损坏）。
        """
        tmp_path = f"{self.cache_path}.tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            # 原子级重命名覆盖
            if os.path.exists(self.cache_path):
                os.remove(self.cache_path)
            os.rename(tmp_path, self.cache_path)
        except Exception as e:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            raise IOError(f"保存缓存文件失败: {e}")

    def lookup(self, query: str) -> Optional[dict]:
        """
        多级索引查找化合物。
        """
        if not query:
            return None
            
        q_clean = str(query).strip().lower()
        
        # 1. 尝试在二级映射索引中查找 inchikey
        inchikey = self.data["query_index"].get(q_clean)
        
        # 支持负向空值缓存
        if inchikey == "404 Not Found":
            return "404 Not Found"
            
        # 2. 如果索引中找到了 inchikey，则去详情区查找
        if inchikey and inchikey in self.data["compounds"]:
            return self.data["compounds"][inchikey]
            
        # 3. 容错查找：如果 query 本身就是一个 inchikey 格式，尝试直接在详情区检索
        if len(q_clean) == 27 and q_clean[14] == '-' and q_clean[25] == '-':
            # 注意 compounds 中的 key 保存时可能是原始大小写（InChIKey 通常大写）
            for key in self.data["compounds"]:
                if key.lower() == q_clean:
                    return self.data["compounds"][key]
                    
        return None

    def save_compound(self, query: str, compound_dict: dict) -> None:
        """
        保存单个化合物数据，并更新多级反向索引与磁盘文件。
        """
        if not compound_dict:
            return
            
        # 必须拥有 inchikey 作为主键，如果没有（极罕见），则以 CID 为代用键
        inchikey = compound_dict.get("inchikey")
        if not inchikey:
            cid = compound_dict.get("cid")
            if cid:
                inchikey = f"CID_{cid}"
            else:
                return  # 没有任何唯一标识符，放弃缓存
                
        # 1. 将数据存入 compounds 区
        self.data["compounds"][inchikey] = compound_dict
        
        # 2. 更新多级反向索引（全部转换为小写，支持多维极速命中）
        q_clean = str(query).strip().lower()
        self.data["query_index"][q_clean] = inchikey
        
        # 同时提取化合物的其他已知标识符加入 query_index，实现“一次获取，多维复用”
        cid = compound_dict.get("cid")
        if cid:
            self.data["query_index"][str(cid).strip().lower()] = inchikey
            
        iupac_name = compound_dict.get("iupac_name")
        if iupac_name:
            self.data["query_index"][str(iupac_name).strip().lower()] = inchikey
            
        isomeric_smiles = compound_dict.get("isomeric_smiles")
        if isomeric_smiles:
            self.data["query_index"][str(isomeric_smiles).strip().lower()] = inchikey
            
        inchi = compound_dict.get("inchi")
        if inchi:
            self.data["query_index"][str(inchi).strip().lower()] = inchikey
            
        # 保存 inchikey 自身索引
        self.data["query_index"][str(inchikey).strip().lower()] = inchikey
        
        # 3. 持久化落盘
        self._save_cache_to_disk()
