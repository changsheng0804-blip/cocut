# 构建《懒》体检考卷：真实旧问题 + 注入故障，带标准答案（labels.json）
import json, os, random, asyncio, shutil
from PIL import Image, ImageDraw, ImageFont
FILM = os.path.expanduser('~/hark-sandbox-CS/argon-film/studio/live')
OUT = os.path.expanduser('~/hark-sandbox-CS/cocut-lab/bench'); shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(f'{OUT}/img', exist_ok=True); os.makedirs(f'{OUT}/aud', exist_ok=True)
d = json.load(open(f'{FILM}/doc.json', encoding='utf-8')); B = {b['id']: b for b in d['beats']}; ids = list(B)
random.seed(7)
def save(im, name):
    im = im.convert('RGB'); im.thumbnail((1280, 1280)); im.save(f'{OUT}/img/{name}', quality=88); return f'img/{name}'
items = []
# S1：r2 版（Gemini 审过）
OLD = {'1b': 'b1b.jpg', '2c': 'r2_b2b.jpg', '3a': 'b2e.jpg', '3b': 'b3a.jpg', '3c': 'b3b.jpg', '4a': 'b4a.jpg', '5b': 'b5b.jpg', '5c': 'b5c.jpg'}
for i in ids:
    p = 'sketch/' + OLD[i] if i in OLD else B[i]['image_sketch']
    items.append(dict(set='S1', id=f'S1_{i}', beat=i, image=save(Image.open(f'{FILM}/{p}'), f'S1_{i}.jpg'),
        label=dict(text=i in ('1b', '3a', '4a'), bad=i in OLD, swap=False)))
# S2：hq 版 + 注入（叠英文字 4 张、换成别拍图片 4 张）+ 已核实缺元素 3 张
TEXT = {'1a': 'SLEEP MODE', '2c': 'SPEED x3', '2d': 'PATCHED', '4b': 'WAIT?'}
SWAP = {'2a': '3c', '3a': '2d', '5b': '2b', '1b': '5a'}
MISS = {'0a', '3b', '5c'}
font_p = next(f for f in ['/System/Library/Fonts/Helvetica.ttc', '/System/Library/Fonts/Supplemental/Arial.ttf'] if os.path.exists(f))
for i in ids:
    src = B[SWAP[i]]['image'] if i in SWAP else B[i]['image']
    im = Image.open(f'{FILM}/{src}').convert('RGB')
    if i in TEXT:  # 像真实生成图里出现的标注字：小、放在画面某处、颜色随底色
        W, H = im.size; f = ImageFont.truetype(font_p, int(H * random.uniform(0.035, 0.055)))
        x, y = int(W * random.uniform(0.08, 0.6)), int(H * random.uniform(0.1, 0.8))
        px = im.getpixel((x, y)); col = (25, 25, 30) if sum(px) > 380 else (240, 240, 235)
        ImageDraw.Draw(im).text((x, y), TEXT[i], fill=col, font=f)
    items.append(dict(set='S2', id=f'S2_{i}', beat=i, image=save(im, f'S2_{i}.jpg'),
        label=dict(text=i in TEXT, swap=i in SWAP, bad=(i in TEXT or i in SWAP or i in MISS), miss=i in MISS)))
# S3：音频。A) 4 个多音字，各合成对/错两版（变语速音高，避免与参照完全相同）；B) 真实配音 15 条，其中 4 条换成别拍音频
import edge_tts
async def synth(text, path, rate, pitch):
    await edge_tts.Communicate(text, 'zh-CN-YunxiNeural', rate=rate, pitch=pitch).save(path)
POLY = [  # 拍, 原文, 字, 正确读音, 正确替身, 错误替身
    ('2b', '六百万行老代码，几周就拆解重构。', '行', 'háng', '航', '形'),
    ('2b', '六百万行老代码，几周就拆解重构。', '重', 'chóng', '虫', '众'),
    ('5a', '把通宵留给它，把清晨还给自己。', '还', 'huán', '环', '孩'),
    ('3c', '看段视频，几小时教会机器人七投七中。', '中', 'zhòng', '众', '钟'),
]
audio = []
for k, (beat, text, ch, py, good, bad) in enumerate(POLY):
    for tag, sub, rate, pitch in (('ok', good, '-2%', '+3Hz'), ('wrong', bad, '-12%', '-2Hz')):
        name = f'P{k}_{tag}.mp3'
        t2 = text.replace('航', '行').replace(ch, sub, 1) if ch != '重' else text.replace('重构', sub + '构')
        if ch == '重': t2 = t2.replace('行', '航')  # 只考「重」，「行」保持正确
        asyncio.run(synth(t2, f'{OUT}/aud/{name}', rate, pitch))
        audio.append(dict(set='S3', id=name[:-4], beat=beat, audio=f'aud/{name}', text=text, poly=dict(char=ch, pinyin=py, good=good, bad=bad),
            label=dict(misread=tag == 'wrong', mismatch=False)))
vb = [i for i in ids if (B[i].get('vo') or {}).get('file')]
SW = {'1a': '4b', '2d': '2e', '3b': '5c', '5b': '0a'}
for i in vb:
    src = B[SW[i]]['vo']['file'] if i in SW else B[i]['vo']['file']
    shutil.copy(f'{FILM}/{src}', f'{OUT}/aud/V_{i}.mp3')
    audio.append(dict(set='S3', id=f'V_{i}', beat=i, audio=f'aud/V_{i}.mp3', text=B[i]['vo']['text'], label=dict(mismatch=i in SW, misread=None)))
beats = {i: dict(what=B[i].get('what', ''), vo=(B[i].get('vo') or {}).get('text'), caption=B[i].get('caption')) for i in ids}
json.dump(dict(items=items, audio=audio, beats=beats), open(f'{OUT}/labels.json', 'w'), ensure_ascii=False, indent=1)
# 给模型的题目（不含答案）
q = dict(beats=beats, images=[dict(id=x['id'], beat=x['beat'], image=x['image']) for x in items],
         audio=[dict(id=x['id'], beat=x['beat'], audio=x['audio'], text=x['text'], poly=x.get('poly')) for x in audio])
json.dump(q, open(f'{OUT}/questions.json', 'w'), ensure_ascii=False, indent=1)
print(len(items), len(audio))
