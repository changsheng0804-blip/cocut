# EmbeddingGemma 2 × 《懒》实验：能否用毫秒级本地嵌入替代/超过之前靠大模型审片发现的问题
import json, os, sys, time, re
os.environ.setdefault('HF_HUB_OFFLINE', '1')
import numpy as np, torch
from PIL import Image
from sentence_transformers import SentenceTransformer
FILM = os.path.expanduser('~/hark-sandbox-CS/argon-film/studio/live')
d = json.load(open(os.path.join(FILM, 'doc.json'), encoding='utf-8'))
B = d['beats']; ids = [b['id'] for b in B]; R = {}
t0 = time.time()
dev = 'mps' if torch.backends.mps.is_available() else 'cpu'
model = SentenceTransformer('google/embeddinggemma-2', device=dev, model_kwargs={'torch_dtype': torch.float32})
R['load_s'] = round(time.time() - t0, 1); R['device'] = dev
def enc(x, prompt=None):
    t = time.time(); e = model.encode(x, prompt_name=prompt, normalize_embeddings=True, batch_size=4, convert_to_numpy=True); return e, time.time() - t
def img(p):
    im = Image.open(os.path.join(FILM, p)).convert('RGB'); im.thumbnail((896, 896)); return {'image': im}

# 三个版本的画面：r2=Gemini 审过的版本（8 拍被判有画面问题），r3=按意见重画的示意图，hq=当前高清
OLD = {'1b': 'b1b.jpg', '2c': 'r2_b2b.jpg', '3a': 'b2e.jpg', '3b': 'b3a.jpg', '3c': 'b3b.jpg', '4a': 'b4a.jpg', '5b': 'b5b.jpg', '5c': 'b5c.jpg'}
BAD = set(OLD)  # Gemini 判画面/事实/叙事有问题的拍（G2-G5, G7-G9, G11）
ver = {'r2': [], 'r3': [], 'hq': []}
for b in B:
    sk = b['image_sketch']
    ver['r3'].append(sk); ver['hq'].append(b['image'])
    ver['r2'].append('sketch/' + OLD[b['id']] if b['id'] in OLD else sk)
what = [b.get('what', '') for b in B]
vo = [(b.get('vo') or {}).get('text') or (b.get('caption') or b.get('what', '')) for b in B]
Ew, tw = enc(what, 'Retrieval-query'); Ev, _ = enc(vo, 'Retrieval-query')
R['text_encode_ms_per_item'] = round(tw / len(what) * 1000)
E = {}; R['image_encode_ms_per_item'] = {}
for k, ps in ver.items():
    E[k], ti = enc([img(p) for p in ps]); R['image_encode_ms_per_item'][k] = round(ti / len(ps) * 1000)

def align(Et, Ei):
    S = Et @ Ei.T; n = len(S)
    diag = np.diag(S); rank_t2i = [int((S[i] > S[i, i]).sum()) + 1 for i in range(n)]
    # 相对分：自己这拍的匹配度减去该图与其他拍文字的平均匹配度（去掉"这张图本身好匹配"的偏置）
    z = [(S[i, i] - np.delete(S[:, i], i).mean()) / (np.delete(S[:, i], i).std() + 1e-6) for i in range(n)]
    return S, diag, rank_t2i, np.array(z)
def auc(scores, bad):  # 分数越低越可疑；bad 为真标签
    pos = [s for s, b in zip(scores, bad) if b]; neg = [s for s, b in zip(scores, bad) if not b]
    return float(np.mean([1.0 if p < q else 0.5 if p == q else 0 for p in pos for q in neg]))
badv = [i in BAD for i in ids]
R['align'] = {}
for k in ver:
    for tk, Et in (('what', Ew), ('vo', Ev)):
        S, diag, rank, z = align(Et, E[k])
        R['align'][f'{k}/{tk}'] = dict(top1=float(np.mean([r == 1 for r in rank])), mean_rank=float(np.mean(rank)),
            mean_diag=round(float(diag.mean()), 4), mean_z=round(float(z.mean()), 2),
            auc_vs_gemini=round(auc(z, badv), 3) if k == 'r2' else None,
            per_beat={i: dict(rank=r, z=round(float(zz), 2), sim=round(float(s), 3)) for i, r, zz, s in zip(ids, rank, z, diag)})
# r2 → r3：被判坏的 8 拍重画后对齐分是否上升（嵌入能否"看见"修复）
S2 = align(Ew, E['r2'])[3]; S3 = align(Ew, E['r3'])[3]; Sh = align(Ew, E['hq'])[3]
R['fix_delta'] = {i: dict(r2=round(float(a), 2), r3=round(float(b), 2), hq=round(float(c), 2)) for i, a, b, c in zip(ids, S2, S3, Sh)}
# 画面一致性：相邻拍、全片两两相似度（风格是否统一）
def coh(Ei):
    S = Ei @ Ei.T; n = len(S); off = S[~np.eye(n, dtype=bool)]
    return dict(mean_pair=round(float(off.mean()), 3), min_pair=round(float(off.min()), 3), adj=[round(float(S[i, i + 1]), 3) for i in range(n - 1)])
