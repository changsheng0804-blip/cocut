// 《懒》动态预览：doc.json（拍点 + 挂在拍点上的旁白/小字）在浏览器里实时合成。时间全部由拍点时长推出，改一处后面自动顺延。
'use strict';
const $ = (s) => document.querySelector(s);
const el = (t, c, x) => { const e = document.createElement(t); if (c) e.className = c; if (x != null) e.textContent = x; return e; };
const btn = (x, c, f, ti) => { const b = el('button', c, x); b.onclick = f; if (ti) b.title = ti; return b; };
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const fmt = (t) => `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, '0')}`;
const MOVES = { static: '固定', push: '缓推', pan: '横移', orbit: '环绕', pull: '拉远' };
const S = { doc: null, t: 0, playing: false, sel: null, tab: 'beat', imgs: {}, undo: [], hud: true, xf: true, safe: false,
            audio: { ctx: null, bufs: {}, srcs: [] }, t0: 0, c0: 0, api: true, draft: null, rv: { status: {}, check: {} }, rvKey: '' };

// ---------- 时间推导 ----------
function layout() {
  let t = 0;
  for (const b of S.doc.beats) { b._s = t; t += b.dur; b._e = t; }
  S.len = t;
}
const beatAt = (t) => S.doc.beats.find((b) => t >= b._s && t < b._e) || S.doc.beats[S.doc.beats.length - 1];
const selBeat = () => S.doc.beats.find((b) => b.id === S.sel);

// ---------- 读音（和 cocut/api.py 同一套规则）----------
// 全片读音表 doc.lexicon = [{w 原文片段, say 读成, py? {字: 拼音}, note?}]；拍点 vo.say 是单拍手动覆盖。
// vo.said = 上次配音实际念的；和现在该念的不一样 → 配音过期。
const reEsc = (x) => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
function lexApply(text, lex) {
  const es = (lex || []).filter((e) => e.w && e.say != null).sort((a, b) => b.w.length - a.w.length);
  if (!es.length || !text) return text || '';
  const m = Object.fromEntries(es.map((e) => [e.w, e.say]));
  return text.replace(new RegExp(es.map((e) => reEsc(e.w)).join('|'), 'g'), (x) => m[x]);
}
const spoken = (b) => (b.vo && b.vo.say) ? b.vo.say : lexApply(b.vo ? b.vo.text : '', S.doc.lexicon);
const said = (b) => ('said' in b.vo) ? b.vo.said : (b.vo.say || b.vo.text);
const readingStale = (b) => !!(b.vo && b.vo.file && said(b) !== spoken(b));
function pinSaid(d) { for (const b of d.beats || []) if (b.vo && b.vo.file && !('said' in b.vo)) b.vo.said = b.vo.say || b.vo.text; return d; }   // 老数据先钉住当时念的
const voStale = (b) => !!(b.vo && (b.vo.stale || readingStale(b)));

// ---------- 配乐骤降（duck）：和 tools/mixdown.py 同一套曲线 ----------
// 拍点 duck = 保留的配乐比例；duck_attack 下压用时（默认 0.04s，越短越像“刹住”，也越像断了）；duck_release 拍点结束后回升用时（默认 0.8s）。
function duckK(t) {
  let k = 1;
  for (const b of S.doc.beats) {
    if (b.duck == null) continue; const a = b.duck_attack || 0.04, r = b.duck_release || 0.8;
    if (t >= b._s - a && t < b._e + r) k *= clamp(t < b._s ? 1 - (t - b._s + a) / a * (1 - b.duck) : t < b._e ? b.duck : b.duck + (t - b._e) / r * (1 - b.duck), 0, 1);
  }
  return k;
}
// 听感断层：没有旁白、没有音效、配乐又压得很低 → 连续超过 0.6s 就像播放断了（#8）
function quietGaps() {
  const bs = S.doc.beats, on = [];
  for (const b of bs) {
    if (b.vo) { const w = (b.vo.words || []).slice(-1)[0]; on.push([b._s + b.vo.lead, b._s + b.vo.lead + (w ? w.t + w.d : b.vo.dur)]); }
    for (const x of b.sfx || []) { const bf = S.audio.bufs[x.file]; on.push([b._s + (x.at || 0), b._s + (x.at || 0) + (bf ? Math.min(bf.duration, 1.2) : 0.6)]); }
  }
  const out = []; let st = null; const m = S.doc.music;
  for (let t = 1; t < S.len - (m.fade_out || 0); t += 0.05) {
    const q = duckK(t) < 0.3 && !on.some(([a, z]) => t >= a && t < z);
    if (q && st == null) st = t; if (!q && st != null) { if (t - st > 0.6) out.push([st, t]); st = null; }
  }
  return out;
}

