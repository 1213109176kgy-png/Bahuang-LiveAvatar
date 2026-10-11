"""Validated portable settings and a separate credential store."""
import base64
import ctypes
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse
from pydantic import BaseModel, Field, ConfigDict, field_validator

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'config/local.json'

def available_avatar():
    folder = ROOT / 'sources/LiveTalking/data/avatars'
    return next((item.name for item in sorted(folder.iterdir()) if (item / 'coords.pkl').is_file()), '') if folder.exists() else ''

class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role_name: str = Field(default='小雅', min_length=1, max_length=32)
    system_prompt: str = Field(default='你叫小雅，是一位自然亲切的数字人。用中文口语简洁回答，不要编造事实。', max_length=12000)
    avatar_id: str = Field(default_factory=available_avatar)
    default_avatar_id: str = ''
    backup_avatar_id: str = ''
    avatar_blend_mode: str = 'feather'
    avatar_feather: float = Field(default=0.08, ge=0.02, le=0.2)
    avatar_batch_size: int = Field(default=4, ge=1, le=16)
    avatar_engine: str = 'wav2lip'
    llm_provider: str = 'local'
    llm_model: str = 'qwen3-4b'
    llm_remote_model: str = 'deepseek-chat'
    llm_model_path: str = 'models/Qwen3-4B-Q4_K_M.gguf'
    llm_base_url: str = 'https://api.deepseek.com/v1'
    llm_port: int = Field(default=8090, ge=1024, le=65535)
    llm_context: int = Field(default=2048, ge=512, le=8192)
    llm_gpu_layers: int = Field(default=99, ge=0, le=99)
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_reply_tokens: int = Field(default=96, ge=16, le=1024)
    history_turns: int = Field(default=4, ge=0, le=20)
    asr_provider: str = 'local'
    asr_model: str = 'models/faster-whisper-small'
    asr_device: str = 'cpu'
    asr_compute_type: str = 'int8'
    asr_language: str = 'zh'
    asr_base_url: str = 'https://api.openai.com/v1'
    asr_remote_model: str = 'whisper-1'
    tts_provider: str = 'local'
    tts_model: str = 'models/qwen3-tts-0.6b'
    tts_mode: str = 'custom'
    tts_clone_engine: str = 'official'
    tts_speaker: str = 'Vivian'
    tts_language: str = 'Chinese'
    tts_ref_audio: str = ''
    tts_ref_text: str = ''
    tts_base_url: str = 'https://api.openai.com/v1'
    tts_remote_model: str = 'tts-1'
    tts_remote_voice: str = 'alloy'
    tts_speed: float = Field(default=1, ge=0.25, le=4)
    tts_streaming: bool = True
    tts_acceleration: bool = True
    avatar_port: int = Field(default=8010, ge=1024, le=65535)
    web_port: int = Field(default=7860, ge=1024, le=65535)
    vad_silence: float = Field(default=0.8, ge=0.3, le=3)
    vad_threshold: float = Field(default=0.015, ge=0.001, le=0.2)
    microphone_device: str = ''
    speaker_device: str = ''
    comfyui_url: str = 'http://127.0.0.1:8188'

    @field_validator('avatar_id', 'default_avatar_id', 'backup_avatar_id')
    @classmethod
    def valid_id(cls, value, info):
        if not value:
            if info.field_name == 'avatar_id':
                raise ValueError('人物编号不能为空')
            return value
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', value):
            raise ValueError('形象编号只能包含字母、数字、下划线和短横线')
        return value

    @field_validator('avatar_blend_mode')
    @classmethod
    def blend_mode(cls, value):
        if value not in ('hard', 'feather'):
            raise ValueError('不支持的融合方式')
        return value

    @field_validator('llm_provider', 'asr_provider', 'tts_provider')
    @classmethod
    def provider(cls, value):
        if value not in ('local', 'openai'):
            raise ValueError('仅支持本地或 OpenAI 兼容接口')
        return value

    @field_validator('llm_base_url', 'asr_base_url', 'tts_base_url', 'comfyui_url')
    @classmethod
    def endpoint(cls, value):
        parsed = urlparse(value)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('接口地址不要包含密钥、查询参数或用户名密码')
        if not parsed.hostname or parsed.scheme not in ('http', 'https'):
            raise ValueError('需要完整 HTTP(S) 接口地址')
        if parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
            raise ValueError('远程接口必须使用 HTTPS')
        return value.rstrip('/')

    @field_validator('tts_mode')
    @classmethod
    def mode(cls, value):
        if value not in ('custom', 'clone'):
            raise ValueError('不支持的声音模式')
        return value

    @field_validator('tts_clone_engine')
    @classmethod
    def clone_engine(cls, value):
        if value not in ('official', 'accelerated'):
            raise ValueError('无效克隆合成路径')
        return value

    @field_validator('asr_device')
    @classmethod
    def device(cls, value):
        if value not in ('cpu', 'cuda'):
            raise ValueError('设备必须为 cpu 或 cuda')
        return value

    @field_validator('asr_compute_type')
    @classmethod
    def precision(cls, value):
        if value not in ('int8', 'float16', 'float32', 'int8_float16'):
            raise ValueError('不支持的 ASR 精度')
        return value

    @field_validator('avatar_engine')
    @classmethod
    def engine(cls, value):
        if value not in ('wav2lip', 'musetalk'):
            raise ValueError('只支持 Wav2Lip256 / MuseTalk 1.5')
        return value

