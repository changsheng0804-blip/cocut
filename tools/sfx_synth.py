# 程序化音效：stop（4a 急停）、stinger（5c 片尾定音）、engine（3b 小赛车+漂移）。python3 synth_v2.py → *.wav
import numpy as np
from scipy.signal import butter, sosfilt
from scipy.io import wavfile
SR = 48000; rng = np.random.default_rng(7)
def t_(d): return np.arange(int(SR * d)) / SR
def bp(x, lo, hi, o=4): return sosfilt(butter(o, [lo, hi], 'band', fs=SR, output='sos'), x)
def lp(x, f, o=4): return sosfilt(butter(o, f, 'low', fs=SR, output='sos'), x)
def hp(x, f, o=4): return sosfilt(butter(o, f, 'high', fs=SR, output='sos'), x)
def env(n, a, r, sus=None):
    e = np.ones(n); na = max(1, int(a * SR)); e[:na] = np.linspace(0, 1, na)
    nr = max(1, int(r * SR)); e[-nr:] *= np.linspace(1, 0, nr) ** 2; return e
def verb(x, dec=1.6, mix=0.3):
    n = int(SR * dec); ir = rng.standard_normal(n) * np.exp(-6.9 * np.arange(n) / n); ir = lp(ir, 6000)
    w = np.convolve(x, ir)[:len(x) + n] / np.sqrt(n) * 3
    y = np.zeros(len(w)); y[:len(x)] += x; return y * (1 - mix) + w * mix
def norm(x, peak=0.89): return x / (np.abs(x).max() + 1e-9) * peak
def save(name, x):
    x = norm(x); st = np.stack([x, x], 1); wavfile.write(name, SR, (st * 32767).astype(np.int16)); print(name, round(len(x) / SR, 2))

# 1) 急停：0.11 秒收敛急刹 → 干脆的磁吸微动锁定「咔」+ 低频顿挫 → 极短收干留白（无高频铃音尾韵）
d = 0.65; t = t_(d); x = np.zeros_like(t)
k0 = int(SR * 0.11); pt = t[:k0]
whoosh = bp(rng.standard_normal(k0), 500, 3600) * (np.linspace(0, 1, k0) ** 2.5) * 0.35
brake_sweep = np.sin(2 * np.pi * (420 * pt - 1200 * pt ** 2)) * (np.linspace(0, 1, k0) ** 2) * 0.28
x[:k0] += whoosh + brake_sweep
kt = t_(0.35)
thump = np.sin(2 * np.pi * (42 * kt + 95 * (1 - np.exp(-kt / 0.022)))) * np.exp(-kt / 0.045) * 0.95
click_body = bp(rng.standard_normal(len(kt)), 700, 2600) * np.exp(-kt / 0.0035) * 0.85
click_snap = bp(rng.standard_normal(len(kt)), 2800, 7200) * np.exp(-kt / 0.0018) * 0.60
lock = np.zeros_like(kt); s_lock = int(SR * 0.007)
lock[s_lock:] = bp(rng.standard_normal(len(kt) - s_lock), 1200, 4200) * np.exp(-kt[:-s_lock] / 0.002) * 0.40
tension = (np.sin(2 * np.pi * 587.33 * kt) + 0.5 * np.sin(2 * np.pi * 880.0 * kt)) * np.exp(-kt / 0.022) * 0.12
x[k0:k0 + len(kt)] += thump + click_body + click_snap + lock + tension
save('stop.wav', verb(x, 0.22, 0.06)[:len(t)] * env(len(t), 0.005, 0.25))

# 2) 片尾定音：深沉同调低频重音（D1/D2）+ 温暖大提琴/铜管感纯五度铺底（避让人声频段）+ 克制氩光泛音晕染
d = 5.0; t = t_(d)
boom_body = np.sin(2 * np.pi * (36.71 * t + 1.8 * (1 - np.exp(-t / 0.12)))) * np.exp(-t / 1.1) * 0.95
boom_punch = np.sin(2 * np.pi * (73.42 * t + 1.2 * (1 - np.exp(-t / 0.06)))) * np.exp(-t / 0.45) * 0.65
boom_air = lp(rng.standard_normal(len(t)), 130) * np.exp(-t / 0.12) * 0.35
boom = (boom_body + boom_punch + boom_air) * env(len(t), 0.015, 1.0)
def warm_osc(f, ph0):
    p = (f * t + ph0) % 1.0
    return 0.45 * (2.0 * p - 1.0) + 0.55 * (1.0 - 4.0 * np.abs(p - 0.5))