// ---------- 检查（和 compile.py 同一套规则，实时跑） ----------
function lint() {
  const out = [], bs = S.doc.beats;
  bs.forEach((b, i) => {
    if (b.vo) {
      const room = b.dur - b.vo.lead - 0.15;
      if (b.vo.dur > room) out.push({ lvl: 'red', beat: b.id, msg: `旁白 ${b.vo.dur.toFixed(1)}s 塞不进（拍点只剩 ${room.toFixed(1)}s）`, fix: ['按旁白延长', () => { b.dur = +(b.vo.lead + b.vo.dur + 0.6).toFixed(2); }] });
      if (b.vo.stale) out.push({ lvl: 'yellow', beat: b.id, msg: '旁白文字改了，配音还是旧的', fix: ['重新配音', () => tts(b)] });
      else if (readingStale(b)) out.push({ lvl: 'yellow', beat: b.id, msg: `读法改了，配音还念「${said(b)}」`, fix: ['重新配音', () => tts(b)] });
    }
    if (b.dur < 1.8) out.push({ lvl: 'yellow', beat: b.id, msg: `只有 ${b.dur.toFixed(1)}s，画面可能看不清` });
    if (!b.image) out.push({ lvl: 'yellow', beat: b.id, msg: '还没有示意图，现在显示文字卡' });
  });
  for (const [a, z] of quietGaps()) { const b = beatAt(a);
    out.push({ lvl: 'red', beat: b.id, msg: `${fmt(a)}–${fmt(z)} 有 ${(z - a).toFixed(1)}s 几乎没声音（配乐压到 ${Math.round((b.duck ?? 1) * 100)}%，没旁白没音效），听起来像断了`,
      fix: b.duck != null ? ['配乐只压到 45%、缓一点', () => { b.duck = 0.45; b.duck_attack = 0.25; b.duck_release = 0.5; }] : null }); }
  const d = S.len - S.doc.target;
  if (Math.abs(d) > 0.5) out.push({ lvl: Math.abs(d) > 3 ? 'red' : 'yellow', msg: `总长 ${S.len.toFixed(1)}s，目标 ${S.doc.target}s（${d > 0 ? '多' : '少'} ${Math.abs(d).toFixed(1)}s）`,
    fix: ['从无旁白的拍点匀', () => fitTarget()] });
  const hero = bs.find((b) => b.hero);
  if (hero && hero._s / S.len < 0.3) out.push({ lvl: 'yellow', beat: hero.id, msg: `高潮落在 ${Math.round(hero._s / S.len * 100)}% 处，偏早` });
  const voT = bs.reduce((a, b) => a + (b.vo ? b.vo.dur : 0), 0);
  if (voT / S.len > 0.7) out.push({ lvl: 'yellow', msg: `旁白占 ${Math.round(voT / S.len * 100)}%，太满` });
  return out;
}
function fitTarget() {
  const bs = S.doc.beats, over = S.len - S.doc.target;
  const slack = bs.map((b) => b.hero ? 0 : Math.max(0, b.dur - Math.max(1.8, b.vo ? b.vo.lead + b.vo.dur + 0.6 : 1.8)));
  const tot = slack.reduce((a, b) => a + b, 0);
  if (over > 0 && tot < over) return toast('没有足够富余，只能删拍点或删旁白');
  bs.forEach((b, i) => { b.dur = +(b.dur - (over > 0 ? over * slack[i] / tot : over / bs.filter((x) => !x.hero).length * (b.hero ? 0 : 1))).toFixed(3); });
}

// ---------- 画面 ----------
function img(src) {
  if (!src) return null;
  if (!S.imgs[src]) { const i = new Image(); i.onload = () => draw(); i.src = src + '?v=' + (S.doc.rev || 1); S.imgs[src] = i; }
  return S.imgs[src].complete && S.imgs[src].naturalWidth ? S.imgs[src] : null;
}
const ease = (p) => p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
function drawBeat(g, b, t, alpha) {
  const p = clamp((t - b._s) / b.dur, 0, 1), e = ease(p);
  let s = 1.02, ox = 0;
  if (b.move === 'push') s = 1 + 0.10 * e;
  else if (b.move === 'pull') s = 1.10 - 0.10 * e;
  else if (b.move === 'pan' || b.move === 'orbit') { s = 1.08; ox = (0.5 - e) * 0.06 * 1920; }
  else s = 1 + 0.02 * p;
  g.save(); g.globalAlpha = alpha;
  const im = img(b.image);
  if (im) {
    const w = 1920 * s, h = 1080 * s;
    g.drawImage(im, (1920 - w) / 2 + ox, (1080 - h) / 2, w, h);
  } else {                                   // 没图：文字卡，照样能看节奏
    g.fillStyle = '#23232c'; g.fillRect(0, 0, 1920, 1080);
    g.fillStyle = '#8f8fa3'; g.font = '40px PFM, sans-serif'; g.textAlign = 'center';
    g.fillText(`${b.id} · ${b.role || ''}·${b.verb || ''}`, 960, 420);
    g.fillStyle = '#d8d8e6'; g.font = '52px PFR, sans-serif';
    wrap(g, b.what || '（空拍点）', 960, 520, 1500, 72);
  }
  if (b.dim) { g.fillStyle = `rgba(0,0,0,${b.dim * clamp(p * 3, 0, 1)})`; g.fillRect(0, 0, 1920, 1080); }
  g.restore();
}
function wrap(g, txt, x, y, maxW, lh) {
  let line = '', yy = y;
  for (const ch of txt) { if (g.measureText(line + ch).width > maxW) { g.fillText(line, x, yy); line = ch; yy += lh; } else line += ch; }
  g.fillText(line, x, yy);
}
function draw() {
  if (!S.doc) return;
  const g = $('#cv').getContext('2d'), t = S.t, b = beatAt(t), i = S.doc.beats.indexOf(b);
  g.fillStyle = '#000'; g.fillRect(0, 0, 1920, 1080);
  drawBeat(g, b, t, 1);
  const XF = 0.25, nx = S.doc.beats[i + 1];
  if (S.xf && nx && b._e - t < XF) drawBeat(g, nx, t, 1 - (b._e - t) / XF);
  if (S.safe) { g.strokeStyle = 'rgba(255,255,255,.35)'; g.lineWidth = 2; g.strokeRect(96, 54, 1728, 972); g.strokeRect(192, 108, 1536, 864); }
  overlay(b, t);
}
function overlay(b, t) {
  const ov = $('#ov'), k = $('#stage').clientWidth / 1920, st = S.doc.style; ov.innerHTML = '';
  const put = (cls, txt, cy, size, extra) => { const d = el('div', 't ' + cls, txt); d.style.fontSize = size * k + 'px'; d.style.top = cy * k + 'px';
    d.style.transform = 'translate(-50%,-50%)'; Object.assign(d.style, extra || {}); ov.appendChild(d); return d; };
  const fade = (a, z, f = 0.3) => clamp(Math.min((t - a) / f, (z - t) / f), 0, 1);
  if (b.vo && !b.title) {
    const a = b._s + b.vo.lead, z = a + b.vo.dur;
    if (t >= a && t <= z) put('sub', b.vo.text.replace(/。$/, ''), 1000, st.sub_size, { background: st.sub_plate });
  }
  if (b.caption && !b.title) { const a = b._s + 0.5, z = b._e - 0.2; if (t >= a && t <= z) put('note', b.caption, 110, st.note_size, { opacity: 0.88 * fade(a, z) }); }
  if (b.title && b.vo) {
    const a = b._s + b.vo.lead; if (t >= a) put('ttl', b.vo.text.split('。')[0], st.title_y || 520, st.title_size, { opacity: clamp((t - a) / 0.4, 0, 1) });
    if (b.caption && t >= a + 0.6) put('ttl2', b.caption, (st.title_y || 520) + 105, st.sub_size, { opacity: clamp((t - a - 0.6) / 0.5, 0, 1) });
  }
  for (const n of S.doc.notes) {
    if (n.status === 'done' || Math.abs(n.t - t) > 1.2) continue;
    const p = el('div', 'pin', n.id.replace('N', '')); p.style.left = n.x * 100 + '%'; p.style.top = n.y * 100 + '%';
    p.onclick = (e) => { e.stopPropagation(); S.tab = 'notes'; renderSide(); }; ov.appendChild(p);
  }
  const rs = S.rv.status[b.id];
  if (rs && (rs.color === 'red' || rs.color === 'yellow')) {
    const txt = rs.color === 'red' ? rs.problems.filter((p) => p.k !== 'text' || !tileOf(rs)).map((p) => rvDesc(p)).join('；') : '';
    const tile = tileOf(rs), textBad = rs.problems.some((p) => p.k === 'text');
    if (tile != null && (textBad || rs.color === 'yellow')) {
      const bx = el('div', 'rvbox'); Object.assign(bx.style, { left: (tile % 3) * 33.33 + '%', top: Math.floor(tile / 3) * 33.33 + '%', width: '33.33%', height: '33.33%' });
      if (rs.color === 'yellow') bx.style.borderColor = 'var(--warm)'; const sp = el('span', '', textBad ? '这里有字' : '待复核：有没有字？'); if (rs.color === 'yellow') sp.style.background = 'var(--warm)';
      bx.appendChild(sp); ov.appendChild(bx);
    }
    if (txt) ov.appendChild(el('div', 'rvtag', txt));
    else if (rs.color === 'yellow' && tile == null) ov.appendChild(el('div', 'rvtag yellow', `待 AI 复核 ${rs.asks.length} 题`));
  }
  $('#hud').style.display = S.hud ? '' : 'none';
  $('#hud').textContent = `${b.id}  ${b.role || ''}·${b.verb || ''}  ${fmt(t)}`;
}

