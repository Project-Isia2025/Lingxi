"""投流调价规则可视化配置。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from api.auth import inject_auth_script, verify_websocket_auth

router = APIRouter(tags=["dashboard"])

_OPERATOR_HOME_HTML = Path(__file__).with_name("agent_workflow.html").read_text(encoding="utf-8")
_RUNTIME_OPERATOR_HTML = Path(__file__).with_name("runtime_operator.html").read_text(encoding="utf-8")
_RUNTIME_ADVANCED_HTML = Path(__file__).with_name("runtime_advanced.html").read_text(encoding="utf-8")


def _html(content: str) -> HTMLResponse:
    return HTMLResponse(inject_auth_script(content))


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_home():
    return _html(_OPERATOR_HOME_HTML)


_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>投流调价规则配置</title>
  <style>
    :root { --bg:#0f1419; --card:#1a2332; --text:#e7ecf3; --muted:#8b9cb3; --accent:#3b82f6; --ok:#22c55e; }
    * { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 24px; }
    h1 { margin: 0 0 8px; font-size: 1.5rem; }
    .sub { color: var(--muted); margin-bottom: 24px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
    .card { background: var(--card); border-radius: 10px; padding: 16px; margin-bottom: 16px; }
    label { display: block; font-size: 0.85rem; color: var(--muted); margin-bottom: 4px; }
    input[type=number], input[type=text] { width: 100%; padding: 8px 10px; border: 1px solid #334155; border-radius: 6px; background: #0f172a; color: var(--text); }
    .rule-row { display: flex; align-items: center; gap: 12px; padding: 8px 0; border-bottom: 1px solid #243044; }
    .rule-row:last-child { border-bottom: none; }
    button { background: var(--accent); color: #fff; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-size: 1rem; }
    button:hover { filter: brightness(1.1); }
    #msg { margin-top: 12px; min-height: 1.2em; }
    .ok { color: var(--ok); }
    .toggle { width: auto; }
  </style>
</head>
<body>
  <h1>投流自动调价规则</h1>
  <p class="sub">配置保存后自动生效 · <a href="/dashboard" style="color:#93c5fd">返回首页</a> · <a href="/dashboard/publish-queue" style="color:#93c5fd">待发布</a> · <a href="/dashboard/analytics" style="color:#93c5fd">赚钱效果</a> · <a href="/dashboard/runtime" style="color:#93c5fd">系统状态</a></p>
  <div class="card">
    <label><input type="checkbox" id="enabled" class="toggle"/> 启用自动调价</label>
  </div>
  <div class="card">
    <h3>阈值参数</h3>
    <div class="grid" id="params"></div>
  </div>
  <div class="card">
    <h3>规则开关</h3>
    <div id="rules"></div>
  </div>
  <button id="save">保存配置</button>
  <div id="msg"></div>
  <script>
    const PARAMS = [
      ["ctr_good", "CTR 良好阈值"], ["ctr_bad", "CTR 过低阈值"],
      ["cpc_max", "CPC 上限(元)"], ["roi_scale", "ROI 加价线"],
      ["roi_cut", "ROI 降价线"], ["budget_up_pct", "加价比例"],
      ["budget_down_pct", "降价比例"], ["min_budget", "最低日预算"],
      ["max_budget", "最高日预算"], ["min_impressions", "最低展示量"]
    ];
    const paramsEl = document.getElementById("params");
    PARAMS.forEach(([k, label]) => {
      const d = document.createElement("div");
      d.innerHTML = `<label>${label}</label><input type="number" step="any" id="p_${k}" data-key="${k}"/>`;
      paramsEl.appendChild(d);
    });
    async function load() {
      const r = await fetch("/api/ad/bid/rules");
      const j = await r.json();
      const rules = j.rules || {};
      document.getElementById("enabled").checked = !!rules.enabled;
      PARAMS.forEach(([k]) => {
        const el = document.getElementById("p_" + k);
        if (el && rules[k] != null) el.value = rules[k];
      });
      const rulesEl = document.getElementById("rules");
      rulesEl.innerHTML = "";
      (rules.rules || []).forEach(row => {
        const div = document.createElement("div");
        div.className = "rule-row";
        div.innerHTML = `<label><input type="checkbox" data-rule-id="${row.id}" ${row.enabled ? "checked" : ""}/> ${row.label || row.id}</label><span style="color:#8b9cb3">优先级 ${row.priority || 1}</span>`;
        rulesEl.appendChild(div);
      });
    }
    document.getElementById("save").onclick = async () => {
      const body = { enabled: document.getElementById("enabled").checked };
      PARAMS.forEach(([k]) => {
        const el = document.getElementById("p_" + k);
        if (el && el.value !== "") body[k] = Number(el.value);
      });
      body.rules = [];
      document.querySelectorAll("[data-rule-id]").forEach(cb => {
        body.rules.push({ id: cb.dataset.ruleId, enabled: cb.checked });
      });
      const r = await fetch("/api/ad/bid/rules", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body) });
      const j = await r.json();
      const msg = document.getElementById("msg");
      msg.className = j.ok ? "ok" : "";
      msg.textContent = j.ok ? "已保存" : (j.detail || "保存失败");
      if (j.ok) load();
    };
    load();
  </script>
</body>
</html>"""


