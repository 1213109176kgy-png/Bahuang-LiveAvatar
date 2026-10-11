# 八荒实时数字人 · Bahuang-LiveAvatar

<img src="app/static/brand/company-logo.png" width="88" alt="八荒科技 Logo" />

支持 Windows 本机运行的实时互动数字人工作台。像打视频电话一样，与数字人进行中文语音或文字对话，自由配置形象、声音、角色性格和本地／在线模型。

**免费开源版｜中文界面｜Windows 便携运行｜源码可修改**

[下载整合包](https://github.com/1213109176kgy-png/Bahuang-LiveAvatar/releases/latest) · [使用说明](docs/Windows便携版使用说明.md) · [开发说明](docs/开发说明.md) · [第三方许可](THIRD_PARTY_NOTICES.md)

## 功能

- 视频通话：一键拨打、至少 3 秒拨号动画、连接画面和开启麦克风、通话计时、挂断、全屏。
- 实时互动：语音识别、回答生成、声音合成、实时口型；文字输入、聊天记录、清空和打断。
- 人物管理：导入动态底片，自动预处理；选择、改名、删除，设置默认和备用形象。
- 声音与人设：本地预设试听、Base 参考录音克隆、在线音色、角色提示词和记忆轮数。
- 模型配置：LLM、ASR、TTS 分别选本地或兼容在线接口，支持模型列表获取、连接检测和本地模型导入。
- 口型引擎：默认 Wav2Lip256；MuseTalk 1.5 是需要额外权重和人物预处理的实验选项。

当前没有集成直播弹幕、礼物或一键推流。身体动作来自人物底片，口型引擎不会凭空生成全身动作。

## Windows 整合包使用

1. 到 [Releases](https://github.com/1213109176kgy-png/Bahuang-LiveAvatar/releases/latest) 下载全部同版本分卷及合并脚本，放在同一个文件夹。
2. 对于 `.zip.001` 等分卷，运行 **Merge-Package.cmd**，再解压生成的 ZIP。不能只下载一个分卷，也不要只移动 EXE。
3. 双击 **数字人工作台.exe**。首次会提示导入 **wav2lip256.pth**，请从 [LiveTalking 官方说明](https://github.com/lipku/LiveTalking#2-快速开始) 获取。公开包不附带该权重，避免再分发授权不明的模型文件。
4. 等三个服务就绪后，点击人物画面内的 **视频通话**，允许麦克风权限，拨号完成后开始聊天。
5. “数字人配置”修改人物、声音和角色；“模型配置”填写在线接口、模型及 API Key。提示需要重启时，点击“重启服务”。

包内自带 Python、桌面运行环境及清单所列本地语音／对话模型，无需另装 Python、Node 或 WSL。需要 Windows 10/11 64 位、NVIDIA 显卡及兼容驱动。在线服务需要自己的账户、网络和密钥。

## 技术路线

```text
麦克风 → VAD / Faster Whisper → 本地 Qwen3 或在线 LLM
       → Qwen3-TTS 或在线 TTS → LiveTalking / Wav2Lip256 → WebRTC
```

| 模块 | 默认／可选方案 |
|---|---|
| 对话大脑 | llama.cpp + Qwen3；DeepSeek、豆包等兼容接口 |
| 听懂语音 | Faster Whisper；兼容在线转写 |
| 生成声音 | Qwen3-TTS CustomVoice / Base；兼容在线 TTS |
| 说话口型 | Wav2Lip256；MuseTalk 1.5 实验选项 |
| 人物底片 | 用户导入；可在外部 ComfyUI 等工具制作 |
| 工作台 | 中文页面、配置管理、Electron 启动和语音连接层 |

验证硬件为 **RTX 4060 Laptop 8GB**。Wav2Lip 网页画面可达约 25 帧/秒；MuseTalk 1.5 说话阶段约 15–17 帧/秒，未达到本机实时目标。实际速度、等待时间和画质受硬件、声音模式及底片影响。

## 源码开发

仓库不包含运行时、巨型权重、个人 API Key、参考录音或聊天日志。建议先运行整合包再修改源码。

```powershell
git clone https://github.com/1213109176kgy-png/Bahuang-LiveAvatar.git
cd Bahuang-LiveAvatar
Copy-Item config/local.example.json config/local.json
```

源码 `app/` 对应整合包 `app/`，`desktop/` 对应包内 `resources/app/`。环境准备和更新方法见 [开发说明](docs/开发说明.md)。

## 已知限制与隐私

- 托腮、遮挡、露齿、转头和人脸裁切都会影响口型效果，不承诺达到真人画质。
- 打断会清空播放并丢弃旧回答，正在执行的 GPU 算子需运行结束。
- 在线兼容性取决于实际接口，文字和音频会发送到用户选择的服务商，费用由该服务商决定。
- 服务默认监听本机；API Key 用 Windows DPAPI 加密。详见 [SECURITY.md](SECURITY.md)。

## 开源许可与致谢

自有代码采用 [Apache-2.0](LICENSE)。LiveTalking、Qwen3-TTS、Faster Whisper、llama.cpp、MuseTalk 等保留原始作者和许可证，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。代码许可不替代模型、人物、音色或第三方素材授权。

感谢各上游项目。欢迎提交 Issue、优化建议和 Pull Request。

## 作者与反馈

作者：**老K**  
公司：**深圳市八荒科技有限公司**

欢迎扫码交流使用体验、反馈 bug 和优化建议。

<img src="app/static/brand/wechat-qr.jpg" width="260" alt="老K 微信反馈二维码" />

**深圳市八荒科技有限公司——开源精神，永不言败**
