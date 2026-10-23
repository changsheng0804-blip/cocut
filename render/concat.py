# 渲染后端（Concat headless MCP）：plan.json -> Concat 工程 -> 审片版 480p（叠拍点号）或 --final 1080p。
# 用法：COCUT_FILM=片子目录 python3 render/concat.py [版本号] [--final]
import json, os, sys, subprocess, shutil, time
HERE = os.path.abspath(os.environ.get('COCUT_FILM') or os.getcwd()); os.chdir(HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'cocut'))
CONCAT = os.environ.get('CONCAT_BIN', '/Applications/Concat.app/Contents/MacOS/concat')
FF = os.environ.get('FFMPEG') or shutil.which('ffmpeg') or os.path.expanduser('~/.local/bin/ffmpeg')
FINAL = '--final' in sys.argv
if FINAL:
    import api as live_api; plan = live_api.to_plan(json.load(open('doc.json')))
else:
    plan = json.load(open('plan.json'))
END = plan['length']; W, H = plan['width'], plan['height']
ver = next((a for a in sys.argv[1:] if not a.startswith('--')), time.strftime('%m%d-%H%M'))
p = subprocess.Popen([CONCAT, '--mcp', 'headless'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=open('mcp.err', 'w'), text=True)
_i = [0]
def rpc(m, params=None):
    _i[0] += 1
    p.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': _i[0], 'method': m, 'params': params or {}}) + '\n'); p.stdin.flush()
    while True:
        l = p.stdout.readline()
        if not l: sys.exit('mcp died: ' + open('mcp.err').read()[-1500:])
        r = json.loads(l)
        if r.get('id') == _i[0]: return r
def C(name, args):
    r = rpc('tools/call', {'name': name, 'arguments': args}); res = r.get('result', r)
    if 'error' in r or res.get('isError'): sys.exit('ERR %s %s' % (name, json.dumps(r, ensure_ascii=False)[:900]))
    return res.get('structuredContent', res)
rpc('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'hark', 'version': '1'}})
p.stdin.write(json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized'}) + '\n'); p.stdin.flush()

PROJ = os.path.join(HERE, 'final_concat' if FINAL else 'preview_concat')
if os.path.exists(PROJ): shutil.rmtree(PROJ)
C('project_create', {'location': HERE, 'name': os.path.basename(PROJ), 'video': {'width': W, 'height': H, 'rateNum': plan['fps'], 'rateDen': 1}})
imp = lambda f: C('media_import', {'path': PROJ, 'file': os.path.join(HERE, f)})['createdId']
def place(mid, start, length=None, track=None):
    a = {'path': PROJ, 'mediaIds': [mid], 'start': start}
    if track: a['trackId'] = track
    cid = C('clips_add_sequence', a)['createdIds'][0] if 'createdIds' in C.__dict__ else None
    return cid
def add(file, start, length=None, track=None):
    mid = imp(file)
    a = {'path': PROJ, 'mediaIds': [mid], 'start': start}
    if track: a['trackId'] = track
    r = C('clips_add_sequence', a)
    cid = (r.get('createdIds') or [r.get('createdId')])[0]
    if length is not None:
        tl = C('timeline_read', {'path': PROJ})['timeline']['clips']
        cur = next(c for c in tl if c['id'] == cid)
        C('clip_trim', {'path': PROJ, 'clipId': cid, 'edge': 'end', 'delta': round(length - cur['duration'], 4)})
    return cid
PF = '"PingFang SC"'
# 画面：每拍一张示意图 + 镜头运动
for b in plan['beats']:
    cid = add(b['image'], b['start'], b['end'] - b['start'], track=None)
    if b['move'] == 'push':
        C('keyframe_set', {'path': PROJ, 'clipId': cid, 'property': 'scale', 'at': 0, 'value': 1.0})
        C('keyframe_set', {'path': PROJ, 'clipId': cid, 'property': 'scale', 'at': 1, 'value': 1.10})
    elif b['move'] in ('pan', 'orbit'):
        C('clip_transform', {'path': PROJ, 'clipId': cid, 'scale': 1.08})
        C('keyframe_set', {'path': PROJ, 'clipId': cid, 'property': 'offsetX', 'at': 0, 'value': 0.03})
        C('keyframe_set', {'path': PROJ, 'clipId': cid, 'property': 'offsetX', 'at': 1, 'value': -0.03})
    b['clip'] = cid
# 声音
if plan['music'].get('file'):                     # 配乐可以没有
    mus = add(plan['music']['file'], 0, END)
    C('clip_update', {'path': PROJ, 'clipId': mus, 'patch': {'volume': plan['music']['gain'], 'fadeOut': plan['music']['fade_out'], 'fadeIn': 0.5}})
for v in plan['vo']:
    vc = add(v['file'], v['start'])
    if plan.get('vo_gain', 1) != 1: C('clip_update', {'path': PROJ, 'clipId': vc, 'patch': {'volume': plan['vo_gain']}})
for x in plan.get('sfx', []):
    xc = add(x['file'], x['start'])
    if x.get('gain', 1) != 1: C('clip_update', {'path': PROJ, 'clipId': xc, 'patch': {'volume': x['gain']}})
# 字
cap = lambda size, weight=400, **k: dict({'fontFamily': PF, 'fontSize': round(size / H, 4), 'fontWeight': weight, 'color': '#ffffff', 'shadow': True}, **k)
C('captions_add', {'path': PROJ, 'offsetY': 0.41, 'style': cap(plan.get('style', {}).get('sub_size', 34), 400, background='#0000009e'),
                   'captions': [{'start': s['start'], 'end': s['end'], 'text': s['text']} for s in plan['subs']]})
for n in plan['notes']:
    if n['kind'] == 'note':
        r = C('title_add', {'path': PROJ, 'start': n['start'], 'duration': n['end'] - n['start'], 'offsetY': -0.4, 'above': True,
                            'style': cap(24, 300, content=n['text'], opacity=0.85)})
        C('clip_update', {'path': PROJ, 'clipId': r['createdId'], 'patch': {'fadeIn': 0.3, 'fadeOut': 0.3}})
tc = plan['title_card']
r = C('title_add', {'path': PROJ, 'start': tc['start'], 'duration': END - tc['start'], 'offsetY': (plan['style'].get('title_y', 520) - 540) / 1080, 'above': True,
                    'style': cap(80, 500, content=tc['text'], tracking=0.003)})
C('clip_update', {'path': PROJ, 'clipId': r['createdId'], 'patch': {'fadeIn': 0.4}})
sub = next((n for n in plan['notes'] if n['kind'] == 'title'), None)
if sub:
    r = C('title_add', {'path': PROJ, 'start': tc['start'] + 0.6, 'duration': END - tc['start'] - 0.6, 'offsetY': (plan['style'].get('title_y', 520) + 105 - 540) / 1080, 'above': True,
                        'style': cap(34, 300, content=sub['text'])})
    C('clip_update', {'path': PROJ, 'clipId': r['createdId'], 'patch': {'fadeIn': 0.5}})
C('project_save', {'path': PROJ})
# 审片层：每拍左上角 拍点号·角色·动词 + 时间（只进审片版，不进工程）
review = []
for b in ([] if FINAL else plan['beats']):
    m, s = divmod(b['start'], 60)
    r = C('title_add', {'path': PROJ, 'start': b['start'], 'duration': b['end'] - b['start'], 'offsetY': -0.44, 'above': True,
                        'style': cap(26, 600, content='%s  %s·%s  %d:%04.1f' % (b['id'], b['role'], b['verb'], m, s), color='#ffe08a',
                                     background='#000000b0', align='left')})
    C('clip_transform', {'path': PROJ, 'clipId': r['createdId'], 'offsetX': -0.36, 'offsetY': -0.44})
    review.append(r['createdId'])
if FINAL:
    os.makedirs(os.path.join(HERE, '..', 'exports'), exist_ok=True); out = os.path.abspath(os.path.join(HERE, '..', 'exports', 'live_%s.mp4' % ver))
else:
    os.makedirs('review', exist_ok=True); out = os.path.join(HERE, 'review', 'preview_%s.mp4' % ver)
t0 = time.time()
j = C('export_start', {'path': PROJ, 'output': out, 'width': W if FINAL else 960, 'height': H if FINAL else 540, 'preset': 'medium' if FINAL else 'veryfast', 'crf': 18 if FINAL else 26})
st = C('export_wait', {'job': j['job'], 'timeoutSeconds': 600})
print('export', st.get('state'), '%.1fs' % (time.time() - t0))
C('clips_remove', {'path': PROJ, 'clipIds': review}) if review else None
C('project_save', {'path': PROJ})   # 工程里不留审片层
if FINAL: print('done', out); sys.exit(0)
# 审片拼图：每拍中点一帧
frames = []
for b in plan['beats']:
    t = (b['start'] + b['end']) / 2; f = 'review/_%s.jpg' % b['id']
    subprocess.run([FF, '-v', 'error', '-y', '-ss', '%.3f' % t, '-i', out, '-frames:v', '1', '-vf', 'scale=480:270', f], check=True); frames.append(f)
args = sum([['-i', f] for f in frames], [])
subprocess.run([FF, '-v', 'error', '-y', *args, '-filter_complex', ''.join('[%d]' % i for i in range(len(frames))) +
                'xstack=inputs=%d:layout=%s' % (len(frames), '|'.join('%d_%d' % ((i % 4) * 480, (i // 4) * 270) for i in range(len(frames)))),
                '-q:v', '4', 'review/sheet_%s.jpg' % ver], check=True)
for f in frames: os.remove(f)
print('done', out)
