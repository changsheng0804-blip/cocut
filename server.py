# cocut 本地服务：把「片子目录」（doc.json + 素材）和交互页 app/ 一起端出来，并提供人和 AI 共用的接口。
# 用法：python3 server.py <片子目录> [端口]      例：python3 server.py examples/lan 8790
import json, os, sys, time, subprocess, mimetypes
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote
ROOT = os.path.dirname(os.path.abspath(__file__)); APP = os.path.join(ROOT, 'app')
FILM = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'examples', 'lan'))
os.environ['COCUT_FILM'] = FILM; sys.path.insert(0, os.path.join(ROOT, 'cocut')); import api, review
JOBS = {}
import threading
CHECK = dict(running=False, pending=False, last=None, seconds=None, error=None, auto=os.environ.get('COCUT_REFLEX', '1') != '0'); RX = {}
_rp = os.path.join(FILM, '.cocut', 'reflex.json')
if os.path.exists(_rp):                                   # 服务重启后接上上次体检的时间
    try: CHECK.update(last=time.strftime('%m-%d %H:%M', time.localtime(os.path.getmtime(_rp))), seconds=json.load(open(_rp)).get('seconds'))
    except Exception: pass

def _check_loop():
    """后台体检：反射层（按内容哈希缓存，只重算改过的拍）→ 开复核单。保存期间又有改动就再跑一轮。"""
    while CHECK['pending']:
        CHECK['pending'] = False
        try:
            sys.path.insert(0, os.path.join(ROOT, 'tools')); import reflex
            if 'rx' not in RX: RX['rx'] = reflex.Reflex(cache=os.path.join(FILM, '.reflex_cache'))
            rep = reflex.check_film(FILM, os.path.join(review._dir(FILM), 'reflex.json'), RX['rx'])
            review.open_tickets(FILM, rep); CHECK.update(last=time.strftime('%H:%M:%S'), seconds=rep['seconds'], error=None)
        except Exception as e: CHECK['error'] = '%s: %s' % (type(e).__name__, e)
    CHECK['running'] = False
    if CHECK['error'] is None and review.list_open(FILM): request_reviewers()

PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8790
REVIEW = dict(running=False, pending=False, who=None, last=None, error=None)

def _reviewers_loop():
    """按 <片子>/.cocut/reviewers.json 依次唤起复核员：先快模型答全部新单，再让 escalate 的强模型只复核红/黄的。"""
    import subprocess
    while REVIEW['pending']:
        REVIEW['pending'] = False
        try: cfg = json.load(open(os.path.join(review._dir(FILM), 'reviewers.json'), encoding='utf-8'))
        except Exception: cfg = []
        for r in cfg:
            if r.get('off'): continue
            REVIEW['who'] = r['by']
            a = [sys.executable, os.path.join(ROOT, 'tools', 'reviewer.py'), '--server', 'http://127.0.0.1:%d' % PORT, '--by', r['by'], '--cmd', r['cmd']]
            if r.get('escalate'): a.append('--escalate')
            p = subprocess.run(a, capture_output=True, text=True)
            REVIEW.update(last=time.strftime('%H:%M:%S') + ' ' + (p.stdout.strip().splitlines() or [''])[-1][:200], error=None if p.returncode == 0 else (p.stderr or p.stdout)[-300:])
    REVIEW.update(running=False, who=None)

def request_reviewers():
    REVIEW['pending'] = True
    if not REVIEW['running']: REVIEW['running'] = True; threading.Thread(target=_reviewers_loop, daemon=True).start()

def request_check():
    CHECK['pending'] = True
    if not CHECK['running']: CHECK['running'] = True; threading.Thread(target=_check_loop, daemon=True).start()

def doc(): return json.load(open(os.path.join(FILM, 'doc.json'), encoding='utf-8'))

