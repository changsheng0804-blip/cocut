# 给 AI 的参与说明

你是这部片子的合作者之一，不是一次性的生成器。人和其他 AI 也在同一份 doc.json 上工作。

## 你能做什么
1. **读片子**：`GET /api/doc` 或 `python3 cocut/cli.py show`。要看画面就看 `image` 引用的图；要看/听成片，请求方会给你审片版视频（叠了拍点号和时间码）。
2. **留意见**：`POST /api/note` 或 `cli.py note --beat 2c --by <你的名字> --dim 画面 --sev 2 "问题" --fix "改法"`。一条意见只说一件事，指明拍点或时间，给出可执行的改法。
3. **改内容**：只改你负责的维度，改拍点字段（`cli.py set <拍点> <字段> <值>` 或整份 `POST /api/save`）。改旁白文字后要重配这一句（`POST /api/tts`），用返回的 file/dur/words 更新该拍的 vo。
4. **回复意见**：改完把对应 note 的 status 设为 done，写 reply 和 by_fix。

## 领复核单（点名复核）
反射层每次改动后自动体检，把可疑处开成「复核单」：哪张图、哪条配音、问哪几个是非题。你只需要答这几题。
1. 领单：`GET /api/review?by=<你的名字>` 的 `open`，或 `cli.py review list --by <你的名字>`。
   每张单有 `image`、`audio`（片子目录里的相对路径，服务端可在 `/live/<路径>` 取到）、`what`、`text` 和 `asks`。
2. 答题：每题只答 `yes` / `no` / `unsure`，键是 `asks[].i`。
   `POST /api/review/answer {"ticket": "3b-8e6abd7068", "by": "<你的名字>", "answers": {"0": "no"}, "note": "可选的一句理由"}`
   或 `cli.py review answer 3b-8e6abd7068 --by <你的名字> '{"0":"no"}'`。
3. 只看点名的那一处，不评价别的；看不到/听不到就答 `unsure`，不要猜。
4. 单子过期（409）说明素材或文案已改，等新体检出新单。
自动领单：`python3 tools/reviewer.py --server http://localhost:8790 --by <名字> --cmd '<你的命令行> {prompt}'`，适配器负责下载图/音、出题、收答案、交回。
想要更全面的意见，照旧用 `/api/note` 留言；复核单只做是非判断。

## 规矩
- 先对齐 `one_thing`，再动手。
- 不要整片重写来解决一处问题；脏哪段改哪段。
- 不要删别人的意见；有分歧就留一条新意见说明理由。
- 拍点时长改了，后面的时间会自动顺延；如有 `target`，注意总长。
- 画面里不要出现生成模型的伪文字；需要的字由小字/字幕层负责。
- 你听不到声音或看不到视频时，不要对声音/动态下结论，交给能听/能看的参与者。
