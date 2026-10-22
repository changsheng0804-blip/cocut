# cocut 片子接口：保存 doc.json（自动备份）、重新配音（字级时间）、把 doc 编译成 plan.json
import json, os, shutil, time, subprocess, asyncio
LIVE = os.path.abspath(os.environ.get('COCUT_FILM') or os.getcwd()); HIST = os.path.join(LIVE, 'history')
def save(doc):
    if not isinstance(doc, dict) or not isinstance(doc.get('beats'), list): return {'error': 'not a live doc'}, 400
    os.makedirs(HIST, exist_ok=True); p = os.path.join(LIVE, 'doc.json'); stamp = time.strftime('%Y%m%d-%H%M%S')
    if os.path.exists(p):
        olds = sorted(os.listdir(HIST))
        if not olds or time.time() - os.path.getmtime(os.path.join(HIST, olds[-1])) > 120: shutil.copy2(p, os.path.join(HIST, 'doc_%s.json' % stamp))
    tmp = p + '.tmp'; json.dump(doc, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1); os.replace(tmp, p)
    return {'ok': True, 'saved': stamp}, 200
def tts(body, voice='zh-CN-YunxiNeural'):
    voice = body.get('voice') or voice; rate = body.get('rate') or '-8%'; pitch = body.get('pitch') or '+0Hz'
    import edge_tts
    bid = ''.join(c for c in str(body.get('id', 'x')) if c.isalnum() or c in "-_'")[:40]; text = str(body.get('say') or body.get('text', '')).strip()  # say：配音用的替换文本（如「行」→「航」），字幕仍用 text
    if not text: return {'error': 'empty text'}, 400
    rel = 'vo/%s_%s.mp3' % (bid, time.strftime('%H%M%S')); out = os.path.join(LIVE, rel); words = []
    async def go():
        c = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary='WordBoundary')
        with open(out, 'wb') as f:
            async for ch in c.stream():
                if ch['type'] == 'audio': f.write(ch['data'])
                elif ch['type'] == 'WordBoundary': words.append({'t': ch['offset'] / 1e7, 'd': ch['duration'] / 1e7, 'w': ch['text']})
    asyncio.run(go())
    ff = shutil.which('ffprobe') or os.path.expanduser('~/.local/bin/ffprobe')
    dur = float(subprocess.check_output([ff, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', out]))
    return {'file': rel, 'dur': round(dur, 3), 'words': words}, 200
def to_plan(doc):
    t = 0; plan = {'title': doc['title'], 'fps': doc['fps'], 'width': doc['width'], 'height': doc['height'], 'one_thing': doc.get('one_thing', ''),
                   'beats': [], 'vo': [], 'sfx': [], 'subs': [], 'notes': [], 'music': dict(file=doc['music']['file'], start=0, gain=doc['music']['gain'], fade_out=doc['music']['fade_out']),
                   'vo_gain': doc.get('vo_gain', 1), 'style': doc.get('style', {})}
    for b in doc['beats']:
        s, e = t, t + b['dur']; t = e
        plan['beats'].append(dict(id=b['id'], start=s, end=e, image=b.get('image'), move=b.get('move', 'static'), role=b.get('role'), verb=b.get('verb'), dim=b.get('dim', 0)))
        if b.get('vo') and b['vo'].get('file'):
            v = b['vo']; vs = s + v['lead']
            plan['vo'].append(dict(id=b['id'], file=v['file'], start=vs, dur=v['dur'], text=v['text']))
            if b.get('title'): plan['title_card'] = dict(text=v['text'].split('。')[0], start=vs, end=None)
            else: plan['subs'].append(dict(id='S' + b['id'], start=vs, end=vs + v['dur'], text=v['text'].rstrip('。'), kind='vo'))
        for x in b.get('sfx') or []: plan['sfx'].append(dict(id=b['id'], file=x['file'], start=s + x.get('at', 0), gain=x.get('gain', 1)))
        if b.get('caption'): plan['notes'].append(dict(id='N' + b['id'], start=s + 0.5, end=e - 0.2, text=b['caption'], kind='title' if b.get('title') else 'note'))
    plan['length'] = t
    if 'title_card' in plan: plan['title_card']['end'] = t
    return plan
if __name__ == '__main__':
    json.dump(to_plan(json.load(open(os.path.join(LIVE, 'doc.json')))), open(os.path.join(LIVE, 'plan.json'), 'w'), ensure_ascii=False, indent=1); print('plan.json ok')
