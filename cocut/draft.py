# 从一份文字脚本直接出可播的预览草稿：doc.json + 每拍配音（带字级时间）。不出图、不渲染、不烧录。
# 没图的拍点审片页自动画成文字卡，照样能看主线、听节奏、在画面上改；图以后逐拍换进来即可。
#   python3 cocut/draft.py script.md 片子目录 [--voice zh-CN-YunxiNeural] [--no-voice]
#   （或 python3 cocut/cli.py new script.md 片子目录）
# 脚本格式（见 examples/hello/script.md）：
#   # 片名
#   一句话：这部片子只想让人记住的一件事
#   时长：40                       目标秒数（可省）
#   配乐：music.mp3                可省；没有就只有旁白
#   读音：cocut→扣卡特；行长→航长   可省；全片读音表，配音照右边念，字幕不变
#   ## 0a 钩子 push                拍点号 + 作用（任意词）+ 可选：镜头 static/push/pull/pan/orbit、「高潮」、「片名」
#   画面：这一拍画面上是什么（先写清楚，以后出图就照这个）
#   旁白：这一拍念的话
#   小字：画面上方的小字（可省）
#   时长：3.5                      可省；默认按配音长度 + 留白
#   图：img/0a.jpg                 可省；有图就用图，没有就是文字卡
# 配音用 edge-tts（免费，需要联网）；没装或 --no-voice 时按字数估时长，页面照样能播（无声）。
import argparse, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor

MOVES = {'static', 'push', 'pull', 'pan', 'orbit'}
KEYS = {'画面': 'what', '旁白': 'vo', '小字': 'caption', '时长': 'dur', '图': 'image', '读法': 'say'}


def parse(text):
    doc = dict(title='', one_thing='', target=None, music=None, beats=[], lexicon=[])
    b = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('<!--'): continue
        if line.startswith('## '):
            tok = line[3:].split(); b = dict(id=tok[0], move='push', role='', verb='', what='')
            for w in tok[1:]:
                if w in MOVES: b['move'] = w
                elif w == '高潮': b['hero'] = True
                elif w == '片名': b['title'] = True; b['move'] = 'static'; b['role'] = b['role'] or '片名'
                elif not b['role']: b['role'] = w
                else: b['verb'] = w
            doc['beats'].append(b); continue
        if line.startswith('# '): doc['title'] = line[2:].strip(); continue
        m = re.match(r'^([^:：]{1,4})[:：]\s*(.*)$', line)
        if not m: continue
        k, v = m.group(1).strip(), m.group(2).strip()
        if b is None:
            if k == '一句话': doc['one_thing'] = v
            elif k == '时长': doc['target'] = float(v)
            elif k == '配乐': doc['music'] = v
            elif k == '读音': doc['lexicon'] += [dict(w=w.strip(), say=y.strip()) for w, y in (re.split(r'→|->|=', x, 1) for x in re.split(r'[;；,，]', v) if re.search(r'→|->|=', x))]
            continue
        if k in KEYS: b[KEYS[k]] = float(v) if k == '时长' else v
    if not doc['beats']: raise SystemExit('脚本里没有拍点（每拍以「## 拍点号」开头）')
    return doc


def est(text): return 0.24 * len(re.sub(r'\s', '', text)) + 0.3      # 没配音时按字数估：约每字 0.24 秒


def build(script, film, voice='zh-CN-YunxiNeural', no_voice=False, jobs=6):
    t0 = time.time(); os.makedirs(os.path.join(film, 'vo'), exist_ok=True)
    src = parse(open(script, encoding='utf-8').read())
    os.environ['COCUT_FILM'] = os.path.abspath(film)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import api
    try:
        import edge_tts  # noqa: F401
        can = not no_voice
    except ImportError:
        can = False; print('没装 edge-tts：先按字数估时长，无声预览（pip install edge-tts 后 cli.py voice stale 补配音）')
    beats = []
    for i, s in enumerate(src['beats']):
        b = dict(id=s['id'], shot='sh%d' % i, role=s.get('role', ''), verb=s.get('verb', ''), what=s.get('what', ''), move=s['move'], image=s.get('image'))
        for k in ('hero', 'title', 'caption'):
            if s.get(k): b[k] = s[k]
        if s.get('vo'):
            b['vo'] = dict(text=s['vo'], lead=0.25, dur=round(est(s['vo']), 3), words=[])
            if s.get('say'): b['vo']['say'] = s['say']
        b['_dur'] = s.get('dur'); beats.append(b)

    def speak(b):
        r, code = api.tts(dict(id=b['id'], text=b['vo']['text'], say=api.spoken(b, src['lexicon'])), voice=voice)
        if code != 200: raise RuntimeError(r)
        b['vo'].update(file=r['file'], dur=r['dur'], words=r['words'], said=r['said'])
    if can:
        todo = [b for b in beats if b.get('vo')]
        with ThreadPoolExecutor(jobs) as ex: list(ex.map(speak, todo))     # 并发配音，几十拍也就十几秒
    for b in beats:
        base = (b['vo']['lead'] + b['vo']['dur'] + (0.9 if b.get('title') else 0.45)) if b.get('vo') else 2.5
        b['dur'] = round(b.pop('_dur') or max(2.2, base), 3)
    total = sum(b['dur'] for b in beats)
    doc = dict(title=src['title'], one_thing=src['one_thing'], fps=24, width=1920, height=1080, target=src['target'] or round(total),
               music=dict(file=src['music'], gain=0.3, fade_in=0.5, fade_out=2) if src['music'] else None, vo_gain=1.4,
               style=dict(sub_size=38, sub_plate='rgba(0,0,0,.62)', note_size=26, title_size=88, title_y=520),
               beats=beats, notes=[], lexicon=src['lexicon'], rev=1, voice=voice, made_from=os.path.basename(script))
    p = os.path.join(film, 'doc.json')
    if os.path.exists(p): os.replace(p, p + '.bak')
    json.dump(doc, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    dt = time.time() - t0
    print('草稿好了：%s  %d 拍  %.1f 秒  配音 %s  用时 %.1f 秒' % (p, len(beats), total, '有' if can else '无（估时）', dt))
    return doc, dt


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('script'); ap.add_argument('film')
    ap.add_argument('--voice', default='zh-CN-YunxiNeural'); ap.add_argument('--no-voice', action='store_true'); ap.add_argument('--jobs', type=int, default=6)
    a = ap.parse_args(); build(a.script, a.film, a.voice, a.no_voice, a.jobs)
