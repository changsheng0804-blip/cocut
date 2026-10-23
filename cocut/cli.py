# 给任何 AI（或人）在终端里用的最小命令行：读片子、留意见、改拍点字段。
#   python3 cocut/cli.py new script.md 片子目录     从文字脚本出可播的预览草稿（配音+文字卡，不出图不渲染），见 cocut/draft.py
#   python3 cocut/cli.py show [片子目录]
#   python3 cocut/cli.py note --beat 2c --by claude --dim 画面 --sev 2 "指针穿出表壳" --fix "指针收回表盘内"
#   python3 cocut/cli.py note --t 24.5 --x 0.5 --y 0.93 --by gemini "字幕压住了表盘"   （看着 frame 快照点位置：自动落到那份素材，图/字幕/小字）
#   python3 cocut/cli.py set 2c dur 4.2      （值按 JSON 解析，失败按字符串）
# 读音（全片读音表 doc.lexicon + 拍点 vo.say 覆盖；改了读法的配音自动算过期）：
#   python3 cocut/cli.py readings                         每拍：原文 → 实际念的，过期的标出来
#   python3 cocut/cli.py lex add 六百万行 六百万航 --py 行=háng --note "代码行数"
#   python3 cocut/cli.py lex rm 六百万行   |   lex list
#   python3 cocut/cli.py say 2c "六百万航老代码"      （单拍覆盖；say 2c --clear 去掉，回到读音表）
#   python3 cocut/cli.py voice stale | voice 2c          按当前读法重新配音（需要 edge-tts）
# 画面快照（审片页同一套渲染截一帧 PNG，需要 cocut 服务在跑、本机有 Chrome；服务地址 COCUT_URL，默认 http://127.0.0.1:8790）：
#   python3 cocut/cli.py frame 12.3 -o f.png | frame 2c | frame all --dir shots/ [--hud] [--width 960]
# AI 智能审核已拆成独立插件 cocheck（体检、复核单、复核员、统一模型接入口），这里只转发到它的 HTTP 服务：
#   python3 cocut/cli.py review status | list --by gemini | answer <单号> --by gemini '{"0":"no"}' | check
#   更多（换模型、并发、远端模型）直接用 cocheck 命令行，见 cocheck 仓库 README。
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if sys.argv[1:2] == ['new']:                     # 从文字脚本出预览草稿：cli.py new script.md 片子目录 [--voice ...] [--no-voice]
    sys.argv = [sys.argv[0]] + sys.argv[2:]; import runpy; runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'draft.py'), run_name='__main__'); sys.exit()
ap = argparse.ArgumentParser(); ap.add_argument('cmd'); ap.add_argument('args', nargs='*')
ap.add_argument('--film', default=os.environ.get('COCUT_FILM', '.')); ap.add_argument('--beat'); ap.add_argument('--t', type=float); ap.add_argument('--x', type=float); ap.add_argument('--y', type=float)
ap.add_argument('--by', default='user'); ap.add_argument('--dim'); ap.add_argument('--sev', type=int); ap.add_argument('--fix')
ap.add_argument('--second', action='store_true'); ap.add_argument('--py', action='append', default=[]); ap.add_argument('--note'); ap.add_argument('--clear', action='store_true'); ap.add_argument('-o', '--out'); ap.add_argument('--dir', default='.'); ap.add_argument('--hud', action='store_true'); ap.add_argument('--width', type=int, default=1920)
a = ap.parse_intermixed_args(); os.environ['COCUT_FILM'] = os.path.abspath(a.film); import api
P = os.path.join(os.environ['COCUT_FILM'], 'doc.json'); d = api.pin_said(json.load(open(P, encoding='utf-8')))
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
    if a.x is not None and a.y is not None:                            # 看着快照点的位置 → 落到对应素材
        n.update(x=a.x, y=a.y); n['layer'] = api.layer_at(d, n['t'], a.x, a.y); n['beat'] = n['layer']['beat']; print('落在：', n['layer'])
    d['notes'].append(n); save(a.by)
elif a.cmd == 'set':
    bid, key, val = a.args[0], a.args[1], ' '.join(a.args[2:])
    try: val = json.loads(val)
    except Exception: pass
    b = next(x for x in d['beats'] if x['id'] == bid); b[key] = val; save(a.by)