class BidRulesPayload(BaseModel):
    enabled: bool | None = None
    ctr_good: float | None = None
    ctr_bad: float | None = None
    cpc_max: float | None = None
    roi_scale: float | None = None
    roi_cut: float | None = None
    budget_up_pct: float | None = None
    budget_down_pct: float | None = None
    min_budget: float | None = None
    max_budget: float | None = None
    min_impressions: int | None = None
    rules: list[dict[str, Any]] = Field(default_factory=list)


@router.get("/dashboard/ad-bid", response_class=HTMLResponse)
def ad_bid_dashboard():
    return _html(_DASHBOARD_HTML)


@router.get("/api/ad/bid/rules")
def get_bid_rules():
    from services.ad_bid_config import load_bid_rules

    return {"ok": True, "rules": load_bid_rules()}


@router.post("/api/ad/bid/rules")
def save_bid_rules_api(body: BidRulesPayload):
    from services.ad_bid_config import load_bid_rules, save_bid_rules, apply_rules_to_env

    current = load_bid_rules()
    patch = body.model_dump(exclude_none=True)
    if body.rules:
        existing = {str(r.get("id")): dict(r) for r in current.get("rules") or [] if isinstance(r, dict)}
        merged_rules = []
        for row in body.rules:
            rid = str(row.get("id") or "")
            base = existing.get(rid, {"id": rid, "label": rid, "priority": 1})
            if "enabled" in row:
                base["enabled"] = bool(row["enabled"])
            merged_rules.append(base)
        patch["rules"] = merged_rules
    saved = save_bid_rules({**current, **patch})
    apply_rules_to_env(saved)
    return {"ok": True, "rules": saved}


