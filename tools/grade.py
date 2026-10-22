# 色调卡 + 统一调色 LUT（argon.cube）。python3 grade.py → argon.cube, color_card.png；python3 grade.py apply in.png out.png
import sys, numpy as np
from PIL import Image, ImageDraw, ImageFont
PAL = [  # 名称, hex, 用途
 ('夜影 靛', '#0E1220', '暗部底色，所有夜景阴影往这里靠'), ('夜中 石板蓝', '#2A3550', '夜景中间调'),
 ('氩光 薰衣草', '#B9A3FF', 'Twin 光与 AI 动作，全片唯一高饱和冷色'), ('氩光 边缘紫', '#7A5CFF', '光晕外圈、片尾星芒'),
 ('钨丝 琥珀', '#F2A65A', '人的世界：台灯、屏幕、咖啡'), ('黎明 桃', '#F6C99A', '5a–5b 清晨'),
 ('警示 红', '#E0473C', '仅 4a 删除键，全片唯一暖高饱和'), ('纸白', '#ECE6DA', '高光上限，不用纯白')]
ACTS = [  # 拍点, 主调, 色温描述
 ('0a–1b', ['#0E1220', '#2A3550', '#F2A65A', '#B9A3FF'], '深夜：冷靛+一点琥珀台灯，Twin 紫光是主光'),
 ('2a–2e', ['#1A2236', '#3B4766', '#B9A3FF', '#ECE6DA'], '工作蒙太奇：冷石板蓝，紫光扫过的地方才亮'),
 ('3a–3c', ['#2A3550', '#6B7690', '#F2A65A', '#B9A3FF'], '空间与具身：稍亮的中性冷调，琥珀点缀'),
 ('4a–4b', ['#0B0E18', '#2A3550', '#E0473C', '#B9A3FF'], '越界：几乎全黑，只剩红键与紫光'),
 ('5a–5b', ['#2A3550', '#F2A65A', '#F6C99A', '#B9A3FF'], '清晨：靛蓝退去，琥珀与桃色接管'),
 ('5c', ['#07070D', '#2B1F4D', '#7A5CFF', '#B9A3FF'], '片尾：紫黑落版')]
def h2r(h): return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)]) / 255
def grade(rgb):  # rgb: (...,3) 0-1
    x = np.clip(rgb, 0, 1)
    L = x @ np.array([.2126, .7152, .0722]); L3 = L[..., None]
    x = L3 + (x - L3) * 0.88                                   # 轻微去饱和
    lav = np.clip(1 - np.abs(np.arctan2(x[..., 2] - x[..., 1], x[..., 0] - x[..., 1]) - 0.85) / 0.6, 0, 1)[..., None]  # 保留紫
    x = x * (1 - 0.12 * lav) + (L3 + (x - L3) * 1.25) * 0.12 * lav
    sh = (1 - L3) ** 2.2; hi = L3 ** 2.0
    x = x + sh * (h2r('#1C2440') - 0.15) * 0.35 + hi * (h2r('#F6D2A8') - 0.85) * 0.25   # 分离色调：暗部靛、亮部暖
    x = np.clip(x, 0, 1); x = x + 0.10 * np.sin(np.pi * (x - 0.5)) * (x * (1 - x)) * 4 * 0.5  # 柔 S 曲线
    lo, hi_ = 0.035, 0.94; return np.clip(lo + x * (hi_ - lo), 0, 1)  # 抬黑压白：黑不死、白不爆
def write_cube(fn, n=33):
    g = np.linspace(0, 1, n); b, gg, r = np.meshgrid(g, g, g, indexing='ij')
    out = grade(np.stack([r, gg, b], -1)).reshape(-1, 3)
    with open(fn, 'w') as f:
        f.write('TITLE "argon"\nLUT_3D_SIZE %d\n' % n)
        for v in out: f.write('%.5f %.5f %.5f\n' % tuple(v))
def font(s):
    for p in ['/workspace/work/fonts/NotoSansSC-VF.ttf', '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc']:
        try: return ImageFont.truetype(p, s)
        except Exception: pass
    import glob; c = glob.glob('/usr/share/fonts/**/*CJK*', recursive=True) + glob.glob('/usr/share/fonts/**/*wqy*', recursive=True)
    return ImageFont.truetype(c[0], s) if c else ImageFont.load_default()
def wrap(d, xy, text, f, maxw, fill, lh):
    x, y = xy; line = ''
    toks = __import__('re').findall(r'[A-Za-z0-9#.\-–]+|.', text)
    for t in toks:
        if d.textlength(line + t, font=f) > maxw and line:
            if t in '，。、；：': line += t; t = ''
            d.text((x, y), line, fill=fill, font=f); y += lh; line = t.lstrip()
        else: line += t
    if line: d.text((x, y), line, fill=fill, font=f)
def card(fn):
    W, H = 1920, 1080; im = Image.new('RGB', (W, H), '#101218'); d = ImageDraw.Draw(im)
    d.text((60, 40), '《懒》色调卡 · 电影化', fill='#ECE6DA', font=font(44))
    d.text((60, 100), '规则：暗部偏靛不死黑；高光偏暖不过 #ECE6DA；全片唯一高饱和冷色=氩光紫，唯一高饱和暖色=4a 警示红；人=琥珀，AI=紫。所有图/视频生成后统一过 argon.cube。', fill='#9AA0B4', font=font(22))
    sw = (W - 120) // len(PAL)
    for i, (n, h, u) in enumerate(PAL):
        x = 60 + i * sw; d.rectangle([x, 160, x + sw - 16, 400], fill=h)
        d.text((x, 410), n, fill='#ECE6DA', font=font(24)); d.text((x, 444), h, fill='#9AA0B4', font=font(20))
        wrap(d, (x, 474), u, font(18), sw - 24, '#7D8398', 26)
    aw = (W - 120) // len(ACTS)
    for i, (b, cs, desc) in enumerate(ACTS):
        x = 60 + i * aw; y = 620
        for j, c in enumerate(cs): d.rectangle([x, y + j * 70, x + aw - 20, y + j * 70 + 66], fill=c)
        d.text((x, y - 44), b, fill='#ECE6DA', font=font(28))
        wrap(d, (x, 910), desc, font(20), aw - 30, '#9AA0B4', 28)
    im.save(fn)
def apply(src, dst):
    a = np.asarray(Image.open(src).convert('RGB')) / 255; Image.fromarray((grade(a) * 255 + .5).astype(np.uint8)).save(dst)
if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'apply': apply(sys.argv[2], sys.argv[3])
    else: write_cube('argon.cube'); card('color_card.png'); print('ok')
