/* ─────────────────────────────────────────────────────────────────────
   GraphRAG UI — app.js
   All UI logic: tab routing, D3 graph, chat, communities, pipeline WS
───────────────────────────────────────────────────────────────────── */

'use strict';

// ── State ──────────────────────────────────────────────────────────────────
let currentMode = 'auto';
let graphData   = { nodes: [], links: [] };
let simulation  = null;
let allCommunities = [];
let ws = null;

const NODE_COLORS = {
  PERSON:  '#38bdf8',
  ORG:     '#a78bfa',
  CONCEPT: '#34d399',
  PLACE:   '#fbbf24',
  EVENT:   '#f87171',
  PRODUCT: '#fb923c',
  OTHER:   '#64748b',
};

// ── Initialisation ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadStatus();
  connectWebSocket();
  setInterval(loadStatus, 15000);

  // Auto-resize textarea
  const ta = document.getElementById('chat-input');
  if (ta) {
    ta.addEventListener('input', () => {
      ta.style.height = 'auto';
      ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
    });
  }
});

// ── Tabs ───────────────────────────────────────────────────────────────────
function showTab(name) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  document.getElementById('nav-' + name).classList.add('active');

  if (name === 'graph')       loadGraph();
  if (name === 'communities') loadCommunities();
}

// ── Status ─────────────────────────────────────────────────────────────────
async function loadStatus() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();

    setText('stat-nodes-val',       d.graph.nodes);
    setText('stat-edges-val',       d.graph.edges);
    setText('stat-communities-val', d.graph.communities);
    setText('stat-files-val',       d.data_files.length);

    // Dot
    const dot   = document.getElementById('status-dot');
    const label = document.getElementById('status-label');
    if (d.pipeline.running) {
      setDot(dot, 'running'); label.textContent = 'Running…';
    } else if (d.ready) {
      setDot(dot, 'ready');   label.textContent = 'Graph ready';
    } else {
      setDot(dot, 'idle');    label.textContent = 'No graph';
    }

    // File list
    const ul = document.getElementById('file-list');
    if (ul) {
      if (d.data_files.length === 0) {
        ul.innerHTML = '<li class="file-item placeholder">No documents indexed yet</li>';
      } else {
        ul.innerHTML = d.data_files.map(f =>
          `<li class="file-item">${escHtml(f)}</li>`
        ).join('');
      }
    }
  } catch (_) {}
}

function setDot(el, cls) {
  el.className = 'dot dot-' + cls;
}
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val ?? '—';
}
function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Quick query (dashboard) ────────────────────────────────────────────────
async function runQuickQuery() {
  const inp = document.getElementById('quick-q-input');
  const q = inp.value.trim();
  if (!q) return;

  const box  = document.getElementById('quick-answer-box');
  const mode = document.getElementById('quick-answer-mode');
  const text = document.getElementById('quick-answer-text');

  box.style.display = 'block';
  mode.textContent  = '⏳ Thinking…';
  text.textContent  = '';

  try {
    const r = await fetch('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q, mode: 'auto' }),
    });
    if (!r.ok) { const e = await r.json(); throw new Error(e.detail); }
    const d = await r.json();
    mode.textContent = d.mode.toUpperCase() + ' SEARCH';
    text.textContent = d.answer;
  } catch (e) {
    mode.textContent = 'ERROR';
    text.textContent = e.message;
  }
}

document.addEventListener('keydown', e => {
  if (e.target.id === 'quick-q-input' && e.key === 'Enter') runQuickQuery();
});

// ── D3 Graph ───────────────────────────────────────────────────────────────
async function loadGraph() {
  const loading = document.getElementById('graph-loading');
  loading.style.display = 'flex';

  try {
    const r = await fetch('/api/graph');
    graphData = await r.json();
    renderGraph(graphData.nodes, graphData.links);
    buildLegend();
  } catch (_) {
    loading.innerHTML = '<p style="color:#f87171">Failed to load graph data.</p>';
  } finally {
    loading.style.display = 'none';
  }
}

function applyGraphFilter() {
  const type = document.getElementById('node-type-filter').value;
  if (type === 'ALL') {
    renderGraph(graphData.nodes, graphData.links);
  } else {
    const filtered = graphData.nodes.filter(n => n.type === type);
    const ids = new Set(filtered.map(n => n.id));
    const filteredLinks = graphData.links.filter(l => ids.has(l.source.id ?? l.source) && ids.has(l.target.id ?? l.target));
    renderGraph(filtered, filteredLinks);
  }
}

function resetGraph() {
  document.getElementById('node-type-filter').value = 'ALL';
  renderGraph(graphData.nodes, graphData.links);
}