elif a.cmd == 'readings':
    lex = d.get('lexicon') or []
    for b in d['beats']:
        if not b.get('vo'): continue
        sp = api.spoken(b, lex); pl = api.poly(b, lex)
        print('%-3s %s%s%s%s' % (b['id'], b['vo']['text'], '' if sp == b['vo']['text'] else ' → ' + sp, ' ' + json.dumps(pl, ensure_ascii=False) if pl else '',
                                 '  ⚠ 配音过期（上次念的：%s）' % api.said(b) if api.reading_stale(b, lex) else ''))
    print('读音表：', '；'.join('%s→%s%s' % (e['w'], e['say'], ' ' + json.dumps(e['py'], ensure_ascii=False) if e.get('py') else '') for e in lex) or '空')
elif a.cmd == 'lex':
    lex = d.setdefault('lexicon', []); sub = (a.args or ['list'])[0]
    if sub == 'list': print(json.dumps(lex, ensure_ascii=False, indent=1))
    elif sub == 'add':
        w, say = a.args[1], a.args[2]; e = dict(w=w, say=say)
        if a.py: e['py'] = dict(x.split('=', 1) for x in a.py)
        if a.note: e['note'] = a.note
        d['lexicon'] = [x for x in lex if x.get('w') != w] + [e]; save(a.by)
    elif sub == 'rm': d['lexicon'] = [x for x in lex if x.get('w') != a.args[1]]; save(a.by)
    else: sys.exit('lex 子命令：list / add / rm')
elif a.cmd == 'say':
    b = next(x for x in d['beats'] if x['id'] == a.args[0])
    if not b.get('vo'): sys.exit('%s 没有旁白' % b['id'])
    if a.clear: b['vo'].pop('say', None)
    else: b['vo']['say'] = ' '.join(a.args[1:])
    save(a.by)
elif a.cmd == 'voice':
    lex = d.get('lexicon') or []; which = a.args[0] if a.args else 'stale'
    ids = [b['id'] for b in d['beats'] if b.get('vo') and (api.reading_stale(b, lex) or b['vo'].get('stale') or not b['vo'].get('file'))] if which == 'stale' else [which]
    for bid in ids:
        r, code = api.voice(d, bid); print(bid, '✓ %ss 念：%s' % (r['dur'], r['said']) if code == 200 else '✗ ' + str(r))
    if ids: save(a.by)
    else: print('没有过期的配音')
elif a.cmd == 'frame':
    import snap; U = os.environ.get('COCUT_URL', 'http://127.0.0.1:8790'); w = (a.args or ['all'])[0]
    ids = [b['id'] for b in d['beats']]
    if w == 'all':
        os.makedirs(a.dir, exist_ok=True)
        from concurrent.futures import ThreadPoolExecutor                     # 每帧一个无头 Chrome，3 个并行
        with ThreadPoolExecutor(int(os.environ.get('COCUT_SNAP_JOBS', 3))) as ex:
            for f in ex.map(lambda bid: snap.shot(U, os.path.join(a.dir, 'frame_%s.png' % bid), beat=bid, hud=a.hud, width=a.width), ids): print(f)
    elif w in ids: print(snap.shot(U, a.out or 'frame_%s.png' % w, beat=w, hud=a.hud, width=a.width))
    else: print(snap.shot(U, a.out or 'frame_%s.png' % w, t=float(w), hud=a.hud, width=a.width))
elif a.cmd == 'review':
    import urllib.request
    U = os.environ.get('COCHECK_URL', 'http://127.0.0.1:8796').rstrip('/') + '/v1/projects/' + (os.environ.get('COCHECK_PROJECT') or os.path.basename(os.environ['COCUT_FILM'].rstrip('/')))
    def http(path, body=None):
        r = urllib.request.Request(U + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json', **({'Authorization': 'Bearer ' + os.environ['COCHECK_TOKEN']} if os.environ.get('COCHECK_TOKEN') else {})})
        return json.load(urllib.request.urlopen(r, timeout=60))
    sub = (a.args or ['status'])[0]
    if sub == 'status':
        for bid, v in http('/status')['status'].items():
            print('%-3s %-6s %s' % (bid, v['color'], '；'.join('%s（%s%s）' % (p['what'], ','.join(p['by']), '；%s 不同意' % ','.join(p['against']) if p['against'] else '') for p in v.get('problems', []))))
    elif sub == 'list': print(json.dumps(http('/tickets?by=%s%s' % (a.by, '&second=1' if a.second else ''))['tickets'], ensure_ascii=False, indent=1))
    elif sub == 'answer': print(json.dumps(http('/answer', dict(ticket=a.args[1], by=a.by, answers=json.loads(a.args[2]), note=a.fix)), ensure_ascii=False))
    elif sub == 'check': print(json.dumps(http('/check', {}), ensure_ascii=False))
    else: sys.exit('review 子命令：status / list / answer / check')
else: sys.exit('未知命令：' + a.cmd)