// ---------- 声音 ----------
async function ensureAudio() {
  const A = S.audio; if (A.ctx) return;
  A.ctx = new AudioContext(); A.master = A.ctx.createGain(); A.master.connect(A.ctx.destination);
  const files = [S.doc.music.file, ...S.doc.beats.filter((b) => b.vo && b.vo.file).map((b) => b.vo.file), ...S.doc.beats.flatMap((b) => (b.sfx || []).map((x) => x.file))];
  await Promise.all(files.map(loadBuf));
}
async function loadBuf(f) {
  const A = S.audio; if (A.bufs[f]) return A.bufs[f];
  try { const r = await fetch(f + '?v=' + Date.now()); A.bufs[f] = await A.ctx.decodeAudioData(await r.arrayBuffer()); } catch (e) { console.warn('audio', f, e); }
  return A.bufs[f];
}
function startAudio() {
  const A = S.audio, now = A.ctx.currentTime + 0.05, from = S.t; stopAudio();
  const m = S.doc.music, mb = A.bufs[m.file];
  if (mb && from < S.len) {
    const s = A.ctx.createBufferSource(), g = A.ctx.createGain(); s.buffer = mb; s.connect(g); g.connect(A.master);
    const v = (t) => m.gain * clamp(Math.min(t / m.fade_in, (S.len - t) / m.fade_out), 0, 1) * duckK(t);
    const n = Math.max(2, Math.ceil((S.len - from) / 0.03)), cur = new Float32Array(n);
    for (let i = 0; i < n; i++) cur[i] = v(from + (S.len - from) * i / (n - 1));
    g.gain.setValueCurveAtTime(cur, now, S.len - from);
    s.start(now, from % mb.duration); s.stop(now + S.len - from); A.srcs.push(s);
  }
  for (const b of S.doc.beats) {
    if (!b.vo) continue; const bf = A.bufs[b.vo.file]; if (!bf) continue;
    const a = b._s + b.vo.lead; if (a + bf.duration < from) continue;
    const s = A.ctx.createBufferSource(), g = A.ctx.createGain(); s.buffer = bf; g.gain.value = S.doc.vo_gain || 1; s.connect(g); g.connect(A.master);
    if (a >= from) s.start(now + a - from); else s.start(now, from - a);
    A.srcs.push(s);
  }
  for (const b of S.doc.beats) for (const x of b.sfx || []) {
    const bf = A.bufs[x.file]; if (!bf) continue; const a = b._s + (x.at || 0); if (a + bf.duration < from) continue;
    const s = A.ctx.createBufferSource(), g = A.ctx.createGain(); s.buffer = bf; g.gain.value = x.gain == null ? 1 : x.gain; s.connect(g); g.connect(A.master);
    if (a >= from) s.start(now + a - from); else s.start(now, from - a);
    A.srcs.push(s);
  }
}
function stopAudio() { for (const s of S.audio.srcs) try { s.stop(); } catch (e) {} S.audio.srcs = []; }
async function togglePlay() {
  if (S.playing) { S.playing = false; stopAudio(); $('#bPlay').textContent = '▶'; return; }
  await ensureAudio(); await S.audio.ctx.resume();
  if (S.t >= S.len - 0.05) S.t = 0;
  S.playing = true; $('#bPlay').textContent = '❚❚'; S.c0 = S.audio.ctx.currentTime + 0.05; S.t0 = S.t; startAudio(); tick();
}
function tick() {
  if (!S.playing) return;
  S.t = S.t0 + Math.max(0, S.audio.ctx.currentTime - S.c0);
  if (S.t >= S.len) { S.t = S.len - 0.001; togglePlay(); }
  frame(); requestAnimationFrame(tick);
}
function seek(t) { S.t = clamp(t, 0, S.len - 0.001); if (S.playing) { S.t0 = S.t; S.c0 = S.audio.ctx.currentTime + 0.05; startAudio(); } frame(); }

