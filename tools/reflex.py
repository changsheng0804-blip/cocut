"""cocut 反射层体检：EmbeddingGemma 2 做高频、局部、对照式检查。

不判"好不好"，只做可核对的局部问题：
  text_in_image  画面切块 vs 合成参照（叠字块/原块），找画里多余的文字
  coverage       把 what 拆成元素，逐元素在全片所有块里找，报缺失元素 / 整张换错
  vo_match       配音音频 ↔ 本拍文案（在全片文案中排名），报配错音频
  polyphone      多音字：用同一音色合成两种读音参照，在配音上按字长滑窗 A/B
所有嵌入按文件内容哈希缓存（.reflex_cache/），只重算改过的东西。

用法：python3 tools/reflex.py <片子目录> [out.json]
"""
import hashlib, json, os, re, subprocess, sys, time, asyncio
import numpy as np

POLY = {  # 字: [(读音, 同音替身), ...]，第一个不一定是正确读音；正确读音由 vo.poly 或调用方指定
    '行': [('háng', '航'), ('xíng', '形')], '重': [('chóng', '虫'), ('zhòng', '众')],
    '还': [('huán', '环'), ('hái', '孩')], '中': [('zhòng', '众'), ('zhōng', '钟')],
    '长': [('cháng', '常'), ('zhǎng', '掌')], '为': [('wèi', '未'), ('wéi', '维')],
    '好': [('hǎo', '郝'), ('hào', '号')], '调': [('diào', '吊'), ('tiáo', '条')],
}
VOICE = 'zh-CN-YunxiNeural'; RATE = '-8%'