function renderGraph(nodes, links) {
  const container = document.getElementById('graph-container');
  const svg = d3.select('#graph-svg');
  svg.selectAll('*').remove();

  if (!nodes.length) {
    document.getElementById('graph-loading').style.display = 'flex';
    document.getElementById('graph-loading').innerHTML = '<p style="color:#475569">No graph data. Run the pipeline first.</p>';
    return;
  }
  document.getElementById('graph-loading').style.display = 'none';

  const W = container.clientWidth;
  const H = container.clientHeight || 560;
  svg.attr('width', W).attr('height', H);

  // Clone data for D3 mutation
  const ns = nodes.map(d => ({ ...d }));
  const ls = links.map(d => ({ ...d }));

  // Zoom
  const g = svg.append('g');
  svg.call(d3.zoom().scaleExtent([0.1, 6]).on('zoom', e => g.attr('transform', e.transform)));

  // Simulation
  if (simulation) simulation.stop();
  simulation = d3.forceSimulation(ns)
    .force('link', d3.forceLink(ls).id(d => d.id).distance(90).strength(0.4))
    .force('charge', d3.forceManyBody().strength(-220))
    .force('center', d3.forceCenter(W / 2, H / 2))
    .force('collision', d3.forceCollide(20));

  // Draw edges
  const link = g.append('g').attr('class', 'links')
    .selectAll('line')
    .data(ls).join('line')
    .attr('stroke', 'rgba(255,255,255,0.08)')
    .attr('stroke-width', d => Math.min(1 + d.weight * 0.5, 3));

  // Edge labels (visible on hover via CSS would need SVG title)
  link.append('title').text(d => d.relation);

  // Draw nodes
  const tooltip = document.getElementById('node-tooltip');
  const node = g.append('g').attr('class', 'nodes')
    .selectAll('circle')
    .data(ns).join('circle')
    .attr('r', d => Math.max(5, Math.min(d.degree * 1.8 + 5, 22)))
    .attr('fill', d => NODE_COLORS[d.type] || NODE_COLORS.OTHER)
    .attr('fill-opacity', 0.85)
    .attr('stroke', d => NODE_COLORS[d.type] || NODE_COLORS.OTHER)
    .attr('stroke-opacity', 0.4)
    .attr('stroke-width', 6)
    .style('cursor', 'pointer')
    .call(d3.drag()
      .on('start', (event, d) => { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag',  (event, d) => { d.fx = event.x; d.fy = event.y; })
      .on('end',   (event, d) => { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
    )
    .on('mouseover', (event, d) => {
      document.getElementById('tooltip-name').textContent   = d.id;
      document.getElementById('tooltip-type').textContent   = d.type;
      document.getElementById('tooltip-desc').textContent   = d.description || '—';
      document.getElementById('tooltip-degree').textContent = `${d.degree} connections`;
      tooltip.style.display = 'block';
      positionTooltip(event);
    })
    .on('mousemove', positionTooltip)
    .on('mouseout', () => { tooltip.style.display = 'none'; });

  // Node labels for high-degree nodes
  const label = g.append('g').attr('class', 'labels')
    .selectAll('text')
    .data(ns.filter(d => d.degree > 1)).join('text')
    .text(d => d.id.length > 18 ? d.id.slice(0, 16) + '…' : d.id)
    .attr('font-size', 11)
    .attr('font-family', 'Inter, sans-serif')
    .attr('fill', 'rgba(148,163,184,0.9)')
    .attr('pointer-events', 'none')
    .attr('text-anchor', 'middle')
    .attr('dy', d => -Math.max(5, Math.min(d.degree * 1.8 + 5, 22)) - 4);

  simulation.on('tick', () => {
    link
      .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
    node.attr('cx', d => d.x).attr('cy', d => d.y);
    label.attr('x', d => d.x).attr('y', d => d.y);
  });
}

function positionTooltip(event) {
  const tooltip = document.getElementById('node-tooltip');
  const container = document.getElementById('graph-container');
  const rect = container.getBoundingClientRect();
  let x = event.clientX - rect.left + 14;
  let y = event.clientY - rect.top  - 10;
  if (x + 270 > rect.width)  x = event.clientX - rect.left - 280;
  if (y + 120 > rect.height) y = event.clientY - rect.top  - 120;
  tooltip.style.left = x + 'px';
  tooltip.style.top  = y + 'px';
}

function buildLegend() {
  const el = document.getElementById('legend-items');
  el.innerHTML = Object.entries(NODE_COLORS).map(([type, color]) =>
    `<div class="legend-item">
       <div class="legend-dot" style="background:${color}"></div>
       <span>${type}</span>
     </div>`
  ).join('');
}

// ── Query / Chat ───────────────────────────────────────────────────────────
function setMode(mode) {
  currentMode = mode;
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('mode-' + mode).classList.add('active');
  const labels = { auto: 'Auto (smart routing)', local: 'Local (entity search)', global: 'Global (community synthesis)' };
  document.getElementById('current-mode-label').textContent = 'Mode: ' + labels[mode];
}

function fillExample(text) {
  const ta = document.getElementById('chat-input');
  ta.value = text;
  ta.dispatchEvent(new Event('input'));
  ta.focus();
}

function handleChatKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendQuery(); }
}

async function sendQuery() {
  const ta  = document.getElementById('chat-input');
  const btn = document.getElementById('send-btn');
  const q   = ta.value.trim();
  if (!q) return;

  ta.value = ''; ta.style.height = 'auto';

  // Remove welcome screen on first message
  const welcome = document.querySelector('.chat-welcome');
  if (welcome) welcome.remove();

  appendBubble('user', q, currentMode);
  const thinkId = appendBubble('assistant', '⏳ Thinking…', currentMode, true);

  btn.disabled = true;

  try {
    const r = await fetch('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q, mode: currentMode }),
    });
    if (!r.ok) { const e = await r.json(); throw new Error(e.detail); }
    const d = await r.json();
    updateBubble(thinkId, d.answer, d.mode);
  } catch (e) {
    updateBubble(thinkId, '❌ ' + e.message, currentMode);
  } finally {
    btn.disabled = false;
  }
}

let _bubbleId = 0;
function appendBubble(role, text, mode, thinking = false) {
  const id = 'bubble-' + (++_bubbleId);
  const msgs = document.getElementById('chat-messages');
  const modeLabel = { auto: 'Auto', local: 'Local', global: 'Global' }[mode] || mode;
  const badgeCls  = { auto: 'badge-auto', local: 'badge-local', global: 'badge-global' }[mode] || 'badge-auto';

  const div = document.createElement('div');
  div.id = id;
  div.className = `chat-bubble bubble-${role}${thinking ? ' bubble-thinking' : ''}`;
  div.innerHTML = `
    <div class="bubble-meta">
      ${role === 'user' ? '🧑 You' : `🤖 GraphRAG <span class="badge ${badgeCls}">${modeLabel}</span>`}
    </div>
    <div class="bubble-content">${escHtml(text)}</div>
  `;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  return id;
}

function updateBubble(id, text, mode) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.remove('bubble-thinking');
  const modeLabel = { auto: 'Auto', local: 'Local', global: 'Global' }[mode] || mode;
  const badgeCls  = { auto: 'badge-auto', local: 'badge-local', global: 'badge-global' }[mode] || 'badge-auto';
  el.innerHTML = `
    <div class="bubble-meta">
      🤖 GraphRAG <span class="badge ${badgeCls}">${modeLabel}</span>
    </div>
    <div class="bubble-content">${escHtml(text)}</div>
  `;
  document.getElementById('chat-messages').scrollTop = 999999;
}

