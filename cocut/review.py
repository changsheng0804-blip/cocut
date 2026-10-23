# cocut 点名复核：反射层先筛，把可疑处开成「复核单」，任何 AI（或人）领单、只答点名的是非题，平台按拍标红/绿。
#
# 流程：
#   1. 反射层体检（tools/reflex.py check_film）→ 报告存 <片子>/.cocut/reflex.json
#   2. open_tickets：按报告给每拍开单；没有疑点的拍直接「绿」；素材或文案变了，旧单自动「过期」
#   3. 复核员 list_open → 看图/听音 → answer（每题 yes / no / unsure）
#   4. status：每拍 green / red / yellow / grey，附理由和谁说的
# 数据都在 <片子>/.cocut/review.json，一个 JSON，人和 AI 都能直接读。
import hashlib, json, os, time

NEAR_TEXT = -0.015          # 文字分接近阈值也送复核（反射层阈值 -0.008）
POSITIVE = {'text': 'yes'}  # 这些题答 yes 说明有问题；其余题（是不是/有没有/读得对不对）答 no 说明有问题
COLORS = {'green': '没问题', 'red': '有问题', 'yellow': '待复核', 'grey': '已过期，需重新体检'}


def _dir(film):
    d = os.path.join(film, '.cocut'); os.makedirs(d, exist_ok=True); return d


def _load(film):
    p = os.path.join(_dir(film), 'review.json')
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {'tickets': {}, 'answers': {}, 'beats': {}}


def _save(film, db):
    p = os.path.join(_dir(film), 'review.json'); tmp = p + '.tmp'
    json.dump(db, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1); os.replace(tmp, p)


def fingerprint(film, b):
    """这一拍「被检查的东西」的指纹：图、画面描述、配音文件、文案、读音要求。任何一样变了，旧单就过期。"""
    h = hashlib.sha1()
    for rel in (b.get('image'), (b.get('vo') or {}).get('file')):
        f = rel and os.path.join(film, rel)
        h.update(open(f, 'rb').read() if f and os.path.exists(f) else b'-')
    vo = b.get('vo') or {}
    h.update(json.dumps([b.get('what'), vo.get('text'), vo.get('say'), vo.get('poly')], ensure_ascii=False).encode())
    return h.hexdigest()[:10]


TILE = ['左上', '上中', '右上', '左中', '正中', '右中', '左下', '下中', '右下']


def asks_for(b, r):
    """把一拍的反射层结果翻译成点名是非题。r = reflex.json 里这一拍。"""
    asks = []; ti = r.get('text_in_image') or {}; cov = r.get('coverage') or {}
    if ti.get('flag') or ti.get('score', -1) > NEAR_TEXT:
        where = TILE[ti['tile']] if isinstance(ti.get('tile'), int) and ti['tile'] < 9 else ''
        asks.append(dict(k='text', tile=ti.get('tile'), q='画面里有没有任何可见的字母、单词或文字（包括小字、手写、编号）？' + (f'重点看{where}。' if where else '')))
    if cov.get('swap'):
        asks.append(dict(k='swap', q=f'这张图画的是不是这个场景：「{b.get("what", "")}」？'))
    else:
        for el in cov.get('missing') or []:
            asks.append(dict(k='el', el=el, q=f'画面里有没有：「{el}」？画错了也算没有；静态图看不出的动作答 unsure。'))
    vo = b.get('vo') or {}
    if (r.get('vo_match') or {}).get('flag'):
        asks.append(dict(k='vo', q=f'这条配音说的是不是这句话：「{vo.get("text", "")}」？'))
    for ch, p in (r.get('polyphone') or {}).items():
        if p.get('flag'):
            py = (vo.get('poly') or {}).get(ch, '')
            asks.append(dict(k='poly', ch=ch, q=f'配音里「{ch}」读的是不是 {py}？'))
    for i, a in enumerate(asks): a['i'] = str(i)
    return asks


def open_tickets(film, report=None):
    """按反射层报告开单。report 缺省读 <片子>/.cocut/reflex.json。返回本次新开/放行/过期的拍。"""
    doc = json.load(open(os.path.join(film, 'doc.json'), encoding='utf-8'))
    if report is None: report = json.load(open(os.path.join(_dir(film), 'reflex.json'), encoding='utf-8'))
    R = report.get('beats', report); db = _load(film); now = time.strftime('%Y-%m-%d %H:%M:%S')
    out = dict(opened=[], cleared=[], stale=[], kept=[])
    for b in doc['beats']:
        if not b.get('image') or b['id'] not in R: continue
        fp = fingerprint(film, b); tid = f'{b["id"]}-{fp}'
        for old in db['tickets'].values():                       # 同一拍的旧单，指纹不同 → 过期
            if old['beat'] == b['id'] and old['fp'] != fp and old['status'] != 'stale':
                old['status'] = 'stale'; out['stale'].append(old['id'])
        if tid in db['tickets'] and db['tickets'][tid]['status'] != 'stale':
            out['kept'].append(tid); continue
        asks = asks_for(b, R[b['id']])
        db['tickets'][tid] = dict(id=tid, beat=b['id'], fp=fp, created=now, image=b.get('image'),
                                  audio=(b.get('vo') or {}).get('file'), what=b.get('what'),
                                  text=(b.get('vo') or {}).get('text'), asks=asks,
                                  status='open' if asks else 'clear')
        out['opened' if asks else 'cleared'].append(tid)
    _save(film, db); return out


