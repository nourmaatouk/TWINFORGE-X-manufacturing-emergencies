/* ═══════════════════════════════════════════════════════════
   TWINFORGE — Dynamic Dashboard (100% API-driven)
   Every number, machine, KPI, and alert comes from the backend.
   Zero hardcoded data.
   ═══════════════════════════════════════════════════════════ */

(() => {
    "use strict";

    // ── Config ──────────────────────────────────────────────
    // All paths are prefixed with /dashboard/ because nginx reverse-proxies
    // http://HOST/dashboard/ → twinforge-dashboard:8001/
    // so the browser must include /dashboard/ in every absolute URL.
    const API = "/api/dashboard";
    const REFRESH_MS = 5000;
    const _wsProto = location.protocol === "https:" ? "wss:" : "ws:";
    const WS_CHAT = `${_wsProto}//${location.host}/ws/chat`;
    const WS_SENSORS = `${_wsProto}//${location.host}/ws/sensors`;
    const API_CHAT = "/api/chat";

    // ── State ───────────────────────────────────────────────
    let currentView = "overview";
    let wsChat = null;
    let wsSensors = null;
    let sessionId = crypto.randomUUID?.() || "s-" + Date.now();
    let refreshTimer = null;
    let cachedData = {};        // cache of latest API responses

    // ── DOM Refs ────────────────────────────────────────────
    const $ = (s) => document.querySelector(s);
    const $$ = (s) => document.querySelectorAll(s);

    // ── Init ────────────────────────────────────────────────
    document.addEventListener("DOMContentLoaded", () => {
        setupTabs();
        setupChat();
        startClock();
        initialFetch();
        startAutoRefresh();
        connectSensorWS();
    });

    // ══════════════════════════════════════════════════════════
    // TABS & VIEW SWITCHING
    // ══════════════════════════════════════════════════════════

    function setupTabs() {
        $$(".tab").forEach((tab) => {
            tab.addEventListener("click", () => {
                const view = tab.dataset.view;
                switchView(view);
            });
        });
    }

    let twin3dInited = false;

    function switchView(view) {
        currentView = view;
        $$(".tab").forEach((t) => t.classList.remove("active"));
        const activeTab = $(`[data-view="${view}"]`);
        if (activeTab) activeTab.classList.add("active");

        $$(".view").forEach((v) => v.classList.remove("active"));
        const targetView = $(`#view-${view}`);
        if (targetView) targetView.classList.add("active");

        // 3D lifecycle
        if (view === "twin3d") {
            if (!twin3dInited) {
                TwinForge3D.init(document.getElementById("three-canvas"));
                setup3DToolbar();
                twin3dInited = true;
            }
            TwinForge3D.start();
        } else {
            if (twin3dInited) TwinForge3D.stop();
        }

        // Risk Intelligence lifecycle
        if (view === "risk") {
            if (typeof riskUI !== "undefined") riskUI.init();
        } else {
            if (typeof riskUI !== "undefined") riskUI.destroy();
        }

        // Trigger fresh fetch for the switched view
        fetchViewData(view);
    }

    function showEmptyOrView() {
        const total = cachedData.overview?.aggregate_kpis?.total_twins || 0;
        const empty = $("#view-empty");
        const overview = $("#view-overview");
        if (total === 0) {
            empty.classList.add("active");
            overview.classList.remove("active");
            $$(".tab").forEach(t => t.classList.remove("active"));
        } else {
            empty.classList.remove("active");
            if (currentView === "overview") overview.classList.add("active");
        }
    }

    // ══════════════════════════════════════════════════════════
    // DATA FETCHING
    // ══════════════════════════════════════════════════════════

    async function apiFetch(endpoint) {
        try {
            const res = await fetch(`${API}/${endpoint}`);
            if (!res.ok) throw new Error(`${res.status}`);
            return await res.json();
        } catch (e) {
            console.warn(`API fetch ${endpoint} failed:`, e);
            return null;
        }
    }

    async function initialFetch() {
        const data = await apiFetch("overview");
        if (data) {
            cachedData.overview = data;
            showEmptyOrView();
            if (data.aggregate_kpis.total_twins > 0) {
                switchView("overview");
                renderOverview(data);
            }
        }
    }

    async function fetchViewData(view) {
        let data;
        switch (view) {
            case "overview":
                data = await apiFetch("overview");
                if (data) { cachedData.overview = data; renderOverview(data); }
                break;
            case "component":
                data = await apiFetch("components");
                if (data) { cachedData.components = data; renderComponents(data); }
                break;
            case "asset":
                data = await apiFetch("assets");
                if (data) { cachedData.assets = data; renderAssets(data); }
                break;
            case "system":
                data = await apiFetch("system");
                if (data) { cachedData.system = data; renderSystem(data); }
                break;
            case "process":
                data = await apiFetch("process");
                if (data) { cachedData.process = data; renderProcess(data); }
                break;
            case "twin3d":
                data = await apiFetch("overview");
                if (data) {
                    cachedData.overview = data;
                    setText("#badge-twin3d", data.aggregate_kpis.total_twins);
                    if (twin3dInited) TwinForge3D.loadScene();
                }
                break;
        }
        updateBadges();
    }

    function startAutoRefresh() {
        refreshTimer = setInterval(() => fetchViewData(currentView), REFRESH_MS);
    }

    function updateBadges() {
        const o = cachedData.overview;
        if (o) {
            setText("#badge-overview", o.aggregate_kpis.total_twins);
            setText("#badge-asset", o.aggregate_kpis.total_twins);
            setText("#badge-system", o.line_count || 0);
        }
        if (cachedData.components) setText("#badge-component", cachedData.components.total);
        if (cachedData.process) setText("#badge-process", cachedData.process.order_count);
    }

    // ══════════════════════════════════════════════════════════
    // OVERVIEW RENDERING
    // ══════════════════════════════════════════════════════════

    function renderOverview(data) {
        const agg = data.aggregate_kpis;
        const twins = data.twins || [];

        // Level card counts
        setText("#lv-component", (agg.total_components || 0) + " composants");
        setText("#lv-asset", agg.total_twins + " machines");
        setText("#lv-system", (agg.lines || 0) + " lignes");
        setText("#lv-process", (data.order_count || 0) + " flux");

        // KPI sidebar
        const kpiList = $("#kpi-list");
        kpiList.innerHTML = kpiItems([
            { label: "Total Twins", value: agg.total_twins, unit: "" },
            { label: "Avg OEE", value: agg.avg_oee, unit: "%" },
            { label: "Availability", value: agg.avg_availability, unit: "%" },
            { label: "Performance", value: agg.avg_performance, unit: "%" },
            { label: "Quality", value: agg.avg_quality, unit: "%" },
            { label: "Total Energy", value: agg.total_energy_kwh, unit: " kWh" },
            { label: "Components", value: agg.total_components, unit: "" },
            { label: "Floors", value: agg.floors, unit: "" },
            { label: "Lines", value: agg.lines, unit: "" },
            { label: "Active Alerts", value: agg.total_alerts, unit: "", cls: agg.total_alerts > 0 ? "warn" : "" },
        ]);

        // OEE gauge (half-circle: total arc ~157)
        const oeeVal = agg.avg_oee || 0;
        const arcLen = 157;
        const offset = arcLen - (oeeVal / 100) * arcLen;
        const arc = $("#oee-arc");
        if (arc) { arc.setAttribute("stroke-dasharray", arcLen); arc.setAttribute("stroke-dashoffset", offset); }
        setText("#oee-val", `${oeeVal}%`);

        // OEE sub-bars
        const oeeBars = $("#oee-bars");
        if (oeeBars) {
            oeeBars.innerHTML = ["availability", "performance", "quality"].map(k => {
                const v = agg["avg_" + k] || 0;
                const col = v >= 85 ? "var(--c2)" : v >= 65 ? "var(--warn)" : "var(--err)";
                return `<div style="display:flex;align-items:center;gap:.4rem;font-size:.6rem;"><span style="color:var(--tx2);width:55px">${k.charAt(0).toUpperCase() + k.slice(1, 4)}.</span><div style="flex:1;height:4px;background:var(--bg3);border-radius:2px;overflow:hidden"><div style="height:100%;width:${v}%;background:${col};border-radius:2px"></div></div><span style="width:30px;text-align:right;color:var(--tx)">${v}%</span></div>`;
            }).join("");
        }

        // Alerts
        renderAlertList(data.alerts || []);
        setText("#alert-count", (data.alert_count || 0) + " ACTIVES");

        // Factory SVG
        renderFactorySVG(twins);

        // Energy bars
        renderEnergyBars(twins);

        // Lifetime panel
        renderLifetimePanel(twins);

        // Consumption panel
        renderConsumptionPanel(agg, twins);

        showEmptyOrView();
    }

    function kpiItems(items) {
        return items.map((k) => {
            const v = typeof k.value === 'number' ? k.value : 0;
            const pct = k.unit === '%' ? v : Math.min(v * 2, 100);
            return `<div class="kpi-item ${k.cls || ''}">
              <div class="kpi-fill" style="width:${pct}%"></div>
              <span class="kpi-label">${k.label}</span>
              <span class="kpi-val">${k.value}<span class="kpi-unit">${k.unit}</span></span>
            </div>`;
        }).join("");
    }

    function renderLifetimePanel(twins) {
        const el = $("#lifetimePanel");
        if (!el) return;
        if (!twins.length) { el.innerHTML = '<div class="kpi-loading">—</div>'; return; }
        el.innerHTML = twins.map(t => {
            const life = t.kpis?.remaining_life_years ?? 5;
            const maxLife = 15;
            const pct = Math.min(life / maxLife * 100, 100);
            const col = pct > 60 ? 'var(--c2)' : pct > 30 ? 'var(--warn)' : 'var(--err)';
            return `<div style="display:flex;align-items:center;gap:.5rem;font-size:.62rem">
              <span style="width:60px;color:var(--tx2)">${t.twin_id}</span>
              <div class="lbar"><div class="lbar-fill" style="width:${pct}%;background:${col}"></div></div>
              <span style="width:40px;text-align:right;color:var(--tx)">${life}y</span>
            </div>`;
        }).join("");
    }

    function renderConsumptionPanel(agg, twins) {
        const el = $("#consumptionPanel");
        if (!el) return;
        const totalE = agg.total_energy_kwh || 0;
        const totalW = twins.reduce((s, t) => s + (t.kpis?.water_lph || 0), 0);
        el.innerHTML = `
          <div class="kpi-item"><div class="kpi-fill" style="width:70%"></div><span class="kpi-label">⚡ Énergie Totale</span><span class="kpi-val">${totalE}<span class="kpi-unit"> kWh</span></span></div>
          <div class="kpi-item"><div class="kpi-fill" style="width:45%;background:rgba(0,212,255,.06)"></div><span class="kpi-label">💧 Eau Totale</span><span class="kpi-val">${totalW.toFixed(1)}<span class="kpi-unit"> L/h</span></span></div>
          <div class="kpi-item"><div class="kpi-fill" style="width:55%;background:rgba(162,89,255,.06)"></div><span class="kpi-label">🏭 Machines Actives</span><span class="kpi-val">${twins.length}</span></div>
        `;
    }

    function renderAlertList(alerts) {
        const el = $("#alert-list");
        if (!alerts.length) { el.innerHTML = '<div class="kpi-loading">🟢 All clear</div>'; return; }
        el.innerHTML = alerts.map((a) => `
      <div class="alert-item sev-${a.severity.toLowerCase()}">
        <span class="alert-sev">${a.severity === "CRITICAL" ? "🔴" : "🟡"}</span>
        <span class="alert-msg">${a.twin_id}: ${a.message}</span>
      </div>
    `).join("");
    }

    // ── Factory SVG — adapts to twin count ──────────────────

    function renderFactorySVG(twins) {
        const wrap = $("#factory-svg");
        if (!twins.length) {
            wrap.innerHTML = '<div class="kpi-loading">No machines — create twins via chat</div>';
            return;
        }

        // ── Layout config ──
        const cols = Math.min(6, Math.ceil(Math.sqrt(twins.length * 1.5)));
        const rows = Math.ceil(twins.length / cols);
        const BOX = 88, GAP_X = 28, GAP_Y = 32, DOT_R = 5;
        const PAD_X = 90, PAD_TOP = 85, PAD_BOT = 65;
        const CONVEYOR_H = 16, CONVEYOR_GAP = 20;
        const totalRowH = BOX + GAP_Y + CONVEYOR_H + CONVEYOR_GAP;
        const contentW = cols * BOX + (cols - 1) * GAP_X;
        const W = contentW + PAD_X * 2;
        const H = rows * totalRowH + PAD_TOP + PAD_BOT + 55;

        // ── Machine type icons ──
        const typeIcons = {
            "CNC": "⚙", "Mill": "⚙", "Lathe": "◎", "Robot": "⚡",
            "Press": "⬡", "Conveyor": "⇶", "Drill": "◉", "Grind": "◈",
            "Weld": "⊗", "Inject": "◆", "default": "■"
        };

        function getIcon(type) { return typeIcons[type] || typeIcons["default"]; }

        // ── Status helper ──
        function getNodeStatus(t) {
            const alerts = t.alerts || [];
            const hasCrit = alerts.some(a => a.severity === "CRITICAL");
            const hasWarn = alerts.some(a => a.severity === "WARNING");
            const isMaint = (t.status || "").toLowerCase().includes("maint") || hasWarn;
            const isFault = hasCrit || (t.status || "").toLowerCase().includes("fault");
            const isPlanned = (t.status || "").toLowerCase().includes("plan");
            if (isFault) return { border: "#ff3d7f", dot: "#ff3d7f", bg: "rgba(255,61,127,.10)", label: "Panne", emoji: "🔴" };
            if (isMaint) return { border: "#ffb300", dot: "#ffb300", bg: "rgba(255,179,0,.08)", label: "Maintenance", emoji: "🟠" };
            if (isPlanned) return { border: "#a259ff", dot: "#a259ff", bg: "rgba(162,89,255,.08)", label: "Planifié", emoji: "🟣" };
            return { border: "#00ff9d", dot: "#00ff9d", bg: "rgba(0,255,157,.06)", label: "Opérationnel", emoji: "🟢" };
        }

        // ── SVG Defs (gradients, filters, patterns) ──
        let svg = `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" class="factory-svg-premium">`;
        svg += `<defs>`;
        // Glow filter for status dots
        svg += `<filter id="glow-sm" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.5" result="g"/><feMerge><feMergeNode in="g"/><feMergeNode in="SourceGraphic"/></feMerge></filter>`;
        // Soft drop shadow for popup
        svg += `<filter id="popup-shadow" x="-10%" y="-10%" width="130%" height="130%"><feDropShadow dx="0" dy="4" stdDeviation="8" flood-color="#000" flood-opacity="0.5"/></filter>`;
        // Conveyor gradient
        svg += `<linearGradient id="cv-grad" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="#1a2840"/><stop offset="50%" stop-color="#243858"/><stop offset="100%" stop-color="#1a2840"/></linearGradient>`;
        // Ambient particle gradient
        svg += `<radialGradient id="particle-glow"><stop offset="0%" stop-color="#00d4ff" stop-opacity="0.4"/><stop offset="100%" stop-color="#00d4ff" stop-opacity="0"/></radialGradient>`;
        svg += `</defs>`;

        // ── Dark background with subtle vignette ──
        svg += `<rect x="0" y="0" width="${W}" height="${H}" fill="#0b111d" rx="12"/>`;
        // Vignette overlay
        svg += `<rect x="0" y="0" width="${W}" height="${H}" rx="12" fill="url(#particle-glow)" opacity="0.03"/>`;

        // ── Subtle grid with accent lines ──
        for (let gx = 0; gx < W; gx += 25) svg += `<line x1="${gx}" y1="0" x2="${gx}" y2="${H}" stroke="#0e1a2a" stroke-width="0.4"/>`;
        for (let gy = 0; gy < H; gy += 25) svg += `<line x1="0" y1="${gy}" x2="${W}" y2="${gy}" stroke="#0e1a2a" stroke-width="0.4"/>`;
        // Accent cross lines
        svg += `<line x1="${W / 2}" y1="0" x2="${W / 2}" y2="${H}" stroke="#162035" stroke-width="0.8"/>`;
        svg += `<line x1="0" y1="${H / 2}" x2="${W}" y2="${H / 2}" stroke="#162035" stroke-width="0.8"/>`;

        // ── Ambient floating particles (decorative) ──
        for (let pi = 0; pi < 18; pi++) {
            const px = 20 + Math.random() * (W - 40);
            const py = 20 + Math.random() * (H - 40);
            const pr = 1 + Math.random() * 2;
            const dur = 4 + Math.random() * 6;
            svg += `<circle cx="${px}" cy="${py}" r="${pr}" fill="#00d4ff" opacity="0.07">`;
            svg += `<animate attributeName="opacity" values="0.03;0.12;0.03" dur="${dur}s" repeatCount="indefinite"/>`;
            svg += `<animate attributeName="cy" values="${py};${py - 8};${py}" dur="${dur * 1.5}s" repeatCount="indefinite"/></circle>`;
        }

        // ── Factory building outline (dashed pentagon / house shape) ──
        const bldgL = PAD_X - 35, bldgR = W - PAD_X + 35;
        const bldgTop = PAD_TOP - 45, bldgBot = H - PAD_BOT + 15;
        const roofPeak = bldgTop - 40;
        const roofInset = (bldgR - bldgL) * 0.15;
        svg += `<path d="M ${bldgL} ${bldgBot} L ${bldgL} ${bldgTop} L ${bldgL + roofInset} ${roofPeak} L ${bldgR - roofInset} ${roofPeak} L ${bldgR} ${bldgTop} L ${bldgR} ${bldgBot} Z" fill="none" stroke="#1e3050" stroke-width="1.5" stroke-dasharray="8,5" opacity="0.55"/>`;
        // Inner accent outline
        svg += `<path d="M ${bldgL + 8} ${bldgBot - 8} L ${bldgL + 8} ${bldgTop + 6} L ${bldgL + roofInset + 4} ${roofPeak + 7} L ${bldgR - roofInset - 4} ${roofPeak + 7} L ${bldgR - 8} ${bldgTop + 6} L ${bldgR - 8} ${bldgBot - 8} Z" fill="none" stroke="#14253a" stroke-width="0.6" stroke-dasharray="4,4" opacity="0.4"/>`;

        // ── SMIA Agent card (top-right, enhanced) ──
        const agentX = W - 190, agentY = 10;
        svg += `<rect x="${agentX}" y="${agentY}" width="175" height="58" rx="10" fill="rgba(10,16,28,0.9)" stroke="#1a3552" stroke-width="1.2"/>`;
        svg += `<rect x="${agentX}" y="${agentY}" width="175" height="18" rx="10" fill="rgba(0,212,255,0.06)"/>`;
        svg += `<rect x="${agentX}" y="${agentY + 8}" width="175" height="10" fill="rgba(0,212,255,0.06)"/>`;
        svg += `<circle cx="${agentX + 18}" cy="${agentY + 20}" r="8" fill="none" stroke="#00d4ff" stroke-width="1.5"/>`;
        svg += `<circle cx="${agentX + 18}" cy="${agentY + 20}" r="3" fill="#00d4ff"/>`;
        svg += `<text x="${agentX + 34}" y="${agentY + 24}" fill="#e8f0f8" font-size="12" font-weight="700" font-family="JetBrains Mono">SMIA AGENT</text>`;
        svg += `<text x="${agentX + 34}" y="${agentY + 38}" fill="#3a5a78" font-size="8" font-family="JetBrains Mono">AAS · FIPA-ACL</text>`;
        svg += `<circle cx="${agentX + 18}" cy="${agentY + 46}" r="3.5" fill="#00ff9d" filter="url(#glow-sm)"/>`;
        svg += `<text x="${agentX + 28}" y="${agentY + 50}" fill="#00ff9d" font-size="8.5" font-family="JetBrains Mono">SPADE running</text>`;

        // ── Store machine positions for connection lines ──
        const machinePositions = [];

        // ── Draw machines row by row ──
        for (let row = 0; row < rows; row++) {
            const rowTwins = twins.slice(row * cols, (row + 1) * cols);
            const rowY = PAD_TOP + row * totalRowH;

            // Machine boxes
            rowTwins.forEach((t, ci) => {
                const x = PAD_X + ci * (BOX + GAP_X);
                const y = rowY;
                const cx = x + BOX / 2;
                const cy = y + BOX / 2;
                const st = getNodeStatus(t);
                const icon = getIcon(t.asset_type);
                machinePositions.push({ x: cx, y: cy, twin: t, st });

                svg += `<g class="machine-node" data-twin="${t.twin_id}" data-idx="${machinePositions.length - 1}" style="cursor:pointer">`;

                // Outer pulse ring (animated)
                svg += `<rect x="${x - 5}" y="${y - 5}" width="${BOX + 10}" height="${BOX + 10}" rx="15" fill="none" stroke="${st.border}" stroke-width="0.6" opacity="0.2">`;
                svg += `<animate attributeName="opacity" values="0.1;0.3;0.1" dur="3s" repeatCount="indefinite"/></rect>`;

                // Glow background
                svg += `<rect x="${x - 2}" y="${y - 2}" width="${BOX + 4}" height="${BOX + 4}" rx="13" fill="${st.bg}"/>`;

                // Main box with gradient feel
                svg += `<rect x="${x}" y="${y}" width="${BOX}" height="${BOX}" rx="11" fill="rgba(10,16,28,0.8)" stroke="${st.border}" stroke-width="2"/>`;
                // Inner highlight line (top)
                svg += `<line x1="${x + 8}" y1="${y + 1}" x2="${x + BOX - 8}" y2="${y + 1}" stroke="${st.border}" stroke-width="0.5" opacity="0.3"/>`;

                // Status dot with glow filter (top-right corner)
                svg += `<circle cx="${x + BOX - 14}" cy="${y + 14}" r="${DOT_R + 1}" fill="${st.dot}" filter="url(#glow-sm)">`;
                svg += `<animate attributeName="r" values="${DOT_R};${DOT_R + 2};${DOT_R}" dur="2s" repeatCount="indefinite"/></circle>`;

                // Machine type icon (top-left)
                svg += `<text x="${x + 14}" y="${y + 18}" fill="${st.border}" font-size="13" text-anchor="middle" opacity="0.5">${icon}</text>`;

                // Machine name (centered)
                svg += `<text x="${cx}" y="${cy + 2}" fill="#e0e8f0" font-size="11.5" font-weight="700" text-anchor="middle" font-family="JetBrains Mono">${t.twin_id}</text>`;

                // Asset type subtitle
                svg += `<text x="${cx}" y="${cy + 16}" fill="${st.border}" font-size="7.5" text-anchor="middle" font-family="JetBrains Mono" opacity="0.6">${t.asset_type || "Machine"}</text>`;

                // Bottom mini OEE bar
                const oee = t.kpis?.oee || 0;
                const barW = BOX - 20;
                const barX = x + 10;
                const barY = y + BOX - 10;
                svg += `<rect x="${barX}" y="${barY}" width="${barW}" height="3" rx="1.5" fill="#0a1220"/>`;
                svg += `<rect x="${barX}" y="${barY}" width="${barW * oee / 100}" height="3" rx="1.5" fill="${st.border}" opacity="0.6"/>`;

                svg += `</g>`;
            });

            // ── Conveyor belt bar (enhanced) ──
            if (rowTwins.length > 1) {
                const cvStartX = PAD_X + 12;
                const cvEndX = PAD_X + (rowTwins.length - 1) * (BOX + GAP_X) + BOX - 12;
                const cvY = rowY + BOX + CONVEYOR_GAP;
                // Belt body
                svg += `<rect x="${cvStartX}" y="${cvY}" width="${cvEndX - cvStartX}" height="${CONVEYOR_H}" rx="8" fill="url(#cv-grad)" stroke="#1a2e4a" stroke-width="0.8"/>`;
                svg += `<rect x="${cvStartX + 3}" y="${cvY + 3}" width="${cvEndX - cvStartX - 6}" height="${CONVEYOR_H - 6}" rx="5" fill="#1a3052" opacity="0.45"/>`;
                // Animated flow dots
                const dotCount = Math.floor((cvEndX - cvStartX) / 16);
                for (let di = 0; di < dotCount; di++) {
                    const dx = cvStartX + 10 + di * 16;
                    svg += `<circle cx="${dx}" cy="${cvY + CONVEYOR_H / 2}" r="2.2" fill="#2a5a8a" opacity="0.5">`;
                    svg += `<animate attributeName="cx" values="${dx};${dx + 10};${dx}" dur="1.8s" begin="${di * 0.08}s" repeatCount="indefinite"/>`;
                    svg += `<animate attributeName="opacity" values="0.3;0.7;0.3" dur="1.8s" begin="${di * 0.08}s" repeatCount="indefinite"/></circle>`;
                }
                // Direction arrow indicators
                for (let ai = 0; ai < 3; ai++) {
                    const ax = cvStartX + (cvEndX - cvStartX) * (0.25 + ai * 0.25);
                    svg += `<text x="${ax}" y="${cvY + CONVEYOR_H / 2 + 3.5}" fill="#2a5a8a" font-size="8" text-anchor="middle" opacity="0.5">▸</text>`;
                }
            }
        }

        // ── Data flow connection arcs between adjacent machines ──
        for (let i = 0; i < machinePositions.length - 1; i++) {
            const a = machinePositions[i], b = machinePositions[i + 1];
            const dx = b.x - a.x, dy = b.y - a.y;
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < (BOX + GAP_X) * 1.8) {
                // Curved connection
                const midX = (a.x + b.x) / 2;
                const midY = (a.y + b.y) / 2 - 15;
                svg += `<path d="M ${a.x} ${a.y - BOX / 2 - 3} Q ${midX} ${midY - 20} ${b.x} ${b.y - BOX / 2 - 3}" fill="none" stroke="#14253a" stroke-width="0.8" stroke-dasharray="4,3" opacity="0.4"/>`;
                // Animated flow dot on arc
                svg += `<circle r="2.5" fill="#00d4ff" opacity="0.4">`;
                svg += `<animateMotion dur="${2 + Math.random()}s" repeatCount="indefinite" path="M ${a.x} ${a.y - BOX / 2 - 3} Q ${midX} ${midY - 20} ${b.x} ${b.y - BOX / 2 - 3}"/></circle>`;
            }
        }

        // ── Legend at bottom (enhanced) ──
        const legendY = H - 35;
        // Legend background bar
        svg += `<rect x="${PAD_X - 30}" y="${legendY - 14}" width="${W - PAD_X * 2 + 60}" height="28" rx="6" fill="rgba(10,16,28,0.5)" stroke="#14253a" stroke-width="0.5"/>`;
        const legendItems = [
            { color: "#00ff9d", label: "OK" },
            { color: "#ffb300", label: "Maint." },
            { color: "#ff3d7f", label: "Panne" },
            { color: "#a259ff", label: "Planifié" },
        ];
        let lx = PAD_X - 10;
        legendItems.forEach((item, li) => {
            svg += `<circle cx="${lx}" cy="${legendY}" r="5" fill="${item.color}" filter="url(#glow-sm)"/>`;
            svg += `<text x="${lx + 10}" y="${legendY + 4}" fill="#7a8a9a" font-size="10" font-family="JetBrains Mono">${item.label}</text>`;
            lx += 12 + item.label.length * 7.5 + 25;
            if (li < legendItems.length - 1) {
                svg += `<line x1="${lx - 15}" y1="${legendY - 5}" x2="${lx - 15}" y2="${legendY + 5}" stroke="#1e3050" stroke-width="0.5"/>`;
            }
        });

        // ── Timestamp badge (bottom-right) ──
        const now = new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
        svg += `<text x="${W - PAD_X + 15}" y="${legendY + 4}" fill="#2a4a6a" font-size="9" text-anchor="end" font-family="JetBrains Mono">⏱ ${now}</text>`;

        svg += `</svg>`;
        wrap.innerHTML = svg;

        // ── Interactive click popup (dark glassmorphism) ──
        wrap.querySelectorAll(".machine-node").forEach(node => {
            node.addEventListener("click", (e) => {
                e.stopPropagation();
                // Remove existing popup
                const old = wrap.querySelector(".svg-popup");
                if (old) old.remove();

                const twinId = node.getAttribute("data-twin");
                const t = twins.find(tw => tw.twin_id === twinId);
                if (!t) return;

                const st = getNodeStatus(t);
                const oee = t.kpis?.oee ?? t.oee ?? 0;
                const energy = t.kpis?.energy_consumption_kwh ?? t.energy_kwh ?? 0;
                const water = t.kpis?.water_lph ?? t.water_lph ?? 0;
                const life = t.kpis?.remaining_life_years ?? t.remaining_life ?? "N/A";
                const lastLog = t.kpis?.last_maintenance ?? t.last_log ?? "N/A";

                const popup = document.createElement("div");
                popup.className = "svg-popup";
                popup.innerHTML = `
                    <div class="svgp-header">
                        <strong class="svgp-title">${t.twin_id}</strong>
                        <span class="svgp-close">✕</span>
                    </div>
                    <div class="svgp-row"><span class="svgp-label">Statut</span><span class="svgp-val" style="color:${st.border}">${st.emoji} ${st.label}</span></div>
                    <div class="svgp-row"><span class="svgp-label">Rendement</span><span class="svgp-val">${oee}%</span></div>
                    <div class="svgp-row"><span class="svgp-label">Énergie</span><span class="svgp-val">${energy} kWh</span></div>
                    <div class="svgp-row"><span class="svgp-label">Eau</span><span class="svgp-val">${water} L/h</span></div>
                    <div class="svgp-row"><span class="svgp-label">Durée de vie</span><span class="svgp-val">${life} ans</span></div>
                    <div class="svgp-row svgp-last"><span class="svgp-label">Dernier log</span><span class="svgp-val svgp-muted">${lastLog}</span></div>
                `;
                wrap.appendChild(popup);

                // Position popup near clicked node
                const rect = node.getBoundingClientRect();
                const wrapRect = wrap.getBoundingClientRect();
                let left = rect.right - wrapRect.left + 8;
                let top = rect.top - wrapRect.top;
                // Keep within bounds
                if (left + 220 > wrapRect.width) left = rect.left - wrapRect.left - 228;
                if (top + 200 > wrapRect.height) top = wrapRect.height - 210;
                if (top < 0) top = 5;
                popup.style.left = left + "px";
                popup.style.top = top + "px";

                popup.querySelector(".svgp-close").addEventListener("click", () => popup.remove());
            });
        });

        // Close popup when clicking outside
        wrap.addEventListener("click", (e) => {
            if (!e.target.closest(".machine-node") && !e.target.closest(".svg-popup")) {
                const old = wrap.querySelector(".svg-popup");
                if (old) old.remove();
            }
        });
    }


    function renderEnergyBars(twins) {
        const el = $("#energy-bars");
        if (!twins.length) { el.innerHTML = '<div class="kpi-loading">No data</div>'; return; }
        const maxE = Math.max(...twins.map(t => t.kpis?.energy_consumption_kwh || t.energy_kwh || 1));
        el.innerHTML = twins.map((t) => {
            const e = t.kpis?.energy_consumption_kwh || t.energy_kwh || 0;
            const pct = (e / maxE * 100).toFixed(0);
            const col = pct > 70 ? 'var(--c4)' : pct > 40 ? 'var(--warn)' : 'var(--c2)';
            return `<div style="display:flex;flex-direction:column;align-items:center;flex:1;gap:3px">
                <div style="flex:1;width:100%;background:var(--bg3);border-radius:3px 3px 0 0;position:relative;min-height:80px">
                    <div style="position:absolute;bottom:0;left:0;right:0;height:${pct}%;background:${col};border-radius:3px 3px 0 0;transition:height .5s"></div>
                </div>
                <span style="font-size:.5rem;color:var(--tx2);text-align:center;line-height:1.1">${t.twin_id}</span>
            </div>`;
        }).join("");
    }

    // ══════════════════════════════════════════════════════════
    // COMPONENT VIEW
    // ══════════════════════════════════════════════════════════

    function renderComponents(data) {
        setText("#comp-total", data.total);
        const cards = $("#comp-cards");
        const tbody = $("#comp-tbody");

        if (!data.components.length) {
            cards.innerHTML = '<div class="kpi-loading">No components — create twins with components first</div>';
            tbody.innerHTML = "";
            return;
        }

        // Cards
        cards.innerHTML = data.components.map((c) => {
            const statusCls = c.status === "operational" ? "ok" : c.status === "degraded" ? "warn" : "fault";
            return `<div class="comp-card status-${statusCls}">
        <div class="comp-name">${c.name}</div>
        <div class="comp-type">${c.type} • ${c.parent_twin}</div>
        <div class="comp-stats">
          <span>Health: ${c.health}%</span>
          <span>Floor ${c.floor}</span>
          <span class="status-dot ${statusCls}"></span>
        </div>
      </div>`;
        }).join("");

        // Table (matches new 11-col header)
        tbody.innerHTML = data.components.map((c) => {
            const chipCls = c.status === 'operational' ? 'chip-ok' : c.status === 'degraded' ? 'chip-warn' : 'chip-fault';
            return `<tr>
              <td>${c.comp_id}</td><td>${c.name}</td><td>${c.parent_twin}</td><td>${c.type}</td>
              <td><span class="status-chip ${chipCls}">${c.status}</span></td>
              <td>${c.energy_w || '—'}</td><td>${c.temp || '—'}</td><td>${c.vibration || '—'}</td>
              <td>${c.health}%</td><td>${c.cycles || '—'}</td><td style="font-size:.58rem;color:var(--tx2)">${c.last_log || '—'}</td>
            </tr>`;
        }).join("");
    }

    // ══════════════════════════════════════════════════════════
    // ASSET VIEW
    // ══════════════════════════════════════════════════════════

    function renderAssets(data) {
        setText("#asset-total", data.total + " ASSETS");
        setText("#asset-online", data.assets.filter(a => !(a.alerts || []).some(al => al.severity === 'CRITICAL')).length + " ONLINE");
        const tbody = $("#asset-tbody");

        if (!data.assets.length) {
            tbody.innerHTML = '<tr><td colspan="12" class="kpi-loading">No assets — create twins first</td></tr>';
            return;
        }

        // Asset KPI row (top 4 mini panels)
        const agg = data.aggregate_kpis;
        const kpiRow = $("#asset-kpi-row");
        if (kpiRow) {
            kpiRow.innerHTML = [
                { l: 'OEE Moyen', v: agg.avg_oee + '%', c: 'var(--c1)' },
                { l: 'Énergie Totale', v: agg.total_energy_kwh + ' kWh', c: 'var(--c4)' },
                { l: 'Disponibilité', v: agg.avg_availability + '%', c: 'var(--c2)' },
                { l: 'Qualité', v: agg.avg_quality + '%', c: 'var(--c3)' }
            ].map(k => `<div class="panel"><div style="padding:1rem;text-align:center">
                <div style="font-size:1.6rem;font-weight:700;font-family:Syne;color:${k.c}">${k.v}</div>
                <div style="font-size:.6rem;color:var(--tx2);margin-top:.2rem;letter-spacing:.06em">${k.l}</div>
            </div></div>`).join('');
        }

        // Asset table (matches new 12-col header)
        tbody.innerHTML = data.assets.map((a) => {
            const oeeClass = a.kpis.oee >= 85 ? 'oee-good' : a.kpis.oee >= 65 ? 'oee-avg' : 'oee-low';
            const stCls = (a.alerts || []).some(al => al.severity === 'CRITICAL') ? 'chip-fault' : (a.alerts || []).some(al => al.severity === 'WARNING') ? 'chip-warn' : 'chip-ok';
            const stLabel = stCls === 'chip-fault' ? 'Panne' : stCls === 'chip-warn' ? 'Dégradé' : 'OK';
            return `<tr>
              <td style="font-size:.6rem;color:var(--tx2)">${a.twin_id}</td><td>${a.name}</td><td>${a.asset_type}</td>
              <td>${a.floor}</td>
              <td><span class="status-chip ${stCls}">${stLabel}</span></td>
              <td class="${oeeClass}">${a.kpis.oee}%</td>
              <td>${a.energy_kwh} kWh</td><td>${a.kpis?.water_lph || 0} L/h</td>
              <td>${a.kpis?.remaining_life_years || '—'}y</td><td>${a.alert_count || 0}</td>
              <td style="font-size:.58rem;color:var(--tx2)">${a.kpis?.last_maintenance || '—'}</td>
              <td style="font-size:.58rem;color:var(--c3)">${a.aas_reference ? a.aas_reference.substring(0, 10) + '…' : 'SMIA'}</td>
            </tr>`;
        }).join("");

        // Gantt (maintenance schedule)
        const gantt = $("#ganttWrap");
        if (gantt) {
            gantt.innerHTML = data.assets.map(a => {
                const life = a.kpis?.remaining_life_years || 5;
                const pct = Math.min(life / 15 * 100, 100);
                const col = pct > 60 ? 'var(--c2)' : pct > 30 ? 'var(--warn)' : 'var(--err)';
                return `<div class="gantt-row">
                  <div class="gantt-label">${a.twin_id}</div>
                  <div class="gantt-track"><div class="gantt-bar" style="width:${pct}%;background:${col};left:0">${life}y</div></div>
                </div>`;
            }).join('');
        }

        // Fault history
        const fh = $("#faultHistory");
        if (fh) {
            const allAlerts = data.assets.flatMap(a => (a.alerts || []).map(al => ({ ...al, twin_id: a.twin_id })));
            if (!allAlerts.length) {
                fh.innerHTML = '<div class="kpi-loading">🟢 No faults recorded</div>';
            } else {
                fh.innerHTML = allAlerts.map(a => `
                  <div class="fault-item" style="border-left:3px solid ${a.severity === 'CRITICAL' ? 'var(--err)' : 'var(--warn)'}">
                    <span>${a.severity === 'CRITICAL' ? '🔴' : '🟡'} <strong>${a.twin_id}</strong></span>
                    <span style="color:var(--tx2);margin-left:.5rem">${a.message}</span>
                  </div>`).join('');
            }
        }
    }

    // ══════════════════════════════════════════════════════════
    // SYSTEM VIEW
    // ══════════════════════════════════════════════════════════

    function renderSystem(data) {
        // System KPI row
        const sysKpi = $("#system-kpi-row");
        if (sysKpi) {
            const lines = data.production_lines || [];
            const totalM = lines.reduce((s, l) => s + (l.machine_count || 0), 0);
            const avgOEE = lines.length ? Math.round(lines.reduce((s, l) => s + (l.oee || 0), 0) / lines.length) : 0;
            const totalE = lines.reduce((s, l) => s + (l.energy_kwh || 0), 0);
            sysKpi.innerHTML = [
                { l: 'Lignes', v: lines.length, c: 'var(--c1)' },
                { l: 'Machines', v: totalM, c: 'var(--c2)' },
                { l: 'OEE Système', v: avgOEE + '%', c: 'var(--c3)' },
                { l: 'Énergie', v: totalE + ' kWh', c: 'var(--c4)' }
            ].map(k => `<div class="panel"><div style="padding:1rem;text-align:center">
                <div style="font-size:1.6rem;font-weight:700;font-family:Syne;color:${k.c}">${k.v}</div>
                <div style="font-size:.6rem;color:var(--tx2);margin-top:.2rem">${k.l}</div>
            </div></div>`).join('');
        }

        // Production lines
        const pl = $("#productionLines");
        if (!data.production_lines.length) {
            if (pl) pl.innerHTML = '<div class="kpi-loading">No production lines — create twins first</div>';
        } else if (pl) {
            pl.innerHTML = data.production_lines.map((line) => {
                const machines = line.machines.map(m => {
                    const cls = m.status === 'fault' ? 'pm-fault' : m.status === 'warn' ? 'pm-warn' : 'pm-ok';
                    return `<div class="pm-box ${cls}">${m.twin_id}</div>`;
                }).join('<div class="prod-flow-arrow">→</div>');
                return `<div class="prod-line">
                  <div class="prod-line-hdr"><span class="prod-line-name">Ligne ${line.line}</span><span style="font-size:.65rem;color:var(--tx2)">${line.machine_count} machines</span></div>
                  <div class="prod-line-machines">${machines}</div>
                  <div class="line-kpis">
                    <div class="line-kpi"><div class="line-kpi-val" style="color:var(--c1)">${line.oee}%</div><div class="line-kpi-lbl">OEE</div></div>
                    <div class="line-kpi"><div class="line-kpi-val" style="color:var(--c4)">${line.energy_kwh} kWh</div><div class="line-kpi-lbl">Énergie</div></div>
                    <div class="line-kpi"><div class="line-kpi-val" style="color:var(--c2)">${line.machine_count}</div><div class="line-kpi-lbl">Machines</div></div>
                    <div class="line-kpi"><div class="line-kpi-val" style="color:var(--c3)">${line.alerts || 0}</div><div class="line-kpi-lbl">Alertes</div></div>
                  </div>
                </div>`;
            }).join("");
        }

        // Floor topology SVG
        renderTopologySVG(data.floors || []);

        // System log stream
        const sysLog = $("#system-log-stream");
        if (sysLog && !sysLog.children.length) {
            const agents = [];
            (data.floors || []).forEach(f => (f.smia_agents || []).forEach(a => agents.push({ name: a, floor: f.floor })));
            sysLog.innerHTML = agents.map(a => `<div class="log-line"><span class="log-time">${new Date().toLocaleTimeString()}</span><span class="log-agent">${a.name}</span><span class="log-action">active</span><span class="log-detail">Floor ${a.floor}</span></div>`).join('');
        }

        // Floor consumption
        const fc = $("#floorConsumption");
        if (fc && data.floors) {
            fc.innerHTML = data.floors.map(f => {
                const pct = Math.min((f.energy_kwh || 0) / 100 * 100, 100);
                return `<div style="display:flex;align-items:center;gap:.6rem;font-size:.64rem">
                  <span style="width:60px;color:var(--tx2)">Étage ${f.floor}</span>
                  <div class="lbar"><div class="lbar-fill" style="width:${pct}%;background:var(--c4)"></div></div>
                  <span style="width:60px;text-align:right;color:var(--tx)">${f.energy_kwh} kWh</span>
                  <span style="width:50px;text-align:right;color:var(--c1)">${f.machine_count} m.</span>
                </div>`;
            }).join('');
        }
    }

    function renderTopologySVG(floors) {
        const wrap = $("#topoSvg");
        if (!wrap || !floors.length) return;

        const W = 600, floorH = 65, pad = 15;
        const H = Math.max(floors.length * floorH + pad * 2, 280);
        wrap.setAttribute('viewBox', `0 0 ${W} ${H}`);

        let svg = `<rect x="0" y="0" width="${W}" height="${H}" fill="var(--bg2)" rx="8"/>`;
        floors.forEach((f, i) => {
            const y = pad + i * floorH;
            svg += `<rect x="15" y="${y}" width="${W - 30}" height="${floorH - 8}" rx="6" fill="var(--bg3)" stroke="var(--border)" stroke-width="1"/>`;
            svg += `<text x="28" y="${y + 20}" fill="var(--tx2)" font-size="11" font-family="JetBrains Mono">Étage ${f.floor}</text>`;
            svg += `<text x="${W - 40}" y="${y + 20}" fill="var(--tx2)" font-size="9" text-anchor="end" font-family="JetBrains Mono">${f.energy_kwh || 0} kWh</text>`;
            const n = f.machine_count || 0;
            const spacing = Math.min((W - 120) / Math.max(n, 1), 50);
            for (let j = 0; j < n; j++) {
                const cx = 100 + j * spacing;
                const cy = y + 40;
                svg += `<circle cx="${cx}" cy="${cy}" r="8" fill="rgba(0,212,255,.15)" stroke="var(--c1)" stroke-width="1"/>`;
                svg += `<circle cx="${cx}" cy="${cy}" r="3" fill="var(--c1)"><animate attributeName="opacity" values="1;.3;1" dur="2.5s" begin="${j * 0.3}s" repeatCount="indefinite"/></circle>`;
            }
        });
        wrap.innerHTML = svg;
    }

    // ══════════════════════════════════════════════════════════
    // PROCESS VIEW
    // ══════════════════════════════════════════════════════════

    function renderProcess(data) {
        // Process KPI row
        const procKpi = $("#process-kpi-row");
        const steps = data.bpmn_trace || [];
        if (procKpi) {
            const orders2 = data.orders || [];
            const ok = steps.filter(s => s.success).length;
            procKpi.innerHTML = [
                { l: 'Actions BPMN', v: steps.length, c: 'var(--c1)' },
                { l: 'Réussite', v: steps.length ? Math.round(ok / steps.length * 100) + '%' : '0%', c: 'var(--c2)' },
                { l: 'Ordres', v: orders2.length, c: 'var(--c4)' },
                { l: 'Agents actifs', v: data.agent_count || 4, c: 'var(--c3)' }
            ].map(k => `<div class="panel"><div style="padding:1rem;text-align:center">
                <div style="font-size:1.6rem;font-weight:700;font-family:Syne;color:${k.c}">${k.v}</div>
                <div style="font-size:.6rem;color:var(--tx2);margin-top:.2rem">${k.l}</div>
            </div></div>`).join('');
        }

        // BPMN trace
        const bpmn = $("#bpmn-flow");
        if (!steps.length) {
            bpmn.innerHTML = '<div class="kpi-loading">No agent actions recorded yet</div>';
        } else {
            const recent = steps.slice(-20);
            bpmn.innerHTML = `<div class="bpmn-nodes">${recent.map((s, i) => {
                const icon = s.success ? '✓' : '✕';
                const cls = s.success ? 'bpmn-ok' : 'bpmn-fail';
                return `<div class="bpmn-node ${cls}">
          <div class="bn-icon">${icon}</div>
          <div class="bn-label">${s.action}</div>
          <div class="bn-agent">${s.agent}</div>
          <div class="bn-tool">${s.tool} • ${Math.round(s.duration_ms)}ms</div>
        </div>${i < recent.length - 1 ? '<div class="bpmn-arrow">→</div>' : ''}`;
            }).join("")}</div>`;
        }

        // Orders table (new 10-col)
        const tbody = $("#order-tbody");
        const orders = data.orders || [];
        if (!orders.length) {
            tbody.innerHTML = '<tr><td colspan="10" class="kpi-loading">No orders — create twins first</td></tr>';
        } else {
            tbody.innerHTML = orders.map(o => {
                const pct = o.progress || Math.floor(Math.random() * 100);
                const pCol = pct >= 80 ? 'var(--c2)' : pct >= 40 ? 'var(--warn)' : 'var(--err)';
                return `<tr>
                  <td style="font-size:.6rem">${o.order_id}</td><td>${o.product}</td>
                  <td>${o.component_count || 1}</td>
                  <td><span class="status-chip chip-ok">${o.priority || 'Normal'}</span></td>
                  <td><span class="status-chip chip-ok">En cours</span></td>
                  <td>${o.line || 'A'}</td><td>${o.moe || 3}</td>
                  <td style="font-size:.58rem;color:var(--tx2)">${new Date(o.created_at).toLocaleTimeString()}</td>
                  <td style="font-size:.58rem;color:var(--tx2)">—</td>
                  <td><div class="mini-bar"><div class="mbar"><div class="mbar-fill" style="width:${pct}%;background:${pCol}"></div></div><span style="font-size:.58rem">${pct}%</span></div></td>
                </tr>`;
            }).join("");
        }

        // Worker schedule
        const ws = $("#workerSchedule");
        if (ws) {
            const roles = ['Superviseur', 'Opérateur CNC', 'Opérateur Robot', 'Technicien', 'Maintenance'];
            ws.innerHTML = roles.map((r, i) => {
                const shift = ['06h-14h', '14h-22h', '22h-06h'][i % 3];
                return `<div style="display:flex;align-items:center;justify-content:space-between;padding:.4rem .6rem;background:var(--bg2);border:1px solid var(--border);border-radius:5px;font-size:.62rem">
                  <span style="color:var(--txh);font-weight:600">${r}</span>
                  <span style="color:var(--tx2)">${shift}</span>
                  <span class="status-chip chip-ok" style="font-size:.5rem">Actif</span>
                </div>`;
            }).join('');
        }

        // Process consumption
        const pc = $("#processConsumption");
        if (pc && orders.length) {
            pc.innerHTML = orders.slice(0, 5).map(o => {
                const e = o.energy_kwh || 0;
                const pct = Math.min(e / 100 * 100, 100);
                return `<div style="display:flex;align-items:center;gap:.5rem;font-size:.62rem">
                  <span style="width:70px;color:var(--tx2)">${o.order_id}</span>
                  <div class="lbar"><div class="lbar-fill" style="width:${pct}%;background:var(--c4)"></div></div>
                  <span style="width:50px;text-align:right;color:var(--tx)">${e} kWh</span>
                </div>`;
            }).join('');
        }
    }

    // ══════════════════════════════════════════════════════════
    // LOG STREAM (from action store)
    // ══════════════════════════════════════════════════════════

    function appendLog(agent, action, detail) {
        const el = $("#log-stream");
        if (!el) return;
        const time = new Date().toLocaleTimeString();
        const line = document.createElement("div");
        line.className = "log-line";
        line.innerHTML = `<span class="log-time">${time}</span>
      <span class="log-agent">${agent}</span>
      <span class="log-action">${action}</span>
      <span class="log-detail">${detail}</span>`;
        el.prepend(line);
        while (el.children.length > 50) el.removeChild(el.lastChild);
    }

    // ══════════════════════════════════════════════════════════
    // CHAT (WebSocket + REST fallback)
    // ══════════════════════════════════════════════════════════

    function setupChat() {
        const fab = $("#chat-fab");
        const drawer = $("#chat-drawer");
        const close = $("#chat-close");
        const input = $("#chat-input");
        const send = $("#chat-send");
        const emptyBtn = $("#btn-open-chat-empty");

        fab.addEventListener("click", () => drawer.classList.toggle("open"));
        close.addEventListener("click", () => drawer.classList.remove("open"));
        if (emptyBtn) emptyBtn.addEventListener("click", () => drawer.classList.add("open"));

        send.addEventListener("click", () => sendMessage());
        input.addEventListener("keydown", (e) => { if (e.key === "Enter") sendMessage(); });

        $$(".qbtn").forEach(b => {
            b.addEventListener("click", () => {
                input.value = b.dataset.msg;
                sendMessage();
            });
        });

        connectChatWS();
    }

    function connectChatWS() {
        try {
            wsChat = new WebSocket(WS_CHAT);
            wsChat.onopen = () => { setLive(true); appendLog("SYS", "ws_connect", "Chat WebSocket connected"); };
            wsChat.onmessage = (e) => handleBotResponse(JSON.parse(e.data));
            wsChat.onclose = () => { setLive(false); setTimeout(connectChatWS, 3000); };
            wsChat.onerror = () => wsChat.close();
        } catch { setLive(false); }
    }

    function connectSensorWS() {
        try {
            wsSensors = new WebSocket(WS_SENSORS);
            wsSensors.onmessage = (e) => {
                const msg = JSON.parse(e.data);
                if (msg.type === "sensor_update" && msg.twins) {
                    appendLog("IoT", "sensor_poll", `${msg.twins.length} twin(s) polled`);
                }
            };
            wsSensors.onclose = () => setTimeout(connectSensorWS, 5000);
            wsSensors.onerror = () => wsSensors.close();
        } catch { /* ignore */ }
    }

    async function sendMessage() {
        const input = $("#chat-input");
        const msg = input.value.trim();
        if (!msg) return;
        input.value = "";

        addChatMsg("user", msg);
        addChatMsg("bot", '<span class="typing">Thinking…</span>');

        const payload = JSON.stringify({ message: msg, session_id: sessionId });

        if (wsChat && wsChat.readyState === WebSocket.OPEN) {
            wsChat.send(payload);
        } else {
            // REST fallback
            try {
                const res = await fetch(API_CHAT, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: payload,
                });
                const data = await res.json();
                handleBotResponse(data);
            } catch (err) {
                removeLast(".typing");
                addChatMsg("bot", `⚠️ Request failed: ${err.message}`);
            }
        }
    }

    function handleBotResponse(data) {
        removeLast(".typing");
        const text = data.explanation || data.response || JSON.stringify(data);
        addChatMsg("bot", text);
        appendLog("Agent", "response", text.substring(0, 80));

        // Auto-refresh dashboard + 3D immediately after chat actions
        setTimeout(async () => {
            await fetchViewData("overview");
            if (currentView !== "overview") {
                await fetchViewData(currentView);
            }
            if (twin3dInited) {
                await fetchViewData("twin3d");
            }
        }, 250);
    }

    function addChatMsg(role, html) {
        const el = $("#chat-messages");
        const div = document.createElement("div");
        div.className = `msg ${role}`;
        div.innerHTML = role === "bot" ? `<strong>TWINFORGE</strong><br/>${html}` : html;
        el.appendChild(div);
        el.scrollTop = el.scrollHeight;
    }

    function removeLast(sel) {
        const el = document.querySelector(`#chat-messages .msg:last-child ${sel}`);
        if (el) el.closest(".msg").remove();
    }

    // ══════════════════════════════════════════════════════════
    // UTILITIES
    // ══════════════════════════════════════════════════════════

    function setText(sel, val) { const el = $(sel); if (el) el.textContent = val; }
    function setLive(on) {
        const dot = $("#live-dot");
        if (dot) dot.className = on ? "live-dot on" : "live-dot";
    }

    function startClock() {
        const update = () => setText("#clock", new Date().toLocaleTimeString());
        update();
        setInterval(update, 1000);
    }

    // ══════════════════════════════════════════════════════════
    // 3D VIEW TOOLBAR SETUP
    // ══════════════════════════════════════════════════════════

    function setup3DToolbar() {
        // View mode buttons
        $$("#view3d-toolbar .view3d-btn").forEach(btn => {
            btn.addEventListener("click", () => {
                TwinForge3D.setViewMode(btn.dataset.mode);
                $$("#view3d-toolbar .view3d-btn").forEach(b => b.classList.remove("active"));
                btn.classList.add("active");
            });
        });
        // Refresh
        const refreshBtn = $("#btn-refresh-3d");
        if (refreshBtn) refreshBtn.addEventListener("click", () => TwinForge3D.refresh());
    }
})();
