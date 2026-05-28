import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ssl
ssl.create_default_context = ssl._create_unverified_context
ssl._create_default_https_context = ssl._create_unverified_context

# 强行清空所有代理环境变量以使用直连
import os
for key in list(os.environ.keys()):
    if "proxy" in key.lower():
        del os.environ[key]

print("Applied proxies: Cleared, Direct Mode")

import requests

try:
    print("Testing PURE DIRECT connection (no proxies)...")
    url = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/2244/property/Title/JSON"
    res = requests.get(url, timeout=10, proxies={"http": None, "https": None})
    print("Success with pure direct requests! Status code:", res.status_code)
    print("JSON Response:", res.json())
except Exception as e:
    print("Pure direct requests failed:")
    import traceback
    traceback.print_exc()
    
try:
    print("\nTesting proxy connection using explicit proxy...")
    # 假设 Clash 的 http 代理是 127.0.0.1:7897 或者是 7890，我们显式传进去看看
    res_proxy = requests.get(url, timeout=10, proxies={"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"})
    print("Success with explicit proxy! Status code:", res_proxy.status_code)
except Exception as e:
    print("Explicit proxy failed:")
    import traceback
    traceback.print_exc()
