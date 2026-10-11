"""Owned local voice bridge: Faster Whisper -> llama.cpp -> Qwen3-TTS -> LiveTalking."""
import asyncio
import base64
from contextlib import asynccontextmanager
import io
import json
import logging
import os
from pathlib import Path
import re
import sys
import time
from collections import OrderedDict
from urllib.parse import urlparse

import httpx
import numpy as np
import soundfile as sf
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from scipy.signal import resample_poly
from .settings import read_settings, auth
from .config_api import router as config_router

ROOT = Path(__file__).resolve().parents[1]
CONFIG = read_settings()
sys.path.insert(0, str(ROOT / 'sources/Qwen3-TTS'))
sys.path.insert(0, str(ROOT / 'sources/faster-qwen3-tts-0.2.6'))
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('livegirl')
avatar_url = f'http://127.0.0.1:{CONFIG["avatar_port"]}'
llm_url = os.environ.get('LIVEGIRL_LLM_URL', 'http://127.0.0.1:8090/v1')
state = {'ready': False, 'error': None, 'tts': None, 'asr': None}
inference_lock = asyncio.Lock()
voice_preview_cache = OrderedDict()

def load_models():
    import torch
    from faster_whisper import WhisperModel
    from faster_qwen3_tts import FasterQwen3TTS
    torch.set_num_threads(4)
    if CONFIG['asr_provider'] == 'local':
        state['asr'] = WhisperModel(str(ROOT / CONFIG['asr_model']), device=CONFIG['asr_device'], compute_type=CONFIG['asr_compute_type'], cpu_threads=4)
    if CONFIG['tts_provider'] != 'local':
        state['ready'] = True
        return
    if not torch.cuda.is_available():
        raise RuntimeError('本地 Qwen3-TTS 需要可用的 NVIDIA GPU；也可以在模型配置中选择在线 TTS')
    model_path = ROOT / CONFIG['tts_model']
    if CONFIG['tts_acceleration']:
        model_path = Path(os.environ.get('LIVEGIRL_TTS_MODEL', str(model_path)))
    if CONFIG['tts_acceleration']:
        state['tts'] = FasterQwen3TTS.from_pretrained(str(model_path), device='cuda:0', dtype=torch.bfloat16, attn_implementation='sdpa', max_seq_len=1024)
        state['tts']._warmup(prefill_len=100)
    else:
        from qwen_tts import Qwen3TTSModel
        state['tts'] = Qwen3TTSModel.from_pretrained(str(model_path), device_map='cuda:0', dtype=torch.bfloat16, attn_implementation='sdpa')
    # Prepare the codec's first streaming decode before showing the service as ready.
    if CONFIG['tts_acceleration'] and CONFIG['tts_mode'] == 'custom':
        for _ in state['tts'].generate_custom_voice_streaming(text='你好。', language=CONFIG['tts_language'], speaker=CONFIG['tts_speaker'], max_new_tokens=64, do_sample=False, chunk_size=12):
            pass
    state['ready'] = True
    state['tts_model_path'] = str(model_path)
    state['tts_mode'] = CONFIG['tts_mode']
    wrapped = getattr(state['tts'], 'model', state['tts'])
    state['tts_model_type'] = getattr(getattr(wrapped, 'model', wrapped), 'config', None).tts_model_type
    log.info('Local ASR and Qwen3-TTS are loaded and warmed up')

@asynccontextmanager
async def lifespan(app):
    async def load():
        try:
            await asyncio.to_thread(load_models)
        except Exception as error:
            state['error'] = str(error)
            log.exception('Model loading failed')
    task = asyncio.create_task(load())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)
app.include_router(config_router)
app.mount('/static', StaticFiles(directory=ROOT / 'app/static'), name='static')

@app.get('/')
async def index():
    return FileResponse(ROOT / 'app/static/workbench.html')

