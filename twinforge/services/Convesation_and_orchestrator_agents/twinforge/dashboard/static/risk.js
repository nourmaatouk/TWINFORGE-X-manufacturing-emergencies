/**
 * TWINFORGE-X — Risk Intelligence Engine Frontend  v2.0
 * ======================================================
 * Fixes implemented for ARSII Challenge compliance:
 *   GAP-1: ML Anomaly badge + AI method displayed per machine
 *   GAP-2: System Architecture panel (scalability / deployment)
 *   GAP-3: Live SMIA Agent Communication Log
 *   GAP-4: Full scenario demo flow for video recording
 *
 * Connects to /ws/risk (2-second stream) and drives:
 *  - Animated Global Risk Score gauge + sparkline
 *  - Machine risk cards with ML anomaly scores
 *  - Predictive forecast bars
 *  - Emergency recommendation feed
 *  - Emergency Mode full-screen overlay
 *  - SMIA Agent Communication Log (live inter-agent messages)
 *  - AI Intelligence Panel (Isolation Forest status)
 *  - System Architecture Panel (scalability narrative)
 *  - Demo scenario controls
 */

(function () {
  'use strict';

  /* ── Constants ─────────────────────────────────────────────────────────── */
  const LEVEL_COLOR = {
    SAFE: '#00ff9d',
    LOW: '#00d4ff',
    MEDIUM: '#f5c518',
    HIGH: '#ff8c42',
    CRITICAL: '#ff2d55',
  };
  const LEVEL_BG = {
    SAFE: 'rgba(0,255,157,.08)',
    LOW: 'rgba(0,212,255,.08)',
    MEDIUM: 'rgba(245,197,24,.10)',
    HIGH: 'rgba(255,140,66,.12)',
    CRITICAL: 'rgba(255,45,85,.14)',
  };
  const AGENT_COLORS = {
    'Agent-3·IoT': '#00d4ff',
    'Agent-4·Verifier': '#a259ff',
    'Agent-5·Security': '#ff8c42',
    'Agent-6·Risk': '#ff2d55',
    'Orchestrator·Ag2': '#f5c518',
    'Dashboard': '#00ff9d',
  };

  /* ── State ─────────────────────────────────────────────────────────────── */
  let ws = null;
  let wsRetry = 0;
  let lastSnap = null;
  let emergencyActive = false;
  let scoreHistory = [];
  let msgCount = 0;

  /* ── DOM helper ─────────────────────────────────────────────────────────── */
  const $ = id => document.getElementById(id);

  /* ── Bootstrap ──────────────────────────────────────────────────────────── */
  function init() {
    if (ws && ws.readyState <= 1) return;
    buildUI();
    connect();
  }

  function destroy() {
    if (ws) { ws.close(); ws = null; }
  }

  /* ── WebSocket ──────────────────────────────────────────────────────────── */
  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws/risk`);
    ws.onopen = () => { wsRetry = 0; setWsStatus(true); };
    ws.onmessage = e => { try { render(JSON.parse(e.data)); } catch (_) { } };
    ws.onclose = () => { setWsStatus(false); wsRetry++; setTimeout(connect, Math.min(5000, 800 * wsRetry)); };
    ws.onerror = () => ws.close();
  }

  function setWsStatus(ok) {
    const el = $('risk-ws-status');
    if (!el) return;
    el.textContent = ok ? '● LIVE' : '● CONNECTING…';
    el.style.color = ok ? 'var(--c2)' : '#888';
  }

  /* ── Master render ──────────────────────────────────────────────────────── */
  function render(snap) {
    lastSnap = snap;
    scoreHistory.push(snap.global_score);
    if (scoreHistory.length > 24) scoreHistory.shift();

    renderGlobalGauge(snap);
    renderMachineGrid(snap);
    renderForecast(snap);
    renderRecommendation(snap);
    renderEmergency(snap);
    renderSparkline(snap);
    renderScenarioBadge(snap);
    renderAgentLog(snap);
    renderAIPanel(snap);
  }

  /* ── Global Gauge ──────────────────────────────────────────────────────── */
  function renderGlobalGauge(snap) {
    const score = snap.global_score;
    const level = snap.global_level;
    const color = LEVEL_COLOR[level] || '#fff';
    const circ = 251.2;
    const arc = $('risk-gauge-arc');
    if (arc) { arc.style.stroke = color; arc.style.strokeDashoffset = circ - (score / 100) * circ; }
    const num = $('risk-gauge-num');
    if (num) { num.textContent = Math.round(score); num.style.fill = color; }
    const badge = $('risk-level-badge');
    if (badge) { badge.textContent = level; badge.style.background = LEVEL_BG[level]; badge.style.color = color; badge.style.borderColor = color + '55'; }
    const ring = $('risk-gauge-ring');
    if (ring) { ring.style.borderColor = color + '44'; ring.classList.toggle('risk-pulse', level === 'CRITICAL'); }
    const header = $('risk-global-header');
    if (header) { header.style.borderColor = color + '88'; header.style.boxShadow = `0 0 24px ${color}22`; }
  }

  /* ── Machine Cards ─────────────────────────────────────────────────────── */
  function renderMachineGrid(snap) {
    const grid = $('risk-machine-grid');
    if (!grid) return;
    snap.machines.forEach(m => {
      let card = $('risk-card-' + m.machine_id);
      if (!card) { card = document.createElement('div'); card.className = 'risk-card'; card.id = 'risk-card-' + m.machine_id; grid.appendChild(card); }
      const col = LEVEL_COLOR[m.risk_level] || '#fff';
      const bg = LEVEL_BG[m.risk_level] || 'transparent';
      card.style.borderColor = col + '60';
      card.style.background = bg;
      const alertsHtml = m.alerts.length ? m.alerts.map(a => `<div class="risk-alert-item">${a}</div>`).join('') : '';
      const workerIcon = m.workers_present
        ? '<span class="worker-badge worker-present">👷 PRESENT</span>'
        : '<span class="worker-badge">👷 CLEAR</span>';
      // ML badge
      const mlColor = m.ml_anomaly_score > 60 ? '#ff2d55' : m.ml_anomaly_score > 30 ? '#ff8c42' : '#00ff9d';
      const mlBadge = `<span class="ml-badge" style="color:${mlColor};border-color:${mlColor}44">🤖 IF: ${m.ml_anomaly_score.toFixed(0)}%</span>`;

      card.innerHTML = `
        <div class="risk-card-hdr">
          <span class="risk-card-id">${m.machine_id}</span>
          <span class="risk-card-type">${m.machine_type}</span>
          <span class="risk-card-score" style="color:${col}">${m.risk_score.toFixed(0)}</span>
          <span class="risk-card-level" style="color:${col};border-color:${col}44">${m.risk_level}</span>
        </div>
        <div class="risk-card-ai-row">${mlBadge}<span class="ai-method-label">↳ ${m.ai_method}</span></div>
        <div class="risk-sensors">
          ${sensorBar('🌡️ Temp', m.temp, 0, 120, '°C', col)}
          ${sensorBar('📳 Vib', m.vibration, 0, 10, 'g', col)}
          ${sensorBar('⚡ Energy', m.energy, 0, 100, 'kW', col)}
          ${miniRiskBar('🔥 Fire', m.fire_risk, col)}
          ${miniRiskBar('⚙️ Fail', m.failure_risk, col)}
          ${miniRiskBar('🚷 Intrusion', m.intrusion_risk, col)}
          ${miniRiskBar('🤖 ML Anomaly', m.ml_anomaly_score, mlColor)}
        </div>
        <div class="risk-worker-row">Zone <strong>${m.zone}</strong> · Floor <strong>${m.floor}</strong> ${workerIcon}</div>
        ${alertsHtml ? `<div class="risk-alerts">${alertsHtml}</div>` : ''}
      `;
    });
  }

  function sensorBar(label, val, min, max, unit, color) {
    const pct = Math.min(100, Math.max(0, ((val - min) / (max - min)) * 100));
    return `<div class="sens-row"><span class="sens-label">${label}</span>
      <div class="sens-track"><div class="sens-fill" style="width:${pct}%;background:${color}"></div></div>
      <span class="sens-val">${val}${unit}</span></div>`;
  }

  function miniRiskBar(label, val, color) {
    return `<div class="sens-row"><span class="sens-label">${label}</span>
      <div class="sens-track"><div class="sens-fill" style="width:${Math.min(100, val)}%;background:${color}aa"></div></div>
      <span class="sens-val">${val.toFixed(0)}%</span></div>`;
  }

  /* ── Forecast ──────────────────────────────────────────────────────────── */
  function renderForecast(snap) {
    const wrap = $('risk-forecast-bars');
    if (!wrap) return;
    wrap.innerHTML = snap.predictions.map(p => {
      const col = p.score >= 85 ? LEVEL_COLOR.CRITICAL : p.score >= 65 ? LEVEL_COLOR.HIGH : p.score >= 40 ? LEVEL_COLOR.MEDIUM : p.score >= 20 ? LEVEL_COLOR.LOW : LEVEL_COLOR.SAFE;
      return `<div class="forecast-col">
        <div class="forecast-bar-wrap"><div class="forecast-bar" style="height:${p.score}%;background:${col}"></div></div>
        <div class="forecast-score" style="color:${col}">${p.score}</div>
        <div class="forecast-label">${p.label}</div>
        <div class="forecast-prob">${p.probability}%</div>
      </div>`;
    }).join('');
  }

  /* ── Recommendation ─────────────────────────────────────────────────────── */
  function renderRecommendation(snap) {
    const el = $('risk-recommendation');
    if (!el) return;
    const col = LEVEL_COLOR[snap.global_level] || '#fff';
    el.style.borderColor = col + '66';
    el.style.background = LEVEL_BG[snap.global_level];
    const icon = snap.global_level === 'CRITICAL' ? '🚨' : snap.global_level === 'HIGH' ? '⚠️' : snap.global_level === 'MEDIUM' ? '🔶' : snap.global_level === 'LOW' ? '🟡' : '✅';
    el.innerHTML = `<div class="rec-icon" style="color:${col}">${icon}</div><div class="rec-text">${snap.recommendation}</div>`;
  }

  /* ── Emergency Overlay ──────────────────────────────────────────────────── */
  function renderEmergency(snap) {
    const overlay = $('emergency-overlay');
    if (!overlay) return;
    if (snap.emergency_mode && !emergencyActive) {
      emergencyActive = true;
      overlay.classList.add('active');
    } else if (!snap.emergency_mode && emergencyActive) {
      emergencyActive = false;
      overlay.classList.remove('active');
    }
    if (emergencyActive) {
      const sc = $('emergency-score'); if (sc) sc.textContent = snap.global_score.toFixed(0);
      const re = $('emergency-rec'); if (re) re.textContent = snap.recommendation;
    }
  }

  /* ── Sparkline ──────────────────────────────────────────────────────────── */
  function renderSparkline(snap) {
    const svg = $('risk-sparkline');
    if (!svg || scoreHistory.length < 2) return;
    const W = 280, H = 48, pad = 4;
    const n = scoreHistory.length;
    const xStep = (W - 2 * pad) / (n - 1);
    const toY = v => H - pad - ((v / 100) * (H - 2 * pad));
    const col = LEVEL_COLOR[snap.global_level] || '#fff';
    svg.innerHTML = `
      <polyline points="${scoreHistory.map((v, i) => `${(pad + i * xStep).toFixed(1)},${toY(v).toFixed(1)}`).join(' ')}"
        fill="none" stroke="${col}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="${(pad + (n - 1) * xStep).toFixed(1)}" cy="${toY(scoreHistory[n - 1]).toFixed(1)}" r="3" fill="${col}"/>
    `;
  }

  /* ── Scenario badge ─────────────────────────────────────────────────────── */
  function renderScenarioBadge(snap) {
    const el = $('risk-scenario-active');
    if (!el) return;
    if (snap.scenario) { el.textContent = '🎬 SCENARIO: ' + snap.scenario.toUpperCase(); el.style.display = 'inline-block'; }
    else { el.style.display = 'none'; }
  }

  /* ── GAP-3: Live SMIA Agent Communication Log ───────────────────────────── */
  function renderAgentLog(snap) {
    const log = $('agent-comm-log');
    if (!log || !snap.agent_messages?.length) return;
    // Only update if new messages
    const newCount = snap.agent_messages.length;
    if (newCount === msgCount && log.children.length > 0) return;
    msgCount = newCount;

    const rows = snap.agent_messages.slice(0, 10).map(msg => {
      const fc = AGENT_COLORS[msg.from] || '#aaa';
      const tc = AGENT_COLORS[msg.to] || '#aaa';
      return `<div class="agent-msg">
        <span class="agent-ts">${msg.ts}</span>
        <span class="agent-from" style="color:${fc}">${msg.from}</span>
        <span class="agent-arrow">→</span>
        <span class="agent-to" style="color:${tc}">${msg.to}</span>
        <span class="agent-type">[${msg.type}]</span>
        <span class="agent-content">${msg.content}</span>
      </div>`;
    }).join('');
    log.innerHTML = rows;
  }

  /* ── GAP-1: AI Intelligence Panel ──────────────────────────────────────── */
  function renderAIPanel(snap) {
    const panel = $('ai-info-panel');
    if (!panel || !snap.ai_info) return;
    const ai = snap.ai_info;
    const ready = ai.models_ready || 0;
    const total = ai.total_models || 6;
    const pct = Math.round((ready / total) * 100);
    const col = pct >= 100 ? '#00ff9d' : pct >= 50 ? '#f5c518' : '#00d4ff';
    panel.innerHTML = `
      <div class="ai-row"><span class="ai-lbl">🤖 Primary Model</span><span class="ai-val" style="color:${col}">${ai.method}</span></div>
      <div class="ai-row"><span class="ai-lbl">🔁 Models Active</span>
        <span class="ai-val">${ready}/${total}
          <div class="ai-prog-track"><div class="ai-prog-fill" style="width:${pct}%;background:${col}"></div></div>
        </span>
      </div>
      <div class="ai-row"><span class="ai-lbl">📊 Features</span><span class="ai-val ai-mono">${(ai.features || []).join(' · ')}</span></div>
      <div class="ai-row"><span class="ai-lbl">⚗️  Fusion Strategy</span><span class="ai-val ai-mono ai-small">${ai.fusion}</span></div>
      <div class="ai-row"><span class="ai-lbl">🎯 Contamination</span><span class="ai-val">${((ai.contamination || 0) * 100).toFixed(0)}% anomaly threshold</span></div>
      <div class="ai-row"><span class="ai-lbl">📐 Window Size</span><span class="ai-val">${ai.window_size} readings / model</span></div>
    `;
  }

  /* ── Build full UI skeleton ─────────────────────────────────────────────── */
  function buildUI() {
    const section = $('view-risk');
    if (!section || section.dataset.built) return;
    section.dataset.built = '1';

    section.innerHTML = `

      <!-- EMERGENCY OVERLAY -->
      <div id="emergency-overlay" class="emergency-overlay">
        <div class="emergency-box">
          <div class="em-pulse-ring"></div>
          <div class="em-icon">🚨</div>
          <div class="em-title">EMERGENCY MODE ACTIVATED</div>
          <div class="em-score-row">Global Risk Score: <span id="emergency-score" class="em-score">--</span> / 100</div>
          <div id="emergency-rec" class="em-rec">--</div>
          <div class="em-actions">
            <button class="em-btn em-btn-red" onclick="riskUI.scenario('clear'); document.getElementById('emergency-overlay').classList.remove('active'); riskUI._emergencyActive=false">✋ CLEAR SCENARIO</button>
            <button class="em-btn em-btn-outline" onclick="document.getElementById('emergency-overlay').classList.remove('active'); riskUI._emergencyActive=false">Dismiss</button>
          </div>
        </div>
      </div>

      <!-- ─── TOP HEADER ROW ─────────────────────────────────────────────── -->
      <div id="risk-global-header" class="risk-global-header">

        <div class="risk-brand">
          <span class="risk-shield">🛡</span>
          <div>
            <div class="risk-brand-name">TWINFORGE-X</div>
            <div class="risk-brand-sub">AI-Powered Industrial Risk Prevention &amp; Emergency Intelligence</div>
            <div class="risk-brand-sub" style="color:#a259ff;margin-top:.15rem">ARSII Carthage · Real-Time · Multi-Agent SMIA</div>
          </div>
        </div>

        <div class="risk-header-center">
          <div class="risk-gauge-wrap">
            <div id="risk-gauge-ring" class="risk-gauge-ring">
              <svg viewBox="0 0 100 100" class="risk-gauge-svg" id="risk-gauge-svg">
                <circle cx="50" cy="50" r="40" fill="none" stroke="rgba(255,255,255,.07)" stroke-width="10"/>
                <circle id="risk-gauge-arc" cx="50" cy="50" r="40" fill="none" stroke="#00ff9d"
                  stroke-width="10" stroke-linecap="round"
                  stroke-dasharray="251.2" stroke-dashoffset="251.2"
                  transform="rotate(-90 50 50)"
                  style="transition:stroke-dashoffset 1s ease,stroke .5s"/>
                <text id="risk-gauge-num" x="50" y="56" text-anchor="middle"
                  font-size="22" font-weight="800" font-family="monospace" fill="#00ff9d">0</text>
              </svg>
            </div>
            <div class="risk-gauge-below">
              <span id="risk-level-badge" class="risk-level-badge">SAFE</span>
              <div class="risk-gauge-label">GLOBAL RISK SCORE</div>
              <svg id="risk-sparkline" width="280" height="48" style="display:block;margin:0 auto;margin-top:.4rem"></svg>
            </div>
          </div>
        </div>

        <div class="risk-header-right">
          <span id="risk-ws-status" class="risk-ws-status">● CONNECTING…</span>
          <span id="risk-scenario-active" class="risk-scenario-badge" style="display:none"></span>
          <div class="risk-scenario-panel">
            <div class="rsp-title">🎬 DEMO SCENARIOS</div>
            <button class="rsp-btn rsp-fire"      onclick="riskUI.scenario('overheat','CNC-001')">🔥 Overheat CNC-001</button>
            <button class="rsp-btn rsp-intrusion" onclick="riskUI.scenario('intrusion','ROB-002')">🚷 Zone Intrusion ROB-002</button>
            <button class="rsp-btn rsp-cascade"   onclick="riskUI.scenario('cascade','PRS-004')">⚡ Cascade Failure PRS-004</button>
            <button class="rsp-btn rsp-clear"     onclick="riskUI.scenario('clear')">✅ Clear / Reset</button>
          </div>
        </div>
      </div>

      <!-- ─── RECOMMENDATION FEED ────────────────────────────────────────── -->
      <div id="risk-recommendation" class="risk-recommendation">
        <div class="rec-icon">⏳</div>
        <div class="rec-text">Connecting to Risk Intelligence Engine (Agent 6)…</div>
      </div>

      <!-- ─── MAIN 3-COLUMN LAYOUT ──────────────────────────────────────── -->
      <div class="risk-main-row">

        <!-- LEFT: Machine Risk Map -->
        <div class="risk-left">
          <div class="risk-section-title">🏭 MACHINE RISK MAP <span class="risk-section-badge">REAL-TIME · 6 MACHINES</span></div>
          <div id="risk-machine-grid" class="risk-machine-grid"></div>
        </div>

        <!-- RIGHT: Forecast + AI + Architecture -->
        <div class="risk-right">

          <!-- Predictive Forecast -->
          <div class="risk-section-title">📈 PREDICTIVE RISK FORECAST <span class="risk-section-badge">NEXT 10 MIN</span></div>
          <div class="risk-forecast-wrap">
            <div id="risk-forecast-bars" class="risk-forecast-bars"></div>
            <div class="forecast-axis"><span>Now</span><span>Forecast window →</span></div>
          </div>

          <!-- GAP-1: AI Intelligence Panel -->
          <div class="risk-section-title" style="margin-top:.5rem">🤖 AI DETECTION ENGINE <span class="risk-section-badge">ISOLATION FOREST · SKLEARN</span></div>
          <div class="ai-panel" id="ai-info-panel">
            <div class="ai-row"><span class="ai-lbl">Status</span><span class="ai-val">Warming up models…</span></div>
          </div>

          <!-- Escalation Matrix -->
          <div class="risk-section-title" style="margin-top:.5rem">⚖️ ESCALATION MATRIX</div>
          <div class="risk-matrix">
            ${[
        ['CRITICAL', '≥85', '🚨 Auto-lockdown · Evacuate · Emergency services'],
        ['HIGH', '≥65', '⚠️ Alert supervisor · Dispatch technician'],
        ['MEDIUM', '≥40', '🔶 Monitor closely · Prepare maintenance'],
        ['LOW', '≥20', '🟡 Routine check within 30 min'],
        ['SAFE', '<20', '✅ All systems nominal · Monitoring active'],
      ].map(([lvl, range, action]) => `
              <div class="matrix-row">
                <span class="matrix-dot" style="background:${LEVEL_COLOR[lvl]}"></span>
                <span class="matrix-lvl" style="color:${LEVEL_COLOR[lvl]}">${lvl}</span>
                <span class="matrix-range">${range}</span>
                <span class="matrix-action">${action}</span>
              </div>`).join('')}
          </div>
        </div>
      </div>

      <!-- ─── BOTTOM ROW: Agent Comm Log + Architecture ─────────────────── -->
      <div class="risk-bottom-row">

        <!-- GAP-3: SMIA Agent Communication Log -->
        <div class="risk-comm-panel">
          <div class="risk-section-title">
            📡 SMIA AGENT COMMUNICATION LOG
            <span class="risk-section-badge">LIVE · INTER-AGENT</span>
            <span class="comm-live-dot"></span>
          </div>
          <div class="agent-flow-diagram">
            <div class="afd-node afd-iot">Agent 3<br><small>IoT</small></div>
            <div class="afd-arrow">→</div>
            <div class="afd-node afd-verifier">Agent 4<br><small>Verifier</small></div>
            <div class="afd-arrow">→</div>
            <div class="afd-node afd-security">Agent 5<br><small>Security</small></div>
            <div class="afd-arrow">→</div>
            <div class="afd-node afd-risk">Agent 6<br><small>Risk Fusion</small></div>
            <div class="afd-arrow">→</div>
            <div class="afd-node afd-orch">Orchestrator<br><small>Ag2</small></div>
            <div class="afd-arrow">→</div>
            <div class="afd-node afd-dash">Dashboard<br><small>UI</small></div>
          </div>
          <div id="agent-comm-log" class="agent-comm-log"></div>
        </div>

        <!-- GAP-2: System Architecture Panel -->
        <div class="risk-arch-panel">
          <div class="risk-section-title">🏗 SYSTEM ARCHITECTURE <span class="risk-section-badge">SCALABILITY · RELIABILITY</span></div>
          <div class="arch-grid">
            <div class="arch-card">
              <div class="arch-icon">⚡</div>
              <div class="arch-title">Low Latency</div>
              <div class="arch-desc">WebSocket streaming. Risk snapshots delivered in &lt;100ms. Real-time anomaly detection per sensor cycle.</div>
            </div>
            <div class="arch-card">
              <div class="arch-icon">🔄</div>
              <div class="arch-title">Scalability</div>
              <div class="arch-desc">Microservice agents. Each Agent (3-6) runs independently. Redis pub/sub ready for horizontal scaling to 100+ machines.</div>
            </div>
            <div class="arch-card">
              <div class="arch-icon">🛡</div>
              <div class="arch-title">Reliability</div>
              <div class="arch-desc">JWT-secured API. Auto-reconnect WebSocket. Graceful degradation: Z-score fallback when ML models warm up.</div>
            </div>
            <div class="arch-card">
              <div class="arch-icon">📡</div>
              <div class="arch-title">Remote Deployment</div>
              <div class="arch-desc">Docker-ready containers. Runs on-premise or edge. No cloud dependency. SMIA AAS protocol compatible.</div>
            </div>
            <div class="arch-card">
              <div class="arch-icon">🤖</div>
              <div class="arch-title">AI Engine</div>
              <div class="arch-desc">Isolation Forest on 3-feature sliding windows. Z-score for early detection. Weighted multi-vector fusion (Classical 60% + IF 25% + Z 15%).</div>
            </div>
            <div class="arch-card">
              <div class="arch-icon">🔗</div>
              <div class="arch-title">Coordination</div>
              <div class="arch-desc">SMIA FIPA-ACL inter-agent messaging. Agents 3→4→5→6→Orchestrator pipeline. No isolated silos — unified safety awareness.</div>
            </div>
          </div>

          <!-- Technology stack badges -->
          <div class="tech-stack">
            <span class="tech-badge">🐍 Python FastAPI</span>
            <span class="tech-badge">🌐 WebSocket</span>
            <span class="tech-badge">🤖 scikit-learn</span>
            <span class="tech-badge">🔐 JWT Auth</span>
            <span class="tech-badge">🏭 SMIA/AAS</span>
            <span class="tech-badge">📊 NumPy</span>
            <span class="tech-badge">⚡ FIPA-ACL</span>
            <span class="tech-badge">🐳 Docker-ready</span>
          </div>
        </div>
      </div>
    `;
  }

  /* ── Public API ─────────────────────────────────────────────────────────── */
  window.riskUI = {
    init,
    destroy,
    _emergencyActive: false,
    scenario(name, machineId) {
      fetch('/api/risk/scenario', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario: name, machine_id: machineId || null }),
      });
    },
  };

})();
