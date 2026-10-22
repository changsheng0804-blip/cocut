# 反射层实验 2：局部、多轮、对照式（A/B 参照）用法
import json, os, sys, time, re, asyncio, subprocess, io
os.environ.setdefault('HF_HUB_OFFLINE', '1')
import numpy as np, torch, soundfile as sf
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from sentence_transformers import SentenceTransformer
FILM = os.path.expanduser('~/hark-sandbox-CS/argon-film/studio/live')
LAB = os.path.expanduser('~/hark-sandbox-CS/cocut-lab'); os.makedirs(f'{LAB}/ref', exist_ok=True)
d = json.load(open(f'{FILM}/doc.json', encoding='utf-8')); B = d['beats']; ids = [b['id'] for b in B]
R = {}; T0 = time.time()
model = SentenceTransformer('google/embeddinggemma-2', device='mps', model_kwargs={'torch_dtype': torch.float32})
def enc(x, prompt=None, pk=None):
    return model.encode(x, prompt_name=prompt, normalize_embeddings=True, batch_size=8, convert_to_numpy=True, processing_kwargs=pk)
LOW = {'image': {'max_soft_tokens': 70}}

# ---------- A. 画面局部：切块 + 合成参照（画里有没有文字） ----------
OLD = {'1b': 'b1b.jpg', '2c': 'r2_b2b.jpg', '3a': 'b2e.jpg', '3b': 'b3a.jpg', '3c': 'b3b.jpg', '4a': 'b4a.jpg', '5b': 'b5b.jpg', '5c': 'b5c.jpg'}
ver = {'r2': [('sketch/' + OLD[b['id']]) if b['id'] in OLD else b['image_sketch'] for b in B], 'hq': [b['image'] for b in B]}
def load(p):
    im = Image.open(f'{FILM}/{p}').convert('RGB'); im.thumbnail((1024, 1024)); return im
