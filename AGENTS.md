# 给 AI 的参与说明

你是这部片子的合作者之一，不是一次性的生成器。人和其他 AI 也在同一份 doc.json 上工作。

## 你能做什么
1. **读片子**：`GET /api/doc` 或 `python3 cocut/cli.py show`。要看画面就看 `image` 引用的图；要看成品画面（镜头运动、字幕、小字、转场都在）用 `GET /api/frame?t=12.3` 或 `cli.py frame 2c`（`frame all --dir shots/` 每拍一张）；要听，用 `tools/mixdown.py` 混出音轨。
2. **留意见**：`POST /api/note` 或 `cli.py note --beat 2c --by <你的名字> --dim 画面 --sev 2 "问题" --fix "改法"`。一条意见只说一件事，指明拍点或时间，给出可执行的改法。
3. **改内容**：只改你负责的维度，改拍点字段（`cli.py set <拍点> <字段> <值>` 或整份 `POST /api/save`）。改旁白文字后要重配这一句（`POST /api/tts`），用返回的 file/dur/words/said 更新该拍的 vo；或直接 `cli.py voice stale`。
4. **读音**：多音字、念法写进全片读音表（`cli.py lex add 六百万行 六百万航 --py 行=háng`），单拍特例用 `cli.py say <拍点> <念法>`；`cli.py readings` 看每拍实际念的和哪些配音过期，`cli.py voice stale` 按当前读法重配。字幕永远显示原文。
4. **回复意见**：改完把对应 note 的 status 设为 done，写 reply 和 by_fix。

## 领复核单（点名复核）
AI 智能审核由独立插件 **cocheck** 负责（体检、复核单、复核员链、统一模型接入口），cocut 只把它的结果画在审片页上。
cocheck 监视 doc.json，每次改动自动体检，把可疑处开成「复核单」：哪张图、哪条配音、问哪几个是非题。你只需要答这几题。
1. 领单：`GET http://127.0.0.1:8796/v1/projects/<片子>/tickets?by=<你的名字>`（或 `cli.py review list --by <你的名字>`）。图/音给的是 URL。
2. 逐题只答 `yes` / `no` / `unsure`，只看点名的那一处，不评价别的。
3. 交卷：`POST /v1/projects/<片子>/answer {"ticket": "3b-8e6abd7068", "by": "<你的名字>", "answers": {"0": "no"}, "note": "可选的一句理由"}`
   或 `cli.py review answer 3b-8e6abd7068 --by <你的名字> '{"0":"no"}'`。
单号随素材/文案指纹变化，过期的单会被拒（409），重新领即可。接口全文见 cocheck 仓库 docs/API.md。
想要更全面的意见，照旧用 `/api/note` 留言；复核单只做是非判断。

## 规矩
- 先对齐 `one_thing`，再动手。
- 不要整片重写来解决一处问题；脏哪段改哪段。
- 不要删别人的意见；有分歧就留一条新意见说明理由。
- 拍点时长改了，后面的时间会自动顺延；如有 `target`，注意总长。
- 画面里不要出现生成模型的伪文字；需要的字由小字/字幕层负责。
- 你听不到声音或看不到视频时，不要对声音/动态下结论，交给能听/能看的参与者。
