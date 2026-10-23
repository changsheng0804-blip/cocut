# 离线混音：按交互页（live.js）同样的规则把配乐（含淡入淡出、duck）、旁白、音效混成一条 wav。
# 用途：给能听声音的 AI 审听；也可作为导出端的成品音轨（导出端因此自动支持 duck）。
# 用法：python3 tools/mixdown.py <片子目录> out.wav [起点秒 终点秒]
import json, os, sys, subprocess, shutil
import numpy as np
SR = 48000
FF = os.environ.get('FFMPEG') or shutil.which('ffmpeg') or os.path.expanduser('~/.local/bin/ffmpeg')
def load(p):
    raw = subprocess.check_output([FF, '-v', 'error', '-i', p, '-f', 'f32le', '-ac', '2', '-ar', str(SR), '-'])
    return np.frombuffer(raw, np.float32).reshape(-1, 2)
film = sys.argv[1]; out = sys.argv[2]; d = json.load(open(os.path.join(film, 'doc.json'), encoding='utf-8'))
t = 0
for b in d['beats']: b['_s'] = t; t += b['dur']; b['_e'] = t
L = t; n = int(L * SR) + 1; mix = np.zeros((n, 2), np.float32)
def put(buf, start, gain):
    i = int(round(start * SR)); j0 = max(0, -i); i = max(0, i); k = min(n - i, len(buf) - j0)
    if k > 0: mix[i:i + k] += buf[j0:j0 + k] * gain
m = d.get('music') or {}; mb = load(os.path.join(film, m['file'])) if m.get('file') else np.zeros((n, 2), np.float32)   # 配乐可以没有
if len(mb) < n: mb = np.tile(mb, (n // len(mb) + 1, 1))
mb = mb[:n]; tt = np.arange(n) / SR
k = np.clip(np.minimum(tt / max(m.get('fade_in', 0.01), 1e-3), (L - tt) / max(m.get('fade_out', 0.01), 1e-3)), 0, 1)
for b in d['beats']:
    if b.get('duck') is None: continue
    r = b.get('duck_release') or 0.8; a = b.get('duck_attack') or 0.04; du = b['duck']; dd = np.ones(n)
    s1 = (tt >= b['_s'] - a) & (tt < b['_s']); dd[s1] = 1 - (tt[s1] - b['_s'] + a) / a * (1 - du)
    s2 = (tt >= b['_s']) & (tt < b['_e']); dd[s2] = du
    s3 = (tt >= b['_e']) & (tt < b['_e'] + r); dd[s3] = du + (tt[s3] - b['_e']) / r * (1 - du)
    k *= np.clip(dd, 0, 1)
mix += mb * (m['gain'] * k)[:, None]
for b in d['beats']:
    if b.get('vo') and b['vo'].get('file'): put(load(os.path.join(film, b['vo']['file'])), b['_s'] + b['vo']['lead'], d.get('vo_gain', 1))
    for x in b.get('sfx') or []: put(load(os.path.join(film, x['file'])), b['_s'] + x.get('at', 0), 1 if x.get('gain') is None else x['gain'])
if len(sys.argv) > 4: mix = mix[int(float(sys.argv[3]) * SR):int(float(sys.argv[4]) * SR)]
peak = float(np.abs(mix).max()); print('length %.2fs peak %.3f%s' % (len(mix) / SR, peak, '  CLIPPING' if peak > 1 else ''))
subprocess.run([FF, '-v', 'error', '-y', '-f', 'f32le', '-ac', '2', '-ar', str(SR), '-i', '-', out], input=np.clip(mix, -1, 1).astype(np.float32).tobytes(), check=True)
