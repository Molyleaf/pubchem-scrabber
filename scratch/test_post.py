import json
import os
import ssl
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.network_engine import sniff_and_apply_proxies

proxies = sniff_and_apply_proxies()
ssl.create_default_context = ssl._create_unverified_context
ssl._create_default_https_context = ssl._create_unverified_context

url = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/inchikey/property/MolecularFormula,CanonicalSMILES,InChIKey/JSON"
data = urllib.parse.urlencode({
    'inchikey': "CSCPPACGZOOCGX-UHFFFAOYSA-N,INVALIDINCHIKEY-UHFFFAOYSA-N"
}).encode('utf-8')

req = urllib.request.Request(url, data=data)
try:
    with urllib.request.urlopen(req, timeout=10) as res:
        print("Status:", res.status)
        res_data = json.loads(res.read().decode())
        print("Properties:")
        print(json.dumps(res_data, indent=2))
except Exception as e:
    print("Failed:", e)
