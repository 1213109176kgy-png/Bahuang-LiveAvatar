# 八荒实时数字人 v0.3.0

Windows 免费开源版：视频通话界面、3 秒拨打动画、自动开启麦克风、通话时长、挂断与全屏；支持人物底片管理、预设音色、参考录音克隆，以及本地和在线对话/ASR/TTS 配置。

## 下载与启动

1. 下载全部 `Bahuang-LiveAvatar-Windows-v0.3.0.zip.001` 等分卷，以及 `合并整合包.cmd`、`Merge-Package.ps1`、`release-manifest.json`，放到同一文件夹。
2. 双击“合并整合包.cmd”，自动校验、合并，再解压 ZIP。
3. 双击“数字人工作台.exe”。首次启动按提示从 LiveTalking 官方渠道获取并导入 Wav2Lip256 权重。
4. 等服务就绪，点击“视频通话”，允许麦克风访问，开始与小爱交流。

已包含 Python、Electron、本地 Qwen3 对话模型、Faster-Whisper、Qwen3-TTS CustomVoice 和 Base 模型。公开版不附带授权不明确的 Wav2Lip256 权重，也不包含 MuseTalk 权重。运行本地模型需要合适的 NVIDIA 显卡和驱动；本机验证为 RTX 4060 Laptop 8GB。口型自然度取决于底片、模型与裁切，并非真人视频质量保证。

不会附带本机 API 密钥、参考录音或聊天日志。在线服务需填自己的接口与密钥。完整说明、许可证和作者二维码见仓库中文 README。

老K · 深圳市八荒科技有限公司——开源精神，永不言败
