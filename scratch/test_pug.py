import os
import urllib.request
import urllib.parse
import ssl
import json

try:
    ssl.create_default_context = ssl._create_unverified_context
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

proxies = urllib.request.getproxies()
if proxies:
    for proto, url in proxies.items():
        proxy_url = url
        if not url.startswith("http://") and not url.startswith("https://"):
            proxy_url = f"http://{url}"
        
        if proto == "http":
            os.environ["HTTP_PROXY"] = proxy_url
        elif proto == "https":
            os.environ["HTTPS_PROXY"] = proxy_url
        os.environ[f"{proto.upper()}_PROXY"] = proxy_url

def test_batch_cids(input_type, items):
    # 测试通过批量 POST 把 input_type (smiles, name, inchi) 转为 CID 列表
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/{input_type}/cids/JSON"
    
    # 尝试用逗号连接
    post_data_comma = urllib.parse.urlencode({
        input_type: ",".join(items)
    }).encode('utf-8')
    
    # 尝试用换行符连接
    post_data_newline = urllib.parse.urlencode({
        input_type: "\n".join(items)
    }).encode('utf-8')
    
    for label, payload in [("comma", post_data_comma), ("newline", post_data_newline)]:
        print(f"\n--- Testing {input_type} batch cids via POST ({label}) ---")
        req = urllib.request.Request(url, data=payload)
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                data = json.loads(res.read().decode('utf-8'))
                print("SUCCESS:")
                print(json.dumps(data, indent=2))
        except Exception as e:
            print(f"FAILED: {e}")
            if hasattr(e, 'read'):
                print(f"  Response: {e.read().decode('utf-8')}")

if __name__ == "__main__":
    test_batch_cids("smiles", ["CC(=O)OC1=CC=CC=C1C(=O)O", "CC(=O)C"])
    test_batch_cids("name", ["aspirin", "glucose"])
