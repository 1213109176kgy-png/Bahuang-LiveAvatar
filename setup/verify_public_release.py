"""Verify the publicly accessible GitHub release without any credentials."""
import hashlib,json,os
from pathlib import Path
import requests
root=Path(__file__).resolve().parents[1]
base=root/'dist/public-v0.3.0'
repo='1213109176kgy-png/Bahuang-LiveAvatar'
session=requests.Session()
if os.environ.get('BAHUANG_GITHUB_PROXY'):
    session.proxies={'https':os.environ['BAHUANG_GITHUB_PROXY']}
def get(url):
    response=session.get(url,timeout=60);response.raise_for_status();return response
release=get('https://api.github.com/repos/'+repo+'/releases/latest').json()
assert release['tag_name']=='v0.3.0' and not release['draft']
manifest=json.loads((base/'release-manifest.json').read_text())
expected={p['file']:(p['bytes'],p['sha256']) for p in manifest['parts']}
for name in ('Merge-Package.cmd','Merge-Package.ps1','release-manifest.json','SHA256SUMS.txt'):
    path=base/name
    expected[name]=(path.stat().st_size,hashlib.sha256(path.read_bytes()).hexdigest())
remote={a['name']:a for a in release['assets']}
for name,(size,digest) in expected.items():
    asset=remote[name];assert asset['size']==size and asset['state']=='uploaded',name
    if asset.get('digest'):assert asset['digest']=='sha256:'+digest,name
readme=get('https://raw.githubusercontent.com/'+repo+'/main/README.md').text
assert '深圳市八荒科技有限公司' in readme and 'wechat-qr.jpg' in readme
for name in ('company-logo.png','wechat-qr.jpg'):
    content=get('https://raw.githubusercontent.com/'+repo+'/main/app/static/brand/'+name).content
    assert content==(root/'app/static/brand'/name).read_bytes(),name
result={'release':release['html_url'],'assets_verified':len(expected),'archive_bytes':sum(p['bytes'] for p in manifest['parts']),'remote_digests_available':all(a.get('digest') for a in remote.values()),'readme_and_brand_assets_verified':True}
(base/'public-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
