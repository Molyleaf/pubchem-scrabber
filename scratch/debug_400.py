import urllib.request
import urllib.parse
import json
import ssl
import sys
import os

# 探测代理
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.network_engine import sniff_and_apply_proxies

proxies = sniff_and_apply_proxies()
print("Using proxies:", proxies)

ssl.create_default_context = ssl._create_unverified_context
ssl._create_default_https_context = ssl._create_unverified_context

# 5个测试 InChIKeys（有些可能有效，有些随便写但格式符合 27 位）
inchikeys = [
    "AEKYOIGTEGFYSI-UHFFFAOYSA-N",
    "AICJARHUOUQZSH-UHFFFAOYSA-N",
    "AIZFETCNFVMZGT-UHFFFAOYSA-N",
    "AJGASUCDTSLMNP-LLVKDONJSA-N",
    "AJSBNWAHEDVQJT-UHFFFAOYSA-N"
]

properties_str = "MolecularFormula,CanonicalSMILES,InChIKey"

# 1. 测试以逗号分隔，单个 key='inchikey' 的形式 (即当前系统的做法)
url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/inchikey/property/{properties_str}/JSON"
data = urllib.parse.urlencode({
    'inchikey': ",".join(inchikeys)
}).encode('utf-8')

print("\n--- Test 1: comma separated in 'inchikey' parameter ---")
req = urllib.request.Request(url, data=data)
try:
    with urllib.request.urlopen(req, timeout=10) as res:
        print("Success! Status:", res.status)
        res_data = json.loads(res.read().decode())
        print("Retrieved properties count:", len(res_data.get("PropertyTable", {}).get("Properties", [])))
except Exception as e:
    print("Failed:", e)

# 2. 测试以换行符分隔，单个 key='inchikey' 的形式
data_nl = urllib.parse.urlencode({
    'inchikey': "\n".join(inchikeys)
}).encode('utf-8')

print("\n--- Test 2: newline separated in 'inchikey' parameter ---")
req = urllib.request.Request(url, data=data_nl)
try:
    with urllib.request.urlopen(req, timeout=10) as res:
        print("Success! Status:", res.status)
        res_data = json.loads(res.read().decode())
        print("Retrieved properties count:", len(res_data.get("PropertyTable", {}).get("Properties", [])))
except Exception as e:
    print("Failed:", e)

# 3. 测试以多个 'inchikey' 键值对的形式 (类似 curl -d 'inchikey=...' -d 'inchikey=...')
# urlencode 可以接受 list of tuples
data_multi = urllib.parse.urlencode([('inchikey', k) for k in inchikeys]).encode('utf-8')

print("\n--- Test 3: multiple 'inchikey' parameters ---")
req = urllib.request.Request(url, data=data_multi)
try:
    with urllib.request.urlopen(req, timeout=10) as res:
        print("Success! Status:", res.status)
        res_data = json.loads(res.read().decode())
        print("Retrieved properties count:", len(res_data.get("PropertyTable", {}).get("Properties", [])))
except Exception as e:
    print("Failed:", e)
