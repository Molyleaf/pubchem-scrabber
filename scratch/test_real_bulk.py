import pandas as pd
import urllib.request
import urllib.parse
import json
import ssl
import sys
import os

# 加载 input 文件
df = pd.read_excel("阳性样本爬smiles.xlsx", sheet_name="InChIKey")
print("Sheet columns:", df.columns)
# 第一列数据
inchikeys = df.iloc[:, 0].dropna().astype(str).tolist()
# 过滤掉 header 等
inchikeys = [x.strip() for x in inchikeys if len(x.strip()) == 27]
print("Total valid InChIKeys in sheet InChIKey:", len(inchikeys))

test_chunk = inchikeys[:50]
print("Testing first 50 InChIKeys:")
for i, k in enumerate(test_chunk):
    print(f"  {i+1}: {k}")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.network_engine import sniff_and_apply_proxies

proxies = sniff_and_apply_proxies()
print("Applied proxies:", proxies)

ssl.create_default_context = ssl._create_unverified_context
ssl._create_default_https_context = ssl._create_unverified_context

url = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/inchikey/property/MolecularFormula,CanonicalSMILES,InChIKey/JSON"
data = urllib.parse.urlencode({
    'inchikey': "\n".join(test_chunk)
}).encode('utf-8')

req = urllib.request.Request(url, data=data)
try:
    print("Sending POST request to PubChem...", flush=True)
    with urllib.request.urlopen(req, timeout=15) as res:
        print("Status code:", res.status, flush=True)
        res_data = json.loads(res.read().decode())
        properties = res_data.get("PropertyTable", {}).get("Properties", [])
        print("Properties retrieved successfully! Count:", len(properties), flush=True)
        for i, p in enumerate(properties[:5]):
            print(f"  {i+1}: {p}", flush=True)
except Exception as e:
    print("Request failed with error:", e, flush=True)
