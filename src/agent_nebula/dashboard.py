"""Real-time monitoring dashboard for AgentNebula workflows.

Serves a web UI that shows:
- Grid visualization of all tasks (color-coded by status)
- Current active session info
- Live session log streaming via WebSocket
- Progress stats and session history
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from agent_nebula.config import ProjectConfig
from agent_nebula.tasks import TaskList
from agent_nebula.state import read_progress, next_session_number


app = FastAPI(title="AgentNebula Dashboard")

# Global state — set by the orchestrator before starting the server
_workflow_dir: Path | None = None
_active_session: dict[str, Any] = {
    "session_num": 0,
    "phase": "idle",
    "current_task_id": None,
    "model": "",
    "started_at": None,
}
_log_lines: list[str] = []
_ws_clients: set[WebSocket] = set()


def set_workflow_dir(workflow_dir: Path) -> None:
    global _workflow_dir
    _workflow_dir = workflow_dir


def update_session_state(**kwargs) -> None:
    _active_session.update(kwargs)
    asyncio.ensure_future(_broadcast({"type": "session_update", "data": _active_session}))


def append_log(line: str) -> None:
    _log_lines.append(line)
    if len(_log_lines) > 500:
        _log_lines.pop(0)
    asyncio.ensure_future(_broadcast({"type": "log", "line": line}))


async def _broadcast(message: dict) -> None:
    dead = set()
    data = json.dumps(message, ensure_ascii=False, default=str)
    for ws in _ws_clients:
        try:
            await ws.send_text(data)
        except Exception:
            dead.add(ws)
    _ws_clients -= dead


def _get_state() -> dict[str, Any]:
    if _workflow_dir is None:
        return {"error": "No workflow directory set"}

    tl = TaskList(_workflow_dir)
    tasks = []
    for t in tl.tasks:
        tasks.append({
            "id": t.id, "category": t.category, "priority": t.priority,
            "description": t.description, "dependencies": t.dependencies,
            "passes": t.passes, "session_attempted": t.session_attempted,
            "notes": t.notes, "metadata": t.metadata,
        })

    done, total = tl.stats()
    session_num = next_session_number(_workflow_dir)

    config_data = {}
    try:
        config = ProjectConfig.load(_workflow_dir)
        config_data = {
            "name": config.name, "cwd": str(config.resolve_cwd(_workflow_dir)),
            "model_complex": config.workflow.model_complex,
            "model_simple": config.workflow.model_simple,
        }
    except Exception:
        pass

    hist_dir = _workflow_dir / "session_history"
    sessions = []
    if hist_dir.exists():
        for sf in sorted(hist_dir.glob("session_*.md")):
            sessions.append({"name": sf.stem, "content": sf.read_text(encoding="utf-8")[:500]})

    return {
        "config": config_data, "tasks": tasks,
        "stats": {"done": done, "total": total, "session_num": session_num - 1},
        "active_session": _active_session,
        "session_history": sessions[-10:],
        "log_lines": _log_lines[-100:],
    }


@app.get("/api/state")
async def api_state():
    return _get_state()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_clients.add(ws)
    try:
        await ws.send_text(json.dumps({"type": "full_state", "data": _get_state()}, ensure_ascii=False, default=str))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(ws)


@app.get("/", response_class=HTMLResponse)
async def index():
    return _DASHBOARD_HTML


_DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgentNebula Dashboard</title>
<style>
:root {
  --bg: #0d1117; --bg2: #161b22; --border: #30363d; --text: #c9d1d9;
  --text-dim: #8b949e; --text-bright: #f0f6fc; --blue: #58a6ff;
  --green: #3fb950; --green-bg: #1b2e1b; --red: #f85149; --purple: #d2a8ff;
  --yellow: #d29922; --orange: #db6d28;
}
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); }

/* Header */
.header { background: var(--bg2); padding: 14px 24px; border-bottom: 1px solid var(--border); display:flex; align-items:center; gap:16px; }
.header h1 { font-size:20px; color:var(--blue); letter-spacing:-0.5px; }
.badge { padding:3px 10px; border-radius:10px; font-size:11px; font-weight:700; text-transform:uppercase; }
.badge-idle { background:var(--border); color:var(--text-dim); }
.badge-initializing { background:#1f2d3d; color:var(--blue); }
.badge-working { background:var(--green-bg); color:var(--green); animation:pulse 2s infinite; }
.badge-completed { background:var(--green-bg); color:var(--green); }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.6} }

/* Layout */
.layout { display:grid; grid-template-columns:1fr 340px; grid-template-rows:auto 1fr; height:calc(100vh - 52px); }
.stats { grid-column:1/-1; background:var(--bg2); padding:10px 24px; border-bottom:1px solid var(--border); display:flex; gap:28px; align-items:center; }
.stat-box { display:flex; flex-direction:column; }
.stat-label { font-size:10px; color:var(--text-dim); text-transform:uppercase; letter-spacing:0.5px; }
.stat-val { font-size:20px; font-weight:700; color:var(--text-bright); }
.prog-wrap { flex:1; display:flex; align-items:center; gap:8px; }
.prog-bar { flex:1; background:#21262d; border-radius:4px; height:6px; }
.prog-fill { height:100%; border-radius:4px; background:linear-gradient(90deg,#238636,var(--green)); transition:width .5s; }
.prog-pct { font-size:13px; color:var(--green); font-weight:600; min-width:40px; text-align:right; }

/* Task Grid (left panel) */
.grid-panel { overflow:auto; padding:16px 20px; }
.grid-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }
.grid-header h2 { font-size:14px; color:var(--text-dim); }
.grid-filter { display:flex; gap:6px; }
.filter-btn { background:var(--bg2); border:1px solid var(--border); color:var(--text-dim); padding:3px 10px; border-radius:4px; font-size:11px; cursor:pointer; }
.filter-btn.active { border-color:var(--blue); color:var(--blue); background:#1f2d3d; }
.task-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(110px, 1fr)); gap:6px; }
.task-cell { background:var(--bg2); border:1px solid var(--border); border-radius:6px; padding:8px; cursor:pointer; transition:all .15s; position:relative; min-height:56px; }
.task-cell:hover { border-color:var(--blue); transform:translateY(-1px); }
.task-cell .tc-id { font-size:11px; font-weight:700; color:var(--text-dim); margin-bottom:2px; }
.task-cell .tc-name { font-size:10px; color:var(--text); line-height:1.3; overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }
.task-cell .tc-icon { position:absolute; top:6px; right:6px; font-size:12px; }
/* States */
.task-cell.pending { border-left:3px solid var(--border); }
.task-cell.completed { border-left:3px solid var(--green); background:#0d1f0d; }
.task-cell.completed .tc-id { color:var(--green); }
.task-cell.in_progress { border-left:3px solid var(--blue); background:#0d1520; box-shadow:0 0 8px rgba(88,166,255,0.15); }
.task-cell.in_progress .tc-id { color:var(--blue); }
.task-cell.failed { border-left:3px solid var(--red); background:#1f0d0d; }

/* Sidebar */
.sidebar { border-left:1px solid var(--border); display:flex; flex-direction:column; overflow:hidden; }
.sb-section { padding:10px 14px; border-bottom:1px solid var(--border); }
.sb-section h3 { font-size:11px; color:var(--text-dim); text-transform:uppercase; letter-spacing:0.5px; margin-bottom:6px; }

/* Active task detail */
.detail-card { background:var(--bg2); border:1px solid var(--border); border-radius:6px; padding:10px 12px; }
.detail-row { display:flex; justify-content:space-between; font-size:12px; margin-bottom:3px; }
.detail-row .dl { color:var(--text-dim); }
.detail-row .dv { color:var(--text-bright); font-weight:600; text-align:right; max-width:180px; overflow:hidden; text-overflow:ellipsis; }

/* Session cards */
.sess-card { background:var(--bg2); border:1px solid var(--border); border-radius:5px; padding:6px 10px; margin-bottom:4px; font-size:11px; }
.sess-card .sc-name { color:var(--blue); font-weight:600; }
.sess-card .sc-info { color:var(--text-dim); margin-top:2px; }

/* Log */
.log-wrap { flex:1; overflow-y:auto; padding:6px 14px; font-family:'Cascadia Code','Fira Code',monospace; font-size:11px; line-height:1.5; background:var(--bg); }
.log-l { color:var(--text-dim); white-space:pre-wrap; word-break:break-all; }
.log-l.tool { color:var(--purple); }
.log-l.err { color:var(--red); }
.log-l.txt { color:var(--text); }

/* Task detail popup */
.popup-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.6); z-index:100; justify-content:center; align-items:center; }
.popup-overlay.show { display:flex; }
.popup { background:var(--bg2); border:1px solid var(--border); border-radius:10px; padding:20px 24px; max-width:520px; width:90%; max-height:80vh; overflow-y:auto; }
.popup h2 { font-size:16px; color:var(--blue); margin-bottom:12px; }
.popup .close-btn { float:right; background:none; border:none; color:var(--text-dim); font-size:18px; cursor:pointer; }
.popup .field { margin-bottom:8px; }
.popup .field-label { font-size:11px; color:var(--text-dim); text-transform:uppercase; }
.popup .field-value { font-size:13px; color:var(--text-bright); }
.popup .meta-table { width:100%; font-size:12px; border-collapse:collapse; margin-top:8px; }
.popup .meta-table td { padding:4px 8px; border-bottom:1px solid var(--border); }
.popup .meta-table td:first-child { color:var(--text-dim); width:40%; }
</style>
</head>
<body>
<div class="header">
    <h1>AgentNebula</h1>
    <span id="phaseBadge" class="badge badge-idle">IDLE</span>
    <span id="projectName" style="color:var(--text-dim);font-size:14px"></span>
</div>
<div class="layout">
    <div class="stats">
        <div class="stat-box"><span class="stat-label">Tasks</span><span class="stat-val" id="sDone">0/0</span></div>
        <div class="stat-box"><span class="stat-label">Sessions</span><span class="stat-val" id="sSess">0</span></div>
        <div class="stat-box"><span class="stat-label">Current</span><span class="stat-val" id="sCur" style="font-size:14px">—</span></div>
        <div class="prog-wrap">
            <div class="prog-bar"><div class="prog-fill" id="progFill" style="width:0%"></div></div>
            <span class="prog-pct" id="progPct">0%</span>
        </div>
    </div>
    <div class="grid-panel">
        <div class="grid-header">
            <h2 id="gridTitle">Tasks</h2>
            <div class="grid-filter">
                <button class="filter-btn active" onclick="setFilter('all')">All</button>
                <button class="filter-btn" onclick="setFilter('pending')">Pending</button>
                <button class="filter-btn" onclick="setFilter('completed')">Done</button>
            </div>
        </div>
        <div class="task-grid" id="taskGrid"></div>
    </div>
    <div class="sidebar">
        <div class="sb-section">
            <h3>Active Session</h3>
            <div id="activeInfo" class="detail-card" style="min-height:40px">No active session</div>
        </div>
        <div class="sb-section" style="max-height:200px; overflow-y:auto;">
            <h3>Session History</h3>
            <div id="histList"></div>
        </div>
        <div class="sb-section" style="padding-bottom:4px"><h3>Live Log</h3></div>
        <div class="log-wrap" id="logBox"></div>
    </div>
</div>

<!-- Task detail popup -->
<div class="popup-overlay" id="popupOverlay" onclick="if(event.target===this)closePopup()">
    <div class="popup" id="popupContent"></div>
</div>

<script>
let S = {tasks:[],stats:{done:0,total:0,session_num:0},active_session:{},config:{},session_history:[],log_lines:[]};
let filter = 'all';

// WS
function connect() {
    const ws = new WebSocket('ws://'+location.host+'/ws');
    ws.onmessage = e => {
        const m = JSON.parse(e.data);
        if (m.type==='full_state') { S=m.data; renderAll(); }
        else if (m.type==='session_update') { S.active_session=m.data; renderStats(); renderActive(); }
        else if (m.type==='log') { S.log_lines.push(m.line); if(S.log_lines.length>200)S.log_lines.shift(); addLog(m.line); }
        else if (m.type==='task_update') { fetch('/api/state').then(r=>r.json()).then(d=>{S=d;renderAll();}); }
    };
    ws.onclose = () => setTimeout(connect,2000);
    ws.onerror = () => ws.close();
}
connect();
setInterval(()=>fetch('/api/state').then(r=>r.json()).then(d=>{S=d;renderAll();}), 5000);

function renderAll() { renderStats(); renderGrid(); renderActive(); renderHist(); renderLog(); }

// Stats
function renderStats() {
    const {done,total,session_num}=S.stats;
    document.getElementById('sDone').textContent=done+'/'+total;
    document.getElementById('sSess').textContent=session_num;
    document.getElementById('sCur').textContent=S.active_session.current_task_id||'—';
    const pct=total>0?(done/total*100):0;
    document.getElementById('progFill').style.width=pct+'%';
    document.getElementById('progPct').textContent=Math.round(pct)+'%';
    const b=document.getElementById('phaseBadge');
    const ph=S.active_session.phase||'idle';
    b.textContent=ph.toUpperCase();
    b.className='badge badge-'+ph;
    document.getElementById('projectName').textContent=S.config.name||'';
}

// Grid
function setFilter(f) {
    filter=f;
    document.querySelectorAll('.filter-btn').forEach(b=>b.classList.toggle('active', b.textContent.toLowerCase()===f||f==='all'&&b.textContent==='All'));
    renderGrid();
}
function renderGrid() {
    const g=document.getElementById('taskGrid');
    g.innerHTML='';
    let tasks=S.tasks;
    if (filter==='pending') tasks=tasks.filter(t=>!t.passes);
    else if (filter==='completed') tasks=tasks.filter(t=>t.passes);

    document.getElementById('gridTitle').textContent=`Tasks (${tasks.length})`;

    tasks.forEach(t => {
        const d=document.createElement('div');
        let cls='task-cell pending';
        let icon='○';
        if (t.passes) { cls='task-cell completed'; icon='✓'; }
        else if (S.active_session.current_task_id===t.id) { cls='task-cell in_progress'; icon='⟳'; }
        d.className=cls;

        // Extract short name from metadata or description
        let shortName = '';
        if (t.metadata && t.metadata.script_name) shortName = t.metadata.script_name;
        else shortName = t.description.replace(/^Generate .* for /,'').substring(0,30);

        d.innerHTML=`<span class="tc-icon">${icon}</span><div class="tc-id">${t.id}</div><div class="tc-name">${shortName}</div>`;
        d.onclick = () => showPopup(t);
        g.appendChild(d);
    });
}

// Popup
function showPopup(t) {
    const p=document.getElementById('popupContent');
    let statusText = t.passes ? '<span style="color:var(--green)">✓ Completed</span>' : '<span style="color:var(--yellow)">○ Pending</span>';
    if (S.active_session.current_task_id===t.id) statusText='<span style="color:var(--blue)">⟳ In Progress</span>';

    let metaHtml='';
    if (t.metadata && Object.keys(t.metadata).length) {
        metaHtml='<table class="meta-table">';
        for (const [k,v] of Object.entries(t.metadata)) {
            metaHtml+=`<tr><td>${k}</td><td style="color:var(--text-bright);word-break:break-all">${v}</td></tr>`;
        }
        metaHtml+='</table>';
    }

    p.innerHTML=`
        <button class="close-btn" onclick="closePopup()">✕</button>
        <h2>${t.id}</h2>
        <div class="field"><div class="field-label">Status</div><div class="field-value">${statusText}</div></div>
        <div class="field"><div class="field-label">Description</div><div class="field-value">${t.description}</div></div>
        <div class="field"><div class="field-label">Category / Priority</div><div class="field-value">${t.category} / p${t.priority}</div></div>
        ${t.dependencies.length ? '<div class="field"><div class="field-label">Dependencies</div><div class="field-value">'+t.dependencies.join(', ')+'</div></div>' : ''}
        ${t.session_attempted ? '<div class="field"><div class="field-label">Session</div><div class="field-value">#'+t.session_attempted+'</div></div>' : ''}
        ${t.notes ? '<div class="field"><div class="field-label">Notes</div><div class="field-value" style="white-space:pre-wrap">'+t.notes+'</div></div>' : ''}
        ${metaHtml ? '<div class="field"><div class="field-label">Metadata</div>'+metaHtml+'</div>' : ''}
    `;
    document.getElementById('popupOverlay').classList.add('show');
}
function closePopup() { document.getElementById('popupOverlay').classList.remove('show'); }
document.addEventListener('keydown', e => { if(e.key==='Escape') closePopup(); });

// Active session
function renderActive() {
    const s=S.active_session, el=document.getElementById('activeInfo');
    if (!s||s.phase==='idle') { el.innerHTML='<span style="color:var(--text-dim);font-size:12px">No active session</span>'; return; }
    el.innerHTML=`
        <div class="detail-row"><span class="dl">Phase</span><span class="dv">${s.phase}</span></div>
        <div class="detail-row"><span class="dl">Session</span><span class="dv">#${s.session_num}</span></div>
        <div class="detail-row"><span class="dl">Task</span><span class="dv">${s.current_task_id||'—'}</span></div>
        <div class="detail-row"><span class="dl">Model</span><span class="dv">${s.model||'—'}</span></div>
        ${s.started_at?'<div class="detail-row"><span class="dl">Started</span><span class="dv">'+new Date(s.started_at*1000).toLocaleTimeString()+'</span></div>':''}
    `;
}

// History
function renderHist() {
    const el=document.getElementById('histList');
    const ss=S.session_history||[];
    el.innerHTML=ss.map(s=>`
        <div class="sess-card"><div class="sc-name">${s.name}</div><div class="sc-info">${(s.content||'').substring(0,100)}...</div></div>
    `).join('')||'<span style="color:var(--text-dim);font-size:11px">No sessions yet</span>';
}

// Log
function renderLog() {
    const el=document.getElementById('logBox');
    el.innerHTML='';
    (S.log_lines||[]).forEach(l=>addLog(l));
}
function addLog(line) {
    const el=document.getElementById('logBox');
    const d=document.createElement('div');
    d.className='log-l';
    if (line.includes('[Tool:')) d.className+=' tool';
    else if (line.toLowerCase().includes('error')) d.className+=' err';
    else d.className+=' txt';
    d.textContent=line;
    el.appendChild(d);
    el.scrollTop=el.scrollHeight;
}
</script>
</body>
</html>"""