// ── Communities ────────────────────────────────────────────────────────────
async function loadCommunities() {
  const grid = document.getElementById('communities-grid');
  grid.innerHTML = '<div class="placeholder-message"><div class="spinner" style="margin:0 auto"></div></div>';
  try {
    const r = await fetch('/api/communities');
    allCommunities = await r.json();
    renderCommunities(allCommunities);
  } catch (_) {
    grid.innerHTML = '<div class="placeholder-message">Failed to load communities.</div>';
  }
}

function renderCommunities(list) {
  const grid = document.getElementById('communities-grid');
  if (!list.length) {
    grid.innerHTML = '<div class="placeholder-message">No communities found. Run the pipeline first.</div>';
    return;
  }
  grid.innerHTML = list.map(c => {
    const tags = c.entity_names.slice(0, 6).map(n =>
      `<span class="community-tag">${escHtml(n)}</span>`
    ).join('');
    const more = c.entity_names.length > 6 ? `<span class="community-tag">+${c.entity_names.length - 6} more</span>` : '';
    const summary = c.summary || '<em>No summary generated yet.</em>';
    return `
      <div class="community-card">
        <div class="community-card-header">
          <span class="community-id">Community #${c.id}</span>
          <span class="community-count">${c.entity_names.length} entities</span>
        </div>
        <p class="community-summary">${escHtml(summary)}</p>
        <div class="community-tags">${tags}${more}</div>
      </div>`;
  }).join('');
}

function filterCommunities() {
  const q = document.getElementById('community-search').value.toLowerCase();
  if (!q) { renderCommunities(allCommunities); return; }
  const filtered = allCommunities.filter(c =>
    c.summary.toLowerCase().includes(q) ||
    c.entity_names.some(n => n.toLowerCase().includes(q))
  );
  renderCommunities(filtered);
}

