"""SPEAR Interactive Replay Timeline - P1-1: Post-action analysis tool.

Generates a self-contained HTML page with:
- Timeline scrubber with play/pause/speed controls
- Event markers color-coded by type and ASDA phase
- State reconstruction at each snapshot time point
- Metrics charts (entities, tracks, vulnerability) rendered via Canvas
- LVC layer breakdown per time point
- Event detail panel with full event inspection
- Threat summary (kinetic/EW/cyber) distribution

This is the SPEAR (Simulation Playback, Evaluation, Analysis & Review)
interactive component that transforms post-simulation data into an
actionable analysis dashboard.
"""

import json
import os

from config import ASDA_PHASES, OUTPUT_DIR


class SpearTimeline:
    """Generates an interactive HTML timeline from SPEAR replay data."""

    def __init__(self):
        self._snapshots: list[dict] = []
        self._events: list[dict] = []
        self._metrics: dict = {}
        self._report: dict = {}
        self._bases: list[dict] = []

    def load_from_spear(self, spear, bases: list = None):
        """Load data from a SpearReplay instance."""
        self._snapshots = spear.snapshots[-500:]  # cap for performance
        self._events = spear.events[-1000:]
        self._metrics = {k: v[-500:] for k, v in spear.metrics.items()}
        self._report = spear.generate_report()
        self._bases = bases or []

    def load_from_json(self, filepath: str, bases: list = None):
        """Load SPEAR data from an exported JSON file."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._snapshots = data.get("snapshots", [])[-500:]
        self._events = data.get("events", [])[-1000:]
        self._metrics = {k: v[-500:] for k, v in data.get("metrics", {}).items()}
        self._report = data.get("report", {})
        self._bases = bases or []

    def generate_html(self, output_path: str = None) -> str:
        """Generate the interactive timeline HTML page."""
        if not output_path:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            output_path = os.path.join(OUTPUT_DIR, "pmtec_spear_timeline.html")

        # Prepare data for embedding
        snapshots_js = json.dumps(self._snapshots, ensure_ascii=False, default=str)
        events_js = json.dumps(self._events, ensure_ascii=False, default=str)
        metrics_js = json.dumps(self._metrics, ensure_ascii=False, default=str)
        report_js = json.dumps(self._report, ensure_ascii=False, default=str)
        bases_js = json.dumps(self._bases, ensure_ascii=False)
        phases_js = json.dumps(ASDA_PHASES, ensure_ascii=False)

        html = _TIMELINE_TEMPLATE
        html = html.replace("__SNAPSHOTS__", snapshots_js)
        html = html.replace("__EVENTS__", events_js)
        html = html.replace("__METRICS__", metrics_js)
        html = html.replace("__REPORT__", report_js)
        html = html.replace("__BASES__", bases_js)
        html = html.replace("__PHASES__", phases_js)

        # Escape any problematic content
        html = html.replace("</script>", "<\\/script>")

        with open(output_path, "w", encoding="utf-8") as f:
            # Un-escape the script closing tags within our data
            f.write(html.replace("<\\/script>", "</script>"))

        return output_path


_TIMELINE_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SPEAR Interactive Timeline - PMTEC DTC 2026</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #0a0e1a; color: #c0c8d8; font-family: 'Segoe UI', 'Courier New', monospace;
         overflow-x: hidden; }
  #header { background: linear-gradient(135deg, #0d1b2a, #1b263b); padding: 12px 24px;
            border-bottom: 2px solid #415977; display: flex; justify-content: space-between; align-items: center; }
  #header h1 { color: #4e9af5; font-size: 18px; }
  #header .meta { font-size: 12px; color: #6a7a8a; }

  #toolbar { background: #0d1b2a; padding: 10px 24px; border-bottom: 1px solid #1b263b;
             display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
  .btn { background: #1b263b; color: #4e9af5; border: 1px solid #415977; padding: 6px 16px;
          border-radius: 4px; cursor: pointer; font-size: 13px; transition: all 0.2s; }
  .btn:hover { background: #2b364b; border-color: #4e9af5; }
  .btn.active { background: #1a4a2a; border-color: #4e9af5; color: #4ef59e; }
  #scrubber { flex: 1; min-width: 300px; height: 28px; }
  #time-display { font-size: 14px; color: #f59e4e; font-family: 'Courier New', monospace;
                  min-width: 120px; }
  #speed-select { background: #1b263b; color: #4e9af5; border: 1px solid #415977;
                   padding: 4px 8px; border-radius: 4px; font-size: 12px; }

  #main { display: flex; min-height: calc(100vh - 100px); }
  #left-panel { flex: 2; display: flex; flex-direction: column; border-right: 1px solid #1b263b; }
  #right-panel { flex: 1; background: #0d1b2a; overflow-y: auto; padding: 12px; }

  #timeline-canvas-wrap { background: #080c14; padding: 8px; position: relative;
                          border-bottom: 1px solid #1b263b; }
  #timeline-canvas { width: 100%; height: 180px; display: block; cursor: crosshair; }
  #timeline-tooltip { position: absolute; background: rgba(13,27,42,0.95); border: 1px solid #415977;
                       padding: 6px 10px; border-radius: 4px; font-size: 11px; pointer-events: none;
                       display: none; z-index: 10; max-width: 300px; }

  #metrics-charts { display: flex; flex-wrap: wrap; gap: 8px; padding: 8px; }
  .chart-box { background: #080c14; border: 1px solid #1b263b; border-radius: 4px;
                padding: 8px; flex: 1; min-width: 280px; }
  .chart-box h4 { color: #4e9af5; font-size: 11px; margin-bottom: 4px; text-transform: uppercase; }
  .chart-canvas { width: 100%; height: 120px; display: block; }

  #state-panel { background: #080c14; padding: 12px; flex: 1; overflow-y: auto; }
  #state-panel h3 { color: #4e9af5; font-size: 13px; margin-bottom: 8px; }
  .state-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .state-item { background: #0d1b2a; padding: 6px 10px; border-radius: 4px; border: 1px solid #1b263b; }
  .state-label { font-size: 10px; color: #6a7a8a; text-transform: uppercase; }
  .state-value { font-size: 16px; color: #f59e4e; font-family: 'Courier New', monospace; }

  .event-list-item { padding: 6px 10px; margin: 3px 0; font-size: 11px;
                      border-left: 3px solid #333; background: #0d1b2a; border-radius: 0 4px 4px 0;
                      cursor: pointer; transition: background 0.15s; }
  .event-list-item:hover { background: #1b263b; }
  .event-list-item.highlight { background: #1a2a4a; border-left-color: #4e9af5; }
  .evt-missile_launch { border-color: #f54e4e; }
  .evt-detect { border-color: #4ef59e; }
  .evt-damage { border-color: #f54e4e; background: #1a0808; }
  .evt-transfer { border-color: #f5e44e; }
  .evt-deploy { border-color: #4e9af5; }
  .evt-asda_cycle { border-color: #9e4ef5; }
  .evt-recover { border-color: #4ef5d4; }
  .evt-ew_jam_start { border-color: #f5a04e; }
  .evt-cyber_attack { border-color: #a04ef5; }
  .evt-cyber_detected { border-color: #4ef5a0; }
  .evt-dqn_decision { border-color: #4ef5d4; }
  .evt-intercept_decision { border-color: #4e9af5; }
  /* P12-4: 政治准入事件 */
  .evt-political_grey_zone { border-color: #f5c44e; background: #1a1408; }
  .evt-political_access_change { border-color: #b04ef5; background: #140a1a; }
  .evt-mrfd_freeze { border-color: #f58a4e; }

  #event-detail { background: #080c14; padding: 10px; margin-top: 8px;
                   border: 1px solid #1b263b; border-radius: 4px; font-size: 11px; display: none; }
  #event-detail h4 { color: #4e9af5; margin-bottom: 6px; }

  .phase-marker { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 4px; }
  .phase-Act { background: #4e9af5; }
  .phase-Sense { background: #4ef59e; }
  .phase-Decide { background: #f5e44e; }
  .phase-Adapt { background: #9e4ef5; }

  .summary-box { background: #0d1b2a; padding: 10px; border-radius: 4px;
                  border: 1px solid #1b263b; margin-bottom: 8px; }
  .summary-box h3 { color: #4e9af5; font-size: 12px; margin-bottom: 6px; }
  .summary-row { display: flex; justify-content: space-between; font-size: 11px; padding: 2px 0; }
  .summary-row span:first-child { color: #6a7a8a; }
  .summary-row span:last-child { color: #f59e4e; font-family: 'Courier New', monospace; }
</style>
</head>
<body>
<div id="header">
  <div>
    <h1>SPEAR Interactive Replay Timeline</h1>
    <div class="meta">PMTEC Digital Battlefield - DTC 2026 Level 3 P1</div>
  </div>
  <div class="meta" id="header-stats"></div>
</div>

<div id="toolbar">
  <button class="btn" id="btn-play" onclick="togglePlay()">Play</button>
  <button class="btn" id="btn-prev" onclick="stepBack()">&lt;&lt;</button>
  <button class="btn" id="btn-next" onclick="stepForward()">&gt;&gt;</button>
  <span id="time-display">T+00:00:00</span>
  <input type="range" id="scrubber" min="0" max="0" value="0" step="1" oninput="onScrub()">
  <select id="speed-select" onchange="changeSpeed()">
    <option value="0.5">0.5x</option>
    <option value="1" selected>1x</option>
    <option value="2">2x</option>
    <option value="4">4x</option>
    <option value="8">8x</option>
  </select>
  <button class="btn" onclick="resetView()">Reset</button>
</div>

<div id="main">
  <div id="left-panel">
    <div id="timeline-canvas-wrap">
      <canvas id="timeline-canvas"></canvas>
      <div id="timeline-tooltip"></div>
    </div>
    <div id="metrics-charts">
      <div class="chart-box">
        <h4>Active Entities Over Time</h4>
        <canvas class="chart-canvas" id="chart-entities"></canvas>
      </div>
      <div class="chart-box">
        <h4>Active Tracks Over Time</h4>
        <canvas class="chart-canvas" id="chart-tracks"></canvas>
      </div>
      <div class="chart-box">
        <h4>Network Vulnerability Over Time</h4>
        <canvas class="chart-canvas" id="chart-vuln"></canvas>
      </div>
      <div class="chart-box">
        <h4>P12-4: Political Escalation &amp; Ally Access Mix</h4>
        <canvas class="chart-canvas" id="chart-political"></canvas>
      </div>
    </div>
    <div id="state-panel">
      <h3>System State at Current Time</h3>
      <div class="state-grid" id="state-grid">
        <div class="state-item"><div class="state-label">Sim Time</div><div class="state-value" id="st-simtime">--</div></div>
        <div class="state-item"><div class="state-label">ASDA Cycle</div><div class="state-value" id="st-cycle">--</div></div>
        <div class="state-item"><div class="state-label">ASDA Phase</div><div class="state-value" id="st-phase">--</div></div>
        <div class="state-item"><div class="state-label">Total Entities</div><div class="state-value" id="st-entities">--</div></div>
        <div class="state-item"><div class="state-label">Active Tracks</div><div class="state-value" id="st-tracks">--</div></div>
        <div class="state-item"><div class="state-label">Net Vulnerability</div><div class="state-value" id="st-vuln">--</div></div>
        <div class="state-item"><div class="state-label">P10 政治升级度</div><div class="state-value" id="st-esc">--</div></div>
        <div class="state-item"><div class="state-label">盟友站点 Full/Restricted/Denied</div><div class="state-value" id="st-access">--</div></div>
      </div>
    </div>
  </div>

  <div id="right-panel">
    <div class="summary-box" id="report-summary"></div>
    <div class="summary-box">
      <h3>Event Log</h3>
      <div id="event-list"></div>
    </div>
    <div id="event-detail"></div>
  </div>
</div>

<script>
var snapshots = __SNAPSHOTS__;
var events = __EVENTS__;
var metrics = __METRICS__;
var report = __REPORT__;
var bases = __BASES__;
var phases = __PHASES__;

var currentIdx = 0;
var playing = false;
var speed = 1;
var playInterval = null;

var evtColors = {
  'missile_launch': '#f54e4e', 'detect': '#4ef59e', 'damage': '#f54e4e',
  'transfer': '#f5e44e', 'deploy': '#4e9af5', 'asda_cycle': '#9e4ef5',
  'recover': '#4ef5d4', 'ew_jam_start': '#f5a04e', 'cyber_attack': '#a04ef5',
  'cyber_detected': '#4ef5a0', 'dqn_decision': '#4ef5d4', 'intercept_decision': '#4e9af5',
  'evade_decision': '#f5e4a0', 'dqn_dispersal': '#4ef5d4', 'sim_start': '#4e9af5',
  'sim_stop': '#6a7a8a',
  // P12-4: 政治准入事件泳道配色
  'political_grey_zone': '#f5c44e', 'political_access_change': '#b04ef5',
  'mrfd_freeze': '#f58a4e'
};

// P12-4: 事件泳道定义（威胁 / 拦截决策 / 战果 / 政治）
var LANES = [
  { label: 'THREATS',   types: ['missile_launch', 'ew_jam_start', 'cyber_attack'], color: '#f54e4e' },
  { label: 'INTERCEPT', types: ['detect', 'intercept_decision', 'dqn_decision', 'evade_decision'], color: '#4e9af5' },
  { label: 'DAMAGE',    types: ['damage', 'recover', 'transfer', 'deploy', 'dqn_dispersal'], color: '#f5e44e' },
  { label: 'POLITICAL', types: ['political_grey_zone', 'political_access_change', 'mrfd_freeze'], color: '#b04ef5' }
];

// P12-4: 事件 → 时间轴 X 坐标（优先 data.asda_cycle 映射，退化到索引比例）
function eventLaneX(ev, cw) {
  var d = ev.data || {};
  if (d.asda_cycle != null && snapshots.length > 1) {
    var maxCycle = snapshots[snapshots.length - 1].asda_cycle || 1;
    return (d.asda_cycle / Math.max(maxCycle, 1)) * cw;
  }
  if (snapshots.length > 1) {
    var idx = Math.min(snapshots.length - 1, Math.floor((events.indexOf(ev) / Math.max(events.length,1)) * snapshots.length));
    return (idx / (snapshots.length - 1)) * cw;
  }
  return cw / 2;
}

// P12-4: 从快照提取政治态势序列 [{esc, full, restricted, denied}]
function politicalSeries() {
  var series = [];
  for (var i = 0; i < snapshots.length; i++) {
    var pa = snapshots[i].political_access;
    if (!pa) { series.push(null); continue; }
    var counts = { full: 0, restricted: 0, denied: 0 };
    for (var c in (pa.by_country || {})) {
      var sites = pa.by_country[c];
      for (var j = 0; j < sites.length; j++) {
        var st = sites[j].state;
        if (counts[st] !== undefined) counts[st]++;
      }
    }
    series.push({ esc: pa.escalation_level || 0, full: counts.full,
                  restricted: counts.restricted, denied: counts.denied });
  }
  return series;
}

function fmtTime(sec) {
  var h = Math.floor(sec / 3600);
  var m = Math.floor((sec % 3600) / 60);
  var s = Math.floor(sec % 60);
  return 'T+' + String(h).padStart(2,'0') + ':' + String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0');
}

function init() {
  // Header stats
  var statsHtml = 'Events: ' + events.length + ' | Snapshots: ' + snapshots.length;
  if (report.total_events) statsHtml += ' | Duration: ' + report.total_duration_s + 's';
  document.getElementById('header-stats').innerHTML = statsHtml;

  // Scrubber
  var scrubber = document.getElementById('scrubber');
  scrubber.max = snapshots.length > 0 ? snapshots.length - 1 : 0;
  scrubber.value = 0;

  // Summary box
  var summaryHtml = '<h3>SPEAR Analysis Report</h3>';
  if (report.summary) summaryHtml += '<pre style="font-size:10px;color:#8a9aaa;white-space:pre-wrap;">' + report.summary + '</pre>';
  if (report.event_distribution) {
    summaryHtml += '<div style="margin-top:6px;">';
    for (var k in report.event_distribution) {
      summaryHtml += '<div class="summary-row"><span>' + k + '</span><span>' + report.event_distribution[k] + '</span></div>';
    }
    summaryHtml += '</div>';
  }
  if (report.asda_phase_activity) {
    summaryHtml += '<div style="margin-top:6px;">';
    for (var p in report.asda_phase_activity) {
      summaryHtml += '<div class="summary-row"><span><span class="phase-marker phase-' + p + '"></span>' + p + '</span><span>' + report.asda_phase_activity[p] + '</span></div>';
    }
    summaryHtml += '</div>';
  }
  document.getElementById('report-summary').innerHTML = summaryHtml;

  drawTimeline();
  drawMetrics();
  updateState(0);
  renderEvents(0);
}

function drawTimeline() {
  var canvas = document.getElementById('timeline-canvas');
  var dpr = window.devicePixelRatio || 1;
  var w = canvas.offsetWidth * dpr;
  var h = canvas.offsetHeight * dpr;
  canvas.width = w; canvas.height = h;
  var ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  var cw = canvas.offsetWidth;
  var ch = canvas.offsetHeight;
  ctx.clearRect(0, 0, cw, ch);

  // Background
  ctx.fillStyle = '#080c14';
  ctx.fillRect(0, 0, cw, ch);

  if (snapshots.length === 0) return;

  // Grid lines
  ctx.strokeStyle = '#1b263b';
  ctx.lineWidth = 1;
  for (var i = 0; i <= 10; i++) {
    var x = (cw / 10) * i;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, ch);
    ctx.stroke();
  }

  // ASDA phase bands
  var maxTime = snapshots[snapshots.length - 1].sim_seconds || 1;
  for (var si = 0; si < snapshots.length; si++) {
    var snap = snapshots[si];
    var phase = snap.asda_phase;
    var x = (snap.sim_seconds / maxTime) * cw;
    var color = {'Act': 'rgba(78,154,245,0.08)', 'Sense': 'rgba(78,245,158,0.08)',
                 'Decide': 'rgba(245,228,78,0.08)', 'Adapt': 'rgba(158,78,245,0.08)'}[phase];
    if (color) {
      ctx.fillStyle = color;
      var width = cw / snapshots.length;
      ctx.fillRect(x - width/2, 0, width + 1, ch);
    }
  }

  // P12-4: 政治准入构成带（每快照 Full/Restricted/Denied 堆叠）+ 升级度曲线
  var pol = politicalSeries();
  var hasPol = pol.some(function (p) { return p !== null; });
  var bandTop = ch * 0.72, bandH = ch * 0.2;
  if (hasPol) {
    var bw = Math.max(cw / snapshots.length, 1);
    for (var pi = 0; pi < snapshots.length; pi++) {
      var p = pol[pi];
      if (!p) continue;
      var total = p.full + p.restricted + p.denied;
      if (total === 0) continue;
      var bx = (pi / Math.max(snapshots.length - 1, 1)) * cw - bw / 2;
      var y0 = bandTop;
      var segs = [
        { n: p.full, c: 'rgba(78,245,158,0.55)' },
        { n: p.restricted, c: 'rgba(245,196,78,0.55)' },
        { n: p.denied, c: 'rgba(245,78,78,0.55)' }
      ];
      for (var si2 = 0; si2 < segs.length; si2++) {
        var hh = (segs[si2].n / total) * bandH;
        if (hh <= 0) continue;
        ctx.fillStyle = segs[si2].c;
        ctx.fillRect(bx, y0, bw + 1, hh);
        y0 += hh;
      }
    }
    // 升级度曲线叠加在准入带上
    ctx.strokeStyle = '#f59e4e';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    var started = false;
    for (var pi2 = 0; pi2 < pol.length; pi2++) {
      if (!pol[pi2]) continue;
      var px = (pi2 / Math.max(pol.length - 1, 1)) * cw;
      var py = bandTop + bandH - (pol[pi2].esc * bandH);
      if (!started) { ctx.moveTo(px, py); started = true; }
      else ctx.lineTo(px, py);
    }
    ctx.stroke();
    ctx.fillStyle = '#6a7a8a';
    ctx.font = '9px Courier New';
    ctx.fillText('ALLY ACCESS MIX (FULL/REST/DENIED) + ESCALATION', 4, bandTop - 2);
  }

  // P12-4: 泳道式事件标记（威胁/拦截/战果/政治）
  var laneTop = ch * 0.08, laneH = (hasPol ? ch * 0.56 : ch * 0.8) / LANES.length;
  for (var li = 0; li < LANES.length; li++) {
    var lane = LANES[li];
    var ly = laneTop + li * laneH;
    // 泳道分隔线与标签
    ctx.strokeStyle = '#1b263b';
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    ctx.moveTo(0, ly);
    ctx.lineTo(cw, ly);
    ctx.stroke();
    ctx.fillStyle = '#4a5a6a';
    ctx.font = '9px Courier New';
    ctx.fillText(lane.label, 4, ly + 10);
  }
  for (var ei = 0; ei < events.length; ei++) {
    var ev = events[ei];
    var evX = eventLaneX(ev, cw);
    // 定位所属泳道
    var laneIdx = -1;
    for (var lj = 0; lj < LANES.length; lj++) {
      if (LANES[lj].types.indexOf(ev.event_type) !== -1) { laneIdx = lj; break; }
    }
    if (laneIdx === -1) laneIdx = 2; // 未分类事件归入战果/机动泳道
    var laneY = laneTop + laneIdx * laneH;
    // 确定性散布（避免 Math.random 每次重绘跳动）
    var jitter = ((ei * 37) % 100) / 100 * laneH * 0.6;
    var y = laneY + laneH * 0.2 + jitter;
    var color = evtColors[ev.event_type] || '#6a7a8a';
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(evX, y, 2, 0, Math.PI * 2);
    ctx.fill();
  }

  // Current position indicator
  if (currentIdx < snapshots.length) {
    var curX = (currentIdx / Math.max(snapshots.length - 1, 1)) * cw;
    ctx.strokeStyle = '#f59e4e';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(curX, 0);
    ctx.lineTo(curX, ch);
    ctx.stroke();
    // Playhead triangle
    ctx.fillStyle = '#f59e4e';
    ctx.beginPath();
    ctx.moveTo(curX - 6, 0);
    ctx.lineTo(curX + 6, 0);
    ctx.lineTo(curX, 8);
    ctx.closePath();
    ctx.fill();
  }

  // Time axis labels
  ctx.fillStyle = '#4a5a6a';
  ctx.font = '10px Courier New';
  for (var ti = 0; ti <= 5; ti++) {
    var labelTime = (maxTime / 5) * ti;
    var lx = (cw / 5) * ti;
    ctx.fillText(fmtTime(labelTime), lx + 2, ch - 2);
  }
}

function drawMetrics() {
  drawChart('chart-entities', metrics['active_entities'] || [], '#4e9af5');
  drawChart('chart-tracks', metrics['active_tracks'] || [], '#4ef59e');
  drawChart('chart-vuln', metrics['network_vuln'] || [], '#f54e4e');
  drawPoliticalChart();
}

// P12-4: 政治升级度曲线 + 盟友准入堆叠柱
function drawPoliticalChart() {
  var canvas = document.getElementById('chart-political');
  if (!canvas) return;
  var dpr = window.devicePixelRatio || 1;
  var w = canvas.offsetWidth * dpr;
  var h = canvas.offsetHeight * dpr;
  canvas.width = w; canvas.height = h;
  var ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  var cw = canvas.offsetWidth;
  var ch = canvas.offsetHeight;
  ctx.clearRect(0, 0, cw, ch);

  var pol = politicalSeries().filter(function (p) { return p !== null; });
  if (pol.length === 0) {
    ctx.fillStyle = '#4a5a6a';
    ctx.font = '11px Courier New';
    ctx.fillText('no political_access data in snapshots (P9- 基地集或空模型)', 8, ch / 2);
    return;
  }

  // 准入堆叠柱
  var bw = Math.max(cw / pol.length, 1);
  for (var i = 0; i < pol.length; i++) {
    var p = pol[i];
    var total = p.full + p.restricted + p.denied;
    if (total === 0) continue;
    var bx = (i / Math.max(pol.length - 1, 1)) * cw - bw / 2;
    var y0 = ch;
    var segs = [
      { n: p.denied, c: 'rgba(245,78,78,0.7)' },
      { n: p.restricted, c: 'rgba(245,196,78,0.7)' },
      { n: p.full, c: 'rgba(78,245,158,0.7)' }
    ];
    for (var s = 0; s < segs.length; s++) {
      var hh = (segs[s].n / total) * ch * 0.8;
      if (hh <= 0) continue;
      ctx.fillStyle = segs[s].c;
      ctx.fillRect(bx, y0 - hh, bw + 1, hh);
      y0 -= hh;
    }
  }

  // 升级度曲线（0-1 缩放）
  var maxEsc = 0;
  for (var j = 0; j < pol.length; j++) maxEsc = Math.max(maxEsc, pol[j].esc);
  if (maxEsc === 0) maxEsc = 1;
  ctx.strokeStyle = '#f59e4e';
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (var k = 0; k < pol.length; k++) {
    var px = (k / Math.max(pol.length - 1, 1)) * cw;
    var py = ch - (pol[k].esc / maxEsc) * ch * 0.8 - 4;
    if (k === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
  }
  ctx.stroke();

  // 当前位置线
  if (currentIdx < pol.length) {
    var cx = (currentIdx / Math.max(pol.length - 1, 1)) * cw;
    ctx.strokeStyle = '#f59e4e';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx, 0);
    ctx.lineTo(cx, ch);
    ctx.stroke();
  }

  // 图例
  ctx.font = '9px Courier New';
  ctx.fillStyle = '#3fb95f'; ctx.fillText('FULL', cw - 150, 10);
  ctx.fillStyle = '#f5c44e'; ctx.fillText('RESTRICTED', cw - 118, 10);
  ctx.fillStyle = '#f54e4e'; ctx.fillText('DENIED', cw - 48, 10);
  ctx.fillStyle = '#f59e4e'; ctx.fillText('— ESCALATION', cw - 150, 22);
}

function drawChart(canvasId, data, color) {
  var canvas = document.getElementById(canvasId);
  if (!canvas || data.length === 0) return;
  var dpr = window.devicePixelRatio || 1;
  var w = canvas.offsetWidth * dpr;
  var h = canvas.offsetHeight * dpr;
  canvas.width = w; canvas.height = h;
  var ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  var cw = canvas.offsetWidth;
  var ch = canvas.offsetHeight;
  ctx.clearRect(0, 0, cw, ch);

  // Find max value
  var maxV = 0;
  for (var i = 0; i < data.length; i++) {
    var v = data[i].value !== undefined ? data[i].value : data[i];
    if (v > maxV) maxV = v;
  }
  if (maxV === 0) maxV = 1;

  // Grid
  ctx.strokeStyle = '#1b263b';
  ctx.lineWidth = 0.5;
  for (var g = 0; g <= 4; g++) {
    var gy = (ch / 4) * g;
    ctx.beginPath();
    ctx.moveTo(0, gy);
    ctx.lineTo(cw, gy);
    ctx.stroke();
  }

  // Data line
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.beginPath();
  for (var j = 0; j < data.length; j++) {
    var val = data[j].value !== undefined ? data[j].value : data[j];
    var px = (j / Math.max(data.length - 1, 1)) * cw;
    var py = ch - (val / maxV) * ch * 0.85 - 5;
    if (j === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.stroke();

  // Fill area
  ctx.lineTo(cw, ch);
  ctx.lineTo(0, ch);
  ctx.closePath();
  ctx.fillStyle = color.replace(')', ',0.1)').replace('rgb', 'rgba');
  ctx.fill();

  // Current position line
  if (currentIdx < data.length) {
    var cx = (currentIdx / Math.max(data.length - 1, 1)) * cw;
    ctx.strokeStyle = '#f59e4e';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx, 0);
    ctx.lineTo(cx, ch);
    ctx.stroke();
  }
}

function updateState(idx) {
  currentIdx = idx;
  if (idx >= snapshots.length) idx = snapshots.length - 1;
  if (idx < 0) idx = 0;
  var snap = snapshots[idx];
  if (!snap) return;

  document.getElementById('time-display').textContent = fmtTime(snap.sim_seconds || 0);
  document.getElementById('st-simtime').textContent = fmtTime(snap.sim_seconds || 0);
  document.getElementById('st-cycle').textContent = snap.asda_cycle || 0;
  document.getElementById('st-phase').innerHTML = '<span class="phase-marker phase-' + (snap.asda_phase||'') + '"></span>' + (snap.asda_phase || '--');
  document.getElementById('st-entities').textContent = snap.total_entities || 0;
  document.getElementById('st-tracks').textContent = snap.active_tracks || 0;
  var vuln = snap.network_vulnerability || 0;
  document.getElementById('st-vuln').textContent = (vuln * 100).toFixed(1) + '%';

  // P12-4: 政治准入态势（P10）
  var pa = snap.political_access;
  if (pa) {
    document.getElementById('st-esc').textContent = ((pa.escalation_level || 0) * 100).toFixed(1) + '%';
    var counts = { full: 0, restricted: 0, denied: 0 };
    for (var c in (pa.by_country || {})) {
      var sites = pa.by_country[c];
      for (var j = 0; j < sites.length; j++) {
        var st = sites[j].state;
        if (counts[st] !== undefined) counts[st]++;
      }
    }
    document.getElementById('st-access').textContent =
      counts.full + ' / ' + counts.restricted + ' / ' + counts.denied;
  } else {
    document.getElementById('st-esc').textContent = 'n/a';
    document.getElementById('st-access').textContent = 'n/a';
  }

  document.getElementById('scrubber').value = idx;

  drawTimeline();
  drawMetrics();
  renderEvents(idx);
}

function renderEvents(idx) {
  var eventList = document.getElementById('event-list');
  eventList.innerHTML = '';
  // Show events around the current time window
  var windowSize = 20;
  var startIdx = Math.max(0, idx * 10 - windowSize);
  var endIdx = Math.min(events.length, startIdx + windowSize * 2);

  for (var i = startIdx; i < endIdx; i++) {
    var ev = events[i];
    if (!ev) continue;
    var div = document.createElement('div');
    div.className = 'event-list-item evt-' + (ev.event_type || 'unknown');
    var phase = ev.data ? ev.data.asda_phase : '';
    var phaseHtml = phase ? ' <span class="phase-marker phase-' + phase + '"></span>' : '';
    div.innerHTML = phaseHtml + '<b style="color:' + (evtColors[ev.event_type]||'#6a7a8a') + ';">' +
      (ev.event_type || 'unknown') + '</b> ' + (ev.description || '');
    div.onclick = (function(e) { return function() { showEventDetail(e); }; })(ev);
    eventList.appendChild(div);
  }
}

function showEventDetail(ev) {
  var detail = document.getElementById('event-detail');
  detail.style.display = 'block';
  var html = '<h4>Event Detail</h4>';
  html += '<div><b>ID:</b> ' + (ev.event_id || '--') + '</div>';
  html += '<div><b>Type:</b> ' + (ev.event_type || '--') + '</div>';
  html += '<div><b>Source:</b> ' + (ev.source || '--') + '</div>';
  html += '<div><b>Description:</b> ' + (ev.description || '--') + '</div>';
  if (ev.data) {
    html += '<div style="margin-top:6px;"><b>Data:</b></div>';
    html += '<pre style="font-size:10px;color:#8a9aaa;background:#0a0e1a;padding:6px;border-radius:4px;overflow-x:auto;">' +
      JSON.stringify(ev.data, null, 2) + '</pre>';
  }
  detail.innerHTML = html;
}

function togglePlay() {
  playing = !playing;
  var btn = document.getElementById('btn-play');
  if (playing) {
    btn.textContent = 'Pause';
    btn.classList.add('active');
    startPlayback();
  } else {
    btn.textContent = 'Play';
    btn.classList.remove('active');
    clearInterval(playInterval);
  }
}

function startPlayback() {
  clearInterval(playInterval);
  var intervalMs = 500 / speed;
  playInterval = setInterval(function() {
    if (currentIdx >= snapshots.length - 1) {
      togglePlay();
      return;
    }
    updateState(currentIdx + 1);
  }, intervalMs);
}

function changeSpeed() {
  speed = parseFloat(document.getElementById('speed-select').value);
  if (playing) startPlayback();
}

function stepForward() {
  if (currentIdx < snapshots.length - 1) updateState(currentIdx + 1);
}

function stepBack() {
  if (currentIdx > 0) updateState(currentIdx - 1);
}

function onScrub() {
  var idx = parseInt(document.getElementById('scrubber').value);
  updateState(idx);
}

function resetView() {
  updateState(0);
  if (playing) togglePlay();
}

// Timeline canvas click handler
document.getElementById('timeline-canvas').addEventListener('click', function(e) {
  var rect = this.getBoundingClientRect();
  var x = e.clientX - rect.left;
  var ratio = x / rect.width;
  var idx = Math.round(ratio * (snapshots.length - 1));
  updateState(Math.max(0, Math.min(snapshots.length - 1, idx)));
});

// Resize handler
window.addEventListener('resize', function() {
  drawTimeline();
  drawMetrics();
});

init();
</script>
</body>
</html>"""