def list_open(film, by=None, second=False):
    """待复核的单。给了 by 时，去掉这位复核员已答过的；second=True 时也给别人答过的（要第二意见）。"""
    db = _load(film); ok = ('open', 'answered') if second else ('open',)
    return [t for t in db['tickets'].values() if t['status'] in ok and not (by and by in db['answers'].get(t['id'], {}))]


def answer(film, tid, by, answers, note=None):
    """复核员交答案：answers = {"0": "yes", "1": "no"}，键是 asks 的下标。"""
    db = _load(film); t = db['tickets'].get(tid)
    if not t: return {'error': f'没有这张单：{tid}'}, 404
    if t['status'] == 'stale': return {'error': '这张单已过期（素材或文案改过），请重新体检后领新单'}, 409
    clean = {}
    for a in t['asks']:
        v = str(answers.get(a['i'], 'unsure')).strip().lower()
        clean[a['i']] = v if v in ('yes', 'no', 'unsure') else 'unsure'
    db['answers'].setdefault(tid, {})[by] = dict(answers=clean, at=time.strftime('%Y-%m-%d %H:%M:%S'), **({'note': note} if note else {}))
    t['status'] = 'answered'; _save(film, db)
    return {'ok': True, 'ticket': tid, 'verdict': verdict(t, db['answers'][tid])}, 200


def verdict(t, by_reviewer):
    """每题：说「有问题」的人数 ≥ 说「没问题」的人数且至少 1 人 → 有问题；全 unsure → 待定。
    人（by=user）答过就以人为准：人是最终裁决。"""
    problems, unsure = [], []; final = 'user' in by_reviewer
    if final: by_reviewer = {'user': by_reviewer['user']}
    for a in t['asks']:
        bad_v = POSITIVE.get(a['k'], 'no'); good_v = 'no' if bad_v == 'yes' else 'yes'
        votes = {r: x['answers'].get(a['i'], 'unsure') for r, x in by_reviewer.items()}
        nb = [r for r, v in votes.items() if v == bad_v]; ng = [r for r, v in votes.items() if v == good_v]
        if nb and len(nb) >= len(ng):
            problems.append(dict(k=a['k'], what=a.get('el') or a.get('ch') or a['k'], by=nb, against=ng))
        elif not nb and not ng: unsure.append(a.get('el') or a['k'])
    color = 'red' if problems else 'yellow' if unsure and len(unsure) == len(t['asks']) else 'green'
    return dict(color=color, problems=problems, unsure=unsure, reviewers=sorted(by_reviewer), final=final)


def status(film):
    """每拍当前颜色：取这一拍最新一张单；若 doc 里这一拍已改（指纹对不上）→ grey，等重新体检。"""
    db = _load(film); latest = {}
    try: cur_fp = {b['id']: fingerprint(film, b) for b in json.load(open(os.path.join(film, 'doc.json'), encoding='utf-8'))['beats'] if b.get('image')}
    except Exception: cur_fp = {}
    for t in db['tickets'].values():
        if t['status'] == 'stale': latest.setdefault(t['beat'], t); continue
        cur = latest.get(t['beat'])
        if not cur or cur['status'] == 'stale' or t['created'] >= cur['created']: latest[t['beat']] = t
    out = {}
    for bid, t in latest.items():
        base = dict(ticket=t['id'], asks=t['asks'], answers=db['answers'].get(t['id'], {}))
        if t['status'] == 'stale' or (bid in cur_fp and cur_fp[bid] != t['fp']): out[bid] = dict(base, color='grey'); continue
        elif t['status'] == 'clear' and not base['answers']: out[bid] = dict(base, color='green', reviewers=['reflex'])
        elif t['status'] == 'open': out[bid] = dict(base, color='yellow', problems=[], unsure=[])
        else: out[bid] = dict(base, **verdict(t, base['answers']))
    for bid in cur_fp:
        if bid not in out: out[bid] = dict(color='grey', ticket=None, asks=[], answers={})
    return out