_PERCEPTION_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>ASR/OCR 感知 Feed</title>
  <style>
    :root { --bg:#0f1419; --card:#1a2332; --text:#e7ecf3; --muted:#8b9cb3; --asr:#38bdf8; --ocr:#a78bfa; --pub:#22c55e; }
    body { font-family: system-ui,sans-serif; background:var(--bg); color:var(--text); margin:0; padding:24px; }
    h1 { margin:0 0 4px; }
    .sub { color:var(--muted); margin-bottom:20px; }
    .nav a { color:#93c5fd; margin-right:16px; }
    .tabs { display:flex; gap:8px; margin-bottom:16px; }
    .tab { padding:8px 14px; border-radius:8px; background:#243044; cursor:pointer; border:none; color:var(--text); }
    .tab.active { background:#3b82f6; }
    .item { background:var(--card); border-radius:10px; padding:14px; margin-bottom:10px; border-left:4px solid #334155; }
    .item.asr { border-left-color:var(--asr); }
    .item.ocr { border-left-color:var(--ocr); }
    .item.pub { border-left-color:var(--pub); }
    .item.roi { border-left-color:#fbbf24; }
    .live { font-size:0.8rem; color:#22c55e; margin-bottom:12px; }
    .meta { font-size:0.8rem; color:var(--muted); margin-top:6px; }
    .body { margin-top:8px; line-height:1.5; white-space:pre-wrap; font-size:0.92rem; }
    .badge { display:inline-block; padding:2px 8px; border-radius:999px; font-size:0.75rem; margin-right:6px; }
    .badge-asr { background:#0c4a6e; color:#7dd3fc; }
    .badge-ocr { background:#4c1d95; color:#c4b5fd; }
    .badge-pub { background:#14532d; color:#86efac; }
    .queue { font-size:0.85rem; }
  </style>
</head>
<body>
  <div class="nav"><a href="/dashboard">首页</a><a href="/dashboard/ad-bid">广告预算</a><a href="/dashboard/perception">识别记录</a><a href="/dashboard/publish-queue">待发布</a><a href="/dashboard/analytics">赚钱效果</a><a href="/dashboard/runtime">系统状态</a></div>
  <h1>感知 Feed</h1>
  <p class="sub">ASR 转写、OCR 识别、发布 ROI 回写 — 来自知识库与 episodic 记忆</p>
  <div id="live" class="live">连接中…</div>
  <div class="tabs">
    <button class="tab active" data-filter="all">全部</button>
    <button class="tab" data-filter="asr">ASR</button>
    <button class="tab" data-filter="ocr">OCR</button>
    <button class="tab" data-filter="publish">发布</button>
    <button class="tab" data-filter="roi">联合ROI</button>
    <button class="tab" data-filter="queue">发布队列</button>
  </div>
  <div id="list"></div>
  <script>
    let feed = [];
    let queue = [];
    async function load() {
      const r = await fetch('/api/dashboard/perception-feed?limit=40');
      const j = await r.json();
      feed = j.items || [];
      queue = j.publish_queue || [];
      render(document.querySelector('.tab.active')?.dataset.filter || 'all');
    }
    function render(filter) {
      const el = document.getElementById('list');
      if (filter === 'queue') {
        el.innerHTML = queue.length ? queue.map(q => `
          <div class="item pub queue">
            <span class="badge badge-pub">${q.status}</span> ${q.platform} / ${q.account_id}
            <div class="body">${(q.title||q.script||'').slice(0,120)}</div>
            <div class="meta">P${q.priority||0} · 重试 ${q.retry_count||0} · ${q.last_error||'—'}</div>
          </div>`).join('') : '<p class="sub">暂无队列任务</p>';
        return;
      }
      const items = feed.filter(i => filter==='all' || i.kind===filter || (filter==='roi' && i.kind==='roi'));
      el.innerHTML = items.length ? items.map(i => `
        <div class="item ${i.kind}">
          <span class="badge badge-${i.kind}">${i.kind.toUpperCase()}</span> ${i.title||''}
          <div class="body">${(i.body||'').slice(0,400)}</div>
          <div class="meta">${i.platform||''} · ROI ${i.roi_score??'-'} · ${new Date((i.updated_ts||0)*1000).toLocaleString()}</div>
        </div>`).join('') : '<p class="sub">暂无数据</p>';
    }
    document.querySelectorAll('.tab').forEach(btn => btn.onclick = () => {
      document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      render(btn.dataset.filter);
    });
    load();
    let ws;
    function connectWs() {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      ws = new WebSocket(`${proto}://${location.host}/ws/dashboard/feed`);
      ws.onopen = () => { document.getElementById('live').textContent = '● 实时推送已连接'; };
      ws.onclose = () => { document.getElementById('live').textContent = '○ 已断开，30s 后重连'; setTimeout(connectWs, 30000); };
      ws.onmessage = (ev) => {
        try {
          const j = JSON.parse(ev.data);
          feed = j.items || feed;
          queue = j.publish_queue || queue;
          document.getElementById('live').textContent = '● 实时更新 ' + new Date().toLocaleTimeString();
          render(document.querySelector('.tab.active')?.dataset.filter || 'all');
        } catch(e) {}
      };
    }
    connectWs();
    setInterval(load, 60000);
  </script>
</body>
</html>"""


_ANALYTICS_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>ROI 指标图表</title>
  <style>
    :root { --bg:#0f1419; --card:#1a2332; --text:#e7ecf3; --muted:#8b9cb3; }
    body { font-family: system-ui,sans-serif; background:var(--bg); color:var(--text); margin:0; padding:24px; }
    .nav a { color:#93c5fd; margin-right:16px; }
    .cards { display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); gap:12px; margin:16px 0; }
    .card { background:var(--card); border-radius:10px; padding:16px; }
    .card h3 { margin:0 0 4px; font-size:0.85rem; color:var(--muted); }
    .card .val { font-size:1.6rem; font-weight:600; }
    canvas { background:var(--card); border-radius:10px; width:100%; max-width:960px; margin-top:12px; }
  </style>
</head>
<body>
  <div class="nav"><a href="/dashboard">首页</a><a href="/dashboard/ad-bid">广告预算</a><a href="/dashboard/perception">识别记录</a><a href="/dashboard/publish-queue">待发布</a><a href="/dashboard/analytics">赚钱效果</a><a href="/dashboard/runtime">系统状态</a></div>
  <h1>发布 / 投流 / 联合 ROI</h1>
  <p style="color:var(--muted)"><span id="live">连接中…</span> · <a href="/api/roi/export/csv?days=14" style="color:#93c5fd">导出 CSV</a></p>
  <div class="cards" id="cards"></div>
  <canvas id="chart" height="320"></canvas>
  <script>
    const COLORS = { publish_roi:'#22c55e', ad_roi:'#3b82f6', combined_roi:'#fbbf24' };
    const LABELS = { publish_roi:'发布ROI', ad_roi:'投流ROI', combined_roi:'联合ROI' };
    function drawChart(series) {
      const canvas = document.getElementById('chart');
      const ctx = canvas.getContext('2d');
      const W = canvas.width = canvas.offsetWidth * 2;
      const H = canvas.height = 640;
      ctx.scale(2,2);
      const w = W/2, h = H/2, pad = 40;
      ctx.clearRect(0,0,w,h);
      const days = [...new Set(series.map(s=>s.day))].sort();
      if (!days.length) { ctx.fillStyle='#8b9cb3'; ctx.fillText('暂无数据', pad, h/2); return; }
      const types = ['publish_roi','ad_roi','combined_roi'];
      const maxV = Math.max(0.01, ...series.map(s=>Number(s.avg_value)||0));
      const xStep = (w - pad*2) / Math.max(days.length-1, 1);
      ctx.strokeStyle='#334155'; ctx.beginPath(); ctx.moveTo(pad,h-pad); ctx.lineTo(w-pad,h-pad); ctx.stroke();
      types.forEach(type => {
        const pts = days.map((d,i) => {
          const row = series.filter(s=>s.day===d && s.event_type===type).pop();
          const v = row ? Number(row.avg_value)||0 : null;
          return v === null ? null : { x: pad + i*xStep, y: h-pad - (v/maxV)*(h-pad*2), v };
        });
        ctx.strokeStyle = COLORS[type]; ctx.lineWidth = 2; ctx.beginPath();
        let started = false;
        pts.forEach(p => { if(!p) return; if(!started){ ctx.moveTo(p.x,p.y); started=true; } else ctx.lineTo(p.x,p.y); });
        ctx.stroke();
        pts.forEach(p => { if(!p) return; ctx.fillStyle=COLORS[type]; ctx.beginPath(); ctx.arc(p.x,p.y,3,0,Math.PI*2); ctx.fill(); });
      });
      ctx.fillStyle='#8b9cb3'; ctx.font='11px sans-serif';
      days.forEach((d,i)=>{ if(i%2===0) ctx.fillText(d.slice(5), pad+i*xStep-12, h-pad+16); });
      let legX = pad;
      types.forEach(t=>{ ctx.fillStyle=COLORS[t]; ctx.fillRect(legX, 12, 12, 12); ctx.fillStyle='#e7ecf3'; ctx.fillText(LABELS[t], legX+16, 22); legX+=100; });
    }
    async function load() {
      const r = await fetch('/api/dashboard/metrics-chart?days=14');
      const j = await r.json();
      applyChart(j);
    }
    function applyChart(j) {
      const cards = document.getElementById('cards');
      const avg = j.latest_avg || {};
      const tot = j.totals || {};
      cards.innerHTML = [
        ['发布ROI均值', avg.publish_roi, COLORS.publish_roi],
        ['投流ROI均值', avg.ad_roi, COLORS.ad_roi],
        ['联合ROI均值', avg.combined_roi, COLORS.combined_roi],
        ['发布成功', tot.publish_ok, '#86efac'],
        ['联合ROI调价', tot.combined_roi_bid, '#fbbf24'],
      ].map(([t,v,c])=>`<div class="card"><h3>${t}</h3><div class="val" style="color:${c}">${v??'—'}</div></div>`).join('');
      drawChart(j.series || []);
    }
    load();
    let ws;
    function connectWs() {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      ws = new WebSocket(`${proto}://${location.host}/ws/dashboard/analytics`);
      ws.onopen = () => { document.getElementById('live').textContent = '● 实时推送已连接'; };
      ws.onclose = () => { document.getElementById('live').textContent = '○ 已断开，30s 后重连'; setTimeout(connectWs, 30000); };
      ws.onmessage = (ev) => {
        try {
          const j = JSON.parse(ev.data);
          applyChart(j);
          document.getElementById('live').textContent = '● 实时更新 ' + new Date().toLocaleTimeString();
        } catch(e) {}
      };
    }
    connectWs();
    setInterval(load, 120000);
  </script>
</body>
</html>"""


_PUBLISH_QUEUE_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>发布队列 Dashboard</title>
  <style>
    :root { --bg:#0f1419; --card:#1a2332; --text:#e7ecf3; --muted:#8b9cb3; --ok:#22c55e; --warn:#fbbf24; --bad:#f87171; }
    body { font-family: system-ui,sans-serif; background:var(--bg); color:var(--text); margin:0; padding:24px; }
    .nav a { color:#93c5fd; margin-right:16px; }
    h1 { margin:0 0 4px; }
    .sub { color:var(--muted); margin-bottom:16px; }
    .cards { display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:12px; margin:16px 0; }
    .card { background:var(--card); border-radius:10px; padding:14px; }
    .card h3 { margin:0 0 6px; font-size:0.8rem; color:var(--muted); font-weight:500; }
    .card .val { font-size:1.5rem; font-weight:600; }
    table { width:100%; border-collapse:collapse; background:var(--card); border-radius:10px; overflow:hidden; }
    th, td { padding:10px 12px; text-align:left; border-bottom:1px solid #243044; font-size:0.88rem; }
    th { color:var(--muted); font-weight:500; background:#121a26; }
    tr:last-child td { border-bottom:none; }
    .badge { display:inline-block; padding:2px 8px; border-radius:999px; font-size:0.72rem; }
    .st-queued { background:#1e3a5f; color:#93c5fd; }
    .st-published { background:#14532d; color:#86efac; }
    .st-failed { background:#450a0a; color:#fca5a5; }
    .toolbar { display:flex; gap:10px; flex-wrap:wrap; margin:12px 0 16px; align-items:center; }
    button { background:#3b82f6; color:#fff; border:none; padding:8px 14px; border-radius:8px; cursor:pointer; }
    button.secondary { background:#334155; }
    #live { font-size:0.85rem; color:var(--ok); }
    .mono { font-family: ui-monospace, monospace; font-size:0.78rem; color:var(--muted); }
  </style>
</head>
<body>
  <div class="nav"><a href="/dashboard">首页</a><a href="/dashboard/ad-bid">广告预算</a><a href="/dashboard/perception">识别记录</a><a href="/dashboard/publish-queue">待发布</a><a href="/dashboard/analytics">赚钱效果</a><a href="/dashboard/runtime">系统状态</a></div>
  <h1>发布队列 Dashboard</h1>
  <p class="sub">多 run 矩阵入队错峰 · ROI 动态优先级 · Worker 状态 · 实时刷新</p>
  <div id="live">加载中…</div>
  <div class="cards" id="cards"></div>
  <div class="toolbar">
    <input id="orgFilter" placeholder="org_id 过滤" style="padding:8px;border-radius:8px;border:1px solid #334155;background:#0f172a;color:#e7ecf3"/>
    <button id="refresh">刷新</button>
    <button id="trigger" class="secondary">立即消费一批</button>
    <button id="refreshPri" class="secondary">刷新 ROI 优先级</button>
    <button id="startWorker" class="secondary">启动 Worker</button>
    <span class="mono" id="rateCfg"></span>
  </div>
  <table>
    <thead><tr>
      <th>状态</th><th>平台/账号</th><th>标题/脚本</th><th>Run</th><th>优先级/ROI</th><th>计划时间</th><th>重试</th>
    </tr></thead>
    <tbody id="rows"></tbody>
  </table>
  <script>
    function fmtTs(ts) {
      if (!ts) return '—';
      const d = new Date(ts * 1000);
      return d.toLocaleString();
    }
    function badge(st) {
      const cls = st==='queued'?'st-queued':(st==='published'?'st-published':'st-failed');
      return `<span class="badge ${cls}">${st}</span>`;
    }
    async function load() {
      const org = document.getElementById('orgFilter').value.trim();
      const q = new URLSearchParams({ limit: '80' });
      if (org) q.set('org_id', org);
      const r = await fetch('/api/dashboard/publish-queue?' + q.toString());
      const j = await r.json();
      const s = j.stats || {};
      const w = j.worker || {};
      const rl = j.rate_limit || {};
      document.getElementById('live').textContent = '● 更新 ' + new Date().toLocaleTimeString()
        + (w.enabled ? ' · Worker ON' : ' · Worker OFF')
        + (j.dynamic_priority ? ' · ROI优先级 ON' : ' · ROI优先级 OFF');
      document.getElementById('rateCfg').textContent =
        `限流 ${rl.enabled?'ON':'OFF'} · 间隔 ${rl.min_interval_sec||0}s · 矩阵错峰 ${rl.matrix_stagger_sec||0}s · run上限 ${rl.max_queued_per_run||0}`;
      document.getElementById('cards').innerHTML = [
        ['待发布(到期)', s.queued_due_now, '#93c5fd'],
        ['待发布(排队)', s.queued_scheduled, '#60a5fa'],
        ['ROI 可调整', s.roi_adjustable, '#34d399'],
        ['手动锁定', s.roi_locked, '#f87171'],
        ['队列总数', s.total, '#e7ecf3'],
        ['活跃 Run', s.unique_runs, '#fbbf24'],
      ].map(([t,v,c])=>`<div class="card"><h3>${t}</h3><div class="val" style="color:${c}">${v??0}</div></div>`).join('');
      function priHint(q) {
        const src = q.priority_source || 'default';
        const roi = q.combined_roi_score != null ? Number(q.combined_roi_score).toFixed(2) : '—';
        const grade = q.roi_grade || '';
        const delta = q.priority_delta || 0;
        const sug = q.suggested_priority || q.priority || 0;
        let tag = src === 'pinned' ? '📌置顶' : (src === 'manual' ? '✋手动' : (src === 'roi' ? '🤖ROI' : ''));
        let diff = '';
        if (delta > 0) diff = `<span style="color:#34d399">→P${sug}(+${delta})</span>`;
        else if (delta < 0) diff = `<span style="color:#f87171">→P${sug}(${delta})</span>`;
        return `<br><span class="mono">ROI ${roi}${grade?(' '+grade):''} ${tag} ${diff}</span>`;
      }
      const rows = j.items || [];
      document.getElementById('rows').innerHTML = rows.length ? rows.map(q => `
        <tr>
          <td>${badge(q.status)}</td>
          <td>${q.platform||''}<br><span class="mono">${q.account_id||''}</span></td>
          <td>${(q.title||q.script||'').slice(0,60)}</td>
          <td class="mono">${(q.run_id||'').slice(0,12)}</td>
          <td>P${q.priority||0}${priHint(q)}
            ${q.status==='queued'?`<br><button data-pin="${q.job_id}" class="secondary" style="margin-top:4px;padding:2px 6px;font-size:0.72rem">置顶</button>
            <button data-bump="${q.job_id}" class="secondary" style="margin-top:4px;padding:2px 6px;font-size:0.72rem">+5</button>
            <button data-cancel="${q.job_id}" class="secondary" style="margin-top:4px;padding:2px 6px;font-size:0.72rem">取消</button>`:''}
          </td>
          <td>${fmtTs(q.scheduled_ts)}<br><span class="mono">${q.due_in_sec?('+'+q.due_in_sec+'s'):''}${q.org_id?(' · '+q.org_id):''}</span></td>
          <td>${q.retry_count||0}${q.last_error?('<br><span class="mono">'+q.last_error.slice(0,40)+'</span>'):''}</td>
        </tr>`).join('') : '<tr><td colspan="7" style="color:#8b9cb3">暂无队列任务</td></tr>';
      document.querySelectorAll('[data-pin]').forEach(btn => btn.onclick = async () => {
        const org = document.getElementById('orgFilter').value.trim();
        await fetch('/api/publish/queue/' + btn.dataset.pin + '/pin?org_id=' + encodeURIComponent(org), { method:'POST' });
        load();
      });
      document.querySelectorAll('[data-bump]').forEach(btn => btn.onclick = async () => {
        const org = document.getElementById('orgFilter').value.trim();
        await fetch('/api/publish/queue/' + btn.dataset.bump + '/bump', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ delta: 5, org_id: org })
        });
        load();
      });
      document.querySelectorAll('[data-cancel]').forEach(btn => btn.onclick = async () => {
        const org = document.getElementById('orgFilter').value.trim();
        await fetch('/api/publish/queue/' + btn.dataset.cancel + '/cancel?org_id=' + encodeURIComponent(org), { method:'POST' });
        load();
      });
    }
    document.getElementById('refresh').onclick = load;
    document.getElementById('trigger').onclick = async () => {
      await fetch('/api/publish/queue/trigger?sync=1', { method:'POST' });
      load();
    };
    document.getElementById('startWorker').onclick = async () => {
      await fetch('/api/publish/queue/start', { method:'POST' });
      load();
    };
    document.getElementById('refreshPri').onclick = async () => {
      const org = document.getElementById('orgFilter').value.trim();
      const q = new URLSearchParams({ limit: '100' });
      if (org) q.set('org_id', org);
      const r = await fetch('/api/publish/queue/refresh-priority?' + q.toString(), { method:'POST' });
      const j = await r.json();
      alert('已刷新 ' + (j.updated||0) + ' 条，跳过锁定 ' + (j.skipped_locked||0) + ' 条');
      load();
    };
    load();
    setInterval(load, 15000);
    let ws;
    function connectWs() {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      ws = new WebSocket(`${proto}://${location.host}/ws/dashboard/feed`);
      ws.onmessage = () => load();
      ws.onclose = () => setTimeout(connectWs, 30000);
    }
    connectWs();
  </script>
</body>
</html>"""


@router.get("/dashboard/publish-queue", response_class=HTMLResponse)
def publish_queue_dashboard():
    return _html(_PUBLISH_QUEUE_DASHBOARD_HTML)


@router.get("/api/dashboard/publish-queue")
def publish_queue_api(limit: int = 80, org_id: str = ""):
    from services.publish_queue_dashboard import build_publish_queue_dashboard

    return build_publish_queue_dashboard(limit=max(10, min(limit, 200)), org_id=org_id.strip())


@router.get("/dashboard/analytics", response_class=HTMLResponse)
def analytics_dashboard():
    return _html(_ANALYTICS_DASHBOARD_HTML)


@router.get("/api/dashboard/metrics-chart")
def metrics_chart(days: int = 14):
    from services.dashboard_metrics import build_metrics_chart

    return build_metrics_chart(days=max(1, min(days, 90)))


@router.get("/dashboard/perception", response_class=HTMLResponse)
def perception_dashboard():
    return _html(_PERCEPTION_DASHBOARD_HTML)


@router.get("/api/dashboard/perception-feed")
def perception_feed(limit: int = 40):
    from services.dashboard_feed import build_perception_feed

    return build_perception_feed(limit=limit)


@router.websocket("/ws/dashboard/feed")
async def ws_dashboard_feed(websocket: WebSocket):
    if not await verify_websocket_auth(websocket):
        await websocket.close(code=4401, reason="unauthorized")
        return
    from services.dashboard_hub import connect_feed, disconnect_feed

    await connect_feed(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await disconnect_feed(websocket)
    except Exception:
        await disconnect_feed(websocket)


@router.websocket("/ws/dashboard/analytics")
async def ws_dashboard_analytics(websocket: WebSocket):
    if not await verify_websocket_auth(websocket):
        await websocket.close(code=4401, reason="unauthorized")
        return
    from services.dashboard_hub import connect_analytics, disconnect_analytics

    await connect_analytics(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await disconnect_analytics(websocket)
    except Exception:
        await disconnect_analytics(websocket)


@router.get("/api/dashboard/ws/status")
def ws_status():
    from services.dashboard_hub import analytics_connection_count, connection_count, runtime_connection_count

    return {
        "ok": True,
        "feed_connections": connection_count(),
        "analytics_connections": analytics_connection_count(),
        "runtime_connections": runtime_connection_count(),
    }


@router.websocket("/ws/dashboard/runtime")
async def ws_dashboard_runtime(
    websocket: WebSocket,
    org_id: str = "",
    platform: str = "douyin",
):
    if not await verify_websocket_auth(websocket):
        await websocket.close(code=4401, reason="unauthorized")
        return
    from services.dashboard_hub import connect_runtime, disconnect_runtime

    await connect_runtime(websocket, org_id=org_id, platform=platform)
    try:
        while True:
            msg = await websocket.receive_text()
            if msg.strip().lower() in ("refresh", "ping"):
                from services.dashboard_hub import broadcast_runtime

                await broadcast_runtime(reason="client_refresh")
    except WebSocketDisconnect:
        await disconnect_runtime(websocket)
    except Exception:
        await disconnect_runtime(websocket)


@router.get("/dashboard/runtime", response_class=HTMLResponse)
def runtime_dashboard_page():
    return _html(_RUNTIME_OPERATOR_HTML)


@router.get("/dashboard/runtime/advanced", response_class=HTMLResponse)
def runtime_dashboard_advanced_page():
    return _html(_RUNTIME_ADVANCED_HTML)


@router.get("/api/dashboard/runtime")
def runtime_dashboard_api(platform: str = "douyin", org_id: str = ""):
    from services.runtime_dashboard import build_runtime_dashboard

    return build_runtime_dashboard(
        platform=platform.strip().lower() or "douyin",
        org_id=org_id.strip(),
    )


@router.get("/api/orgs/catalog")
def org_catalog_api():
    from services.org_catalog import org_catalog_status

    return org_catalog_status()
