"""路线 D：反射层先筛，大模型只复核点名处。
用法：python3 bench_route_d.py build <bench目录>   -> questions_D.json
      python3 bench_route_d.py score <bench目录> <answers_D_x.json> [labels.json]
"""
import json, sys, os

NEAR_TEXT = -0.015   # 文字分接近阈值也送复核

def build(bench):
    q = json.load(open(os.path.join(bench, 'questions.json')))
    A = json.load(open(os.path.join(bench, 'answers_A.json')))['answers']
    beats = q['beats']
    items, skipped = [], []
    for im in q['images']:
        a = A[im['id']]; b = beats[im['beat']]
        asks = []
        if a['text'] or a['text_score'] > NEAR_TEXT:
            asks.append({'k': 'text', 'q': '画面里有没有任何可见的字母、单词或文字（包括小字、手写、编号）？'})
        if a['swap']:
            asks.append({'k': 'swap', 'q': f'这张图画的是不是这个场景：「{b["what"]}」？（不是=画成了别的场景）'})
        for el in a['missing'] if not a['swap'] else []:
            asks.append({'k': 'el', 'el': el, 'q': f'画面里有没有：「{el}」？画错了也算没有；静态图看不出的动作答 unsure。'})
        if asks:
            items.append({'id': im['id'], 'image': im['image'], 'asks': asks})
        else:
            skipped.append(im['id'])
    aud = []
    for au in q['audio']:
        a = A.get(au['id'], {})
        if a.get('mismatch'):
            aud.append({'id': au['id'], 'audio': au['audio'],
                        'asks': [{'k': 'vo', 'q': f'这条音频说的是不是这句话：「{au["text"]}」？'}]})
    out = {'note': '每题回答 yes / no / unsure，只看点名的这一处，不要评价别的。',
           'images': items, 'audio': aud, 'skipped_images': skipped}
    json.dump(out, open(os.path.join(bench, 'questions_D.json'), 'w'), ensure_ascii=False, indent=1)
    n = sum(len(i['asks']) for i in items)
    print(f'送复核图片 {len(items)}/{len(q["images"])}，问题 {n} 个；音频 {len(aud)} 条；直接放行 {len(skipped)} 张')

def decide(asks, ans):
    """ans: {"0": "yes", ...} 按 asks 下标。"""
    text = swap = False; miss = []
    for i, a in enumerate(asks):
        v = str(ans.get(str(i), 'unsure')).lower()
        if a['k'] == 'text' and v == 'yes': text = True
        if a['k'] == 'swap' and v == 'no': swap = True
        if a['k'] == 'el' and v == 'no': miss.append(a['el'])
    return dict(text=text, swap=swap, missing=miss, bad=text or swap or bool(miss))

def score(bench, ans_path, labels=None):
    qd = json.load(open(os.path.join(bench, 'questions_D.json')))
    R = json.load(open(ans_path))
    L = json.load(open(labels or os.path.join(bench, 'labels.json')))
    lab = {i['id']: i['label'] for i in L['items']}
    pred = {i: dict(text=False, swap=False, missing=[], bad=False) for i in qd['skipped_images']}
    for it in qd['images']:
        pred[it['id']] = decide(it['asks'], R.get(it['id'], {}))
    tp = sum(1 for k in lab if lab[k]['bad'] and pred[k]['bad'])
    fp = [k for k in lab if not lab[k]['bad'] and pred[k]['bad']]
    fn = [k for k in lab if lab[k]['bad'] and not pred[k]['bad']]
    nb = sum(1 for k in lab if lab[k]['bad'])
    s2 = [k for k in lab if k.startswith('S2') and lab[k]['bad']]
    res = dict(caught=f'{tp}/{nb}', fp=fp, missed=fn,
               s2=f'{sum(pred[k]["bad"] for k in s2)}/{len(s2)}', pred=pred)
    vo = {}
    for it in qd['audio']:
        v = str(R.get(it['id'], {}).get('0', 'unsure')).lower()
        vo[it['id']] = {'mismatch': v == 'no', 'raw': v}
    res['audio'] = vo
    print(json.dumps({k: v for k, v in res.items() if k != 'pred'}, ensure_ascii=False, indent=1))
    return res

if __name__ == '__main__':
    if sys.argv[1] == 'build': build(sys.argv[2])
    else: score(*sys.argv[2:])