// ---------- 时间线 ----------
const X = (t) => t / S.len * $('#tl').clientWidth;
const T = (x) => clamp(x / $('#tl').clientWidth * S.len, 0, S.len);
function renderTL() {
  const rb = $('#rowBeats'); rb.innerHTML = ''; const bad = new Set(lint().filter((l) => l.lvl === 'red' && l.beat).map((l) => l.beat));
  S.doc.beats.forEach((b, i) => {
    const c = el('div', 'cell' + (b.id === S.sel ? ' sel' : '') + (b.hero ? ' hero' : '') + (bad.has(b.id) ? ' bad' : ''));
    c.style.left = X(b._s) + 'px'; c.style.width = X(b.dur) + 'px';
    if (b.image) c.style.backgroundImage = `url(${b.image})`; else c.appendChild(el('div', 'card', b.what || ''));
    c.appendChild(el('div', 'nm', `${b.id} ${b.verb || ''}`));
    const rs = S.rv.status[b.id]; if (rs) { const r = el('div', 'rv ' + rvCls(rs)); c.title = `${b.id}：${rvLine(rs)}`; c.appendChild(r); }
    const h = el('div', 'h'); c.appendChild(h);
    h.onmousedown = (e) => { e.stopPropagation(); resizeDrag(e, b); };
    c.onmousedown = (e) => { if (e.target === h) return; S.sel = b.id; S.tab = 'beat'; reorderDrag(e, b); };
    rb.appendChild(c);
  });
  const rv = $('#rowVo'); rv.querySelectorAll('.vo').forEach((x) => x.remove());
  for (const b of S.doc.beats) if (b.vo) {
    const v = el('div', 'vo' + (voStale(b) ? ' stale' : ''), b.vo.text); const a = b._s + b.vo.lead;
    v.style.left = X(a) + 'px'; v.style.width = X(b.vo.dur) + 'px'; v.title = b.vo.text;
    for (const w of b.vo.words || []) { const i = el('i'); i.style.left = X(w.t) + 'px'; v.appendChild(i); }
    v.onmousedown = (e) => { e.stopPropagation(); S.sel = b.id; leadDrag(e, b); }; rv.appendChild(v);
  }
  const ra = $('#rowAux'); ra.querySelectorAll('.aux').forEach((x) => x.remove());
  for (const b of S.doc.beats) if (b.caption) {
    const a = el('div', 'aux', b.caption); a.style.left = X(b._s + 0.5) + 'px'; a.style.width = Math.max(10, X(b.dur - 0.7)) + 'px'; ra.appendChild(a);
  }
  for (const n of S.doc.notes) if (n.status !== 'done') { const a = el('div', 'aux npin'); a.style.left = X(n.t) + 'px'; a.title = n.text; ra.appendChild(a); }
  const ru = $('#ruler'); ru.innerHTML = '';
  for (let s = 0; s <= S.len; s += 5) { const k = el('div', 'tick'); k.style.left = X(s) + 'px'; k.appendChild(el('span', '', fmt(s).replace(/\.0$/, ''))); ru.appendChild(k); }
  placePH();
}
function placePH() { $('#ph').style.left = X(S.t) + 'px'; }
function resizeDrag(e, b) {
  push(); const x0 = e.clientX, d0 = b.dur;
  const mv = (ev) => { b.dur = +Math.max(0.5, d0 + T(ev.clientX - x0)).toFixed(2); changed(true); };
  const up = () => { removeEventListener('mousemove', mv); removeEventListener('mouseup', up); changed(); };
  addEventListener('mousemove', mv); addEventListener('mouseup', up);
}
function leadDrag(e, b) {
  push(); const x0 = e.clientX, l0 = b.vo.lead;
  const mv = (ev) => { b.vo.lead = +clamp(l0 + T(ev.clientX - x0), 0, b.dur - 0.2).toFixed(2); changed(true); };
  const up = () => { removeEventListener('mousemove', mv); removeEventListener('mouseup', up); changed(); };
  addEventListener('mousemove', mv); addEventListener('mouseup', up);
}
function reorderDrag(e, b) {            // 点一下 = 选中并跳到这拍；横向拖 = 换位置
  const x0 = e.clientX; let moved = false, target = null;
  const mv = (ev) => {
    if (Math.abs(ev.clientX - x0) > 8) moved = true; if (!moved) return;
    const t = T(ev.clientX - $('#tl').getBoundingClientRect().left);
    target = S.doc.beats.find((x) => t >= x._s && t < x._e);
    document.querySelectorAll('.cell').forEach((c, i) => c.classList.toggle('drop', S.doc.beats[i] === target && target !== b));
  };
  const up = () => {
    removeEventListener('mousemove', mv); removeEventListener('mouseup', up);
    if (moved && target && target !== b) { push(); const bs = S.doc.beats; bs.splice(bs.indexOf(b), 1); bs.splice(bs.indexOf(target), 0, b); changed(); toast(`${b.id} 移到 ${target.id} 前面`); }
    else { seek(b._s + 0.01); renderAll(); }
  };
  addEventListener('mousemove', mv); addEventListener('mouseup', up);
}

