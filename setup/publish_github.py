"""Publish clean release using the existing Git credential helper; never print tokens."""
from pathlib import Path
import argparse,json,os,subprocess
import requests
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'dist/public-v0.3.0';SOURCE=BASE/'source'
REPO='1213109176kgy-png/Bahuang-LiveAvatar'
p=argparse.ArgumentParser();p.add_argument('--upload',action='store_true');args=p.parse_args()
credential=subprocess.run(['git','-c','credential.interactive=false','credential','fill'],input='protocol=https\nhost=github.com\n\n',text=True,capture_output=True,timeout=20,check=True)
values=dict(x.split('=',1) for x in credential.stdout.splitlines() if '=' in x)
token=values.get('password');assert token,'No saved GitHub credential'
env=os.environ.copy();env['GH_TOKEN']=token;env['GH_PAGER']='cat';env['GIT_TERMINAL_PROMPT']='0'
session=requests.Session();session.headers.update({'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
# Respect the local configured proxy when present; tokens stay in memory.
if os.environ.get('BAHUANG_GITHUB_PROXY'):session.proxies={'https':os.environ['BAHUANG_GITHUB_PROXY']}
user=session.get('https://api.github.com/user',timeout=30);user.raise_for_status();assert user.json()['login']==REPO.split('/')[0]
existing=session.get('https://api.github.com/repos/'+REPO,timeout=30)
if existing.status_code==404:
    result=session.post('https://api.github.com/user/repos',json={'name':REPO.split('/')[1],'description':'八荒实时数字人：Windows 便携工作台、视频通话、语音互动、可配置人物/声音/本地及在线模型','private':False,'has_issues':True,'has_wiki':False,'auto_init':False},timeout=30);result.raise_for_status();print('Created '+result.json()['html_url'],flush=True)
else:existing.raise_for_status();assert existing.json()['owner']['login']==user.json()['login']
def run(command,**kwargs):
    result=subprocess.run(command,cwd=SOURCE,env=env,text=True,capture_output=True,**kwargs)
    if result.returncode:raise RuntimeError(f'{command[0]} operation failed (exit {result.returncode}); no credential output printed')
    return result.stdout.strip()
if not (SOURCE/'.git').exists():
    run(['git','init','-b','main']);run(['git','config','user.name','老K']);run(['git','config','user.email','297553809+1213109176kgy-png@users.noreply.github.com'])
    run(['git','remote','add','origin','https://github.com/'+REPO+'.git'])
run(['git','add','--all'])
if run(['git','status','--porcelain']):run(['git','commit','-m','Release v0.3.0: 中文实时数字人工作台与 Windows 便携发布'])
run(['git','push','-u','origin','main'],timeout=180)
print('Source pushed: '+run(['git','rev-parse','HEAD']),flush=True)
notes=BASE/'release-notes.md'
check=subprocess.run(['gh','release','view','v0.3.0','--repo',REPO],env=env,text=True,capture_output=True)
if check.returncode:
    subprocess.run(['gh','release','create','v0.3.0','--repo',REPO,'--title','八荒实时数字人 v0.3.0 · Windows 免费开源版','--notes-file',str(notes),'--draft','--target','main'],env=env,check=True)
if args.upload:
    manifest=json.loads((BASE/'release-manifest.json').read_text())
    assets=[BASE/x['file'] for x in manifest['parts']]+[BASE/x for x in ('合并整合包.cmd','Merge-Package.ps1','release-manifest.json','SHA256SUMS.txt')]
    for file in assets:
        print('Uploading '+file.name,flush=True)
        subprocess.run(['gh','release','upload','v0.3.0',str(file),'--repo',REPO,'--clobber'],env=env,check=True)
    subprocess.run(['gh','release','edit','v0.3.0','--repo',REPO,'--draft=false','--latest'],env=env,check=True)
    print('Published https://github.com/'+REPO+'/releases/tag/v0.3.0',flush=True)
else:print('Draft release ready; assets not yet uploaded.',flush=True)
