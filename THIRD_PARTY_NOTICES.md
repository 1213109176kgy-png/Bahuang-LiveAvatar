# 第三方组件与模型

本项目整合第三方组件，保留原始作者和许可证。根目录 LICENSE 仅适用于本项目自有代码，不替代下列组件的许可证。

| 组件 | 用途 | 上游及说明 |
|---|---|---|
| LiveTalking | 实时数字人、WebRTC、Wav2Lip256 接入 | https://github.com/lipku/LiveTalking ，Apache-2.0；固定提交见 setup/sources.json |
| Wav2Lip 系列 | 口型推理 | https://github.com/Rudrabha/Wav2Lip ，原始公开版本有非商业使用限制。LiveTalking 提供的 256 权重未取得明确再分发授权，公开整合包不附带该权重 |
| MuseTalk 1.5 | 可选实验口型引擎 | https://github.com/TMElyralab/MuseTalk ，保留 app/vendor/MuseTalk-LICENSE；不默认打包权重 |
| Qwen3 / Qwen3-TTS | 本地对话与语音生成 | https://github.com/QwenLM/Qwen3 、https://github.com/QwenLM/Qwen3-TTS ，Apache-2.0；Base 与 CustomVoice 作用不同 |
| faster-qwen3-tts | TTS 加速路径 | sources/faster-qwen3-tts-0.2.6 中保留许可证及来源 |
| Faster Whisper / Whisper | 本地转写 | https://github.com/SYSTRAN/faster-whisper 、https://github.com/openai/whisper ，保留上游许可 |
| llama.cpp | GGUF 推理 | https://github.com/ggml-org/llama.cpp ，MIT |
| Electron / Python / PyTorch / FFmpeg 等 | 运行环境 | 整合包保留各组件许可和依赖元数据，使用者仍需遵守相关许可 |

人物、声音参考录音和公司 Logo 不作为通用训练数据授权。开发者微信二维码仅用于项目交流，请勿用于其他用途。项目授权不自动授权任何第三方人物或声音素材。

源码开源、权重可下载、模型可商用是不同事项。公开直播或商业产品请核实实际使用的模型及人物、音色授权。