// ---------- 右侧面板 ----------
function renderSide() {
  const tabs = $('#tabs'); tabs.innerHTML = ''; const L = lint();
  const nR = Object.values(S.rv.status).filter((x) => x.color === 'red').length;
  for (const [k, n] of [['beat', '拍点'], ['review', `复核${nR ? ' ' + nR : ''}`], ['lint', `检查 ${L.length}`], ['notes', `意见 ${S.doc.notes.filter((x) => x.status !== 'done').length}`], ['say', '读音'], ['film', '整片']])
    tabs.appendChild(btn(n, S.tab === k ? 'cur' : '', () => { S.tab = k; renderSide(); }));
  const p = $('#panel'); p.innerHTML = '';
  ({ beat: beatPanel, review: reviewPanel, lint: lintPanel, notes: notesPanel, say: sayPanel, film: filmPanel })[S.tab](p, L);
}
function field(p, label, node) { const s = el('div', 'sec'); s.appendChild(el('h3', '', label)); s.appendChild(node); p.appendChild(s); return node; }
function beatPanel(p) {
  const b = selBeat() || beatAt(S.t); S.sel = b.id;
  const th = el('div', 'thumb'); if (b.image) th.style.backgroundImage = `url(${b.image}?v=${S.doc.rev})`; p.appendChild(th);
  const r = el('div', 'row2'); r.appendChild(el('b', '', `${b.id}`)); r.appendChild(el('span', 'muted', `${fmt(b._s)}–${fmt(b._e)} · ${b.shot || ''}`)); p.appendChild(r);
  const brs = S.rv.status[b.id]; if (brs) { const q = el('div', 'rvc ' + rvCls(brs)); q.appendChild(el('div', '', '复核：' + rvLine(brs))); q.onclick = () => { S.tab = 'review'; renderSide(); }; q.style.cursor = 'pointer'; p.appendChild(q); }
  const r2 = el('div', 'row2');
  const du = el('input'); du.type = 'number'; du.step = 0.1; du.value = b.dur; du.onchange = () => { push(); b.dur = Math.max(0.5, +du.value); changed(); };
  const mv = el('select'); for (const [k, n] of Object.entries(MOVES)) { const o = el('option', '', n); o.value = k; o.selected = b.move === k; mv.appendChild(o); }
  mv.onchange = () => { push(); b.move = mv.value; changed(); };
  const hero = el('label', 'muted'); const hc = el('input'); hc.type = 'checkbox'; hc.checked = !!b.hero; hc.onchange = () => { push(); b.hero = hc.checked; changed(); };
  hero.append(hc, ' 高潮');
  r2.append('时长', du, '秒', mv, hero); p.appendChild(r2);
  const ta = (v, h, on) => { const t = el('textarea'); t.value = v || ''; t.style.height = h + 'px'; t.onchange = () => { push(); on(t.value.trim()); changed(); }; return t; };
  field(p, '画面（示意图按这句出）', ta(b.what, 56, (v) => { b.what = v; b.image_stale = true; }));
  const vo = field(p, '旁白', ta(b.vo ? b.vo.text : '', 52, (v) => {
    if (!v) { delete b.vo; return; }
    if (!b.vo) b.vo = { file: '', dur: v.length * 0.24, text: v, words: [], lead: 0.25, stale: true };
    else if (v !== b.vo.text) { b.vo.text = v; b.vo.stale = true; b.vo.dur = Math.max(b.vo.dur, v.length * 0.24); }
  }));
  if (b.vo) {
    const rr = el('div', 'row2'); rr.append(el('span', 'muted', `${b.vo.dur.toFixed(2)}s · 拍点内起点 ${b.vo.lead}s`), btn(voStale(b) ? '重新配音' : '重配', 'small', () => tts(b))); vo.after(rr);
    const sy = el('input'); sy.value = b.vo.say || ''; sy.placeholder = lexApply(b.vo.text, S.doc.lexicon); sy.style.width = '100%';
    sy.onchange = () => { push(); const v = sy.value.trim(); if (v && v !== lexApply(b.vo.text, S.doc.lexicon)) b.vo.say = v; else delete b.vo.say; changed(); };
    const sec = el('div', 'sec'); sec.append(el('h3', '', '读法（配音实际念的；空着就按读音表）'), sy);
    if (readingStale(b)) sec.appendChild(el('div', 'muted', `配音还念「${said(b)}」，要重新配音`));
    rr.after(sec);
  }
  field(p, '画面小字', ta(b.caption, 40, (v) => { if (v) b.caption = v; else delete b.caption; }));
  const r3 = el('div', 'row2'); const rl = el('input'); rl.value = b.role || ''; rl.style.width = '90px'; rl.onchange = () => { push(); b.role = rl.value; changed(); };
  const vb = el('input'); vb.value = b.verb || ''; vb.style.width = '90px'; vb.onchange = () => { push(); b.verb = vb.value; changed(); };
  r3.append('讯息角色', rl, '动词', vb); p.appendChild(r3);
  const r4 = el('div', 'row2');
  r4.append(btn('后面插一拍', 'small', () => insertAfter(b)), btn('复制', 'small', () => insertAfter(b, true)), btn('删除这拍', 'small', () => delBeat(b)),
    btn('换图（交给 Hark）', 'small', () => addNote({ t: b._s + b.dur / 2, x: 0.5, y: 0.5, beat: b.id, text: `重出示意图：${b.what}`, kind: 'image' })));
  p.appendChild(r4);
  if (b.image_stale) p.appendChild(el('div', 'muted', '画面说明改过了，示意图还是旧的：可以点“换图”交给 Hark。'));
}
function lintPanel(p, L) {
  if (!L.length) p.appendChild(el('div', 'muted', '没有问题。'));
  for (const l of L) {
    const c = el('div', 'lint ' + l.lvl); c.appendChild(el('div', '', (l.beat ? l.beat + '  ' : '') + l.msg));
    const a = el('div', 'a');
    if (l.beat) a.appendChild(btn('跳过去', 'small', () => { const b = S.doc.beats.find((x) => x.id === l.beat); S.sel = b.id; seek(b._s + 0.01); }));
    if (l.fix) a.appendChild(btn(l.fix[0], 'small', () => { push(); l.fix[1](); changed(); }));
    c.appendChild(a); p.appendChild(c);
  }
}
function notesPanel(p) {
  p.appendChild(el('div', 'muted', '点画面留意见。Hark 读的就是这里：每条带时间、位置和拍点号。'));
  for (const n of [...S.doc.notes].reverse()) {
    const c = el('div', 'ncard' + (n.status === 'done' ? ' done' : '')); const m = el('div', 'm');
    const w = el('b', '', `#${n.id.replace('N', '')} ${fmt(n.t)}`); w.onclick = () => seek(n.t); m.append(w, ` · ${n.beat} · ${n.by === 'hark' ? 'Hark' : '你'}${n.status === 'done' ? ' · 已处理' : ''}`);
    c.append(m, el('div', '', n.text));
    if (n.reply) c.appendChild(el('div', 'muted', 'Hark：' + n.reply));
    const a = el('div', 'row2'); a.style.marginTop = '6px';
    a.append(btn(n.status === 'done' ? '重开' : '标记处理', 'small', () => { push(); n.status = n.status === 'done' ? 'todo' : 'done'; changed(); }),
             btn('删除', 'small', () => { push(); S.doc.notes = S.doc.notes.filter((x) => x !== n); changed(); }));
    c.appendChild(a); p.appendChild(c);
  }
}
function sayPanel(p) {
  const d = S.doc; d.lexicon = d.lexicon || [];
  p.appendChild(el('div', 'muted', '全片读音表：旁白里出现左边的字词，配音就念右边的；字幕不变。写带上下文的词（「六百万行」），别只写单字。拼音要求会交给复核员核对。'));
  for (const e of d.lexicon) {
    const r = el('div', 'lex'); const n = d.beats.filter((b) => b.vo && b.vo.text.includes(e.w)).length;
    const i = (v, w, on) => { const x = el('input'); x.value = v || ''; x.onchange = () => { push(); on(x.value.trim()); changed(); }; return x; };
    r.append(i(e.w, '30%', (v) => { e.w = v; }), '→', i(e.say, '30%', (v) => { e.say = v; }),
      i(e.py ? Object.entries(e.py).map(([k, v]) => k + '=' + v).join(' ') : '', '22%', (v) => { const o = Object.fromEntries(v.split(/\s+/).filter((x) => x.includes('=')).map((x) => x.split('='))); if (Object.keys(o).length) e.py = o; else delete e.py; }),
      el('span', 'muted', `${n} 拍`), btn('删', 'small', () => { push(); d.lexicon = d.lexicon.filter((x) => x !== e); changed(); }));
    p.appendChild(r);
  }
  const add = el('div', 'lex'); const aw = el('input'); aw.placeholder = '原文'; const as = el('input'); as.placeholder = '念成';
  const ap = el('input'); ap.placeholder = '字=拼音'; ap.title = '拼音要求，如 行=háng；交给复核员核对';
  add.append(aw, '→', as, ap, btn('加', 'small', () => { const w = aw.value.trim(), sy = as.value.trim(); if (!w || !sy) return; push();
    const e = { w, say: sy }; const o = Object.fromEntries(ap.value.trim().split(/\s+/).filter((x) => x.includes('=')).map((x) => x.split('='))); if (Object.keys(o).length) e.py = o;
    d.lexicon = d.lexicon.filter((x) => x.w !== w).concat([e]); changed(); }), el('span', ''));
  p.appendChild(add);
  const vb = d.beats.filter((b) => b.vo); const st = vb.filter(voStale);
  const h = el('div', 'row2'); h.style.marginTop = '14px'; h.append(el('b', '', '每拍实际念的'), el('span', 'muted', st.length ? `${st.length} 拍配音过期` : '配音都是最新的'));
  if (st.length) h.appendChild(btn('重配过期的', 'small', async () => { for (const b of st) await tts(b); }));
  p.appendChild(h);
  for (const b of vb) {
    const sp = spoken(b); const c = el('div', 'lint ' + (voStale(b) ? 'yellow' : 'ok'));
    c.appendChild(el('div', '', `${b.id}  ${sp}${b.vo.say ? '（单拍覆盖）' : ''}`));
    if (sp !== b.vo.text) c.appendChild(el('div', 'muted', '字幕：' + b.vo.text));
    if (readingStale(b)) c.appendChild(el('div', 'muted', '配音还念：' + said(b)));
    c.onclick = () => { S.sel = b.id; seek(b._s + 0.01); }; c.style.cursor = 'pointer'; p.appendChild(c);
  }
}
function filmPanel(p) {
  const d = S.doc; const r = el('div', 'row2');
  const tg = el('input'); tg.type = 'number'; tg.value = d.target; tg.onchange = () => { push(); d.target = +tg.value; changed(); };
  r.append('目标时长', tg, '秒', el('span', 'muted', `现在 ${S.len.toFixed(1)}s · ${d.beats.length} 拍`)); p.appendChild(r);
  const g = (lbl, obj, key, min, max, step) => { const rr = el('div', 'row2'); const i = el('input'); i.type = 'range'; i.min = min; i.max = max; i.step = step; i.value = obj[key];
    const v = el('span', 'muted', String(obj[key])); i.oninput = () => { obj[key] = +i.value; v.textContent = i.value; changed(true); }; i.onchange = () => changed();
    rr.append(lbl, i, v); p.appendChild(rr); };
  g('配乐音量', d.music, 'gain', 0, 1, 0.05); g('旁白增益', d, 'vo_gain', 0.5, 3, 0.1);
  g('字幕字号', d.style, 'sub_size', 24, 56, 1); g('片名字号', d.style, 'title_size', 48, 140, 2);
  p.appendChild(el('div', 'muted', `一句话：${d.one_thing}`));
  p.appendChild(el('div', 'muted', '这一页不烧录任何视频。只有点右上角“导出成片”才用 Concat 出一次 MP4。'));
}

