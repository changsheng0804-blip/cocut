# 通用复核员适配器：从 cocut 服务领单 → 交给某个 AI 答点名是非题 → 把答案交回。两种接法：
#
# 1) 命令行代理（能读文件的 AI CLI，如 agy）：在临时目录放好图/音和 tickets.json，调 --cmd。
#    python3 tools/reviewer.py --by flash --jobs 4 \
#      --cmd 'agy --model gemini-3.8-flash --dangerously-skip-permissions -p {prompt}'
#    --jobs N：把单分成 N 份、N 个进程同时跑（代理逐张开图，单进程很慢）。
#
# 2) 直连模型接口（Gemini generateContent 兼容，如本机 Vertex 桥 http://127.0.0.1:8050）：
#    python3 tools/reviewer.py --by gemini --api http://127.0.0.1:8050 --model gemini-4-argon --jobs 6
#    每张单一次请求，图/音内联，要求 JSON 输出；--jobs 为并发数。没有代理的来回，最快。
#
# 分级：快模型先答全部，强模型加 --escalate 只看红/黄。
import argparse, base64, json, os, shlex, shutil, subprocess, sys, tempfile, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

PROMPT = ('你是审片复核员。打开当前目录的 tickets.json。对每张单：打开它的 image（有 audio 且题目问配音时听 audio），'
          '按 asks 逐题只回答 yes、no 或 unsure；只看点名的这一处，不评价别的，看不清或听不出就答 unsure，不读当前目录以外的文件。'
          '把结果写成 JSON 到 answers.json：{"单号": {"0": "yes", "1": "no"}, ...}（内层键是 asks 的 i），然后回复"完成"。')
API_PROMPT = ('你是审片复核员。下面是一张画面{audio}和几个点名问题。逐题只回答 yes、no 或 unsure；只看点名的这一处，不评价别的，'
              '看不清或听不出就答 unsure。只输出 JSON：{{"题号": "yes|no|unsure", ...}}。\n画面说明：{what}\n{text}问题：\n{asks}')
MIME = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp', '.mp3': 'audio/mpeg', '.wav': 'audio/wav'}


def call(server, path, body=None):
    req = urllib.request.Request(server + path, data=None if body is None else json.dumps(body).encode(), method='GET' if body is None else 'POST')
    return json.load(urllib.request.urlopen(req, timeout=60))


def fetch(server, rel):
    return urllib.request.urlopen(server + '/live/' + rel, timeout=60).read()


def needs_audio(t): return any(q['k'] in ('vo', 'poly') for q in t['asks'])


# ---------- 接法 1：命令行代理 ----------
def run_cli(a, tickets):
    def one(chunk):
        work = tempfile.mkdtemp(prefix='cocut-review-'); slim = []
        for t in chunk:
            x = dict(ticket=t['id'], beat=t['beat'], what=t.get('what'), text=t.get('text'), asks=[dict(i=q['i'], q=q['q']) for q in t['asks']])
            for key in ('image', 'audio') if needs_audio(t) else ('image',):
                if t.get(key):
                    local = '%s_%s%s' % (t['beat'], key, os.path.splitext(t[key])[1])
                    open(os.path.join(work, local), 'wb').write(fetch(a.server, t[key])); x[key] = local
            slim.append(x)
        json.dump(slim, open(os.path.join(work, 'tickets.json'), 'w'), ensure_ascii=False, indent=1)
        r = subprocess.run(a.cmd.replace('{prompt}', shlex.quote(PROMPT)), shell=True, cwd=work, capture_output=True, text=True)
        f = os.path.join(work, 'answers.json'); ans = json.load(open(f, encoding='utf-8')) if os.path.exists(f) else {}
        if not ans: print('这一份没交答案：', (r.stdout + r.stderr)[-400:], file=sys.stderr)
        if not a.keep: shutil.rmtree(work, ignore_errors=True)
        return ans
    n = max(1, min(a.jobs, len(tickets))); chunks = [tickets[i::n] for i in range(n)]
    out = {}
    with ThreadPoolExecutor(n) as ex:
        for ans in ex.map(one, chunks): out.update(ans)
    return out


