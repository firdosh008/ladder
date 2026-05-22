// ===== Pipeline Layer Definitions =====
const LAYERS = [
  {
    id: 'demand_side', name: 'Demand-Side Signals', num: 1,
    agents: [
      { id: 'WebSearch', name: 'Web Search', detail: 'Tavily + Exa' },
      { id: 'Reddit', name: 'Reddit', detail: 'Posts + Comments' },
      { id: 'YouTube', name: 'YouTube', detail: 'Videos + Comments' },
      { id: 'HackerNews', name: 'Hacker News', detail: 'Algolia API' },
      { id: 'PAA', name: 'People Also Ask', detail: 'DataForSEO' },
      { id: 'Supadata', name: 'Supadata', detail: 'Video Transcripts' },
    ]
  },
  {
    id: 'comment_mining', name: 'Comment Mining', num: 2,
    agents: [
      { id: 'Clusterer', name: 'Embed + Cluster', detail: 'Embeddings + Sonnet' },
    ]
  },
  {
    id: 'supply_side', name: 'Supply-Side Analysis', num: 3,
    agents: [
      { id: 'TopContent', name: 'Top Content Pull', detail: 'YT Data API' },
      { id: 'GapDetection', name: 'Gap Detection', detail: '4 gap types' },
    ]
  },
  {
    id: 'kg_filter', name: 'Context Filter', num: 4,
    agents: [
      { id: 'GapScore', name: 'Gap + Saturation', detail: 'Caller context' },
    ]
  },
  {
    id: 'scoring', name: 'Outlier Scoring', num: 5,
    agents: [
      { id: 'TrendScore', name: 'TrendScore Formula', detail: '7 weights' },
    ]
  },
  {
    id: 'synthesis', name: 'Thesis Synthesis', num: 6,
    agents: [
      { id: 'Strategy Lens', name: 'Strategy Lens', detail: 'Macro narrative' },
      { id: 'Signal Lens', name: 'Signal Lens', detail: 'Leading indicator' },
      { id: 'Execution Lens', name: 'Execution Lens', detail: 'Operator how-to' },
      { id: 'Contrarian Lens', name: 'Contrarian Lens', detail: 'View inversion' },
      { id: 'Moderator', name: 'Moderator', detail: 'Pick winner' },
    ]
  },
  {
    id: 'verification', name: 'Fact Verification', num: 7,
    agents: [
      { id: 'ClaimTriage', name: 'Claim Triage', detail: 'Tiered check' },
    ]
  },
];

// ===== Config =====
const API_BASE = window.location.origin;
const USE_BACKEND = window.location.protocol !== 'file:'; // true if served from FastAPI

// ===== State =====
let state = { running: false, ws: null, runId: null, layerTimers: {}, sources: [], sourcePage: 0, sourcePageSize: 10 };

// ===== Build Pipeline UI =====
function buildPipeline() {
  const el = document.getElementById('pipeline');
  el.innerHTML = LAYERS.map(layer => `
    <div class="layer-card" id="layer-${layer.id}" data-layer="${layer.id}">
      <div class="layer-header">
        <div class="layer-indicator">${layer.num}</div>
        <div class="layer-info">
          <div class="layer-name">${layer.name}</div>
          <div class="layer-status" id="status-${layer.id}">Waiting</div>
        </div>
      </div>
      <div class="layer-agents">
        <div class="agent-list">
          ${layer.agents.map(a => `
            <div class="agent-item" id="agent-${a.id.replace(/\s+/g, '_')}" data-agent="${a.id}">
              <div class="agent-dot"></div>
              <span class="agent-name">${a.name}</span>
              <span class="agent-detail">${a.detail}</span>
            </div>
          `).join('')}
        </div>
      </div>
    </div>
  `).join('');
}

// ===== Research Start =====
async function startResearch() {
  const input = document.getElementById('queryInput').value.trim();
  if (!input || state.running) return;

  state.running = true;
  document.getElementById('submitBtn').disabled = true;
  document.getElementById('globalStatus').textContent = 'Researching…';
  document.getElementById('globalStatus').className = 'status-badge running';
  document.getElementById('mainContent').style.display = 'grid';

  buildPipeline();
  hideResults();
  document.getElementById('exportBtn').disabled = true;
  state.layerTimers = {};

  if (USE_BACKEND) {
    await startResearchBackend(input);
  } else {
    await startResearchSimulation(input);
  }
}

