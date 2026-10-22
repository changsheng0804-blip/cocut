# 源文件格式（doc.json）

一部片子就是一份 doc.json。**只存意图，不存时间线**：拍点只写时长，开始时间由顺序自动推出；旁白、小字、音效挂在拍点上。

## 顶层
| 字段 | 说明 |
|---|---|
| title, fps, width, height | 片名与输出规格 |
| target | 目标总长（秒） |
| one_thing | 这部片子只想让人记住的一句话（所有参与者对齐的锚） |
| music | `{file, gain, fade_in, fade_out}` 配乐 |
| vo_gain | 旁白整体增益 |
| style | `{sub_size, sub_plate, note_size, title_size, title_y}` 字幕与小字样式；title_y 为片名纵向位置（像素，默认 520，副标题在其下 +105） |
| beats | 拍点数组（顺序即时间顺序） |
| notes | 意见数组（人和 AI 同一格式） |
| rev, saved | 版本号与最后保存标记（页面据此自动刷新） |
| look | 可选：画质阶梯记录（如 sketch → hq） |

## 拍点 beat
| 字段 | 说明 |
|---|---|
| id | 拍点号，如 `2c` |
| dur | 时长（秒） |
| image | 当前画面（相对片子目录）；没有图时页面自动显示文字卡 |
| image_sketch | 可选：提质前的示意图，便于对照与回退 |
| move | 镜头运动：static / push / pull / pan / orbit（由代码实现，不靠视频模型） |
| role, verb | 叙事角色与动作（如 证据·提速） |
| what | 画面要表达什么（给生成模型和审片者看） |
| hero | 关键拍：自动重排时间时不让时长 |
| vo | `{text, say, file, dur, lead, words:[{t,d,w}]}` 旁白；lead 为拍内起点；words 为字级时间；say 可选，为配音时实际朗读的文本（纠正多音字，如「六百万航老代码」），字幕与片名仍显示 text |
| vo_style | 配音语气说明 |
| caption | 画面小字 |
| title | 是否片名拍（旁白第一句作片名，caption 作副标题） |
| dim | 压暗程度 0–1 |
| duck, duck_release | 配乐骤降（如急停拍）；duck 为保留的配乐比例，0 即全静音，慎用（《懒》N14 的成因） |
| sfx | `[{file, at, gain}]` 音效，at 为拍内偏移（可为负） |

## 意见 note
人在画面上点一下留下的意见，和 AI 给出的意见，是同一种结构：
| 字段 | 说明 |
|---|---|
| id | N 开头为人，A 开头为 AI（历史数据里也有 G 开头的 Gemini 意见） |
| by | 谁留的：`user`、`claude`、`gemini-4-argon-high`、`gpt-…` |
| t, beat | 时间点与拍点（给一个即可，另一个自动推出） |
| x, y | 画面位置（0–1） |
| dim | 维度：叙事 / 画面 / 字 / 声 / 节奏 |
| sev | 严重度 1–3 |
| text | 问题 |
| fix | 建议改法 |
| status | open / todo / done |
| reply, by_fix | 谁改了、怎么改的 |

## 复核 review（`<片子>/.cocut/review.json`，由平台维护）
反射层（`tools/reflex.py`）体检报告存 `.cocut/reflex.json`；`cocut/review.py` 按报告给每拍开单。
| 对象 | 字段 |
|---|---|
| ticket | `id`（拍点-指纹）、`beat`、`fp`（图+what+配音文件+文案+say+poly 的指纹，变了旧单即过期）、`image`、`audio`、`what`、`text`、`asks`、`status`（open / clear / answered / stale） |
| ask | `i` 下标、`k` 类型（text 有无文字 / swap 是不是本拍场景 / el 有无某元素 / vo 配音是不是这句 / poly 多音字读得对不对）、`q` 问题、`el` 或 `ch` |
| answers | `answers[ticket][复核员] = {answers: {"0": "yes"}, at, note?}` |
判定：text 题答 yes、其余题答 no 即「有问题」；多个复核员时，说有问题的人数 ≥ 说没问题的人数即判有问题，并记下反对者。
每拍颜色：green 没问题（反射层直接放行或复核通过）/ red 有问题 / yellow 待复核或全是 unsure / grey 已过期。
接口：`GET /api/review[?by=&second=1]`、`POST /api/review/open {report?}`、`POST /api/review/answer`；CLI `cli.py review open|list|answer|status`。
