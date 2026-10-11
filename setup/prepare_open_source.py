"""Export a clean source checkout and public Windows release; never copy credentials."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,sys,zipfile
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'dist/public-v0.3.0'
SOURCE=BASE/'source'
PACKAGE=BASE/'Bahuang-LiveAvatar-Windows'
parser=argparse.ArgumentParser();parser.add_argument('--archive',action='store_true');args=parser.parse_args()
sys.path.insert(0,str(ROOT))
from app.settings import Settings,read_settings
cfg=read_settings();avatar=cfg.get('default_avatar_id') or cfg['avatar_id']
default=Settings().model_dump();default.update(role_name='小爱',avatar_id=avatar,default_avatar_id=avatar,backup_avatar_id=avatar)
default['system_prompt']='你叫小爱，是一位自然亲切的数字人。用中文口语回答，每次一两句，尽量控制在50个字以内。不要编造事实。/no_think'
SOURCE.mkdir(parents=True,exist_ok=True);PACKAGE.mkdir(parents=True,exist_ok=True)
def ignored(folder,names):
    return [n for n in names if n in {'.git','node_modules','__pycache__','.cache','logs','desktop-profile','record','.env','credentials.dpapi','credentials.private.json','local.previous.json'} or n.endswith(('.pyc','.log','.parts','.wav','.mp4')) or (Path(folder).name=='static' and n=='comparison')]
def safe_copy(src,dst):
    dst=Path(dst)
    if not dst.resolve().is_relative_to(BASE.resolve()):raise ValueError('Output escaped release directory')
    dst.parent.mkdir(parents=True,exist_ok=True)
    if dst.exists():return str(dst)
    try:os.link(src,dst)
    except OSError:shutil.copy2(src,dst)
    return str(dst)
for name in ('app','desktop','docs'):
    shutil.copytree(ROOT/name,SOURCE/name,dirs_exist_ok=True,ignore=ignored)
for name in ('README.md','LICENSE','NOTICE','THIRD_PARTY_NOTICES.md','SECURITY.md','.gitignore'):
    shutil.copy2(ROOT/name,SOURCE/name)
for project in ('LiveTalking','Qwen3-TTS','faster-qwen3-tts-0.2.6'):
    def source_ignore(folder,names):
        return ignored(folder,names)+[n for n in names if n.endswith(('.pth','.bin','.safetensors','.onnx','.gguf')) or (Path(folder).name=='LiveTalking' and n in ('data','models'))]
    shutil.copytree(ROOT/'sources'/project,SOURCE/'sources'/project,dirs_exist_ok=True,ignore=source_ignore)
(SOURCE/'config').mkdir(exist_ok=True)
example=default.copy();example.update(avatar_id='',default_avatar_id='',backup_avatar_id='')
(SOURCE/'config/local.example.json').write_text(json.dumps(example,ensure_ascii=False,indent=2),encoding='utf-8')
(SOURCE/'setup').mkdir(exist_ok=True)
for name in ('sources.json','requirements-windows-lock.txt','prepare_open_source.py','publish_github.py','Merge-Package.ps1','合并整合包.cmd','release-notes.md'):
    if (ROOT/'setup'/name).exists():shutil.copy2(ROOT/'setup'/name,SOURCE/'setup'/name)
for name in ('Merge-Package.ps1','合并整合包.cmd','release-notes.md'):
    if (ROOT/'setup'/name).exists():shutil.copy2(ROOT/'setup'/name,BASE/name)
electron=Path('D:/dev/营销浏览器/GeekezBrowser/node_modules/electron/dist')
shutil.copytree(electron,PACKAGE,dirs_exist_ok=True,copy_function=safe_copy)
# The executable must not remain hardlinked when renamed or edited.
if (PACKAGE/'electron.exe').exists():(PACKAGE/'electron.exe').replace(PACKAGE/'数字人工作台.exe')
shutil.copytree(ROOT/'desktop',PACKAGE/'resources/app',dirs_exist_ok=True,ignore=ignored)
for name in ('app','docs'):
    shutil.copytree(SOURCE/name,PACKAGE/name,dirs_exist_ok=True,ignore=ignored)
for name in ('runtime/windows-python','runtime/llama'):
    shutil.copytree(ROOT/name,PACKAGE/name,dirs_exist_ok=True,ignore=ignored,copy_function=safe_copy)
for name in ('faster-whisper-small','qwen3-tts-0.6b','qwen3-tts-0.6b-base'):
    shutil.copytree(ROOT/'models'/name,PACKAGE/'models'/name,dirs_exist_ok=True,ignore=ignored,copy_function=safe_copy)
safe_copy(ROOT/'models/Qwen3-4B-Q4_K_M.gguf',PACKAGE/'models/Qwen3-4B-Q4_K_M.gguf')
for project in ('LiveTalking','Qwen3-TTS','faster-qwen3-tts-0.2.6'):
    shutil.copytree(SOURCE/'sources'/project,PACKAGE/'sources'/project,dirs_exist_ok=True,ignore=ignored,copy_function=safe_copy)
# Face detector supplied with upstream preprocessing; Wav2Lip and MuseTalk weights omitted.
sfd='sources/LiveTalking/avatars/wav2lip/face_detection/detection/sfd/s3fd.pth'
safe_copy(ROOT/sfd,PACKAGE/sfd)
def avatar_ignore(folder,names):return ignored(folder,names)+[n for n in names if n=='musetalk']
shutil.copytree(ROOT/'sources/LiveTalking/data/avatars'/avatar,PACKAGE/'sources/LiveTalking/data/avatars'/avatar,dirs_exist_ok=True,ignore=avatar_ignore,copy_function=safe_copy)
for name in ('config','assets/voices','assets/videos','logs','sources/LiveTalking/models','setup'):(PACKAGE/name).mkdir(parents=True,exist_ok=True)
(PACKAGE/'config/local.json').write_text(json.dumps(default,ensure_ascii=False,indent=2),encoding='utf-8')
(PACKAGE/'config/avatar-names.json').write_text(json.dumps({avatar:'小爱'},ensure_ascii=False),encoding='utf-8')
for name in ('README.md','LICENSE','NOTICE','THIRD_PARTY_NOTICES.md','SECURITY.md'):
    shutil.copy2(SOURCE/name,PACKAGE/name)
shutil.copy2(SOURCE/'docs/Windows便携版使用说明.md',PACKAGE/'使用说明.md')
shutil.copy2(ROOT/'setup/sources.json',PACKAGE/'setup/sources.json')
manifest={'version':'0.3.0','included_models':['Qwen3-4B-Q4_K_M','Qwen3-TTS-0.6B-CustomVoice','Qwen3-TTS-0.6B-Base','Faster-Whisper-small'],'excluded':['API keys','private config','reference recordings','chat logs','Wav2Lip256 weights','MuseTalk weights'],'avatar':'小爱','first_run':'Import wav2lip256.pth obtained from LiveTalking upstream under its applicable license'}
(PACKAGE/'package-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
files=list(SOURCE.rglob('*'));oversized=[str(f.relative_to(SOURCE)) for f in files if f.is_file() and f.stat().st_size>90_000_000]
assert not oversized,oversized
assert not list(PACKAGE.rglob('credentials.dpapi'))
assert not list(PACKAGE.rglob('credentials.private.json'))
assert not (PACKAGE/'sources/LiveTalking/models/wav2lip.pth').exists()
assert not any((PACKAGE/'assets/voices').iterdir())
print(json.dumps({'source_files':sum(f.is_file() for f in files),'package_bytes':sum(f.stat().st_size for f in PACKAGE.rglob('*') if f.is_file())}),flush=True)
if args.archive:
    archive=BASE/'Bahuang-LiveAvatar-Windows-v0.3.0.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as z:
        for number,f in enumerate(PACKAGE.rglob('*')):
            if f.is_file():z.write(f,f.relative_to(BASE).as_posix())
            if number%3000==0:print(f'Archive entries: {number}',flush=True)
    chunks=[];limit=1_800_000_000
    with archive.open('rb') as stream:
        i=1
        while True:
            block=stream.read(8*1024*1024)
            if not block:break
            part=archive.with_name(archive.name+f'.{i:03}');h=hashlib.sha256();size=0
            with part.open('wb') as output:
                while block:
                    output.write(block);h.update(block);size+=len(block)
                    if size>=limit:break
                    block=stream.read(min(8*1024*1024,limit-size))
            chunks.append({'file':part.name,'bytes':size,'sha256':h.hexdigest()});print(f'Part {i} ready: {size}',flush=True);i+=1
    archive_hash=hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()
    (BASE/'release-manifest.json').write_text(json.dumps({'archive':archive.name,'sha256':archive_hash,'parts':chunks},indent=2),encoding='utf-8')
    (BASE/'SHA256SUMS.txt').write_text('\n'.join(x['sha256']+'  '+x['file'] for x in chunks)+'\n'+archive_hash+'  '+archive.name+'\n',encoding='ascii')