class Reflex:
    def __init__(self, cache='.reflex_cache', device=None):
        import torch
        from sentence_transformers import SentenceTransformer
        os.environ.setdefault('HF_HUB_OFFLINE', '1')
        dev = device or ('mps' if torch.backends.mps.is_available() else 'cuda' if torch.cuda.is_available() else 'cpu')
        self.m = SentenceTransformer('google/embeddinggemma-2', device=dev, model_kwargs={'torch_dtype': torch.float32})
        self.cache = cache; os.makedirs(cache, exist_ok=True); self.stats = dict(hit=0, miss=0)
        self._refs = None

    # ---- 嵌入 + 缓存 ----
    def _key(self, kind, payload):
        h = hashlib.sha1(kind.encode())
        h.update(payload if isinstance(payload, bytes) else str(payload).encode()); return h.hexdigest()
    def embed(self, items, kinds, prompt=None, pk=None):
        out = [None] * len(items); todo = []
        for n, (x, k) in enumerate(zip(items, kinds)):
            f = f'{self.cache}/{k}.npy'
            if os.path.exists(f): out[n] = np.load(f); self.stats['hit'] += 1
            else: todo.append(n)
        if todo:
            E = self.m.encode([items[n] for n in todo], prompt_name=prompt, normalize_embeddings=True, batch_size=8,
                              convert_to_numpy=True, processing_kwargs=pk)
            for n, e in zip(todo, E): np.save(f'{self.cache}/{kinds[n]}.npy', e); out[n] = e
            self.stats['miss'] += len(todo)
        return np.stack(out)
    def text(self, xs, prompt):
        return self.embed(list(xs), [self._key('t' + prompt, x) for x in xs], prompt)
    def tiles(self, path, g=3):
        from PIL import Image
        raw = open(path, 'rb').read(); im = Image.open(path).convert('RGB'); im.thumbnail((1024, 1024)); W, H = im.size
        crops = [im] + [im.crop((x * W // g, y * H // g, (x + 1) * W // g, (y + 1) * H // g)) for y in range(g) for x in range(g)]
        return self.embed([{'image': c} for c in crops], [self._key(f'tile{g}_{n}', raw) for n in range(len(crops))],
                          pk={'image': {'max_soft_tokens': 70}})
    def audio(self, wavs, keys):
        return self.embed([{'audio': w} for w in wavs], [self._key('a', k) for k in keys])

    # ---- 参照：叠字块 vs 原块 ----
    def text_refs(self, ref_images):
        if self._refs is not None: return self._refs
        from PIL import Image, ImageDraw, ImageFont
        fp = next((f for f in ['/System/Library/Fonts/Helvetica.ttc', '/System/Library/Fonts/Supplemental/Arial.ttf',
                               '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'] if os.path.exists(f)), None)
        font = ImageFont.truetype(fp, 46) if fp else ImageFont.load_default()
        words = ['DELETE', 'PUSH!', 'CLICK', '3D MODEL', 'TEMPLE', 'OUTLINE', 'SPEED', 'ERROR']
        pos, neg, keys = [], [], []
        for k, p in enumerate(ref_images):
            im = Image.open(p).convert('RGB'); im.thumbnail((1024, 1024)); W, H = im.size
            for j in range(0, 9, 2):
                x, y = j % 3, j // 3; t = im.crop((x * W // 3, y * H // 3, (x + 1) * W // 3, (y + 1) * H // 3))
                q = t.copy(); ImageDraw.Draw(q).text((20, q.size[1] // 2 - 25), words[(k + j) % 8],
                                                      fill=(20, 20, 20) if j % 4 else (255, 255, 255), font=font)
                neg.append({'image': t}); pos.append({'image': q}); keys.append(f'{p}:{j}')
        pk = {'image': {'max_soft_tokens': 70}}
        Ep = self.embed(pos, [self._key('refpos', k) for k in keys], pk=pk)
        En = self.embed(neg, [self._key('refneg', k) for k in keys], pk=pk)
        self._refs = (Ep.mean(0), En.mean(0)); return self._refs

    # ---- 检查 ----
    def text_in_image(self, path, refs, thr=-0.008):
        cp, cn = refs; T = self.tiles(path)[1:]; s = T @ cp - T @ cn
        return dict(score=round(float(s.max()), 4), tile=int(s.argmax()), flag=bool(s.max() > thr))

    @staticmethod
    def elements(what):
        w = re.sub(r'[（(][^）)]*[）)]', '', what or '')
        w = re.sub(r'(?<=\d),(?=\d)', '', w)  # 1,000,000 不拆
        return [x.strip() for x in re.split(r'[，、；。,;]', w) if len(x.strip()) >= 3][:6]

    def coverage(self, beats, images, miss_rank=3, bad_rank=10, swap_frac=0.6):
        """beats: [(id, what)], images: [path] 同序；每个元素在全片块里排第几"""
        TE = [self.tiles(p) for p in images]; out = {}
        for i, (bid, what) in enumerate(beats):
            els = self.elements(what)
            if not els: continue
            E = self.text(els, 'Retrieval-query'); rows = []
            for e, t in zip(E, els):
                m = np.array([float((A @ e).max()) for A in TE]); rows.append((t, int((m > m[i]).sum()) + 1))
            miss = [t for t, r in rows if r > miss_rank]; worst = max(r for _, r in rows)
            out[bid] = dict(elements=[dict(el=t, rank=r) for t, r in rows], missing=miss, worst=worst,
                            swap=len(miss) / len(rows) >= swap_frac, flag=worst >= bad_rank)
        return out

    @staticmethod
    def wav(path, a=None, b=None):
        x = np.frombuffer(subprocess.run(['ffmpeg', '-v', 'quiet', '-i', path, '-ac', '1', '-ar', '16000', '-f', 'f32le', '-'],
                                         capture_output=True).stdout, dtype=np.float32)
        return x if a is None else x[int(a * 16000):int(b * 16000)]

    def vo_match(self, pairs):
        """pairs: [(id, audio_path, text)]；音频在全部文案中检索，自己的文案排第几"""
        A = self.audio([self.wav(p) for _, p, _ in pairs], [open(p, 'rb').read() for _, p, _ in pairs])
        T = self.text([t for *_, t in pairs], 'Retrieval-query'); S = A @ T.T; out = {}
        for n, (bid, _, _) in enumerate(pairs):
            r = int((S[n] > S[n, n]).sum()) + 1; out[bid] = dict(rank=r, flag=r > 1, best=pairs[int(S[n].argmax())][0])
        return out

    def _synth(self, text, path):
        import edge_tts
        async def go():
            c = edge_tts.Communicate(text, VOICE, rate=RATE, boundary='WordBoundary'); wb = []
            with open(path, 'wb') as f:
                async for ch in c.stream():
                    if ch['type'] == 'audio': f.write(ch['data'])
                    elif ch['type'] == 'WordBoundary': wb.append((ch['offset'] / 1e7, ch['duration'] / 1e7, ch['text']))
            return wb
        if not os.path.exists(path + '.wb.json'):
            json.dump(asyncio.run(go()), open(path + '.wb.json', 'w'))
        return json.load(open(path + '.wb.json'))

    def polyphone(self, audio_path, text, char, good_sub, bad_sub):
        refs = []
        for sub in (good_sub, bad_sub):
            t = text.replace(char, sub, 1); p = f'{self.cache}/ref_{self._key("tts", VOICE + RATE + t)}.mp3'
            wb = self._synth(t, p); w = next(((o, d) for o, d, tx in wb if sub in tx), None)
            refs.append((p, w))
        segs = [self.wav(p, max(0, w[0] - 0.25), w[0] + w[1] + 0.25) if w else self.wav(p) for p, w in refs]
        R = self.audio(segs, [f'{p}:{w}' for p, w in refs])
        x = self.wav(audio_path); L = len(segs[0]); hop = 1600; raw = open(audio_path, 'rb').read()
        starts = list(range(0, max(1, len(x) - L), hop))
        W = self.audio([x[s:s + L] for s in starts], [raw + f':{s}:{L}'.encode() for s in starts])
        g, b = W @ R[0], W @ R[1]; j = int(np.argmax(np.maximum(g, b)))
        return dict(good=round(float(g[j]), 4), bad=round(float(b[j]), 4), at=round(starts[j] / 16000, 2), flag=bool(b[j] > g[j]))


def check_film(film, out=None):
    d = json.load(open(f'{film}/doc.json', encoding='utf-8')); B = [b for b in d['beats'] if b.get('image')]
    rx = Reflex(cache=f'{film}/.reflex_cache'); t0 = time.time()
    imgs = [f'{film}/{b["image"]}' for b in B]
    refs = rx.text_refs(imgs[:4]); res = {b['id']: {} for b in B}
    for b, p in zip(B, imgs): res[b['id']]['text_in_image'] = rx.text_in_image(p, refs)
    for k, v in rx.coverage([(b['id'], b.get('what', '')) for b in B], imgs).items(): res[k]['coverage'] = v
    vb = [(b['id'], f'{film}/{b["vo"]["file"]}', b['vo']['text']) for b in B if (b.get('vo') or {}).get('file')]
    for k, v in rx.vo_match(vb).items(): res[k]['vo_match'] = v
    for b in B:
        vo = b.get('vo') or {}
        for ch, py in (vo.get('poly') or {}).items():  # vo.poly: {"行": "háng"}
            opts = dict(POLY.get(ch, [])); good = opts.get(py); bad = next((s for p, s in POLY.get(ch, []) if p != py), None)
            if good and bad and vo.get('file'):
                res[b['id']].setdefault('polyphone', {})[ch] = rx.polyphone(f'{film}/{vo["file"]}', vo.get('say') or vo['text'], ch, good, bad)
    report = dict(beats=res, seconds=round(time.time() - t0, 1), cache=rx.stats)
    if out: json.dump(report, open(out, 'w'), ensure_ascii=False, indent=1)
    return report


if __name__ == '__main__':
    r = check_film(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    flags = {k: [c for c, v in x.items() if isinstance(v, dict) and v.get('flag')] for k, x in r['beats'].items()}
    print(json.dumps(dict(seconds=r['seconds'], cache=r['cache'], flags={k: v for k, v in flags.items() if v}), ensure_ascii=False))