// ---------- 编辑操作 ----------
let idn = 0;
function insertAfter(b, copy) {
  push(); const bs = S.doc.beats; const nb = copy ? JSON.parse(JSON.stringify(b)) : { shot: b.shot, dur: 3, move: 'static', role: '', verb: '', what: '新拍点：写一句画面' };
  nb.id = b.id + '-' + Math.random().toString(36).slice(2, 5); delete nb.hero; delete nb.title; if (copy && nb.vo) nb.vo.stale = nb.vo.stale || false;
  bs.splice(bs.indexOf(b) + 1, 0, nb); S.sel = nb.id; changed(); seek(b._e + 0.01);
}
function delBeat(b) { if (S.doc.beats.length < 2) return; push(); S.doc.beats = S.doc.beats.filter((x) => x !== b); S.sel = null; changed(); toast(`删了 ${b.id}，可撤销`); }
function addNote(o) { push(); const n = Math.max(0, ...S.doc.notes.map((x) => +x.id.slice(1))) + 1;
  S.doc.notes.push(Object.assign({ id: 'N' + n, status: 'todo', by: 'user', made: new Date().toISOString() }, o)); changed(); toast('意见已记下 #' + n); }
async function tts(b) {
  toast('配音中…');
  try {
    const r = await fetch('/live/tts', { method: 'POST', body: JSON.stringify({ id: b.id, text: b.vo.text, say: spoken(b) }) }); const j = await r.json();
    if (!r.ok || j.error) throw new Error(j.error || r.status);
    push(); Object.assign(b.vo, { file: j.file, dur: j.dur, words: j.words, stale: false, said: j.said || spoken(b) }); delete S.audio.bufs[j.file];
    if (S.audio.ctx) await loadBuf(j.file); changed(); toast('已重新配音');
  } catch (e) { toast('配音接口没连上（审片室服务需要更新后重启）：' + e.message); }
}

// ---------- 留意见 ----------
function stageClick(e) {
  const r = $('#stage').getBoundingClientRect(); const x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
  if (S.playing) togglePlay();
  const old = $('#composer'); if (old) old.remove();
  const c = el('div'); c.id = 'composer'; c.style.left = Math.min(e.clientX - r.left, r.width - 310) + 'px'; c.style.top = Math.min(e.clientY - r.top + 12, r.height - 150) + 'px';
  const b = beatAt(S.t); c.appendChild(el('div', 'muted', `${fmt(S.t)} · ${b.id} · 这里怎么改？`));
  const ta = el('textarea'); c.appendChild(ta); const rr = el('div', 'r');
  rr.append(btn('取消', 'small', () => c.remove()), btn('记下', 'small primary', () => { if (ta.value.trim()) addNote({ t: +S.t.toFixed(2), x: +x.toFixed(3), y: +y.toFixed(3), beat: b.id, text: ta.value.trim() }); c.remove(); }));
  c.appendChild(rr); c.onclick = (ev) => ev.stopPropagation(); $('#stage').appendChild(c); ta.focus();
  ta.onkeydown = (ev) => { if (ev.key === 'Enter' && (ev.metaKey || ev.ctrlKey)) rr.lastChild.click(); if (ev.key === 'Escape') c.remove(); };
}