def tiles(im, g=3):
    W, H = im.size; out = []
    for gy in range(g):
        for gx in range(g):
            out.append(im.crop((gx * W // g, gy * H // g, (gx + 1) * W // g, (gy + 1) * H // g)))
    return out
# 合成参照：拿 hq 画面里的小块，叠上英文/中文字 = 正例；原块 = 负例。模型只需比"像有字的块"还是"像没字的块"
fonts = ['/System/Library/Fonts/Helvetica.ttc', '/System/Library/Fonts/Supplemental/Arial.ttf']
font = next((ImageFont.truetype(f, 46) for f in fonts if os.path.exists(f)), ImageFont.load_default())
words = ['DELETE', 'PUSH!', 'CLICK', '3D MODEL', 'TEMPLE', 'OUTLINE', 'SPEED', 'ERROR']
pos, neg = [], []
for k, p in enumerate(['hq/hq_0a.jpg', 'hq/hq_2b.jpg', 'hq/hq_5a.jpg', 'hq/hq_2e.jpg']):
    for j, t in enumerate(tiles(load(p))[::2]):
        neg.append(t); q = t.copy(); dr = ImageDraw.Draw(q)
        dr.text((20, q.size[1] // 2 - 25), words[(k + j) % len(words)], fill=(20, 20, 20) if j % 2 else (255, 255, 255), font=font)
        pos.append(q)
Ep = enc([{'image': x} for x in pos], pk=LOW); En = enc([{'image': x} for x in neg], pk=LOW)
cp, cn = Ep.mean(0), En.mean(0)
R['text_in_image'] = {}
t = time.time(); ntile = 0
for k, ps in ver.items():
    res = {}
    for i, p in zip(ids, ps):
        ts = tiles(load(p)); ntile += len(ts)
        Et = enc([{'image': x} for x in ts], pk=LOW)
        s = Et @ cp - Et @ cn  # 每块"有字"偏向
        res[i] = dict(max=round(float(s.max()), 4), tile=int(s.argmax()))
    R['text_in_image'][k] = res
R['tile_ms'] = round((time.time() - t) / ntile * 1000)
R['text_truth_r2'] = ['1b', '3a', '4a']  # Gemini 明确指出 r2 中这三张带英文

# ---------- B. 画面局部：what 拆成元素，逐元素在块里找（元素覆盖） ----------
def phrases(w):
    w = re.sub(r'[（(][^）)]*[）)]', '', w)
    return [x.strip() for x in re.split(r'[，、；。,]', w) if len(x.strip()) >= 3][:6]
R['coverage'] = {}
for k, ps in ver.items():
    allE = []
    for p in ps:
        im = load(p); allE.append(enc([{'image': x} for x in [im] + tiles(im)], pk=LOW))
    out = {}
    for i, b in enumerate(B):
        ph = phrases(b.get('what', ''))
        if not ph: continue
        Eph = enc(ph, 'Retrieval-query')
        # 每个元素：在本拍所有块中的最大匹配，跟它在其他拍块中的最大匹配比排名
        rows = []
        for e, txt in zip(Eph, ph):
            m = np.array([float((A @ e).max()) for A in allE]); rank = int((m > m[i]).sum()) + 1
            rows.append(dict(el=txt[:24], rank=rank))
        out[b['id']] = dict(miss=[r['el'] for r in rows if r['rank'] > 3], n=len(rows), worst=max(r['rank'] for r in rows))
    R['coverage'][k] = out

# ---------- C. 声音局部：多音字 A/B 参照，裁到字级窗口 ----------
import edge_tts
async def synth(text, voice, path):
    c = edge_tts.Communicate(text, voice, rate='-8%', boundary='WordBoundary'); wb = []
    with open(path, 'wb') as f:
        async for ch in c.stream():
            if ch['type'] == 'audio': f.write(ch['data'])
            elif ch['type'] == 'WordBoundary': wb.append((ch['offset'] / 1e7, ch['duration'] / 1e7, ch['text']))
    return wb
def wav(path, a=None, b=None):
    out = subprocess.run(['ffmpeg', '-v', 'quiet', '-i', path, '-ac', '1', '-ar', '16000', '-f', 'f32le', '-'], capture_output=True).stdout
    x = np.frombuffer(out, dtype=np.float32)
    return x if a is None else x[int(a * 16000):int(b * 16000)]
cases = [  # (拍, 句子, 字, 正确读音替身, 错误读音替身, 被测音频{名字:文件})
    ('2b', '六百万{}老代码，几周就拆解重构。', '行', '航', '形', {'old_wrong(xíng)': 'vo/2b_r3_092201.mp3', 'new_fixed(háng)': 'vo/2b_024748.mp3'}),
    ('2b', '六百万航老代码，几周就拆解{}构。', '重', '虫', '众', {'new_fixed': 'vo/2b_024748.mp3'}),
]
R['polyphone'] = []
for voice in ('zh-CN-YunxiNeural', 'zh-CN-XiaoxiaoNeural'):
    for beat, tpl, ch, good, bad, tests in cases:
        refs = {}
        for tag, c in (('good', good), ('bad', bad)):
            p = f'{LAB}/ref/{beat}_{ch}_{tag}_{voice}.mp3'; wb = asyncio.run(synth(tpl.format(c), voice, p))
            w = next(((o, du) for o, du, tx in wb if c in tx), None)
            full = wav(p); seg = wav(p, max(0, w[0] - 0.25), w[0] + w[1] + 0.25) if w else full
            refs[tag] = dict(full=full, seg=seg)
        Er = enc([{'audio': refs['good']['full']}, {'audio': refs['bad']['full']}, {'audio': refs['good']['seg']}, {'audio': refs['bad']['seg']}])
        for name, f in tests.items():
            x = wav(f'{FILM}/{f}'); Ef = enc([{'audio': x}])[0]
            # 局部：在被测音频上滑窗（与参照段等长），取最像参照段的窗口
            L = len(refs['good']['seg']); hop = 1600
            wins = [x[s:s + L] for s in range(0, max(1, len(x) - L), hop)]
            Ew = enc([{'audio': w} for w in wins])
            sg, sb = Ew @ Er[2], Ew @ Er[3]; j = int(np.argmax(np.maximum(sg, sb)))
            R['polyphone'].append(dict(voice=voice, beat=beat, char=ch, audio=name,
                full_good=round(float(Ef @ Er[0]), 4), full_bad=round(float(Ef @ Er[1]), 4),
                local_good=round(float(sg[j]), 4), local_bad=round(float(sb[j]), 4), at_s=round(j * hop / 16000, 2),
                verdict='good' if sg[j] > sb[j] else 'bad'))
R['total_s'] = round(time.time() - T0, 1)
json.dump(R, open(f'{LAB}/eg2_local_result.json', 'w'), ensure_ascii=False, indent=1)
print('done', R['total_s'], 'tile_ms', R['tile_ms'])
