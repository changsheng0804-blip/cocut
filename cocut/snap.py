# 画面快照：用无头 Chrome 打开审片页的快照模式（app/live.js 的 #snap），截出某一时刻的成品画面（PNG）。
# 和审片页同一套渲染（镜头运动、交叉淡化、字幕、小字、片名、压暗），所以 AI 看到的就是人看到的那一帧。
#   python3 cocut/snap.py http://127.0.0.1:8790 out.png --t 12.3 [--hud] [--marks] [--width 960]
#   python3 cocut/snap.py http://127.0.0.1:8790 out.png --beat 2c          （取这拍正中）
# 需要本机装 Chrome/Chromium；路径可用环境变量 COCUT_CHROME 指定。
import os, shutil, subprocess, sys, tempfile
from urllib.parse import quote

CANDIDATES = [os.environ.get('COCUT_CHROME'), '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
              '/Applications/Chromium.app/Contents/MacOS/Chromium', 'google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'chrome']


def chrome():
    for c in CANDIDATES:
        if c and (os.path.isfile(c) or shutil.which(c)): return shutil.which(c) or c
    raise RuntimeError('没找到 Chrome/Chromium，请安装或设置 COCUT_CHROME')


def shot(base, out, t=None, beat=None, hud=False, marks=False, xf=True, width=1920, timeout=40):
    """截一帧到 out（PNG）。base 为 cocut 服务地址，如 http://127.0.0.1:8790。返回 out。"""
    h = 'snap' + ('&beat=' + quote(str(beat)) if beat is not None else '&t=%.3f' % float(t or 0))
    h += ('&hud=1' if hud else '') + ('&marks=1' if marks else '') + ('' if xf else '&xf=0')
    url = base.rstrip('/') + '/live/index.html#' + h
    scale = max(0.1, min(2.0, width / 1920.0)); prof = tempfile.mkdtemp(prefix='cocut-snap-')
    try:
        subprocess.run([chrome(), '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run', '--no-proxy-server',
                        '--user-data-dir=' + prof, '--window-size=1920,1080', '--force-device-scale-factor=%g' % scale,
                        '--virtual-time-budget=8000', '--screenshot=' + os.path.abspath(out), url],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout, check=False)
    finally: shutil.rmtree(prof, ignore_errors=True)
    if not os.path.isfile(out) or os.path.getsize(out) < 1000: raise RuntimeError('截图失败：' + url)
    return out


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument('base'); ap.add_argument('out'); ap.add_argument('--t', type=float); ap.add_argument('--beat')
    ap.add_argument('--hud', action='store_true'); ap.add_argument('--marks', action='store_true'); ap.add_argument('--no-xf', action='store_true'); ap.add_argument('--width', type=int, default=1920)
    a = ap.parse_args(); print(shot(a.base, a.out, a.t, a.beat, a.hud, a.marks, not a.no_xf, a.width))
