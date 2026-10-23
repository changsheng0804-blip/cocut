# 路线

## 近期
- [x] **反射层体检**：`tools/reflex.py`（EmbeddingGemma 2，本地，按内容哈希缓存，改一拍约 4 秒）。
- [x] **点名复核接口**：`cocut/review.py` + `/api/review*` + `cli.py review`。反射层开单、任何 AI 只答是非题、平台按拍标红绿；素材改了旧单自动过期。实验依据见 experiments/bench/RESULTS.md 路线 D。
- [x] 审片页按拍显示红/绿/黄/灰（时间轴色带、画面框出可疑块、「复核」面板、转成意见、你的裁决为准）；保存后服务端自动体检+开单（模型常驻，改一拍约 2 秒）。
- [x] 通用复核员适配器 `tools/reviewer.py`（领单→调任意 AI 命令行→交答案），Gemini 已实测：13 张单 309 秒，单张约 55 秒。
- [x] 改动后自动唤起复核员：`<片子>/.cocut/reviewers.json` 按序执行，快模型答全部、`escalate` 的强模型只复核红/黄（例：examples/reviewers.example.json）。改回旧版本自动恢复原判。
- [x] 复核员提速：`--jobs N` 并发（代理拆份/接口并发）+ `--api` 直连 generateContent（无代理来回）+ 429 指数退避。12 张单：agy Flash 644→178 秒；Gemini 4 直连 149 秒（逐张）/约 100 秒（并发，受 Vertex 配额限流，额度充足时 31 秒）；答案与原来 17–19/19 一致。
- [x] AI 智能审核拆成独立插件 cocheck：统一模型接入口（embed/ask 两种能力；local_embed、gemini、openai 兼容、cli 代理、remote）、适配器（cocut/items/folder）、HTTP /v1 + CLI + 可嵌入色带组件；cocut 只做转发和画面。
- [ ] 云端大模型领单、MCP 工具（在 cocheck 里做）。
- [x] **读音**（《懒》N13，issue #1）：全片读音表 `doc.lexicon` 自动套用、单拍 `vo.say` 覆盖、`vo.said` 记录实际念的、读法变了配音自动算过期；界面「读音」面板和拍点「读法」框；`cli.py readings / lex / say / voice stale`；拼音要求经 cocheck 交复核员核对。
- [x] **4a 音频出错排查**（《懒》N14，已修复）：`tools/mixdown.py` 离线混音后定位为 duck=0 造成 55.0–56.6 秒纯数字静音，改 duck 0.12 + 急停音余尾。
- [ ] **导出端直接用 mixdown 音轨**：render/concat.py 不再自己摆配乐/旁白/音效，改为铺一条 mixdown.py 生成的成品音轨，浏览器与导出声音完全一致，顺带解决导出端 duck。
- [ ] **静音检查**：对 mixdown 结果扫整片，任何超过 0.5 秒低于 -60 dB 的段落即报警（进页面的问题清单和 CLI）。
- [ ] MCP 服务：把 /api/* 包成 MCP 工具，让任一支持 MCP 的 AI 客户端直接接入。
- [x] 画面快照接口（#4）：`GET /api/frame?t=|beat=`、`cli.py frame`、`cocut/snap.py`；无头 Chrome 打开审片页快照模式（`#snap`），和人看到的是同一帧。
- [ ] Concat 导出端支持配乐 duck（目前只有浏览器端支持；可由「导出端直接用 mixdown 音轨」一并解决）。
- [ ] 意见面板里显示 by（谁留的），按参与者过滤。

## 中期
- [ ] 参与者注册：每个 AI 声明负责的维度（文案 / 画面 / 声音 / 节奏），意见自动分派。
- [ ] 版本差异：两版 doc 的逐拍差异，审片包里带上。
- [ ] 提质流水线脚本化：角色设定 → 色调卡 → 逐拍出图 → LUT → 审画 → 超分，每步记耗时与费用。
- [ ] 渲染后端可插拔（Concat / ffmpeg / 浏览器录制）。