// ===== Backend Mode (WebSocket) =====
async function startResearchBackend(query) {
  try {
    setMcpPendingUi('Checking MCP server...');
    await callMcp('tools/list');
    setMcpPendingUi('Starting MCP run...');

    const result = await callMcp('tools/call', {
      name: 'run_research',
      arguments: {
        query,
        user_id: 'default',
        output_mode: 'research_report',
        context: {},
        config: {},
        async: true,
      },
    });

    const toolText = result?.content?.[0]?.text || '{}';
    const toolPayload = JSON.parse(toolText);
    if (!toolPayload.success) throw new Error(toolPayload.error || 'Research failed');

    state.runId = toolPayload.data?.run_id;
    if (!state.runId) throw new Error('MCP did not return a run_id');
    setMcpPendingUi(`MCP run started: ${state.runId.slice(0, 8)}`);
    connectResearchWebSocket(state.runId);

  } catch (err) {
    console.error('Failed to start research:', err);
    document.getElementById('globalStatus').textContent = 'Error';
    document.getElementById('globalStatus').className = 'status-badge error';
    showMcpError(err);
    finishResearch();
  }
}

function connectResearchWebSocket(runId) {
  const wsUrl = `${API_BASE.replace('http', 'ws')}/ws/research/${runId}`;
  const ws = new WebSocket(wsUrl);
  state.ws = ws;

  ws.onopen = () => {
    setMcpPendingUi('Streaming pipeline events...');
  };

  ws.onmessage = (evt) => {
    const event = JSON.parse(evt.data);
    handleEvent(event);
  };

  ws.onerror = (err) => {
    console.error('WebSocket error:', err);
    document.getElementById('globalStatus').textContent = 'Stream error';
    document.getElementById('globalStatus').className = 'status-badge error';
  };

  ws.onclose = async () => {
    if (!state.running) return;
    await loadResultAfterStreamClose(runId);
  };
}

async function loadResultAfterStreamClose(runId) {
  try {
    for (let i = 0; i < 120; i++) {
      const resp = await fetch(`${API_BASE}/api/research/${runId}`);
      if (resp.status === 404) {
        await sleep(1000);
        continue;
      }
      if (!resp.ok) throw new Error(`Result fetch failed (${resp.status})`);
      const data = await resp.json();
      if (['complete', 'rejected', 'error'].includes(data.status)) {
        if (data.status === 'error') throw new Error(data.error || 'Research failed');
        showResults(data);
        return;
      }
      document.getElementById('globalStatus').textContent = `Run ${data.status || 'running'}...`;
      await sleep(1000);
    }
    throw new Error('Timed out waiting for research result');
  } catch (err) {
    showMcpError(err);
  } finally {
    finishResearch();
  }
}

async function callMcp(method, params) {
  const resp = await fetch(`${API_BASE}/mcp`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', id: Date.now(), method, params }),
  });
  const rpc = await resp.json();
  if (rpc.error) throw new Error(rpc.error.message || `MCP ${method} failed`);
  return rpc.result;
}

function setMcpPendingUi(message) {
  document.getElementById('globalStatus').textContent = message;
  const firstLayer = document.getElementById('layer-demand_side');
  if (firstLayer) {
    firstLayer.classList.add('active');
    document.getElementById('status-demand_side').textContent = message;
  }
}

function showMcpError(err) {
  const card = document.getElementById('thesisCard');
  card.style.display = 'block';
  document.getElementById('winnerLens').textContent = 'MCP error';
  document.getElementById('thesisStatement').textContent = err.message || 'MCP request failed';
  document.getElementById('thesisPoints').innerHTML = '';
  document.getElementById('thesisRationale').textContent = 'Check the server terminal or C:\\tmp\\research-agent-mcp.err.log for the backend traceback.';
}

