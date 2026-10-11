import asyncio
import json
from pathlib import Path
import re
import subprocess
import sys
import uuid
import shutil
import httpx
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from .settings import ROOT, read_settings, save_settings, save_credentials, credentials, auth

router = APIRouter(prefix='/api')
AVATARS = ROOT / 'sources/LiveTalking/data/avatars'
jobs = {}
AVATAR_META = ROOT / 'config/avatar-names.json'

def muse_installed():
    model = ROOT / 'sources/LiveTalking/models'
    return all((model / path).is_file() for path in ('musetalkV15/unet.pth', 'musetalkV15/musetalk.json', 'sd-vae/diffusion_pytorch_model.bin', 'whisper/pytorch_model.bin', 'face-parse-bisent/79999_iter.pth'))

@router.post('/avatars/{avatar_id}/prepare-musetalk')
async def prepare_musetalk(avatar_id: str):
    folder = safe_avatar(avatar_id)
    if not (folder / 'coords.pkl').is_file():
        raise HTTPException(404, '人物尚未处理完成')
    if not muse_installed():
        raise HTTPException(409, 'MuseTalk 1.5 模型尚未安装完整')
    if any(job.get('avatar_id') == avatar_id and job.get('kind') == 'musetalk' and job['status'] in ('queued', 'processing') for job in jobs.values()):
        raise HTTPException(409, '该人物正在预处理中')
    identifier = 'muse_' + uuid.uuid4().hex[:12]
    jobs[identifier] = {'name': 'MuseTalk 1.5 人物预处理', 'status': 'queued', 'avatar_id': avatar_id, 'kind': 'musetalk'}
    async def run():
        jobs[identifier]['status'] = 'processing'
        try:
            with (ROOT / 'logs' / f'{identifier}.log').open('w', encoding='utf-8') as output:
                process = await asyncio.create_subprocess_exec(sys.executable, '-X', 'utf8', str(ROOT / 'app/muse_assets.py'), avatar_id, '--cpu', stdout=output, stderr=output, cwd=ROOT)
                jobs[identifier]['pid'] = process.pid
                if await process.wait():
                    raise RuntimeError('MuseTalk 预处理失败，请查看该任务日志')
            jobs[identifier]['status'] = 'complete'
        except Exception as error:
            jobs[identifier].update(status='failed', error=str(error))
    asyncio.create_task(run())
    return {'job_id': identifier, 'message': '正在用 CPU 预处理，避免占用实时服务显存'}