R['coherence'] = {k: coh(E[k]) for k in ver}
# 零样本检测：画面里有没有英文字、有没有 Twin（Gemini 意见里的两类常见问题）
probes = ['画面中有醒目的英文文字标注', '纯插画画面，没有任何文字', '一颗淡紫色小星星角色', '黑白漫画分格']
Ep, _ = enc(probes, 'Classification')
R['probes'] = {k: {i: [round(float(x), 3) for x in row] for i, row in zip(ids, E[k] @ Ep.T)} for k in ('r2', 'hq')}
# 意见：定位到拍点 + 维度分派（用 Gemini 意见自带的 [维度] 标签和 beat 字段做真值）
notes = [n for n in d['notes'] if n.get('beat')]
ntext = [re.sub(r'^\[[^\]]*\]\s*', '', n['text']) for n in notes]
En, _ = enc(ntext, 'Retrieval-query')
beatdoc = [f"{b.get('what','')} {(b.get('vo') or {}).get('text','')} {b.get('caption') or ''}" for b in B]
Eb, _ = enc(beatdoc, 'Retrieval-document')
Eimg = E['hq']
loc = []
for n, e in zip(notes, En):
    s = e @ Eb.T; order = [ids[j] for j in np.argsort(-s)]
    loc.append(dict(id=n['id'], true=n['beat'], top3=order[:3], hit1=order[0] == n['beat'], hit3=n['beat'] in order[:3]))
R['note_locate'] = dict(hit1=float(np.mean([x['hit1'] for x in loc])), hit3=float(np.mean([x['hit3'] for x in loc])), items=loc)
dims = {'画面': '画面构图、插画内容、图像质量问题', '字幕': '字幕、画面小字的可读性与样式问题', '声音': '配音、配乐、音效、音频问题', '事实': '事实准确性、与官方资料不符', '叙事': '叙事结构、节奏、文案逻辑问题'}
Ed, _ = enc(list(dims.values()), 'Classification'); En2, _ = enc(ntext, 'Classification')
dl = list(dims); cls = []
for n, e in zip(notes, En2):
    m = re.match(r'^\[([^/\]]+)', n['text']); pred = dl[int(np.argmax(e @ Ed.T))]
    cls.append(dict(id=n['id'], true=m.group(1) if m else None, pred=pred))
lab = [c for c in cls if c['true']]
R['note_dim'] = dict(acc_on_gemini=round(float(np.mean([c['true'] == c['pred'] for c in lab])), 3) if lab else None, items=cls)
# 音频：旁白音频 ↔ 文本 跨模态检索；2b 旧读音(xíng) vs 新读音(háng)
vb = [b for b in B if (b.get('vo') or {}).get('file')]
Ea, ta = enc([{'audio': os.path.join(FILM, b['vo']['file'])} for b in vb])
R['audio_encode_ms_per_item'] = round(ta / len(vb) * 1000)
Et2, _ = enc([b['vo']['text'] for b in vb], 'Retrieval-query')
Sa = Et2 @ Ea.T; ra = [int((Sa[i] > Sa[i, i]).sum()) + 1 for i in range(len(vb))]
R['audio_text'] = dict(n=len(vb), top1=float(np.mean([r == 1 for r in ra])), mean_rank=float(np.mean(ra)), per={b['id']: r for b, r in zip(vb, ra)})
old2b, new2b = os.path.join(FILM, 'vo/2b_r3_092201.mp3'), os.path.join(FILM, 'vo/2b_024748.mp3')
Eo, _ = enc([{'audio': old2b}, {'audio': new2b}])
Eq, _ = enc(['六百万行（háng）老代码，几周就拆解重构。', '六百万行（xíng）老代码，几周就拆解重构。', '六百万航老代码，几周就拆解重构。'], 'Retrieval-query')
R['2b_reading'] = {'old_xing_audio': [round(float(x), 4) for x in Eo[0] @ Eq.T], 'new_hang_audio': [round(float(x), 4) for x in Eo[1] @ Eq.T], 'audio_audio_sim': round(float(Eo[0] @ Eo[1]), 4)}
# 音效检索：用拍点描述在音效库里找声音（先检索后生成）
sfx = sorted(os.listdir(os.path.join(FILM, 'sfx'))); Es, _ = enc([{'audio': os.path.join(FILM, 'sfx', f)} for f in sfx])
R['sfx_retrieval'] = {f: [ids[j] for j in np.argsort(-(Es[k] @ Ew.T))[:3]] for k, f in enumerate(sfx)}
R['sfx_used'] = {x['file']: b['id'] for b in B for x in b.get('sfx') or []}
# 跨模态"以文搜片"：自然语言找镜头
qs = ['红色危险按键', '机器人投沙包', '清晨的咖啡', '代码城市', '古寺宝塔', '书桌上的小赛车']
Eqs, _ = enc(qs, 'SearchQuery')
R['search'] = {q: [ids[j] for j in np.argsort(-(e @ E['hq'].T))[:3]] for q, e in zip(qs, Eqs)}
R['total_s'] = round(time.time() - t0, 1)
json.dump(R, open(sys.argv[1] if len(sys.argv) > 1 else 'eg2_result.json', 'w'), ensure_ascii=False, indent=1)
print(json.dumps({k: R[k] for k in ('load_s', 'device', 'text_encode_ms_per_item', 'image_encode_ms_per_item', 'audio_encode_ms_per_item', 'total_s')}, ensure_ascii=False))