// ===== Event Handler =====
function handleEvent(event) {
  switch (event.event) {
    case 'layer_start': {
      const card = document.getElementById(`layer-${event.layer}`);
      if (card) {
        card.classList.add('active');
        document.getElementById(`status-${event.layer}`).textContent = 'Running…';
        state.layerTimers[event.layer] = event.timestamp ? Date.parse(event.timestamp) : Date.now();
      }
      break;
    }

    case 'layer_complete': {
      const card = document.getElementById(`layer-${event.layer}`);
      if (card) {
        card.classList.remove('active');
        card.classList.add('done');
        document.getElementById(`status-${event.layer}`).textContent = event.message || 'Complete';
      }
      break;
    }

    case 'agent_start': {
      const agentId = event.agent?.replace(/\s+/g, '_');
      const el = document.getElementById(`agent-${agentId}`);
      if (el) {
        el.classList.add('running');
        el.querySelector('.agent-detail').textContent = event.message || '';
      }
      break;
    }

    case 'agent_complete': {
      const agentId = event.agent?.replace(/\s+/g, '_');
      const el = document.getElementById(`agent-${agentId}`);
      if (el) {
        el.classList.remove('running');
        el.classList.add('done');
        el.querySelector('.agent-detail').textContent = event.message || 'Done';
      }
      break;
    }

    case 'agent_error': {
      const agentId = event.agent?.replace(/\s+/g, '_');
      const el = document.getElementById(`agent-${agentId}`);
      if (el) {
        el.classList.remove('running');
        el.classList.add('error');
        el.querySelector('.agent-detail').textContent = event.message || 'Error';
      }
      break;
    }

    case 'complete': {
      if (event.data) showResults(event.data);
      finishResearch();
      break;
    }

    case 'error': {
      console.error('Research error:', event.message);
      finishResearch();
      break;
    }
  }
}

function finishResearch() {
  state.running = false;
  document.getElementById('submitBtn').disabled = false;
  if (!document.getElementById('globalStatus').classList.contains('error')) {
    document.getElementById('globalStatus').textContent = 'Complete';
    document.getElementById('globalStatus').className = 'status-badge';
    if (state.runId) {
      document.getElementById('exportBtn').disabled = false;
    }
  }
  if (state.ws) { state.ws.close(); state.ws = null; }
}

function exportResearch() {
  if (!state.runId) return;
  const url = `${API_BASE}/api/research/${state.runId}/export`;
  window.open(url, '_blank');
}

// ===== Simulation Mode (offline / file:// protocol) =====
async function startResearchSimulation(query) {
  for (let i = 0; i < LAYERS.length; i++) {
    await simulateLayer(LAYERS[i]);
  }
  showResults(MOCK_RESULT);
  finishResearch();
}

async function simulateLayer(layer) {
  handleEvent({ event: 'layer_start', layer: layer.id });

  const parallelLayers = ['demand_side', 'synthesis'];
  if (parallelLayers.includes(layer.id)) {
    const promises = layer.agents.map((agent, idx) => simulateAgent(layer.id, agent, idx * 200));
    await Promise.all(promises);
  } else {
    for (const agent of layer.agents) {
      await simulateAgent(layer.id, agent, 0);
    }
  }

  handleEvent({ event: 'layer_complete', layer: layer.id, message: 'Complete' });
  const costSoFar = Object.values(MOCK_RESULT.cost_breakdown.layers)
    .slice(0, LAYERS.indexOf(layer) + 1)
    .reduce((a, b) => a + b, 0);
  document.getElementById('globalCost').textContent = `$${costSoFar.toFixed(2)}`;
}

async function simulateAgent(layerId, agent, delay) {
  await sleep(delay);
  handleEvent({ event: 'agent_start', layer: layerId, agent: agent.id, message: agent.detail });
  await sleep(600 + Math.random() * 800);
  handleEvent({ event: 'agent_complete', layer: layerId, agent: agent.id, message: `${agent.detail} ✓` });
}

// ===== Results Rendering =====
function hideResults() {
  ['thesisCard', 'rejectedCard', 'sourcesCard', 'unmetCard', 'costCard']
    .forEach(id => document.getElementById(id).style.display = 'none');
  state.sources = [];
  state.sourcePage = 0;
}

