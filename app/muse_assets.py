"""Prepare MuseTalk V1.5 latents and official face parsing masks for an existing avatar."""
from pathlib import Path
import os,sys,json,pickle
ROOT=Path(__file__).resolve().parents[1]
def prepare(identifier, cpu=False):
    if cpu:os.environ['CUDA_VISIBLE_DEVICES']=''
    import cv2,torch
    torch.set_num_threads(4)
    sys.path.insert(0,str(ROOT/'sources/LiveTalking'))
    sys.path.insert(0,str(ROOT))
    from avatars.musetalk.models.vae import VAE
    from avatars.musetalk.utils.blending import get_image_prepare_material
    from app.vendor.muse_face_parsing import FaceParsing
    base=ROOT/'sources/LiveTalking/data/avatars'/identifier
    assert base.resolve().is_relative_to((ROOT/'sources/LiveTalking/data/avatars').resolve())
    out=base/'musetalk';out.mkdir(exist_ok=True);(out/'mask').mkdir(exist_ok=True)
    frames=sorted((base/'full_imgs').glob('*.png'))
    coords=pickle.loads((base/'coords.pkl').read_bytes())
    old=os.getcwd();os.chdir(ROOT/'sources/LiveTalking')
    try:
        vae=VAE(str(ROOT/'sources/LiveTalking/models/sd-vae'),use_float16=not cpu)
        fp=FaceParsing(left_cheek_width=90,right_cheek_width=90)
        latents=[];boxes=[];crops=[]
        with torch.inference_mode():
            torch.manual_seed(42)
            for i,(file,coord) in enumerate(zip(frames,coords)):
                frame=cv2.imread(str(file));y1,y2,x1,x2=map(int,coord);box=[x1,y1,x2,y2]
                face=cv2.resize(frame[y1:y2,x1:x2],(256,256),interpolation=cv2.INTER_LANCZOS4)
                latents.append(vae.get_latents_for_unet(face).cpu())
                mask,crop=get_image_prepare_material(frame,box,fp=fp,mode='jaw')
                assert 0<=crop[0]<crop[2]<=frame.shape[1] and 0<=crop[1]<crop[3]<=frame.shape[0],crop
                cv2.imwrite(str(out/'mask'/f'{i:08d}.png'),mask)
                boxes.append(box);crops.append(crop)
                if i%20==0:print(f'MuseTalk avatar preparation: {i}/{len(frames)}',flush=True)
        torch.save(latents,out/'latents.pt')
        (out/'coords.pkl').write_bytes(pickle.dumps(boxes));(out/'mask_coords.pkl').write_bytes(pickle.dumps(crops))
        (out/'ready.json').write_text(json.dumps({'engine':'musetalk','version':'1.5','frames':len(frames),'source_avatar':identifier,'face_parsing':'official jaw mask','bbox':'existing SFD face box; same video frames as Wav2Lip'},indent=2),encoding='utf-8')
    finally:os.chdir(old)
    print('MuseTalk avatar prepared: '+identifier,flush=True)

def load(identifier):
    import cv2,torch
    base=ROOT/'sources/LiveTalking/data/avatars'/identifier;out=base/'musetalk'
    if not (out/'ready.json').is_file():raise RuntimeError('此形象尚未生成 MuseTalk 数据，请先预处理')
    frames=[cv2.imread(str(p)) for p in sorted((base/'full_imgs').glob('*.png'))]
    masks=[cv2.imread(str(p)) for p in sorted((out/'mask').glob('*.png'))]
    latents=torch.load(out/'latents.pt',map_location='cpu',weights_only=True)
    latents=[item.to('cuda' if torch.cuda.is_available() else 'cpu') for item in latents]
    return frames,masks,pickle.loads((out/'coords.pkl').read_bytes()),pickle.loads((out/'mask_coords.pkl').read_bytes()),latents

if __name__=='__main__':prepare(sys.argv[1],cpu='--cpu' in sys.argv)