@router.patch('/avatars/{avatar_id}')
async def avatar_preferences(avatar_id: str, payload: dict):
    folder = safe_avatar(avatar_id)
    if not (folder / 'coords.pkl').is_file():
        raise HTTPException(404, '形象不存在或尚未处理完成')
    if set(payload) - {'name', 'default', 'backup'}:
        raise HTTPException(400, '无效形象配置')
    values = {}
    if payload.get('default') is True:
        values['default_avatar_id'] = avatar_id
    if payload.get('backup') is True:
        values['backup_avatar_id'] = avatar_id
    name = payload.get('name')
    if name is not None and (not isinstance(name, str) or not 1 <= len(name.strip()) <= 32):
        raise HTTPException(400, '名称需为1–32个字')
    try:
        settings, _ = save_settings(values)
        if name is not None:
            names = json.loads(AVATAR_META.read_text(encoding='utf-8')) if AVATAR_META.exists() else {}
            names[avatar_id] = name.strip()
            temporary = AVATAR_META.with_suffix('.tmp')
            temporary.write_text(json.dumps(names, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(AVATAR_META)
        from .server import CONFIG
        CONFIG.clear()
        CONFIG.update(settings)
        return {'values': settings}
    except Exception:
        raise HTTPException(400, '形象设置保存失败') from None

@router.delete('/avatars/{avatar_id}')
async def delete_avatar(avatar_id: str):
    folder = safe_avatar(avatar_id)
    settings = read_settings()
    if avatar_id in (settings['avatar_id'], settings['default_avatar_id'], settings['backup_avatar_id']):
        raise HTTPException(409, '正在使用、默认或备用的形象不能删除，请先切换或指定其他形象')
    if jobs.get(avatar_id, {}).get('status') in ('queued', 'processing'):
        raise HTTPException(409, '底片正在处理中，请等待完成')
    if not folder.is_dir():
        raise HTTPException(404, '形象不存在')
    if folder.is_symlink() or not folder.resolve().is_relative_to(AVATARS.resolve()):
        raise HTTPException(400, '无效人物目录')
    shutil.rmtree(folder)
    jobs.pop(avatar_id, None)
    return {'ok': True}

@router.post('/models/discover')
async def discover_models(payload: dict):
    from .settings import Settings
    try:
        kind = payload.get('kind', 'llm')
        if kind not in ('llm', 'asr', 'tts'):
            raise ValueError('无效模型类型')
        endpoint = Settings(llm_base_url=payload.get('base_url', '')).llm_base_url
        key = payload.get('api_key', '')
        if not isinstance(key, str):
            raise ValueError('无效密钥')
        headers = {'Authorization': 'Bearer ' + key.strip()} if key.strip() else auth(kind)
        async with httpx.AsyncClient(timeout=20, trust_env=False, follow_redirects=False) as client:
            response = await client.get(endpoint + '/models', headers=headers)
        if not response.is_success:
            raise HTTPException(400, f'模型列表接口返回 HTTP {response.status_code}，可手动填写模型或接入点 ID')
        entries = response.json().get('data', [])
        models = sorted({item['id'] for item in entries if isinstance(item, dict) and isinstance(item.get('id'), str)})
        return {'models': models, 'message': ('已获取服务商模型列表；请选支持' + {'llm': '对话', 'asr': '转写', 'tts': '语音合成'}[kind] + '接口的模型，列表本身不保证推理兼容') if models else '接口未返回模型列表，请手动填写模型或接入点 ID'}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, '无法获取模型列表，请检查地址、密钥或手动填写；部分服务商不支持此接口') from None

def safe_avatar(value):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', value):
        raise HTTPException(400, '无效人物编号')
    return AVATARS / value

@router.get('/config')
async def config():
    saved = credentials()
    return {'values': read_settings(), 'keys': {key: bool(saved.get(key)) for key in ('llm', 'asr', 'tts')}}

@router.put('/config')
async def update(payload: dict):
    try:
        keys = payload.get('keys', {})
        if not isinstance(keys, dict) or set(keys) - {'llm', 'asr', 'tts'} or any(v is not None and not isinstance(v, str) for v in keys.values()):
            raise ValueError('无效凭据类型')
        values, restart = save_settings(payload.get('values', {}))
        if payload.get('keys'):
            save_credentials(payload['keys'])
        from .server import CONFIG
        CONFIG.clear()
        CONFIG.update(values)
        return {'values': values, 'restart_required': restart}
    except Exception as error:
        # Validation output never contains the submitted credential payload.
        raise HTTPException(400, str(error)) from None

@router.get('/catalog')
async def catalog():
    avatars = []
    names = json.loads(AVATAR_META.read_text(encoding='utf-8')) if AVATAR_META.exists() else {}
    settings = read_settings()
    for folder in sorted(AVATARS.iterdir()):
        frames = sorted((folder / 'full_imgs').glob('*.png'))
        if not frames or not (folder / 'coords.pkl').is_file():
            continue
        avatars.append({'id': folder.name, 'name': names.get(folder.name, folder.name), 'default': folder.name == settings['default_avatar_id'], 'backup': folder.name == settings['backup_avatar_id'], 'frames': len(frames), 'seconds': round(len(frames) / 25, 1), 'thumbnail': f'/api/avatars/{folder.name}/thumbnail'})
        avatars[-1]['musetalk_ready'] = (folder / 'musetalk/ready.json').is_file()
    models = []
    for file in sorted((ROOT / 'models').glob('*.gguf')):
        models.append({'kind': 'llm', 'path': file.relative_to(ROOT).as_posix(), 'name': file.name})
    for directory in sorted((ROOT / 'models').iterdir()):
        cfg = directory / 'config.json'
        if not cfg.is_file():
            continue
        info = json.loads(cfg.read_text(encoding='utf-8'))
        kind = 'tts' if 'tts_model_type' in info else 'asr'
        if kind == 'tts' and not ((directory / 'model.safetensors').is_file() and (directory / 'speech_tokenizer/model.safetensors').is_file()):
            continue
        models.append({'kind': kind, 'path': directory.relative_to(ROOT).as_posix(), 'name': directory.name, 'type': info.get('tts_model_type', '')})
    selected = ROOT / read_settings()['tts_model'] / 'config.json'
    if selected.is_file() and json.loads(selected.read_text(encoding='utf-8')).get('tts_model_type') == 'base':
        selected = next((ROOT / item['path'] / 'config.json' for item in models if item['kind'] == 'tts' and item['type'] == 'custom_voice'), selected)
    speaker_map = json.loads(selected.read_text(encoding='utf-8')).get('talker_config', {}).get('spk_id', {}) if selected.is_file() else {}
    labels = {'vivian': 'Vivian', 'serena': 'Serena', 'uncle_fu': 'Uncle_Fu', 'ono_anna': 'Ono_Anna'}
    speakers = [labels.get(name, name.title()) for name in speaker_map]
    return {'comparison_ready': (ROOT / 'app/static/comparison/side-by-side.mp4').is_file(), 'avatars': avatars, 'models': models, 'speakers': speakers, 'engines': [{'id': 'wav2lip', 'name': 'Wav2Lip256', 'ready': True}, {'id': 'musetalk', 'name': 'MuseTalk 1.5', 'ready': muse_installed()}], 'jobs': jobs}

@router.get('/avatars/{avatar_id}/thumbnail')
async def thumbnail(avatar_id: str):
    frames = sorted((safe_avatar(avatar_id) / 'full_imgs').glob('*.png'))
    if not frames:
        raise HTTPException(404, '未找到人物')
    return FileResponse(frames[0])

@router.post('/models/test')
async def test_model(payload: dict):
    kind = payload.get('kind')
    if kind not in ('llm', 'asr', 'tts', 'comfyui'):
        raise HTTPException(400, '无效服务')
    config = read_settings()
    try:
        if kind == 'comfyui':
            endpoint, headers, route = config['comfyui_url'], {}, '/system_stats'
        elif config[kind + '_provider'] == 'local':
            if kind == 'llm':
                endpoint, headers, route = f'http://127.0.0.1:{config["llm_port"]}/v1', {}, '/models'
            else:
                path = ROOT / config[kind + '_model']
                return {'ok': path.is_dir(), 'message': '本地模型目录已找到；推理是否就绪请查看控制台状态'}
        else:
            endpoint, headers, route = config[kind + '_base_url'], auth(kind), '/models'
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            response = await client.get(endpoint + route, headers=headers)
        return {'ok': response.is_success, 'message': '连接成功（仅验证服务可达，不代表完成计费推理）' if response.is_success else f'服务返回 HTTP {response.status_code}；部分语音接口不支持模型列表，仍需试听/转写验证'}
    except Exception:
        return {'ok': False, 'message': '连接失败，请检查已保存的地址、密钥和网络；详细密钥不会出现在日志中'}

async def run_media(job_id, path):
    jobs[job_id].update(status='processing', progress=5)
    log = ROOT / 'logs' / f'import-{job_id}.log'
    try:
        with log.open('w', encoding='utf-8') as output:
            process = await asyncio.create_subprocess_exec(sys.executable, '-X', 'utf8', str(ROOT / 'app/media_worker.py'), str(path), job_id, stdout=output, stderr=output, cwd=ROOT)
            jobs[job_id]['pid'] = process.pid
            result = await process.wait()
        if result:
            raise RuntimeError('人物预处理失败，请查看该任务日志。需清晰的单人正面视频。')
        jobs[job_id].update(status='complete', progress=100, avatar_id=job_id)
    except Exception as error:
        jobs[job_id].update(status='failed', error=str(error))

@router.post('/assets/import')
async def import_asset(kind: str, file: UploadFile = File(...)):
    allowed = {'video': {'.mp4', '.mov', '.mkv', '.avi'}, 'voice': {'.wav', '.mp3', '.m4a', '.flac'}}
    suffix = Path(file.filename or '').suffix.lower()
    if kind not in allowed or suffix not in allowed[kind]:
        raise HTTPException(400, '不支持的素材类型')
    folder = ROOT / 'assets' / ('videos' if kind == 'video' else 'voices')
    folder.mkdir(parents=True, exist_ok=True)
    identifier = 'avatar_' + uuid.uuid4().hex[:12] if kind == 'video' else 'voice_' + uuid.uuid4().hex[:12]
    target = folder / (identifier + suffix)
    size = 0
    try:
        with target.open('wb') as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > (300 if kind == 'video' else 30) * 1024 * 1024:
                    raise HTTPException(413, '素材超过大小限制')
                output.write(chunk)
        if kind == 'video':
            jobs[identifier] = {'status': 'queued', 'progress': 0, 'name': Path(file.filename).name}
            asyncio.create_task(run_media(identifier, target))
        return {'path': target.relative_to(ROOT).as_posix(), 'job': identifier if kind == 'video' else None}
    except Exception:
        target.unlink(missing_ok=True)
        raise

@router.get('/jobs')
async def get_jobs():
    return jobs