def add_note(body):
    """任何参与者（人或任一 AI）留意见：{t|beat, text, by, dim?, sev?, fix?, x?, y?}"""
    d = doc(); notes = d.setdefault('notes', [])
    if not body.get('text'): return {'error': 'text required'}, 400
    beat = body.get('beat'); t = body.get('t'); s = 0
    for b in d['beats']:
        if beat == b['id'] and t is None: t = s + b['dur'] / 2
        if beat is None and t is not None and s <= t < s + b['dur']: beat = b['id']
        s += b['dur']
    n = dict(id='%s%d' % ('N' if body.get('by', 'user') == 'user' else 'A', len(notes) + 1), status='open', by=body.get('by', 'user'),
             made=time.strftime('%Y-%m-%d %H:%M:%S'), t=t or 0, x=body.get('x', 0.5), y=body.get('y', 0.5), beat=beat, text=body['text'])
    for k in ('dim', 'sev', 'fix'):
        if body.get(k): n[k] = body[k]
    notes.append(n); d['saved'] = time.strftime('%Y-%m-%dT%H:%M:%S') + '-' + n['by']
    return api.save(d)[0] | {'note': n}, 200

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode(); self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8'); self.send_header('Content-Length', len(b)); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = urlparse(self.path); p = unquote(u.path)
        if p == '/api/doc': return self._json(doc())
        if p == '/api/plan': return self._json(api.to_plan(doc()))
        if p == '/api/review':                          # 每拍颜色 + 待复核的单；?by=gemini 去掉它答过的
            from urllib.parse import parse_qs; q = parse_qs(u.query); by = (q.get('by') or [None])[0]
            return self._json(dict(status=review.status(FILM), open=review.list_open(FILM, by, bool(q.get('second'))), check=CHECK, reviewers=REVIEW))
        if p.startswith('/api/job/'):
            j = JOBS.get(p.split('/')[-1]); return self._json(j and dict(running=j['p'].poll() is None, rc=j['p'].poll(), log=open(j['log']).read()[-3000:]) or {'error': 'no job'})
        rel = p.lstrip('/').removeprefix('live/') or 'index.html'
        bases = (APP, FILM) if rel in ('index.html', 'live.js') else (FILM, APP)   # 页面本身用平台的，doc.json 和素材用片子目录的
        for base in bases:
            f = os.path.normpath(os.path.join(base, rel))
            if f.startswith(base) and os.path.isfile(f):
                data = open(f, 'rb').read(); self.send_response(200)
                self.send_header('Content-Type', mimetypes.guess_type(f)[0] or 'application/octet-stream'); self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', len(data)); self.end_headers(); return self.wfile.write(data)
        if p in ('/', '/live', '/live/'): self.send_response(302); self.send_header('Location', '/live/index.html'); self.end_headers(); return
        self._json({'error': 'not found'}, 404)
    def do_POST(self):
        p = urlparse(self.path).path; n = int(self.headers.get('Content-Length') or 0)
        try: body = json.loads(self.rfile.read(n) or b'{}')
        except Exception: return self._json({'error': 'bad json'}, 400)
        if p in ('/live/save', '/api/save'):
            r = api.save(body)
            if r[1] == 200 and CHECK['auto']: request_check()      # 改一拍 → 自动重新体检、开新单
            return self._json(*r)
        if p == '/api/review/check': request_check(); return self._json({'ok': True, 'check': CHECK})
        if p in ('/live/tts', '/api/tts'):
            try: return self._json(*api.tts(body))
            except Exception as e: return self._json({'error': str(e)}, 500)
        if p == '/api/note': return self._json(*add_note(body))
        if p == '/api/review/open':                     # {report?}：缺省读 .cocut/reflex.json
            try: return self._json(review.open_tickets(FILM, body.get('report')))
            except FileNotFoundError: return self._json({'error': '还没有体检报告：先跑 tools/reflex.py 或 cli review open --run'}, 409)
        if p == '/api/review/answer':                   # {ticket, by, answers:{"0":"yes"}, note?}
            if not body.get('ticket') or not body.get('by'): return self._json({'error': 'ticket and by required'}, 400)
            return self._json(*review.answer(FILM, body['ticket'], body['by'], body.get('answers') or {}, body.get('note')))
        if p in ('/live/export', '/api/export'):
            jid = time.strftime('export-%H%M%S'); log = os.path.join(FILM, 'job_%s.log' % jid)
            cmd = [sys.executable, os.path.join(ROOT, 'render', 'concat.py')] + (['--final'] if body.get('final', True) else [body.get('ver', 'review')])
            if not body.get('final', True): json.dump(api.to_plan(doc()), open(os.path.join(FILM, 'plan.json'), 'w'), ensure_ascii=False, indent=1)
            JOBS[jid] = dict(p=subprocess.Popen(cmd, cwd=FILM, stdout=open(log, 'w'), stderr=subprocess.STDOUT, env=os.environ.copy()), log=log)
            return self._json({'job': jid})
        self._json({'error': 'unknown endpoint'}, 404)

if __name__ == '__main__':
    port = PORT
    print('cocut: http://localhost:%d/live/  片子：%s' % (port, FILM), flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()