function showResults(data) {
  const thesis = data.winning_thesis;
  if (thesis) {
    const tc = document.getElementById('thesisCard');
    tc.style.display = 'block';
    document.getElementById('winnerLens').textContent = thesis.lens || 'signal';
    document.getElementById('thesisStatement').textContent = thesis.statement || '';
    document.getElementById('thesisPoints').innerHTML = (thesis.supporting_points || [])
      .map(p => `<div class="thesis-point"><span>${esc(p)}</span></div>`).join('');
    document.getElementById('thesisRationale').textContent = thesis.supply_side_rationale || '';
  }

  const rejected = data.rejected_candidates || data.rejected_theses || [];
  if (rejected.length) {
    setTimeout(() => {
      document.getElementById('rejectedCard').style.display = 'block';
      document.getElementById('rejectedList').innerHTML = rejected.map(c => `
        <div class="rejected-item">
          <div class="rejected-lens ${c.lens}">${c.lens}</div>
          <div class="rejected-statement">${esc(c.statement)}</div>
          <div class="rejected-reason">Rejected: ${esc(c.rejection_reason || 'Score lower than winner')}</div>
        </div>
      `).join('');
    }, 200);
  }

  const sources = data.sources || [];
  if (sources.length) {
    setTimeout(() => {
      state.sources = orderSourcesForDisplay(sources);
      state.sourcePage = 0;
      document.getElementById('sourcesCard').style.display = 'block';
      renderSourcesPage();
    }, 400);
  }

  const unmet = data.unmet_asks || data.comment_clusters || [];
  const unmetAsks = unmet.filter(u => u.unmet_ask !== false);
  if (unmetAsks.length) {
    setTimeout(() => {
      document.getElementById('unmetCard').style.display = 'block';
      document.getElementById('unmetList').innerHTML = unmetAsks.map(u => `
        <div class="unmet-item">
          <div class="unmet-theme">${esc(u.theme)}</div>
          <div class="unmet-comments">${(u.representative_comments || []).map(c => esc(c)).join(' · ')}</div>
          <div class="unmet-freq">${u.frequency || 0} comments across platforms</div>
        </div>
      `).join('');
    }, 600);
  }

  const cost = data.cost_breakdown;
  if (cost) {
    setTimeout(() => {
      document.getElementById('costCard').style.display = 'block';
      const layers = cost.layer_costs || cost.layers || {};
      const total = cost.total || 0;
      const duration = cost.duration_seconds || cost.duration || 0;
      const colorClass = total < 1 ? 'green' : total < 1.5 ? 'amber' : 'red';
      document.getElementById('globalCost').textContent = `$${total.toFixed(2)}`;
      document.getElementById('costGrid').innerHTML =
        Object.entries(layers).map(([k, v]) => `
          <div class="cost-item">
            <div class="cost-label">${esc(k)}</div>
            <div class="cost-value">$${v.toFixed(2)}</div>
          </div>
        `).join('') +
        `<div class="cost-item"><div class="cost-label">Total</div><div class="cost-value ${colorClass}">$${total.toFixed(2)}</div></div>` +
        `<div class="cost-item"><div class="cost-label">Duration</div><div class="cost-value">${Math.round(duration)}s</div></div>`;
    }, 800);
  }
}