@app.get('/api/status')
async def status():
    import torch
    services = {}
    async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
        for name, url in [('llm', llm_url + '/models'), ('avatar', avatar_url + '/index.html')]:
            if name == 'llm' and CONFIG['llm_provider'] != 'local':
                from .settings import credentials
                services[name] = bool(credentials().get('llm'))
                continue
            try:
                services[name] = (await client.get(url)).status_code == 200
            except httpx.HTTPError:
                services[name] = False
    return {'ready': state['ready'], 'error': state['error'], 'services': services, 'cuda': torch.cuda.is_available(), 'runtime': 'Windows 原生' if os.name == 'nt' else 'WSL', 'config': {k: CONFIG[k] for k in ['avatar_id', 'tts_speaker', 'tts_mode', 'tts_provider', 'tts_model', 'tts_ref_audio', 'asr_device', 'role_name']}, 'voice': voice_route(), 'last_voice': state.get('last_voice')}

def voice_route():
    return {'provider': CONFIG['tts_provider'], 'mode': CONFIG['tts_mode'], 'model': CONFIG['tts_model'], 'loaded_model': state.get('tts_model_path'), 'loaded_type': state.get('tts_model_type'), 'reference': CONFIG['tts_ref_audio'] if CONFIG['tts_mode'] == 'clone' else '', 'speaker': CONFIG['tts_speaker'] if CONFIG['tts_mode'] == 'custom' else None, 'engine': CONFIG['tts_clone_engine'] if CONFIG['tts_mode'] == 'clone' else 'preset'}

def record_voice_route():
    state['last_voice'] = voice_route()
    (ROOT / 'logs/last-voice-route.json').write_text(json.dumps(state['last_voice'], ensure_ascii=False, indent=2), encoding='utf-8')

@app.post('/api/avatar/offer')
async def offer(payload: dict):
    payload['avatar'] = CONFIG['avatar_id']
    async with httpx.AsyncClient(timeout=45, trust_env=False) as client:
        response = await client.post(avatar_url + '/offer', json=payload)
        response.raise_for_status()
        return response.json()

@app.post('/api/avatar/interrupt')
async def interrupt(payload: dict):
    async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
        return (await client.post(avatar_url + '/interrupt_talk', json=payload)).json()

