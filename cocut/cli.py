# 给任何 AI（或人）在终端里用的最小命令行：读片子、留意见、改拍点字段。
#   python3 cocut/cli.py show [片子目录]
#   python3 cocut/cli.py note --beat 2c --by claude --dim 画面 --sev 2 "指针穿出表壳" --fix "指针收回表盘内"
#   python3 cocut/cli.py set 2c dur 4.2      （值按 JSON 解析，失败按字符串）
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ap = argparse.ArgumentParser(); ap.add_argument('cmd'); ap.add_argument('args', nargs='*')
ap.add_argument('--film', default=os.environ.get('COCUT_FILM', '.')); ap.add_argument('--beat'); ap.add_argument('--t', type=float)
ap.add_argument('--by', default='user'); ap.add_argument('--dim'); ap.add_argument('--sev', type=int); ap.add_argument('--fix')
a = ap.parse_args(); os.environ['COCUT_FILM'] = os.path.abspath(a.film); import api
P = os.path.join(os.environ['COCUT_FILM'], 'doc.json'); d = json.load(open(P, encoding='utf-8'))
def save(by): d['saved'] = time.strftime('%Y-%m-%dT%H:%M:%S') + '-' + by; print(api.save(d)[0])
if a.cmd == 'show':
    s = 0
    for b in d['beats']:
        print('%-3s %5.1f-%5.1f %-6s %s | 旁白:%s | 小字:%s | 图:%s' % (b['id'], s, s + b['dur'], b.get('move', ''), b.get('what', ''), (b.get('vo') or {}).get('text', ''), b.get('caption', ''), b.get('image')))
        s += b['dur']
    print('open notes:', [(n['id'], n.get('beat'), n['text'][:40]) for n in d.get('notes', []) if n.get('status') != 'done'])
elif a.cmd == 'note':
    n = dict(id='%s%d' % ('N' if a.by == 'user' else 'A', len(d.setdefault('notes', [])) + 1), status='open', by=a.by, made=time.strftime('%Y-%m-%d %H:%M:%S'),
             t=a.t or 0, x=0.5, y=0.5, beat=a.beat, text=' '.join(a.args))
    if a.t is None and a.beat:
        s = 0
        for b in d['beats']:
            if b['id'] == a.beat: n['t'] = s + b['dur'] / 2
            s += b['dur']
    for k in ('dim', 'sev', 'fix'):
        if getattr(a, k) is not None: n[k] = getattr(a, k)
    d['notes'].append(n); save(a.by)
elif a.cmd == 'set':
    bid, key, val = a.args[0], a.args[1], ' '.join(a.args[2:])
    try: val = json.loads(val)
    except Exception: pass
    b = next(x for x in d['beats'] if x['id'] == bid); b[key] = val; save(a.by)
else: sys.exit('未知命令：' + a.cmd)
