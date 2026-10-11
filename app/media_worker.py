"""Build a real animated Wav2Lip avatar from a bounded 25fps video."""
import os
os.environ['CUDA_VISIBLE_DEVICES'] = ''
os.environ['OMP_NUM_THREADS'] = '4'
from pathlib import Path
import subprocess
import sys
import cv2
import imageio_ffmpeg
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'sources/LiveTalking'))
source, identifier = sys.argv[1:3]
video = cv2.VideoCapture(source)
count, fps = video.get(cv2.CAP_PROP_FRAME_COUNT), video.get(cv2.CAP_PROP_FPS)
video.release()
if not fps or count < 10 or count / fps > 30:
    raise ValueError('请使用 1–30 秒的有效单人正面视频')
normalized = ROOT / 'assets/videos' / (identifier + '-25fps.mp4')
subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-i', source, '-an', '-vf', "scale='min(768,iw)':-2,fps=25", '-c:v', 'libx264', '-crf', '20', str(normalized)], check=True)
from avatars.wav2lip.genavatar import generate_avatar
from avatars.wav2lip import face_detection
video = cv2.VideoCapture(str(normalized))
ok, frame = video.read()
video.release()
detector = face_detection.FaceAlignment(face_detection.LandmarksType._2D, flip_input=False, device='cpu')
if not ok or detector.get_detections_for_batch(frame[None])[0] is None:
    raise ValueError('底片首帧没有检测到清晰人脸')
del detector
generate_avatar(str(normalized), identifier, save_path=str(ROOT / 'sources/LiveTalking/data/avatars'), img_size=256, face_det_batch_size=2)
print('Avatar ready: ' + identifier)
