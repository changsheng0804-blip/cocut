# cocut · 共剪

**人和 AI 在同一份源文件上共同成片。** 既不是传统的手工剪辑，也不是向 AI 许个愿、然后像抽卡一样苦等成片。

## 为什么
- **先看交互草稿，不先出视频。** 打开页面就是一部能播、能拖、能改的片子：示意图 + 占位配音 + 配乐草切 + 字幕，在浏览器里实时合成。
- **字-音-画随时替换。** 改一句旁白只重配这一句，换一张图只换这一拍，时间自动顺延；不用为改一处重抽整片。
- **AI 参与闭环，而不是只接收提示词。** 任何 AI（Claude、Gemini、ChatGPT、Hark、本地模型）都能读片子、在画面上留意见、改拍点，和人用的是**同一种格式**。不同 AI 可以各管一维：一个写文案，一个听声音，一个审画面。
- **最后才提质。** 叙事和节奏在草稿阶段锁定后，再逐拍把示意图升级成高清画面（角色设定 + 色调卡 + 扩散模型 + 统一调色 + 超分），最后一次导出。贵的算力只花在定稿上。

## 结构
```
app/            交互页（index.html + live.js）：canvas 画面 + 镜头运动、DOM 字幕、WebAudio 旁白/配乐/音效、拍点条拖拽、画面留意见、撤销
cocut/api.py    源文件接口：保存（自动备份）、重新配音（edge-tts，带字级时间）、doc → plan 编译
cocut/cli.py    给 AI / 人在终端里用：show / note / set
server.py       本地服务：端出片子目录 + 交互页，HTTP 接口
render/concat.py 渲染后端（Concat headless MCP）：审片版 480p（叠拍点号）/ 定稿 1080p
tools/grade.py  色调卡 + LUT（.cube）生成与套用，保证图与视频同一色调
tools/sfx_synth.py 程序化音效（numpy/scipy）
tools/mixdown.py  离线混音（同交互页规则：配乐淡入淡出+duck、旁白、音效）→ wav，给会听的 AI 审听；python3 tools/mixdown.py <片子目录> out.wav [起 止]（需 numpy）
examples/lan/   示例：《懒》Gemini 4 Argon 宣传片（只带 doc.json，媒体不入库）
docs/           SPEC（源文件格式）、AGENTS（AI 参与说明）、METHOD（方法与实测数据）、ROADMAP
```

## 跑起来
```
pip install edge-tts            # 配音（可选）
python3 server.py <片子目录> 8790
# 打开 http://localhost:8790/live/
```
片子目录 = `doc.json` + 它引用的素材（图、配音、音效、配乐）。页面每 3 秒读一次 doc.json：AI 或脚本改了文件，页面自动接上。

## 接口（人和 AI 共用）
| 方法 | 路径 | 作用 |
|---|---|---|
| GET | /api/doc | 当前源文件 |
| GET | /api/plan | 编译后的时间线（每拍起止、旁白、字幕、音效） |
| POST | /api/save | 整份保存（自动备份到 history/） |
| POST | /api/note | 留意见 `{beat或t, text, by, dim, sev, fix}` |
| POST | /api/tts | 重配一句 `{id, text, voice?, rate?, pitch?}` → 文件 + 时长 + 字级时间 |
| POST | /api/export | 导出 `{final:true}` 1080p，或 `{final:false, ver}` 审片版 |

详见 docs/SPEC.md 与 docs/AGENTS.md。
