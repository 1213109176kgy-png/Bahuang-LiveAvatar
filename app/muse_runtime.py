"""MuseTalk 1.5 loader: keep full precision checkpoints on CPU, load GPU in FP16."""
from pathlib import Path
import json
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
def load_model():
    import torch
    from diffusers import UNet2DConditionModel
    from avatars.musetalk.models.vae import VAE
    from avatars.musetalk.models.unet import PositionalEncoding
    from avatars.musetalk.whisper.audio2feature import Audio2Feature
    base=ROOT/'sources/LiveTalking/models'
    device=torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    dtype=torch.float16 if device.type=='cuda' else torch.float32
    if device.type=='cuda':torch.backends.cudnn.benchmark=True
    vae=VAE(str(base/'sd-vae'),use_float16=device.type=='cuda')
    vae.vae=vae.vae.to(memory_format=torch.channels_last)
    config=json.loads((base/'musetalkV15/musetalk.json').read_text())
    net=UNet2DConditionModel(**config).to(dtype=dtype)
    weights=torch.load(base/'musetalkV15/unet.pth',map_location='cpu',weights_only=True,mmap=True)
    net.load_state_dict(weights);del weights
    net=net.to(device=device,memory_format=torch.channels_last).eval()
    unet=SimpleNamespace(model=net,device=device)
    pe=PositionalEncoding(d_model=384).to(device=device,dtype=dtype)
    processor=Audio2Feature(model_path=str(base/'whisper'))
    return vae,unet,pe,torch.tensor([0],device=device),processor