# ---------- 接法 2：直连模型接口 ----------
def run_api(a, tickets):
    def one(t):
        parts = []
        for key in ('image', 'audio') if needs_audio(t) else ('image',):
            if t.get(key):
                parts.append({'inlineData': {'mimeType': MIME.get(os.path.splitext(t[key])[1].lower(), 'application/octet-stream'),
                                             'data': base64.b64encode(fetch(a.server, t[key])).decode()}})
        asks = '\n'.join('%s. %s' % (q['i'], q['q']) for q in t['asks'])
        parts.append({'text': API_PROMPT.format(audio='、一段配音' if len(parts) > 1 else '', what=t.get('what') or '',
                                                text=('配音文案：%s\n' % t['text']) if needs_audio(t) and t.get('text') else '', asks=asks)})
        body = {'contents': [{'role': 'user', 'parts': parts}], 'generationConfig': {'responseMimeType': 'application/json', 'temperature': 0}}
        url = '%s/v1beta/models/%s:generateContent' % (a.api.rstrip('/'), a.model)
        for attempt in range(5):
            try:
                req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
                r = json.load(urllib.request.urlopen(req, timeout=180))
                txt = ''.join(p.get('text', '') for p in r['candidates'][0]['content']['parts'] if not p.get('thought'))
                txt = txt[txt.find('{'):txt.rfind('}') + 1]
                return t['id'], {str(k): str(v).lower() for k, v in json.loads(txt).items()}
            except Exception as e:                                   # 429 限流 → 指数退避
                err = e; time.sleep((4 * 2 ** attempt) if '429' in str(e) else 2 + attempt * 3)
        print('%s 没答上：%s' % (t['id'], err), file=sys.stderr); return t['id'], None
    out = {}
    with ThreadPoolExecutor(max(1, a.jobs)) as ex:
        for tid, ans in ex.map(one, tickets):
            if ans: out[tid] = ans
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--server', default='http://localhost:8790'); ap.add_argument('--by', required=True)
    ap.add_argument('--cmd'); ap.add_argument('--api'); ap.add_argument('--model', default='gemini-4-argon')
    ap.add_argument('--jobs', type=int, default=1); ap.add_argument('--second', action='store_true'); ap.add_argument('--keep', action='store_true')
    ap.add_argument('--escalate', action='store_true', help='只复核当前判红或黄（拿不准）的单，给强模型做第二意见')
    ap.add_argument('--dry', action='store_true', help='只答不交（测速/对比用），答案打印出来')
    a = ap.parse_args()
    if not (a.cmd or a.api): sys.exit('要么给 --cmd（命令行代理），要么给 --api（直连模型接口）')
    r = call(a.server, '/api/review?by=%s%s' % (a.by, '&second=1' if a.second or a.escalate else ''))
    tickets = r['open']
    if a.escalate:
        hot = {v['ticket'] for v in r['status'].values() if v['color'] in ('red', 'yellow')}
        tickets = [t for t in tickets if t['id'] in hot]
    if not tickets: print(json.dumps(dict(by=a.by, tickets=0, msg='没有待复核的单'), ensure_ascii=False)); return
    t0 = time.time(); ans = run_api(a, tickets) if a.api else run_cli(a, tickets); secs = round(time.time() - t0, 1)
    done = 0
    for t in tickets:
        if t['id'] in ans:
            if not a.dry: call(a.server, '/api/review/answer', dict(ticket=t['id'], by=a.by, answers=ans[t['id']]))
            done += 1
    print(json.dumps(dict(by=a.by, mode='api' if a.api else 'cli', jobs=a.jobs, tickets=len(tickets), answered=done, seconds=secs,
                          **({'answers': ans} if a.dry else {})), ensure_ascii=False))


if __name__ == '__main__':
    main()
