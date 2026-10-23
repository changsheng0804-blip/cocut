# 通用复核员适配器：从 cocut 服务领单 → 在临时工作目录里放好图/音和题目 → 调任意能读文件的 AI 命令行 → 收答案交回。
# 用法（Gemini 例，需在能读钥匙串的桌面会话里跑）：
#   python3 tools/reviewer.py --server http://localhost:8790 --by gemini \
#     --cmd 'agy --model gemini-4-argon-high --dangerously-skip-permissions -p {prompt}'
# 分级：快模型先答全部，强模型加 --escalate 只看红/黄。
# 换别的 AI：只换 --cmd（{prompt} 会被替换为已转义的提示词）和 --by。
import argparse, json, os, shlex, shutil, subprocess, sys, tempfile, time, urllib.request

PROMPT = ('你是审片复核员。打开当前目录的 tickets.json。对每张单：打开它的 image（有 audio 且题目问配音时听 audio），'
          '按 asks 逐题只回答 yes、no 或 unsure；只看点名的这一处，不评价别的，看不清或听不出就答 unsure，不读当前目录以外的文件。'
          '把结果写成 JSON 到 answers.json：{"单号": {"0": "yes", "1": "no"}, ...}（内层键是 asks 的 i），然后回复"完成"。')


def call(server, path, body=None):
    req = urllib.request.Request(server + path, data=None if body is None else json.dumps(body).encode(), method='GET' if body is None else 'POST')
    return json.load(urllib.request.urlopen(req, timeout=60))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--server', default='http://localhost:8790'); ap.add_argument('--by', required=True)
    ap.add_argument('--cmd', required=True); ap.add_argument('--second', action='store_true'); ap.add_argument('--keep', action='store_true')
    ap.add_argument('--escalate', action='store_true', help='只复核当前判红或黄（拿不准）的单，给强模型做第二意见')
    a = ap.parse_args()
    r = call(a.server, '/api/review?by=%s%s' % (a.by, '&second=1' if a.second or a.escalate else ''))
    tickets = r['open']
    if a.escalate:
        hot = {v['ticket'] for v in r['status'].values() if v['color'] in ('red', 'yellow')}
        tickets = [t for t in tickets if t['id'] in hot]
    if not tickets: print('没有待复核的单'); return
    work = tempfile.mkdtemp(prefix='cocut-review-'); slim = []
    for t in tickets:
        x = dict(ticket=t['id'], beat=t['beat'], what=t.get('what'), text=t.get('text'), asks=[dict(i=q['i'], q=q['q']) for q in t['asks']])
        need_audio = any(q['k'] in ('vo', 'poly') for q in t['asks'])
        for key in ('image', 'audio') if need_audio else ('image',):
            if t.get(key):
                local = '%s_%s%s' % (t['beat'], key, os.path.splitext(t[key])[1])
                urllib.request.urlretrieve(a.server + '/live/' + t[key], os.path.join(work, local)); x[key] = local
        slim.append(x)
    json.dump(slim, open(os.path.join(work, 'tickets.json'), 'w'), ensure_ascii=False, indent=1)
    t0 = time.time(); cmd = a.cmd.replace('{prompt}', shlex.quote(PROMPT))
    r = subprocess.run(cmd, shell=True, cwd=work, capture_output=True, text=True)
    secs = round(time.time() - t0, 1); f = os.path.join(work, 'answers.json')
    if not os.path.exists(f): sys.exit('复核员没交答案（%ss）：%s' % (secs, (r.stdout + r.stderr)[-800:]))
    ans = json.load(open(f, encoding='utf-8')); done = 0
    for x in slim:
        if x['ticket'] in ans:
            call(a.server, '/api/review/answer', dict(ticket=x['ticket'], by=a.by, answers=ans[x['ticket']])); done += 1
    print(json.dumps(dict(by=a.by, tickets=len(slim), answered=done, seconds=secs, workdir=work if a.keep else None), ensure_ascii=False))
    if not a.keep: shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
