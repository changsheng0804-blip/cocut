# 路线 A：反射层答卷 + 计时（冷启动 / 改一拍后增量）
import json, os, sys, time, shutil
sys.path.insert(0, os.path.expanduser('~/hark-sandbox-CS/cocut-lab'))
from reflex import Reflex
FILM = os.path.expanduser('~/hark-sandbox-CS/argon-film/studio/live')
BEN = os.path.expanduser('~/hark-sandbox-CS/cocut-lab/bench')
q = json.load(open(f'{BEN}/questions.json')); beats = q['beats']
cache = f'{BEN}/.cache_A'; shutil.rmtree(cache, ignore_errors=True)
t0 = time.time(); rx = Reflex(cache=cache); load = time.time() - t0
def run():
    ans = {}; t = time.time()
    refs = rx.text_refs([f'{FILM}/hq/hq_{i}.jpg' for i in ('0a', '2b', '5a', '2e')])
    for S in ('S1', 'S2'):
        its = [x for x in q['images'] if x['id'].startswith(S)]
        cov = rx.coverage([(x['id'], beats[x['beat']]['what']) for x in its], [f'{BEN}/{x["image"]}' for x in its])
        for x in its:
            ti = rx.text_in_image(f'{BEN}/{x["image"]}', refs); c = cov.get(x['id'], {})
            ans[x['id']] = dict(text=ti['flag'], swap=c.get('swap', False), bad=ti['flag'] or c.get('flag', False) or c.get('swap', False),
                                missing=c.get('missing', []), text_score=ti['score'], worst=c.get('worst'))
    V = [x for x in q['audio'] if x['id'].startswith('V_')]
    for k, v in rx.vo_match([(x['id'], f'{BEN}/{x["audio"]}', x['text']) for x in V]).items(): ans[k] = dict(mismatch=v['flag'], rank=v['rank'])
    for x in q['audio']:
        if x.get('poly'):
            p = x['poly']; r = rx.polyphone(f'{BEN}/{x["audio"]}', x['text'], p['char'], p['good'], p['bad'])
            ans[x['id']] = dict(misread=r['flag'], **r)
    return ans, time.time() - t
ans, cold = run()
# 改一拍：把 S2_4a 换成另一张图后重跑（只有这一张 + 它的块需要重新嵌入）
p = f'{BEN}/img/S2_4a.jpg'; bak = p + '.bak'; shutil.copy(p, bak)
from PIL import Image; im = Image.open(p); im.transpose(Image.FLIP_LEFT_RIGHT).save(p, quality=88)
h0 = dict(rx.stats); _, warm = run(); shutil.move(bak, p)
json.dump(dict(answers=ans, timing=dict(load_s=round(load, 1), cold_s=round(cold, 1), edit_one_beat_s=round(warm, 1),
          new_embeddings_on_edit=rx.stats['miss'] - h0['miss'])), open(f'{BEN}/answers_A.json', 'w'), ensure_ascii=False, indent=1)
print('A done', round(cold, 1), round(warm, 1))