RESTART = {'avatar_blend_mode', 'avatar_feather', 'llm_provider', 'llm_model', 'llm_model_path', 'llm_context', 'llm_gpu_layers', 'llm_port', 'avatar_port', 'web_port', 'avatar_batch_size', 'tts_model', 'tts_mode', 'tts_provider', 'tts_acceleration', 'asr_model', 'asr_device', 'asr_compute_type', 'asr_provider'}
RESTART.add('avatar_engine')

def read_settings():
    return Settings.model_validate(json.loads(PATH.read_text(encoding='utf-8-sig'))).model_dump()

def save_settings(values):
    current = read_settings()
    proposed = Settings.model_validate({**current, **values}).model_dump()
    if len({proposed['llm_port'], proposed['avatar_port'], proposed['web_port']}) != 3:
        raise ValueError('三个服务端口不能重复')
    if proposed['asr_device'] == 'cpu' and proposed['asr_compute_type'] in ('float16', 'int8_float16'):
        raise ValueError('CPU 识别请选择 int8 或 float32')
    for field in ('llm_model_path', 'asr_model', 'tts_model'):
        if proposed[field] != current[field] and not (ROOT / proposed[field]).exists():
            raise ValueError(f'{field} 对应的本地模型不存在')
    if proposed['tts_mode'] == 'clone' and proposed['tts_provider'] == 'local':
        model = json.loads((ROOT / proposed['tts_model'] / 'config.json').read_text(encoding='utf-8'))
        if model.get('tts_model_type') != 'base':
            raise ValueError('声音克隆需要 Qwen3-TTS Base 模型，请先导入对应权重')
        if not all((ROOT / proposed['tts_model'] / part).is_file() for part in ('model.safetensors', 'speech_tokenizer/model.safetensors')):
            raise ValueError('Base 克隆模型尚未下载完整，请等待下载完成后再保存')
        if not proposed['tts_ref_audio'] or not (ROOT / proposed['tts_ref_audio']).is_file():
            raise ValueError('声音克隆需要有效参考录音')
    for identifier in (proposed['avatar_id'], proposed['default_avatar_id'], proposed['backup_avatar_id']):
        if identifier:
            avatar = ROOT / 'sources/LiveTalking/data/avatars' / identifier
            if not (avatar / 'coords.pkl').is_file() or not (avatar / 'full_imgs').is_dir():
                raise ValueError('人物底片不存在或尚未完成预处理')
    if proposed['avatar_engine'] == 'musetalk' and not (ROOT / 'sources/LiveTalking/data/avatars' / proposed['avatar_id'] / 'musetalk/ready.json').is_file():
        raise ValueError('此人物尚未预处理 MuseTalk 1.5，请在真人口型配置中先执行预处理')
    PATH.with_suffix('.previous.json').write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary = PATH.with_suffix('.tmp')
    temporary.write_text(json.dumps(proposed, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(PATH)
    return proposed, sorted(k for k in RESTART if current[k] != proposed[k])

class Blob(ctypes.Structure):
    _fields_ = [('size', ctypes.c_ulong), ('data', ctypes.POINTER(ctypes.c_ubyte))]

def dpapi(value, decrypt=False):
    buffer = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
    source, result = Blob(len(value), buffer), Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        ctypes.WinDLL('kernel32').LocalFree(result.data)

def credentials():
    filename = ROOT / 'config' / ('credentials.dpapi' if os.name == 'nt' else 'credentials.private.json')
    if not filename.exists():
        return {}
    raw = filename.read_bytes()
    if os.name == 'nt':
        raw = dpapi(raw, decrypt=True)
    return json.loads(raw)

def save_credentials(values):
    if set(values) - {'llm', 'asr', 'tts'}:
        raise ValueError('未知凭据类型')
    if any(value is not None and not isinstance(value, str) for value in values.values()):
        raise ValueError('密钥必须是文本')
    stored = credentials()
    for key, value in values.items():
        if value is None:
            stored.pop(key, None)
        elif value.strip():
            stored[key] = value.strip()
    filename = ROOT / 'config' / ('credentials.dpapi' if os.name == 'nt' else 'credentials.private.json')
    raw = json.dumps(stored).encode('utf-8')
    filename.write_bytes(dpapi(raw) if os.name == 'nt' else raw)
    if os.name != 'nt':
        filename.chmod(0o600)

def auth(kind):
    token = credentials().get(kind)
    if not token:
        raise ValueError('请在模型配置中填写并保存此服务的 API Key')
    return {'Authorization': 'Bearer ' + token}
