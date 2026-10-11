"""Launch upstream LiveTalking with an optional, reversible edge blend."""
from pathlib import Path
import runpy
import sys
import cv2
import numpy as np
from app.settings import read_settings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sources/LiveTalking'))
from avatars.wav2lip_avatar import LipReal

settings = read_settings()
if settings['avatar_engine'] == 'musetalk':
    import avatars.musetalk_avatar as muse
    from app.muse_assets import load
    from app.muse_runtime import load_model
    muse.load_avatar = load
    muse.load_model = load_model
if settings['avatar_engine'] == 'wav2lip' and settings['avatar_blend_mode'] == 'feather':
    def paste_back_frame(self, pred_frame, idx):
        y1, y2, x1, x2 = self.coord_list_cycle[idx]
        frame = self.frame_list_cycle[idx].copy()
        height, width = y2-y1, x2-x1
        generated = cv2.resize(pred_frame.astype(np.uint8), (width, height))
        edge = max(1, round(min(width, height) * settings['avatar_feather']))
        yy, xx = np.mgrid[:height, :width]
        distance = np.minimum(np.minimum(xx, width-1-xx), np.minimum(yy, height-1-yy))
        alpha = np.clip(distance.astype(np.float32)/edge, 0, 1)[..., None]
        original = frame[y1:y2, x1:x2]
        frame[y1:y2, x1:x2] = np.round(generated*alpha + original*(1-alpha)).astype(np.uint8)
        return frame
    LipReal.paste_back_frame = paste_back_frame

runpy.run_path(str(ROOT / 'sources/LiveTalking/app.py'), run_name='__main__')
