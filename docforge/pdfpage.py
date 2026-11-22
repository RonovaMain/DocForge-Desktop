"""Страница для просмотра PDF: свой HTML и скрипт (масштаб, ленивая подгрузка страниц, пометки, режим презентации).

Страницы приходят картинками по адресу docforge://local/pdf/N?w=ширина&v=версия. Масштаб считает сам скрипт, а не
масштаб окна браузера: иначе страницы с шириной «100%» всегда занимали бы всю ширину и не уменьшались.
Пометки рисуются поверх страницы на прозрачных холстах; в файл они попадают только при сохранении (см. pdfedit.py).
"""
from __future__ import annotations

import json
import uuid

BASE = "docforge://local/"

_CSS = """
*{box-sizing:border-box}
html{overflow-y:scroll;background:var(--bg);--bg:#d9dbe1;--paper:#fff;color-scheme:light}
html.dark{--bg:#232429;color-scheme:dark}
body{margin:0;background:var(--bg);user-select:none;-webkit-user-select:none}
#doc{position:relative;padding:18px 0 4px;min-height:100vh}
.pg{position:relative;margin:0 auto 14px;background:var(--paper);box-shadow:0 1px 3px rgba(0,0,0,.28),0 6px 18px rgba(0,0,0,.12);overflow:hidden}
.pg img{position:absolute;left:0;top:0;width:100%;height:100%;display:block;-webkit-user-drag:none;pointer-events:none}
.pg canvas{position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none}
.ovm{mix-blend-mode:multiply}
html.night .pg{background:#111}
html.night .pg img{filter:invert(.92) hue-rotate(180deg)}
html.night .ovm{mix-blend-mode:normal;opacity:.6}
body.tool .pg{cursor:crosshair;touch-action:none}
body.tool-eraser .pg{cursor:cell}
html.pres,html.pres body{height:100%;margin:0;padding:0;overflow:hidden;background:#000}
html.pres #doc{position:absolute;left:0;top:0;width:100%!important;height:100%;padding:0;min-height:0}
html.pres .pg{position:absolute;margin:0;box-shadow:none}
html.pres.night{background:#000}
"""