def transcribe(audio: bytes):
    if CONFIG['asr_provider'] != 'local':
        with httpx.Client(timeout=120, trust_env=False) as client:
            response = client.post(CONFIG['asr_base_url'] + '/audio/transcriptions', headers=auth('asr'), data={'model': CONFIG['asr_remote_model'], 'language': CONFIG['asr_language']}, files={'file': ('input.wav', audio, 'audio/wav')})
        if not response.is_success:
            raise RuntimeError(f'在线语音识别返回 HTTP {response.status_code}')
        return response.json().get('text', '').strip()
    samples, sr = sf.read(io.BytesIO(audio), dtype='float32')
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    if sr != 16000:
        import math
        common = math.gcd(sr, 16000)
        samples = resample_poly(samples, 16000 // common, sr // common).astype(np.float32)
    if len(samples) > 16000 * 45:
        raise ValueError('Audio exceeds 45 seconds')
    segments, _ = state['asr'].transcribe(samples, language=CONFIG['asr_language'] or None, beam_size=1, vad_filter=True)
    return ''.join(part.text for part in segments).strip()

def synthesize(text: str):
    record_voice_route()
    if CONFIG['tts_provider'] != 'local':
        with httpx.Client(timeout=120, trust_env=False) as client:
            response = client.post(CONFIG['tts_base_url'] + '/audio/speech', headers=auth('tts'), json={'model': CONFIG['tts_remote_model'], 'input': text, 'voice': CONFIG['tts_remote_voice'], 'speed': CONFIG['tts_speed'], 'response_format': 'wav'})
        if not response.is_success:
            raise RuntimeError(f'在线语音合成返回 HTTP {response.status_code}')
        samples, sample_rate = sf.read(io.BytesIO(response.content), dtype='float32')
        if samples.ndim > 1: samples = samples.mean(axis=1)
    else:
        if state.get('tts_model_path') != str(ROOT / CONFIG['tts_model']) or state.get('tts_mode') != CONFIG['tts_mode']:
            raise RuntimeError('声音模型或模式已改变，请先重启服务再试听或对话')
        engine = state['tts']
        if CONFIG['tts_mode'] == 'clone' and CONFIG['tts_clone_engine'] == 'official' and hasattr(engine, 'talker_graph'):
            engine = engine.model
        function = engine.generate_voice_clone if CONFIG['tts_mode'] == 'clone' else engine.generate_custom_voice
        extra = {'ref_audio': str(ROOT / CONFIG['tts_ref_audio']), 'ref_text': CONFIG['tts_ref_text']} if CONFIG['tts_mode'] == 'clone' else {'speaker': CONFIG['tts_speaker']}
        wavs, sample_rate = function(text=text, language=CONFIG['tts_language'], non_streaming_mode=True, max_new_tokens=512, do_sample=False, **extra)
        samples = wavs[0]
    import math
    common = math.gcd(sample_rate, 16000)
    samples = resample_poly(samples, 16000 // common, sample_rate // common)
    output = io.BytesIO()
    sf.write(output, samples, 16000, format='WAV', subtype='PCM_16')
    return output.getvalue(), len(samples) / 16000

def stream_to_avatar(text, session_id, is_current):
    """Send PCM chunks as they arrive, preserving LiveTalking's existing audio queue."""
    started = time.perf_counter()
    first = None
    duration = 0.0
    record_voice_route()
    if CONFIG['tts_provider'] == 'local' and (state.get('tts_model_path') != str(ROOT / CONFIG['tts_model']) or state.get('tts_mode') != CONFIG['tts_mode']):
        raise RuntimeError('声音模型或模式已改变，请先重启服务再试听或对话')
    import math
    with httpx.Client(timeout=30, trust_env=False) as client:
        if CONFIG['tts_provider'] != 'local' or (CONFIG['tts_mode'] == 'clone' and CONFIG['tts_clone_engine'] == 'official') or not CONFIG['tts_streaming'] or not CONFIG['tts_acceleration'] or not hasattr(state['tts'], 'generate_voice_clone_streaming' if CONFIG['tts_mode'] == 'clone' else 'generate_custom_voice_streaming'):
            audio, duration = synthesize(text)
            if is_current():
                response = client.post(avatar_url + '/humanaudio', data={'sessionid': session_id}, files={'file': ('reply.wav', audio, 'audio/wav')})
                response.raise_for_status()
                if response.json().get('code') != 0: raise RuntimeError('数字人音频发送失败')
            return duration, time.perf_counter() - started
        extra = {'ref_audio': str(ROOT / CONFIG['tts_ref_audio']), 'ref_text': CONFIG['tts_ref_text']} if CONFIG['tts_mode'] == 'clone' else {'speaker': CONFIG['tts_speaker']}
        function = state['tts'].generate_voice_clone_streaming if CONFIG['tts_mode'] == 'clone' else state['tts'].generate_custom_voice_streaming
        for samples, sr, _ in function(
            text=text, language=CONFIG['tts_language'], **extra,
            non_streaming_mode=True, max_new_tokens=512, do_sample=False, chunk_size=12
        ):
            if not is_current():
                break
            if len(samples) == 0:
                continue
            common = math.gcd(sr, 16000)
            samples = resample_poly(samples, 16000 // common, sr // common)
            output = io.BytesIO()
            sf.write(output, samples, 16000, format='WAV', subtype='PCM_16')
            response = client.post(avatar_url + '/humanaudio', data={'sessionid': session_id}, files={'file': ('chunk.wav', output.getvalue(), 'audio/wav')})
            response.raise_for_status()
            result = response.json()
            if result.get('code') != 0:
                raise RuntimeError(result.get('msg', '数字人音频发送失败'))
            first = first if first is not None else time.perf_counter() - started
            duration += len(samples) / 16000
    return duration, first

@app.post('/api/test/tts')
async def test_tts(payload: dict):
    if not state['ready']:
        raise HTTPException(503, state['error'] or 'Models are loading')
    async with inference_lock:
        audio, duration = await asyncio.to_thread(synthesize, str(payload.get('text', '你好，我是小雅，很高兴见到你。'))[:100])
    (ROOT / 'logs/tts-test.wav').write_bytes(audio)
    return Response(audio, media_type='audio/wav', headers={'X-Audio-Duration': str(duration)})

@app.post('/api/test/asr')
async def test_asr(request: Request):
    if not state['ready']:
        raise HTTPException(503, state['error'] or 'Models are loading')
    audio = await request.body()
    if len(audio) > 4 * 1024 * 1024:
        raise HTTPException(413, 'Test audio is too large')
    start = time.perf_counter()
    async with inference_lock:
        text = await asyncio.to_thread(transcribe, audio)
    return {'text': text, 'seconds': round(time.perf_counter() - start, 2)}

@app.post('/api/voices/preview')
async def preview_preset(payload: dict):
    model = state.get('tts')
    if not state['ready'] or model is None:
        raise HTTPException(409, '请先加载本地 CustomVoice 模型；切换模型后需保存并重启服务')
    base = getattr(model, 'model', None)
    if not hasattr(base, 'get_supported_speakers'):
        base = model
    speakers = base.get_supported_speakers() or []
    speaker = payload.get('speaker', '')
    language = payload.get('language', 'Chinese')
    if not isinstance(speaker, str) or speaker.lower() not in {name.lower() for name in speakers}:
        raise HTTPException(400, '当前加载模型不支持此预设音色；请确认使用 CustomVoice 并已重启')
    if language not in (base.get_supported_languages() or []):
        # Official language names may be returned in lower case.
        if not isinstance(language, str) or language.lower() not in {name.lower() for name in (base.get_supported_languages() or [])}:
            raise HTTPException(400, '不支持此合成语言')
    key = (state.get('tts_model_path'), speaker.lower(), language.lower())
    async with inference_lock:
        if key not in voice_preview_cache:
            def generate():
                wavs, sr = model.generate_custom_voice(text='你好，很高兴认识你。欢迎来到我的直播间。', speaker=speaker, language=language, non_streaming_mode=True, max_new_tokens=256, do_sample=False)
                output = io.BytesIO()
                sf.write(output, wavs[0], sr, format='WAV', subtype='PCM_16')
                return output.getvalue()
            try:
                voice_preview_cache[key] = await asyncio.to_thread(generate)
            except Exception:
                raise HTTPException(500, '试听生成失败，请检查当前本地模型及运行日志') from None
            if len(voice_preview_cache) > 24:
                voice_preview_cache.popitem(last=False)
        voice_preview_cache.move_to_end(key)
        audio = voice_preview_cache[key]
    return Response(audio, media_type='audio/wav', headers={'Cache-Control': 'no-store'})

@app.websocket('/api/chat')
async def chat(websocket: WebSocket):
    await websocket.accept()
    history = []
    current_task = None
    turn = 0
    session_id = ''

    async def run_turn(message, my_turn):
        started = time.perf_counter()
        try:
            if not state['ready']:
                raise RuntimeError(state['error'] or '语音模型还在加载，请稍等')
            async with inference_lock:
                user_text = str(message.get('text', '')).strip()[:500]
                if message.get('audio'):
                    await websocket.send_json({'type': 'phase', 'text': '正在识别语音'})
                    user_text = await asyncio.to_thread(transcribe, base64.b64decode(message['audio'], validate=True))
                if not user_text:
                    await websocket.send_json({'type': 'done', 'empty': True})
                    return
                await websocket.send_json({'type': 'user', 'text': user_text})
                remembered = history[-CONFIG['history_turns'] * 2:] if CONFIG['history_turns'] else []
                messages = [{'role': 'system', 'content': CONFIG['system_prompt']}] + remembered + [{'role': 'user', 'content': user_text}]
                await websocket.send_json({'type': 'phase', 'text': '正在生成回答'})
                async with httpx.AsyncClient(timeout=120, trust_env=False) as client:
                    endpoint = llm_url if CONFIG['llm_provider'] == 'local' else CONFIG['llm_base_url']
                    headers = {} if CONFIG['llm_provider'] == 'local' else auth('llm')
                    request = {'model': CONFIG['llm_model'] if CONFIG['llm_provider']=='local' else CONFIG['llm_remote_model'], 'messages': messages, 'max_tokens': CONFIG['max_reply_tokens'], 'temperature': CONFIG['temperature']}
                    if CONFIG['llm_provider'] == 'local': request['chat_template_kwargs'] = {'enable_thinking': False}
                    elif urlparse(endpoint).hostname == 'api.deepseek.com':
                        # Realtime replies have a small output budget; reasoning would consume it.
                        request['thinking'] = {'type': 'disabled'}
                    response = await client.post(endpoint + '/chat/completions', headers=headers, json=request)
                    if not response.is_success: raise RuntimeError(f'对话模型返回 HTTP {response.status_code}')
                    choice = response.json()['choices'][0]
                    answer = choice.get('message', {}).get('content') or ''
                    answer = re.sub(r'<think>.*?</think>', '', answer, flags=re.S).strip()
                    if not answer:
                        if choice.get('finish_reason') == 'length':
                            raise RuntimeError('对话模型达到输出长度上限，尚未生成正式回答。请关闭模型思考模式或提高回答 token 上限。')
                        raise RuntimeError('对话模型没有返回可朗读的回答，请检查模型是否支持普通文本对话。')
                    await websocket.send_json({'type': 'assistant', 'text': answer})
                    await websocket.send_json({'type': 'phase', 'text': '正在合成声音'})
                    before_tts = time.perf_counter()
                    first_audio = None
                    if session_id:
                        duration, first_audio = await asyncio.to_thread(stream_to_avatar, answer, session_id, lambda: my_turn == turn)
                    else:
                        audio, duration = await asyncio.to_thread(synthesize, answer)
                    if my_turn != turn:
                        return
                    if not session_id:
                        await websocket.send_json({'type': 'audio', 'audio': base64.b64encode(audio).decode()})
                    history.extend([{'role': 'user', 'content': user_text}, {'role': 'assistant', 'content': answer}])
                    total = time.perf_counter() - started
                    first_latency = before_tts - started + first_audio if first_audio is not None else total
                    await websocket.send_json({'type': 'done', 'latency': round(total, 2), 'first_audio_seconds': round(first_latency, 2), 'tts_seconds': round(time.perf_counter() - before_tts, 2), 'audio_seconds': round(duration, 2), 'playback_seconds': round(max(0, duration - (total - first_latency)), 2)})
        except asyncio.CancelledError:
            raise
        except Exception as error:
            log.exception('Conversation failed')
            await websocket.send_json({'type': 'error', 'text': str(error)})

    try:
        while True:
            message = await websocket.receive_json()
            if message.get('type') == 'session':
                session_id = str(message.get('sessionid', ''))
            elif message.get('type') == 'clear':
                turn += 1
                history.clear()
            elif message.get('type') in ['interrupt', 'chat']:
                turn += 1
                # Generation running in a thread is not cancelled mid-kernel. Its audio is discarded.
                if current_task and not current_task.done():
                    await websocket.send_json({'type': 'phase', 'text': '正在结束上一轮生成'})
                    await current_task
                if message.get('type') == 'chat':
                    current_task = asyncio.create_task(run_turn(message, turn))
    except WebSocketDisconnect:
        turn += 1
        if current_task:
            await current_task