// ===== Mock Data (for file:// mode) =====
const MOCK_RESULT = {
  winning_thesis: {
    lens: 'signal',
    statement: 'The real AI agent opportunity isn\'t building agents — it\'s building the evaluation infrastructure that tells you whether your agent actually works.',
    supporting_points: [
      'Agent framework launches up 340% YoY, but production deployment rates remain under 12%',
      'Top pain point in r/MachineLearning and HN: "my agent works in demos but fails in production"',
      'LangSmith, Braintrust, and Arize saw 5× ARR growth — eval tooling, not agent building',
    ],
    supply_side_rationale: 'The top 3 videos on "AI agents 2026" focus on building with CrewAI/LangGraph. None address the evaluation gap.',
  },
  rejected_candidates: [
    { lens: 'strategy', statement: 'AI agents represent the third wave of software — from tools to assistants to autonomous workers.', rejection_reason: 'Too broad. 8 creators with >100K followers already own this narrative.' },
    { lens: 'execution', statement: 'Ship your first production AI agent in 48 hours using LangGraph v1.1.3.', rejection_reason: 'Saturated supply. Top 10 results are all tutorials with strong engagement.' },
    { lens: 'contrarian', statement: 'Most AI agents being built today will never reach production — and that\'s fine.', rejection_reason: 'Weak defendability. Hard to back with data.' },
  ],
  sources: [
    { title: '"Why my AI agent fails in production" — 847 upvotes', url: '#', platform: 'reddit', snippet: 'Detailed post-mortem on agent reliability issues...' },
    { title: 'The Agent Evaluation Gap (2026)', url: '#', platform: 'web', snippet: 'Research report on the growing disconnect...' },
    { title: 'Building Reliable AI Agents — 234K views', url: '#', platform: 'youtube', snippet: 'Most-watched agent reliability video...' },
    { title: 'Ask HN: How do you test your AI agents?', url: '#', platform: 'hackernews', snippet: '312 points, 189 comments.' },
    { title: 'How to evaluate AI agent performance', url: '#', platform: 'paa', snippet: 'Search volume up 520% in 90 days.' },
  ],
  unmet_asks: [
    { theme: '"How do I know if my agent is actually working?"', representative_comments: ['Need concrete eval metrics', 'Testing strategies?'], frequency: 34, unmet_ask: true },
    { theme: '"Show me a production agent, not another demo"', representative_comments: ['Want real case studies'], frequency: 28, unmet_ask: true },
  ],
  cost_breakdown: {
    layers: { 'Demand-Side': 0.28, 'Comment Mining': 0.08, 'Supply-Side': 0.12, 'KG Filter': 0.03, 'Scoring': 0.02, 'Synthesis': 0.38, 'Verification': 0.09 },
    total: 0.92, duration: 47,
  }
};

// ===== Helpers =====
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

function renderSourcesPage() {
  const start = state.sourcePage * state.sourcePageSize;
  const page = state.sources.slice(start, start + state.sourcePageSize);
  const totalPages = Math.max(1, Math.ceil(state.sources.length / state.sourcePageSize));
  const sourcesCard = document.getElementById('sourcesCard');
  let controls = document.getElementById('sourcesControls');
  if (!controls) {
    controls = document.createElement('div');
    controls.id = 'sourcesControls';
    controls.className = 'source-controls';
    sourcesCard.appendChild(controls);
  }

  document.getElementById('sourcesList').innerHTML = page.map(s => {
    const platform = esc(s.platform || 'web');
    return `
      <div class="source-item">
        <span class="source-platform ${platform}">${platform}</span>
        <div class="source-info">
          <div class="source-title"><a href="${esc(s.url)}" target="_blank">${esc(s.title)}</a></div>
          <div class="source-snippet">${esc(s.snippet)}</div>
        </div>
      </div>
    `;
  }).join('');

  controls.innerHTML = `
    <button class="source-page-btn" ${state.sourcePage === 0 ? 'disabled' : ''} onclick="changeSourcesPage(-1)">Prev</button>
    <span class="source-page-status">Page ${state.sourcePage + 1} / ${totalPages} · ${state.sources.length} sources</span>
    <button class="source-page-btn" ${state.sourcePage >= totalPages - 1 ? 'disabled' : ''} onclick="changeSourcesPage(1)">Next</button>
  `;
}

function changeSourcesPage(delta) {
  const totalPages = Math.max(1, Math.ceil(state.sources.length / state.sourcePageSize));
  state.sourcePage = Math.max(0, Math.min(totalPages - 1, state.sourcePage + delta));
  renderSourcesPage();
}

function orderSourcesForDisplay(sources) {
  const priority = ['youtube', 'hackernews', 'reddit', 'web', 'paa'];
  const byPlatform = new Map();
  for (const source of sources) {
    const platform = source.platform || 'web';
    if (!byPlatform.has(platform)) byPlatform.set(platform, []);
    byPlatform.get(platform).push(source);
  }

  const selected = [];
  const seen = new Set();
  const add = (source) => {
    const key = source.url || `${source.platform}:${source.title}`;
    if (seen.has(key)) return;
    seen.add(key);
    selected.push(source);
  };

  for (const platform of priority) {
    for (const source of (byPlatform.get(platform) || []).slice(0, 5)) add(source);
  }
  for (const source of sources) add(source);
  return selected;
}

// Handle Enter key
document.getElementById('queryInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') startResearch();
});

// Init
buildPipeline();