// ── Pipeline ───────────────────────────────────────────────────────────────
async function startPipeline() {
  const btn = document.getElementById('run-btn');
  btn.disabled = true;
  btn.textContent = '⏳ Running…';
  document.getElementById('progress-section').style.display = 'block';
  document.getElementById('log-console').innerHTML = '';

  try {
    const r = await fetch('/api/pipeline/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input_dir: './data' }),
    });
    if (!r.ok) {
      const e = await r.json();
      appendLog('ERROR: ' + e.detail, 'error');
      resetRunBtn();
    }
  } catch (e) {
    appendLog('ERROR: ' + e.message, 'error');
    resetRunBtn();
  }
}

function resetRunBtn() {
  const btn = document.getElementById('run-btn');
  btn.disabled = false;
  btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><polygon points="5 3 19 12 5 21 5 3"/></svg> Start Indexing`;
}

function clearLogs() {
  document.getElementById('log-console').innerHTML =
    '<span class="log-placeholder">Logs will appear here during pipeline execution…</span>';
}

function appendLog(line, cls = '') {
  const console_ = document.getElementById('log-console');
  const placeholder = console_.querySelector('.log-placeholder');
  if (placeholder) placeholder.remove();
  const span = document.createElement('div');
  span.className = 'log-line ' + cls;
  span.textContent = line;
  console_.appendChild(span);
  console_.scrollTop = console_.scrollHeight;
}

const STEP_ORDER = ['chunking','extracting','building_graph','detecting_communities','summarizing','saving','complete'];

function updatePipelineStep(step, progress) {
  document.getElementById('progress-bar').style.width  = progress + '%';
  document.getElementById('progress-label').textContent = step.replace(/_/g,' ') + ' — ' + progress + '%';

  // Update visual steps
  const idx = STEP_ORDER.indexOf(step);
  STEP_ORDER.forEach((s, i) => {
    const el = document.getElementById('ps-' + s);
    if (!el) return;
    if (i < idx)       { el.classList.remove('active'); el.classList.add('done'); }
    else if (i === idx) { el.classList.add('active'); el.classList.remove('done'); }
    else               { el.classList.remove('active','done'); }
  });
}

// ── File upload ────────────────────────────────────────────────────────────
function handleDragOver(e) {
  e.preventDefault();
  document.getElementById('drop-zone').classList.add('drag-over');
}
function handleDrop(e) {
  e.preventDefault();
  document.getElementById('drop-zone').classList.remove('drag-over');
  uploadFiles(e.dataTransfer.files);
}
function handleFileSelect(e) { uploadFiles(e.target.files); }

async function uploadFiles(fileList) {
  if (!fileList.length) return;
  const form = new FormData();
  for (const f of fileList) form.append('files', f);

  const status = document.getElementById('upload-status');
  status.style.display = 'block';
  status.textContent = '⏳ Uploading…';

  try {
    const r = await fetch('/api/upload', { method: 'POST', body: form });
    if (!r.ok) throw new Error(await r.text());
    const d = await r.json();
    status.textContent = `✅ Uploaded: ${d.saved.join(', ')}`;
    loadStatus();
  } catch (e) {
    status.textContent = '❌ ' + e.message;
    status.style.background = 'rgba(248,113,113,.1)';
    status.style.borderColor = 'rgba(248,113,113,.3)';
    status.style.color = '#f87171';
  }
}

// ── WebSocket ──────────────────────────────────────────────────────────────
function connectWebSocket() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws/pipeline`);

  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);

    if (msg.type === 'pipeline_log') {
      const line = msg.line || '';
      const cls  = line.includes('✅') || line.includes('saved') ? 'success'
                  : line.includes('ERROR') || line.includes('error') ? 'error' : '';
      appendLog(line, cls);
      if (msg.step)     updatePipelineStep(msg.step, msg.progress || 0);
    }

    if (msg.type === 'pipeline_complete') {
      appendLog('✅ Pipeline complete!', 'success');
      updatePipelineStep('complete', 100);
      resetRunBtn();
      loadStatus();
      // Refresh graph/communities if those tabs were already loaded
      graphData = { nodes: [], links: [] };
    }

    if (msg.type === 'pipeline_error') {
      appendLog('❌ ' + (msg.message || 'Unknown error'), 'error');
      resetRunBtn();
    }

    if (msg.type === 'pipeline_status' && msg.data) {
      const d = msg.data;
      if (d.running) {
        updatePipelineStep(d.step, d.progress);
      }
      if (d.logs && d.logs.length) {
        d.logs.forEach(l => appendLog(l));
      }
    }
  };

  ws.onclose = () => setTimeout(connectWebSocket, 3000);
  ws.onerror = () => ws.close();
}