// ---------- 保存 / 撤销 ----------
function push() { S.undo.push(JSON.stringify(S.doc)); if (S.undo.length > 200) S.undo.shift(); }
function undo() { if (!S.undo.length) return toast('没有可撤销的'); S.doc = JSON.parse(S.undo.pop()); changed(); toast('已撤销'); }
let saveT = null;
function changed(light) { layout(); frame(); renderTL(); if (light) return; renderSide(); clearTimeout(saveT); setSave('有改动…'); saveT = setTimeout(save, 700); }
async function save() {
  S.doc.rev = (S.doc.rev || 1); S.doc.saved = new Date().toISOString();
  localStorage.setItem('lan_live_doc', JSON.stringify(S.doc));
  try {
    const r = await fetch('/live/save', { method: 'POST', body: JSON.stringify(S.doc) }); if (!r.ok) throw new Error(r.status);
    const j = await r.json(); setSave('已保存 ' + (j.saved || '')); setTimeout(() => pollReview(true), 300);
  } catch (e) { setSave('只存在浏览器里（保存接口未启用）', true); }
}
function setSave(t, bad) { const s = $('#save'); s.textContent = t; s.classList.toggle('bad', !!bad); }
let lastDisk = '';
async function poll() {                   // Hark 在外面改了 doc.json，页面自动接上
  try {
    const r = await fetch('doc.json?ts=' + Date.now()); const txt = await r.text(); if (txt === lastDisk) return; const disk = JSON.parse(txt);
    if (lastDisk && disk.saved !== S.doc.saved) { push(); S.doc = pinSaid(disk); S.imgs = {}; S.audio.bufs = {}; if (S.audio.ctx) await ensureAudioFiles(); changed(true); renderSide(); toast('Hark 更新了片子'); }
    lastDisk = txt;
  } catch (e) {}
}
async function ensureAudioFiles() { S.audio.bufs = {}; const A = S.audio; A.ctx && await Promise.all([S.doc.music.file, ...S.doc.beats.filter((b) => b.vo && b.vo.file).map((b) => b.vo.file), ...S.doc.beats.flatMap((b) => (b.sfx || []).map((x) => x.file))].map(loadBuf)); }


// ---------- 复核（反射层开单 → AI 答是非题 → 按拍红绿） ----------
const RVNAME = (r) => ({ user: '你', reflex: '反射层' })[r] || r;
const RVC = { green: '没问题', red: '有问题', yellow: '待复核', grey: '改过了，重新体检中' };
function rvCls(rs) { return rs.color === 'red' && !rs.final && rs.problems.some((p) => p.against.length) ? 'red split' : rs.color; }
function tileOf(rs) { const a = (rs.asks || []).find((x) => x.k === 'text'); return a && Number.isInteger(a.tile) && a.tile < 9 ? a.tile : null; }
function rvDesc(p) { return ({ text: '画面里有字', swap: '不是这个场景', el: '缺：' + p.what, vo: '配音不是这句', poly: `「${p.what}」读错` })[p.k] || p.what; }
function rvLine(rs) {
  if (rs.color === 'red') return rs.problems.map((p) => rvDesc(p) + `（${p.by.map(RVNAME).join('、')}${p.against.length ? '；' + p.against.map(RVNAME).join('、') + ' 不同意' : ''}）`).join('；');
  if (rs.color === 'green') return '没问题（' + (rs.reviewers || ['反射层']).map(RVNAME).join('、') + '）';
  if (rs.color === 'yellow') return rs.unsure && rs.unsure.length ? '复核员拿不准：' + rs.unsure.join('、') : `等 AI 复核 ${rs.asks.length} 题`;
  return RVC.grey;
}
function renderRvSum() {
  const v = Object.values(S.rv.status), n = (c) => v.filter((x) => x.color === c).length, s = $('#rvsum'); if (!v.length) { s.style.display = 'none'; return; }
  s.style.display = ''; s.innerHTML = `复核 <b class="cG">${n('green')}</b>绿 <b class="cR">${n('red')}</b>红 <b class="cY">${n('yellow')}</b>待 ${n('grey') ? `<b class="cN">${n('grey')}</b>重查` : ''}${S.rv.check.running ? ' · 体检中…' : (S.rv.reviewers || {}).who ? ` · ${RVNAME(S.rv.reviewers.who)} 复核中…` : ''}`;
  s.onclick = () => { S.tab = 'review'; renderSide(); };
}
async function pollReview(force) {
  try {
    const j = await (await fetch('/api/review')).json(); if (!j.status) return; const k = JSON.stringify([j.status, j.check.running, j.check.error, (j.reviewers || {}).who]);
    if (!force && k === S.rvKey) return; S.rv = j; S.rvKey = k; renderTL(); renderRvSum(); frame();
    if (['review', 'beat'].includes(S.tab) && !$('#panel').contains(document.activeElement)) renderSide();
  } catch (e) {}
}
async function rvJudge(rs, bad) {
  const answers = {}; for (const a of rs.asks) answers[a.i] = (a.k === 'text') === bad ? 'yes' : 'no';
  const r = await fetch('/api/review/answer', { method: 'POST', body: JSON.stringify({ ticket: rs.ticket, by: 'user', answers }) }); const j = await r.json();
  toast(j.error ? '没记上：' + j.error : bad ? '已判有问题' : '已判没问题'); pollReview(true);
}
function reviewPanel(p) {
  const c = S.rv.check || {}, hd = el('div', 'row2');
  hd.append(el('span', 'muted', c.running ? '反射层体检中…' : c.error ? '体检出错：' + c.error : c.last ? `上次体检 ${c.last}，用时 ${c.seconds}s` : '还没有体检'),
    btn('重新体检', 'small', async () => { await fetch('/api/review/check', { method: 'POST', body: '{}' }); toast('开始体检'); pollReview(true); }));
  p.appendChild(hd);
  const rr = S.rv.reviewers || {}; if (rr.who || rr.last || rr.error) p.appendChild(el('div', 'muted', rr.who ? `${RVNAME(rr.who)} 正在复核…` : rr.error ? '复核员出错：' + rr.error : '上次复核：' + rr.last));
  p.appendChild(el('div', 'muted', '反射层先筛，可疑处出是非题给 AI 复核；你只需看红的和有分歧的。你的判断是最终的。'));
  const order = { red: 0, yellow: 1, grey: 2, green: 3 }, rows = S.doc.beats.filter((b) => S.rv.status[b.id]).sort((a, b) => order[S.rv.status[a.id].color] - order[S.rv.status[b.id].color]);
  let greens = 0;
  for (const b of rows) {
    const rs = S.rv.status[b.id]; if (rs.color === 'green' && !rs.final) { greens++; continue; }
    const card = el('div', 'rvc ' + rvCls(rs)); card.appendChild(el('div', '', '')).innerHTML = `<b>${b.id}</b> <span class="muted">${RVC[rs.color]}${rs.final ? ' · 你已裁决' : ''}</span>`;
    card.appendChild(el('div', 'who', b.what || ''));
    if (rs.color === 'red') for (const q of rs.problems) card.appendChild(el('div', 'p', `${rvDesc(q)} —— ${q.by.map(RVNAME).join('、')} 说有问题${q.against.length ? '，' + q.against.map(RVNAME).join('、') + ' 不同意' : ''}`));
    if (rs.color === 'yellow') for (const a of rs.asks) card.appendChild(el('div', 'p', '？ ' + a.q));
    for (const [who, x] of Object.entries(rs.answers || {})) if (x.note) card.appendChild(el('div', 'who', `${RVNAME(who)}：${x.note}`));
    const a = el('div', 'row2'); a.style.marginTop = '6px';
    a.appendChild(btn('跳过去', 'small', () => { S.sel = b.id; seek(b._s + 0.01); }));
    if (rs.color === 'red') a.appendChild(btn('转成意见', 'small', () => { addNote({ t: b._s + b.dur / 2, x: 0.5, y: 0.5, beat: b.id, text: '复核：' + rs.problems.map(rvDesc).join('；') }); toast('已加到意见'); }));
    if (rs.ticket && rs.asks.length && rs.color !== 'grey') a.append(btn('我判没问题', 'small', () => rvJudge(rs, false)), btn('我判有问题', 'small', () => rvJudge(rs, true)));
    card.appendChild(a); p.appendChild(card);
  }
  if (greens) p.appendChild(el('div', 'muted', `另有 ${greens} 拍没问题。`));
}

