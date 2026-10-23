# cocut 本地服务：把「片子目录」（doc.json + 素材）和交互页 app/ 一起端出来，并提供人和 AI 共用的接口。
# 用法：python3 server.py <片子目录> [端口]      例：python3 server.py examples/lan 8790
import json, os, sys, time, subprocess, mimetypes, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, unquote
ROOT = os.path.dirname(os.path.abspath(__file__)); APP = os.path.join(ROOT, 'app')
FILM = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'examples', 'lan'))
os.environ['COCUT_FILM'] = FILM; sys.path.insert(0, os.path.join(ROOT, 'cocut')); import api
JOBS = {}
# ---- AI 智能审核：交给独立插件 cocheck（https://github.com/changsheng0804-blip/cocheck），这里只做转发 ----
# cocheck 自己监视 doc.json：一保存就体检、开单、唤起复核员。没开 cocheck 服务时页面上的复核功能静默不显示。
import urllib.request, urllib.error
COCHECK = os.environ.get('COCHECK_URL', 'http://127.0.0.1:8796').rstrip('/')
CPROJ = os.environ.get('COCHECK_PROJECT') or os.path.basename(FILM.rstrip('/'))
CHDR = {'Content-Type': 'application/json', **({'Authorization': 'Bearer ' + os.environ['COCHECK_TOKEN']} if os.environ.get('COCHECK_TOKEN') else {})}

def cocheck(path, body=None, retry=True):
    url = '%s/v1/projects/%s%s' % (COCHECK, CPROJ, path)
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), headers=CHDR)
    try: return json.load(urllib.request.urlopen(req, timeout=30)), 200
    except urllib.error.HTTPError as e:
        if e.code == 404 and retry:                      # 项目还没登记 → 自动登记这部片子
            try:
                r = urllib.request.Request(COCHECK + '/v1/projects', data=json.dumps(dict(name=CPROJ, adapter='cocut', path=FILM)).encode(), headers=CHDR)
                urllib.request.urlopen(r, timeout=30); return cocheck(path, body, False)
            except Exception: pass
        try: return json.load(e), e.code
        except Exception: return {'error': 'cocheck %d' % e.code}, e.code
    except Exception as e: return {'error': 'cocheck 服务没连上（%s）：%s' % (COCHECK, e)}, 503

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
        if p == '/api/review':                          # 转发 cocheck：每拍颜色、体检/复核员状态
            return self._json(*cocheck('/status'))
        if p in ('/api/frame', '/live/frame'):          # 画面快照：?t=12.3 或 ?beat=2c [&hud=1&marks=1&xf=0&width=960] → PNG
            import snap, tempfile
            from urllib.parse import parse_qs
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            if 't' not in q and 'beat' not in q: return self._json({'error': 't or beat required'}, 400)
            out = os.path.join(tempfile.gettempdir(), 'cocut-frame-%d.png' % threading.get_ident())
            try: snap.shot('http://127.0.0.1:%d' % self.server.server_port, out, q.get('t'), q.get('beat'), q.get('hud') == '1', q.get('marks') == '1', q.get('xf') != '0', int(q.get('width') or 1920))
            except Exception as e: return self._json({'error': str(e)}, 500)
            data = open(out, 'rb').read(); os.remove(out); self.send_response(200); self.send_header('Content-Type', 'image/png')
            self.send_header('Cache-Control', 'no-store'); self.send_header('Content-Length', len(data)); self.end_headers(); return self.wfile.write(data)
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
        if p in ('/live/save', '/api/save'): return self._json(*api.save(body))     # cocheck 监视 doc.json，自动重新体检
        if p == '/api/review/check': return self._json(*cocheck('/check', {}))
        if p in ('/live/tts', '/api/tts'):
            try: return self._json(*api.tts(body))
            except Exception as e: return self._json({'error': str(e)}, 500)
        if p == '/api/note': return self._json(*add_note(body))
        if p == '/api/review/answer':                   # {ticket, by, answers:{"0":"yes"}, note?} → cocheck
            if not body.get('ticket') or not body.get('by'): return self._json({'error': 'ticket and by required'}, 400)
            return self._json(*cocheck('/answer', body))
        if p in ('/live/export', '/api/export'):
            jid = time.strftime('export-%H%M%S'); log = os.path.join(FILM, 'job_%s.log' % jid)
            cmd = [sys.executable, os.path.join(ROOT, 'render', 'concat.py')] + (['--final'] if body.get('final', True) else [body.get('ver', 'review')])
            if not body.get('final', True): json.dump(api.to_plan(doc()), open(os.path.join(FILM, 'plan.json'), 'w'), ensure_ascii=False, indent=1)
            JOBS[jid] = dict(p=subprocess.Popen(cmd, cwd=FILM, stdout=open(log, 'w'), stderr=subprocess.STDOUT, env=os.environ.copy()), log=log)
            return self._json({'job': jid})
        self._json({'error': 'unknown endpoint'}, 404)

if __name__ == '__main__':
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8790
    print('cocut: http://localhost:%d/live/  片子：%s' % (port, FILM), flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()
