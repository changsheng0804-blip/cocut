# 源文件格式（doc.json）

一部片子就是一份 doc.json。**只存意图，不存时间线**：拍点只写时长，开始时间由顺序自动推出；旁白、小字、音效挂在拍点上。

## 顶层
| 字段 | 说明 |
|---|---|
| title, fps, width, height | 片名与输出规格 |
| target | 目标总长（秒） |
| one_thing | 这部片子只想让人记住的一句话（所有参与者对齐的锚） |
| music | `{file, gain, fade_in, fade_out}` 配乐；可为空（只有旁白） |
| voice, made_from | 可选：默认配音音色；草稿由哪份脚本生成（`cli.py new`） |
| vo_gain | 旁白整体增益 |
| style | `{sub_size, sub_plate, note_size, title_size, title_y}` 字幕与小字样式；title_y 为片名纵向位置（像素，默认 520，副标题在其下 +105） |
| beats | 拍点数组（顺序即时间顺序） |
| notes | 意见数组（人和 AI 同一格式） |
| lexicon | 全片读音表 `[{w, say, py?, note?}]`：旁白里出现 w（原文片段，写带上下文的词）配音就念 say，字幕不变；py 为拼音要求 `{字: 拼音}`，交给复核员核对 |
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
| vo | `{text, say, file, dur, lead, words:[{t,d,w}]}` 旁白；lead 为拍内起点；words 为字级时间；say 可选，单拍手动指定配音念的文本（覆盖读音表）；said 为上次配音实际念的（配音接口回填）。该念的 = say 或「读音表套到 text」，和 said 不一样即配音过期；字幕与片名仍显示 text |
| vo_style | 配音语气说明 |
| caption | 画面小字 |
| title | 是否片名拍（旁白第一句作片名，caption 作副标题） |
| dim | 压暗程度 0–1 |
| duck, duck_attack, duck_release | 配乐骤降（如急停拍）；duck 为保留的配乐比例，0 即全静音；duck_attack 下压用时（默认 0.04s），duck_release 拍点结束后回升用时（默认 0.8s）。压到 30% 以下且没有旁白/音效超过 0.6s，检查会标红「听起来像断了」（《懒》N14、N15 的成因） |
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
| layer | 落到哪份素材 `{kind, beat, src}`：kind 为 image（src 是图路径）/ sub（旁白字幕，src=vo.text）/ caption / title / title2。带 x、y 留意见时自动算出（页面按点中的元素，接口按字号估算） |

## 复核 review（由插件 cocheck 维护）
AI 智能审核（反射层体检、复核单、复核员链、统一模型接入口）已拆成独立插件 cocheck，数据在 `<片子>/.cocheck/`，规格见 cocheck 仓库 docs/API.md。
cocut 侧只有：`server.py` 把 `GET /api/review`、`POST /api/review/check`、`POST /api/review/answer` 转发到 cocheck（`COCHECK_URL` 默认 `http://127.0.0.1:8796`，项目名 `COCHECK_PROJECT` 默认片子目录名，未登记时自动以 cocut 适配器登记）；`app/live.js` 画时间轴色带、可疑块框和「复核」面板；`cli.py review status|list|answer|check` 转发。
cocheck 没开时，审片页的复核功能不显示，其余功能不受影响。