// ---------- 其它 ----------
function toast(m) { const t = $('#toast'); t.textContent = m; t.style.display = 'block'; clearTimeout(t._h); t._h = setTimeout(() => (t.style.display = 'none'), 2600); }
function frame() {
  draw(); placePH(); const b = beatAt(S.t);
  $('#time').innerHTML = `${fmt(S.t)} <small>/ ${fmt(S.len)}</small>`; $('#beatName').textContent = `${b.id} · ${b.what || ''}`;
}
function fit() {
  const w = $('#stagewrap'), k = Math.min((w.clientWidth - 28) / 1920, (w.clientHeight - 18) / 1080);
  $('#stage').style.width = 1920 * k + 'px'; $('#stage').style.height = 1080 * k + 'px'; frame(); renderTL();
}
function renderAll() { renderTL(); renderSide(); frame(); }
async function exportFilm() {
  if (!confirm('导出成片只在定稿后做一次：用 Concat 按当前页面的内容出 1080p MP4。现在导出吗？')) return;
  try { const r = await fetch('/live/export', { method: 'POST', body: '{}' }); const j = await r.json(); toast(j.error ? '导出失败：' + j.error : '导出已开始：' + (j.out || '')); }
  catch (e) { toast('导出接口没连上（审片室服务需要更新后重启）'); }
}
async function main() {
  const txt = await (await fetch('doc.json?ts=' + Date.now())).text(); lastDisk = txt; S.doc = pinSaid(JSON.parse(txt));
  const ls = localStorage.getItem('lan_live_doc');
  if (ls) { const l = JSON.parse(ls); if (l.saved && (!S.doc.saved || l.saved > S.doc.saved)) { S.doc = pinSaid(l); toast('接上你上次在浏览器里的改动'); } }
  layout(); S.sel = S.doc.beats[0].id;
  const hm = location.hash.match(/t=([\d.]+)/); if (hm) { S.t = clamp(+hm[1], 0, S.len - 0.01); S.sel = beatAt(S.t).id; }
  const ht = location.hash.match(/tab=(\w+)/); if (ht) S.tab = ht[1];          // 直达某个面板：#tab=say&t=12
  $('#stage').onclick = stageClick; $('#bPlay').onclick = togglePlay; $('#bUndo').onclick = undo; $('#bExport').onclick = exportFilm;
  const tog = (id, k) => { $(id).onclick = () => { S[k] = !S[k]; $(id).classList.toggle('on', S[k]); frame(); }; };
  tog('#bHud', 'hud'); tog('#bXf', 'xf'); tog('#bSafe', 'safe');
  $('#tl').onmousedown = (e) => { if (e.target.closest('.cell,.vo')) return; const r = $('#tl').getBoundingClientRect(); seek(T(e.clientX - r.left));
    const mv = (ev) => seek(T(ev.clientX - r.left)); const up = () => { removeEventListener('mousemove', mv); removeEventListener('mouseup', up); };
    addEventListener('mousemove', mv); addEventListener('mouseup', up); };
  addEventListener('keydown', (e) => {
    if (e.target.matches('input,textarea,select')) return;
    if (e.code === 'Space') { e.preventDefault(); togglePlay(); }
    else if (e.key === 'ArrowLeft') seek(S.t - (e.shiftKey ? 1 : 1 / 24)); else if (e.key === 'ArrowRight') seek(S.t + (e.shiftKey ? 1 : 1 / 24));
    else if ((e.metaKey || e.ctrlKey) && e.key === 'z') { e.preventDefault(); undo(); }
  });
  addEventListener('resize', fit); document.fonts.ready.then(fit); fit(); renderSide(); setInterval(poll, 3000); pollReview(true); setInterval(pollReview, 2000);
}
main();