pad = np.zeros_like(t)
for f, amp in [(73.42, 0.26), (110.0, 0.22), (146.83, 0.20), (220.0, 0.14), (293.66, 0.10), (329.63, 0.08)]:
    for dt in (-0.08, -0.03, 0.0, 0.03, 0.08):
        pad += warm_osc(f * (2.0 ** (dt / 12.0)), rng.uniform(0, 1)) * (amp / 5.0)
pad_env = env(len(t), 0.18, 1.8) * (0.35 + 0.65 * np.exp(-np.maximum(0, t - 0.18) / 1.35))
pad = lp(pad, 780) * pad_env * 0.85
bell = np.zeros_like(t)
for f, amp, delay in [(440.0, 0.09, 0.02), (587.33, 0.08, 0.05), (880.0, 0.045, 0.09)]:
    s = int(SR * delay); tt = t[:len(t) - s]
    atk = 1.0 - np.exp(-tt / 0.06)
    shimmer = np.sin(2 * np.pi * f * tt) + 0.4 * np.sin(2 * np.pi * (f * 1.0015) * tt + 0.7)
    bell[s:] += shimmer * atk * np.exp(-tt / 1.35) * amp
shim = bp(rng.standard_normal(len(t)), 2200, 5200) * env(len(t), 0.08, 1.0) * np.exp(-t / 0.35) * 0.025
save('stinger.wav', verb(boom + pad + bell + shim, 2.2, 0.28))

# 3) 小赛车：四冲程脉冲+排气共振模拟微缩引擎（进弯降档、出弯加速+多普勒）+ 桌面橡胶摩擦漂移（无正弦哨音）
d = 2.6; t = t_(d)
jitter = lp(rng.standard_normal(len(t)), 18) * 2.5
rpm = 72 + 56 * np.clip(t / 0.95, 0, 1) - 30 * np.clip((t - 0.95) / 0.35, 0, 1) + 48 * np.clip((t - 1.35) / 0.95, 0, 1) + jitter
dop = 1.0 + 0.09 * np.tanh((1.25 - t) * 2.8)
ph = np.cumsum(rpm * dop) / SR
pulse = sum(np.sin(2 * np.pi * h * ph + ph0) * a for h, a, ph0 in [(0.5, .35, 0.0), (1.0, .65, 0.2), (1.5, .22, 0.5), (2.0, .40, 1.1), (3.0, .20, 0.7), (4.0, .10, 1.9)])
chuff = bp(rng.standard_normal(len(t)), 220, 1350) * ((0.5 + 0.5 * np.sin(2 * np.pi * ph)) ** 2) * 0.55
raw_eng = np.tanh(pulse * 1.6) + chuff
eng_body = bp(raw_eng, 95, 540) * 1.1 + bp(raw_eng, 500, 1380) * 0.48
eng = lp(eng_body, 1450) * (0.22 + 0.78 * np.exp(-((t - 1.25) / 0.68) ** 2))
sq = np.zeros_like(t); s0, s1 = int(SR * 0.95), int(SR * 1.65); n = s1 - s0
slip_mod = 0.65 + 0.35 * np.sin(2 * np.pi * np.cumsum(np.linspace(58, 36, n)) / SR)
rub_noise = bp(rng.standard_normal(n), 600, 1950) * 0.85 + bp(rng.standard_normal(n), 1400, 2600) * 0.35
fsq = np.linspace(820, 640, n) + 35 * np.sin(np.linspace(0, 5, n))
rub_tone = np.sin(2 * np.pi * np.cumsum(fsq) / SR) * bp(rng.standard_normal(n), 500, 1500) * 0.45
sq[s0:s1] = (rub_noise * slip_mod + rub_tone) * np.hanning(n)
whoosh_pass = bp(rng.standard_normal(len(t)), 280, 1100) * np.exp(-((t - 1.25) / 0.32) ** 2) * 0.28
save('engine.wav', verb((eng + whoosh_pass) * env(len(t), 0.28, 0.65) + sq * 0.32, 0.45, 0.10))
