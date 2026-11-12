// CreatorHub AI — React 18 + htm (JSX-like templates without a build step)
const { useEffect, useState, useCallback } = React;
const html = htm.bind(React.createElement);

const STATUSES = ["Idea", "Drafting", "Ready", "Scheduled", "Published"];
const fmt = (n) => Intl.NumberFormat("en-US", { notation: "compact" }).format(n);
const pct = (x) => (x * 100).toFixed(1) + "%";

async function api(path, body) {
  const res = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  if (!res.ok) throw new Error((await res.json()).error || res.statusText);
  return res.json();
}

function StatCards({ totals }) {
  const cards = [
    ["Published", totals.published],
    ["Impressions", fmt(totals.impressions)],
    ["Engagements", fmt(totals.engagements)],
    ["Engagement rate", pct(totals.engagement_rate)],
  ];
  return html`<div class="cards">${cards.map(([k, v]) => html`<div class="card" key=${k}><div class="v">${v}</div><div class="k">${k}</div></div>`)}</div>`;
}

function Bars({ title, data }) {
  const rows = Object.entries(data).sort((a, b) => b[1].engagement_rate - a[1].engagement_rate);
  const max = Math.max(...rows.map(([, v]) => v.engagement_rate), 0.0001);
  return html`<section class="panel"><h3>${title}</h3>
    ${rows.map(([k, v]) => html`<div class="bar-row" key=${k}>
      <span class="bar-label">${k}</span>
      <span class="bar"><span style=${{ width: (v.engagement_rate / max) * 100 + "%" }}></span></span>
      <span class="bar-val">${pct(v.engagement_rate)}</span></div>`)}
  </section>`;
}

function Board({ posts, onMove, onSuggest }) {
  return html`<section class="board">
    ${STATUSES.map((s) => html`<div class="col" key=${s}>
      <h4>${s} <span class="count">${posts.filter((p) => p.status === s).length}</span></h4>
      ${posts.filter((p) => p.status === s).slice(0, s === "Published" ? 4 : 99).map((p) => html`
        <div class="post" key=${p.id}>
          <div class="title">${p.title}</div>
          <div class="meta"><span class=${"pill " + p.platform}>${p.platform}</span> ${p.pillar}</div>
          ${p.publish_at && html`<div class="meta">${new Date(p.publish_at).toLocaleString([], { month: "short", day: "numeric", hour: "numeric" })}</div>`}
          ${p.caption && html`<div class="caption">${p.caption}</div>`}
          ${s !== "Published" && html`<div class="actions">
            ${STATUSES.indexOf(s) < 3 && html`<button onClick=${() => onMove(p, STATUSES[STATUSES.indexOf(s) + 1])}>Move →</button>`}
            <button class="ghost" onClick=${() => onSuggest(p)}>✨ Caption</button></div>`}
        </div>`)}
    </div>`)}
  </section>`;
}

function App() {
  const [posts, setPosts] = useState([]);
  const [mode, setMode] = useState("");
  const [stats, setStats] = useState(null);
  const [plan, setPlan] = useState(null);
  const [toast, setToast] = useState("");

  const load = useCallback(async () => {
    const [p, a] = await Promise.all([api("/api/posts"), api("/api/analytics")]);
    setPosts(p.posts); setMode(p.mode); setStats(a);
  }, []);
  useEffect(() => { load(); }, [load]);

  const flash = (msg) => { setToast(msg); setTimeout(() => setToast(""), 3500); };
  const move = async (p, status) => { await api(`/api/posts/${p.id}`, { status }); await load(); };
  const suggest = async (p) => {
    const s = await api(`/api/suggest/${p.id}`, {});
    await api(`/api/posts/${p.id}`, { caption: s.caption });
    flash(`Caption added (${s.source}${s.inspired_by ? `, modeled on “${s.inspired_by}”` : ""})`);
    await load();
  };
  const preview = async () => setPlan((await api("/api/schedule", { apply: false })).plan);
  const apply = async () => {
    const r = await api("/api/schedule", { apply: true });
    setPlan(null); flash(`Scheduled ${r.plan.length} post(s) at each platform's best-performing hour`); await load();
  };

  if (!stats) return html`<div class="wrap">Loading…</div>`;
  return html`<div class="wrap">
    <header><div><h1>CreatorHub <span class="ai">AI</span></h1>
      <div class="sub">Content pipeline, engagement analytics, and smart scheduling — synced with Notion</div></div>
      <span class=${"mode " + mode}>${mode === "notion" ? "● Live Notion" : "● Demo data"}</span></header>
    <${StatCards} totals=${stats.totals} />
    <div class="grid">
      <${Bars} title="Engagement rate by platform" data=${stats.by_platform} />
      <${Bars} title="Engagement rate by content pillar" data=${stats.by_pillar} />
      <section class="panel"><h3>Smart scheduler</h3>
        <p class="muted">Best posting hours learned from your history:</p>
        <div class="hours">${Object.entries(stats.best_hours).map(([k, h]) => html`<span key=${k} class=${"pill " + k}>${k} ${h}:00</span>`)}</div>
        <div class="actions"><button onClick=${preview}>Preview schedule</button>
          ${plan && plan.length > 0 && html`<button onClick=${apply}>Apply ${plan.length}</button>`}</div>
        ${plan && html`<ul class="plan">${plan.length ? plan.map((x) => html`<li key=${x.id}><b>${x.title}</b> — ${x.platform}, ${new Date(x.publish_at).toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "numeric" })}</li>`) : html`<li>No posts in “Ready”.</li>`}</ul>`}
      </section>
    </div>
    <${Board} posts=${posts} onMove=${move} onSuggest=${suggest} />
    ${toast && html`<div class="toast">${toast}</div>`}
  </div>`;
}

ReactDOM.createRoot(document.getElementById("root")).render(html`<${App} />`);