_JS = r"""
(function () {
  'use strict';
  var SIZES = __SIZES__;
  var BASE = '__BASE__';
  var PT = 96 / 72, GAP = 14, MARGIN = 18, ZMIN = 0.1, ZMAX = 5;
  var STEPS = [0.1, 0.25, 0.33, 0.5, 0.67, 0.75, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3, 4, 5];
  var BUCKETS = [700, 1000, 1400, 1900, 2500, 3200, 4000];
  var total = SIZES.length;
  var docEl = document.getElementById('doc');
  var pgs = [], imgs = [], cvm = [], cvn = [], ctxm = [], ctxn = [], tokens = [], vers = [], vis = [];
  var ops = {}, live = {};
  var mode = '__MODE__', pct = __PCT__, z = 1;
  var tool = 'none', toolColor = '#ffeb3b', toolPt = 2;
  var pres = false, presIdx = 0, lastPage = 0, drag = null, rafMark = false, rafPage = false, loadTimer = 0;
  var dpr = window.devicePixelRatio || 1;
  var maxW = 1, maxH = 1;
  var A = function () { return window.Android; };

  for (var s = 0; s < total; s++) { maxW = Math.max(maxW, SIZES[s][0]); maxH = Math.max(maxH, SIZES[s][1]); }

  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function viewW() { return document.documentElement.clientWidth; }
  function viewH() { return document.documentElement.clientHeight; }

  // ------------------------------------------------------------------ страницы
  var io = ('IntersectionObserver' in window) ? new IntersectionObserver(function (list) {
    list.forEach(function (e) {
      var i = +e.target.getAttribute('data-i');
      vis[i] = e.isIntersecting;
      if (e.isIntersecting) { loadImg(i); }
    });
  }, { rootMargin: '1400px 0px 1400px 0px' }) : null;

  for (var i = 0; i < total; i++) {
    var pg = document.createElement('div');
    pg.className = 'pg';
    pg.setAttribute('data-i', i);
    var im = document.createElement('img');
    im.alt = '';
    im.draggable = false;
    var cm = document.createElement('canvas'); cm.className = 'ovm';
    var cn = document.createElement('canvas'); cn.className = 'ovn';
    pg.appendChild(im); pg.appendChild(cm); pg.appendChild(cn);
    docEl.appendChild(pg);
    pgs.push(pg); imgs.push(im); cvm.push(cm); cvn.push(cn);
    ctxm.push(cm.getContext('2d')); ctxn.push(cn.getContext('2d'));
    tokens.push(0); vers.push(0); vis.push(false);
    if (io) { io.observe(pg); }
  }

  function bucketFor(px) {
    for (var k = 0; k < BUCKETS.length; k++) { if (BUCKETS[k] >= px) { return BUCKETS[k]; } }
    return BUCKETS[BUCKETS.length - 1];
  }

  function loadImg(i, force) {
    var w = pgs[i].clientWidth;
    if (!w) { return; }
    var need = bucketFor(w * dpr), im = imgs[i], cur = +im.getAttribute('data-b') || 0;
    if (!force && cur >= need && cur <= need * 2.6) { return; }
    var token = ++tokens[i], t = new Image();
    t.onload = function () {
      if (token !== tokens[i]) { return; }
      im.src = t.src;
      im.setAttribute('data-b', need);
    };
    t.src = BASE + 'pdf/' + i + '?w=' + need + '&v=' + vers[i];
  }

  function loadVisible(force) {
    clearTimeout(loadTimer);
    loadTimer = setTimeout(function () {
      for (var i = 0; i < total; i++) { if (vis[i] || pres) { loadImg(i, force); } }
    }, 120);
  }

  // ------------------------------------------------------------------ раскладка и масштаб
  function sizePage(i, w, h) {
    var p = pgs[i];
    p.style.width = w + 'px';
    p.style.height = h + 'px';
    [cvm[i], cvn[i]].forEach(function (c) {
      c.width = Math.max(1, Math.round(w * dpr));
      c.height = Math.max(1, Math.round(h * dpr));
    });
    redraw(i);
  }

  function computeZoom() {
    var aw = Math.max(60, viewW() - 2 * MARGIN), ah = Math.max(60, viewH() - 2 * MARGIN);
    var zw = aw / (maxW * PT), zp = Math.min(zw, ah / (maxH * PT));
    if (mode === 'width') { z = zw; } else if (mode === 'page') { z = zp; } else { z = pct / 100; }
    z = clamp(z, ZMIN, ZMAX);
  }

  function anchor() {
    var vh = viewH(), mid = vh / 2, idx = 0, frac = 0;
    for (var i = 0; i < total; i++) {
      var r = pgs[i].getBoundingClientRect();
      if (r.bottom + GAP / 2 > mid || i === total - 1) {
        idx = i; frac = r.height ? (mid - r.top) / r.height : 0; break;
      }
    }
    var dw = docEl.scrollWidth || 1;
    return { i: idx, f: frac, x: (window.scrollX + viewW() / 2) / dw };
  }

  function restore(a) {
    if (!a) { return; }
    var r = pgs[a.i].getBoundingClientRect(), top = r.top + window.scrollY;
    window.scrollTo(a.x * (docEl.scrollWidth || 1) - viewW() / 2, top + a.f * r.height - viewH() / 2);
  }

  function reportZoom() {
    if (A() && A().zoom) { A().zoom(Math.round(z * 100), mode); }
  }

  function layout(a) {
    if (pres) { presLayout(); return; }
    computeZoom();
    var k = z * PT, widest = 0;
    for (var i = 0; i < total; i++) {
      var w = SIZES[i][0] * k, h = SIZES[i][1] * k;
      widest = Math.max(widest, w);
      sizePage(i, w, h);
    }
    docEl.style.width = Math.max(viewW(), widest + 2 * MARGIN) + 'px';
    restore(a);
    loadVisible(false);
    reportZoom();
    schedulePage();
  }

  window.setZoom = function (m, p) {
    var a = anchor();
    mode = (m === 'width' || m === 'page') ? m : 'custom';
    if (mode === 'custom') { pct = clamp(+p || 100, ZMIN * 100, ZMAX * 100); }
    layout(a);
  };
  window.zoomStep = function (dir) {
    var a = anchor(), cur = Math.round(z * 100) / 100, next = cur;
    if (dir > 0) { for (var k = 0; k < STEPS.length; k++) { if (STEPS[k] > cur + 0.004) { next = STEPS[k]; break; } } if (next === cur) { next = ZMAX; } }
    else { for (var j = STEPS.length - 1; j >= 0; j--) { if (STEPS[j] < cur - 0.004) { next = STEPS[j]; break; } } if (next === cur) { next = ZMIN; } }
    mode = 'custom'; pct = Math.round(next * 100);
    layout(a);
  };
  window.zoomBy = function (f) {
    var a = anchor();
    mode = 'custom'; pct = clamp(Math.round(z * 100 * f), ZMIN * 100, ZMAX * 100);
    layout(a);
  };

  window.addEventListener('resize', function () {
    dpr = window.devicePixelRatio || 1;
    layout(pres ? null : anchor());
  });

  // ------------------------------------------------------------------ номер страницы
  function curPage() {
    var vh = viewH(), best = 0, bestVis = -1;
    for (var i = 0; i < total; i++) {
      var r = pgs[i].getBoundingClientRect();
      if (r.top > vh) { break; }
      var v = Math.min(r.bottom, vh) - Math.max(r.top, 0);
      if (v > bestVis) { bestVis = v; best = i; }
    }
    if (window.pageYOffset + vh >= document.documentElement.scrollHeight - 2) { return total; }
    return best + 1;
  }
  function reportPage() {
    rafPage = false;
    if (!total) { return; }
    var c = pres ? presIdx + 1 : curPage();
    if (c !== lastPage) { lastPage = c; if (A() && A().page) { A().page(c, total); } }
  }
  function schedulePage() { if (!rafPage) { rafPage = true; requestAnimationFrame(reportPage); } }
  window.addEventListener('scroll', schedulePage, { passive: true });

  window.gotoPage = function (n) {
    if (!total) { return; }
    var i = clamp(Math.round(n), 1, total) - 1;
    if (pres) { presIdx = i; presLayout(); reportPage(); return; }
    window.scrollTo(window.scrollX, pgs[i].getBoundingClientRect().top + window.pageYOffset - MARGIN + 4);
  };

  // ------------------------------------------------------------------ тема
  window.setNight = function (on) { document.documentElement.classList.toggle('night', !!on); };
  window.setChrome = function (dark) { document.documentElement.classList.toggle('dark', !!dark); };

  // ------------------------------------------------------------------ пометки: рисование
  function strokePath(ctx, pts, w, h) {
    ctx.beginPath();
    ctx.moveTo(pts[0][0] * w, pts[0][1] * h);
    for (var k = 1; k < pts.length - 1; k++) {
      var mx = (pts[k][0] + pts[k + 1][0]) / 2 * w, my = (pts[k][1] + pts[k + 1][1]) / 2 * h;
      ctx.quadraticCurveTo(pts[k][0] * w, pts[k][1] * h, mx, my);
    }
    ctx.lineTo(pts[pts.length - 1][0] * w, pts[pts.length - 1][1] * h);
    ctx.stroke();
  }

  function drawOp(op, w, h, i) {
    var ctx = (op.tool === 'highlight' || op.tool === 'marker') ? ctxm[i] : ctxn[i];
    ctx.save();
    if (op.tool === 'highlight') {
      ctx.fillStyle = op.color;
      op.rects.forEach(function (r) { ctx.fillRect(r[0] * w, r[1] * h, (r[2] - r[0]) * w, (r[3] - r[1]) * h); });
    } else if (op.tool === 'cover') {
      ctx.fillStyle = op.color;
      var r = op.rect;
      ctx.fillRect(r[0] * w, r[1] * h, (r[2] - r[0]) * w, (r[3] - r[1]) * h);
    } else if (op.points && op.points.length) {
      var lw = Math.max(1, op.width * w);
      ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.lineWidth = lw;
      ctx.strokeStyle = op.color; ctx.fillStyle = op.color;
      if (op.tool === 'marker') { ctx.globalAlpha = 0.45; }
      if (op.points.length === 1) {
        ctx.beginPath(); ctx.arc(op.points[0][0] * w, op.points[0][1] * h, lw / 2, 0, Math.PI * 2); ctx.fill();
      } else { strokePath(ctx, op.points, w, h); }
    }
    ctx.restore();
  }

  function redraw(i) {
    var w = pgs[i].clientWidth, h = pgs[i].clientHeight;
    if (!w || !h) { return; }
    [ctxm[i], ctxn[i]].forEach(function (c) { c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, w, h); });
    (ops[i] || []).forEach(function (op) { drawOp(op, w, h, i); });
    if (live[i]) { drawOp(live[i], w, h, i); }
  }
  var dirty = {};
  function scheduleRedraw(i) {
    dirty[i] = true;
    if (rafMark) { return; }
    rafMark = true;
    requestAnimationFrame(function () {
      rafMark = false;
      Object.keys(dirty).forEach(function (k) { redraw(+k); });
      dirty = {};
    });
  }

  window.setOps = function (i, json) {
    try { ops[i] = JSON.parse(json) || []; } catch (e) { ops[i] = []; }
    redraw(i);
  };
  window.clearOps = function () {
    ops = {}; live = {};
    for (var i = 0; i < total; i++) { redraw(i); }
  };
  window.reloadPages = function () {
    for (var i = 0; i < total; i++) { vers[i]++; }
    loadVisible(true);
  };
  window.setTool = function (name, color, ptWidth) {
    tool = name || 'none';
    toolColor = color || toolColor;
    toolPt = +ptWidth || toolPt;
    document.body.classList.toggle('tool', tool !== 'none');
    document.body.classList.toggle('tool-eraser', tool === 'eraser');
    if (tool === 'none' && drag) { cancelDrag(); }
  };

  // ------------------------------------------------------------------ пометки: ввод
  function pos(ev, i) {
    var r = pgs[i].getBoundingClientRect();
    return [clamp((ev.clientX - r.left) / r.width, 0, 1), clamp((ev.clientY - r.top) / r.height, 0, 1)];
  }
  function cancelDrag() {
    if (!drag) { return; }
    var i = drag.i; live[i] = null; drag = null; redraw(i);
  }
  function commit(i, op) {
    (ops[i] = ops[i] || []).push(op);
    redraw(i);
    if (A() && A().addOp) { A().addOp(i, JSON.stringify(op)); }
  }

  function textRequest(d) {
    d.busy = true; d.dirty = false;
    A().selectText(d.i, d.a[0], d.a[1], d.b[0], d.b[1], function (res) {
      d.busy = false;
      var r = {};
      try { r = JSON.parse(res) || {}; } catch (e) { r = {}; }
      d.rects = r.rects || [];
      if (d.dirty) { textRequest(d); return; }
      if (d.ended) { finishText(d); return; }
      live[d.i] = d.rects.length ? { tool: 'highlight', color: toolColor, rects: d.rects } : null;
      scheduleRedraw(d.i);
    });
  }
  function finishText(d) {
    live[d.i] = null;
    if (drag === d) { drag = null; }
    if (d.rects && d.rects.length) { commit(d.i, { tool: 'highlight', color: toolColor, rects: d.rects }); }
    else {
      redraw(d.i);
      if (A() && A().hint) { A().hint('Здесь нет текста. Начните выделение прямо на тексте; у сканов текста нет — используйте «Маркер».'); }
    }
  }

  function hitOp(op, p, w, h) {
    var x = p[0] * w, y = p[1] * h;
    if (op.tool === 'highlight') {
      return op.rects.some(function (r) { return x >= r[0] * w && x <= r[2] * w && y >= r[1] * h && y <= r[3] * h; });
    }
    if (op.tool === 'cover') {
      var r = op.rect; return x >= r[0] * w && x <= r[2] * w && y >= r[1] * h && y <= r[3] * h;
    }
    var lim = Math.max(op.width * w / 2, 2) + 6, pts = op.points;
    for (var k = 0; k < pts.length; k++) {
      var ax = pts[k][0] * w, ay = pts[k][1] * h, bx = ax, by = ay;
      if (k + 1 < pts.length) { bx = pts[k + 1][0] * w; by = pts[k + 1][1] * h; }
      var dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy, t = len2 ? clamp(((x - ax) * dx + (y - ay) * dy) / len2, 0, 1) : 0;
      var ex = ax + t * dx - x, ey = ay + t * dy - y;
      if (ex * ex + ey * ey <= lim * lim) { return true; }
    }
    return false;
  }
  function eraseAt(i, p) {
    var list = ops[i] || [], w = pgs[i].clientWidth, h = pgs[i].clientHeight;
    for (var k = list.length - 1; k >= 0; k--) {
      if (hitOp(list[k], p, w, h)) {
        list.splice(k, 1);
        redraw(i);
        if (A() && A().eraseOp) { A().eraseOp(i, k); }
        return;
      }
    }
  }

  docEl.addEventListener('pointerdown', function (ev) {
    if (pres || tool === 'none' || ev.button !== 0 || drag) { return; }
    var pg = ev.target.closest ? ev.target.closest('.pg') : null;
    if (!pg) { return; }
    var i = +pg.getAttribute('data-i'), p = pos(ev, i);
    ev.preventDefault();
    try { pg.setPointerCapture(ev.pointerId); } catch (e) { /* не страшно */ }
    if (tool === 'pen' || tool === 'marker') {
      var op = { tool: tool, color: toolColor, width: toolPt / SIZES[i][0], points: [p] };
      drag = { i: i, kind: 'stroke', op: op, lx: ev.clientX, ly: ev.clientY };
      live[i] = op;
      scheduleRedraw(i);
    } else if (tool === 'cover') {
      drag = { i: i, kind: 'rect', a: p, b: p };
      live[i] = { tool: 'cover', color: toolColor, rect: [p[0], p[1], p[0], p[1]] };
      scheduleRedraw(i);
    } else if (tool === 'highlight') {
      drag = { i: i, kind: 'text', a: p, b: p, rects: [], busy: false, dirty: false, ended: false };
      textRequest(drag);
    } else if (tool === 'eraser') {
      drag = { i: i, kind: 'erase' };
      eraseAt(i, p);
    }
  });

  docEl.addEventListener('pointermove', function (ev) {
    if (!drag) { return; }
    var d = drag, p = pos(ev, d.i);
    if (d.kind === 'stroke') {
      var dx = ev.clientX - d.lx, dy = ev.clientY - d.ly;
      if (dx * dx + dy * dy < 2.25) { return; }
      d.lx = ev.clientX; d.ly = ev.clientY;
      d.op.points.push(p);
      scheduleRedraw(d.i);
    } else if (d.kind === 'rect') {
      d.b = p;
      live[d.i] = { tool: 'cover', color: toolColor, rect: [Math.min(d.a[0], p[0]), Math.min(d.a[1], p[1]), Math.max(d.a[0], p[0]), Math.max(d.a[1], p[1])] };
      scheduleRedraw(d.i);
    } else if (d.kind === 'text') {
      d.b = p; d.dirty = true;
      if (!d.busy) { textRequest(d); }
    } else if (d.kind === 'erase') {
      eraseAt(d.i, p);
    }
  });

  function endDrag(ev) {
    if (!drag) { return; }
    var d = drag;
    if (d.kind === 'stroke') {
      live[d.i] = null; drag = null;
      commit(d.i, d.op);
    } else if (d.kind === 'rect') {
      var r = live[d.i] ? live[d.i].rect : null;
      live[d.i] = null; drag = null;
      if (r && r[2] - r[0] > 0.002 && r[3] - r[1] > 0.002) { commit(d.i, { tool: 'cover', color: toolColor, rect: r }); } else { redraw(d.i); }
    } else if (d.kind === 'text') {
      d.b = ev && ev.type === 'pointerup' ? pos(ev, d.i) : d.b;
      d.ended = true;
      if (!d.busy) { textRequest(d); } else { d.dirty = true; }
    } else {
      drag = null;
    }
  }
  docEl.addEventListener('pointerup', endDrag);
  docEl.addEventListener('pointercancel', function () { cancelDrag(); });

  // ------------------------------------------------------------------ режим презентации
  function presLayout() {
    if (!pres) { return; }
    var vw = window.innerWidth, vh = window.innerHeight, rx = 0, ry = 0, rw = vw, rh = vh;
    for (var i = 0; i < total; i++) {
      var p = pgs[i];
      if (Math.abs(i - presIdx) > 1) { p.style.display = 'none'; continue; }
      var w = SIZES[i][0], h = SIZES[i][1], k = Math.min(vw / w, vh / h), bw = w * k, bh = h * k;
      var bx = (vw - bw) / 2, by = (vh - bh) / 2;
      p.style.display = 'block';
      p.style.left = bx + 'px'; p.style.top = by + 'px';
      p.style.visibility = i === presIdx ? 'visible' : 'hidden';
      sizePage(i, bw, bh);
      if (i === presIdx) { rx = bx; ry = by; rw = bw; rh = bh; }
    }
    loadVisible(false);
    if (A() && A().presRect) { A().presRect(presIdx, rx, ry, rw, rh, vw); }
  }
  window.presStart = function (n) {
    if (!total) { return; }
    cancelDrag();
    pres = true; presIdx = clamp(Math.round(n), 1, total) - 1;
    document.documentElement.classList.add('pres');
    document.body.classList.add('pres');
    window.scrollTo(0, 0);
    presLayout(); reportPage();
  };
  window.presStop = function () {
    if (!pres) { return; }
    pres = false;
    document.documentElement.classList.remove('pres');
    document.body.classList.remove('pres');
    for (var i = 0; i < total; i++) { pgs[i].style.cssText = ''; }
    layout(null);
    window.gotoPage(presIdx + 1);
    reportPage();
  };
  window.presGo = function (d) {
    if (!pres) { return; }
    var i = clamp(presIdx + d, 0, total - 1);
    if (i !== presIdx) { presIdx = i; presLayout(); reportPage(); }
  };

  layout(null);
  reportPage();
})();
"""


def build_html(sizes: list[tuple[float, float]], mode: str = "width", percent: int = 100) -> str:
    """Страница PDF. [sizes] — размеры страниц в пунктах; [mode] — width | page | custom."""
    nonce = uuid.uuid4().hex
    safe_mode = mode if mode in ("width", "page", "custom") else "width"
    js = (
        _JS.replace("__SIZES__", json.dumps([[round(w, 2), round(h, 2)] for w, h in sizes]))
        .replace("__BASE__", BASE)
        .replace("__MODE__", safe_mode)
        .replace("__PCT__", str(int(max(10, min(500, percent)))))
    )
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f'<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src {BASE} data:; '
        f"style-src 'unsafe-inline'; script-src 'nonce-{nonce}'\">"
        f"<style>{_CSS}</style></head><body><div id=\"doc\"></div>"
        f'<script nonce="{nonce}">{js}</script></body></html>'
    )
