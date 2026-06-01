(function () {
  "use strict";

  // ---- State ----
  const state = {
    page: 1,
    limit: 25,
    total: 0,
    refreshInterval: null,
  };

  // ---- Chart.js defaults ----
  Chart.defaults.color = "#9ca3af";
  Chart.defaults.borderColor = "rgba(45, 55, 72, 0.6)";
  Chart.defaults.font.family = "'SF Mono','Fira Code',Consolas,monospace";

  // ---- DOM refs ----
  const $ = (sel) => document.querySelector(sel);

  const els = {
    lastUpdated: $("#last-updated"),
    statTotal: $("#stat-total"),
    statDupRate: $("#stat-dup-rate"),
    statTopTactic: $("#stat-top-tactic"),
    filterTactic: $("#filter-tactic"),
    filterDuplicate: $("#filter-duplicate"),
    filterDateFrom: $("#filter-date-from"),
    filterDateTo: $("#filter-date-to"),
    filterSearch: $("#filter-search"),
    btnRefresh: $("#btn-refresh"),
    tbody: $("#alerts-tbody"),
    btnPrev: $("#btn-prev"),
    btnNext: $("#btn-next"),
    pageInfo: $("#page-info"),
    modalOverlay: $("#modal-overlay"),
    modalBody: $("#modal-body"),
    modalClose: $("#modal-close"),
  };

  // ---- Charts ----
  const chartTacticBar = new Chart($("#chart-tactic-bar"), {
    type: "bar",
    data: { labels: [], datasets: [{ label: "Alerts", data: [], backgroundColor: "#00d4aa", borderRadius: 4 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { maxRotation: 45, minRotation: 45, font: { size: 10 } } }, y: { beginAtZero: true, ticks: { precision: 0 } } } },
  });

  const chartDoughnut = new Chart($("#chart-doughnut"), {
    type: "doughnut",
    data: { labels: ["Unique", "Duplicate"], datasets: [{ data: [0, 0], backgroundColor: ["#00d4aa", "#ef4444"], borderWidth: 0 }] },
    options: { responsive: true, maintainAspectRatio: false, cutout: "65%", plugins: { legend: { position: "bottom", labels: { padding: 16, font: { size: 11 } } } } },
  });

  const chartVolumeLine = new Chart($("#chart-volume-line"), {
    type: "line",
    data: { labels: [], datasets: [{ label: "Alerts", data: [], borderColor: "#ffb020", backgroundColor: "rgba(255,176,32,0.08)", fill: true, tension: 0.3, pointRadius: 3, pointBackgroundColor: "#ffb020" }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { font: { size: 10 } } }, y: { beginAtZero: true, ticks: { precision: 0 } } } },
  });

  // ---- Helpers ----
  function fmtDate(iso) {
    if (!iso) return "--";
    try {
      const d = new Date(iso);
      return d.toLocaleString("en-US", { month: "short", day: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
    } catch { return iso; }
  }

  function getConfidenceBadge(score) {
    if (score == null) return '<span class="badge badge-blue">--</span>';
    if (score >= 0.8) return '<span class="badge badge-green">' + (score * 100).toFixed(0) + "%</span>";
    if (score >= 0.5) return '<span class="badge badge-amber">' + (score * 100).toFixed(0) + "%</span>";
    return '<span class="badge badge-red">' + (score * 100).toFixed(0) + "%</span>";
  }

  function buildQueryString(overrides) {
    const params = new URLSearchParams();
    params.set("page", overrides.page != null ? overrides.page : state.page);
    params.set("limit", state.limit);
    const tactic = els.filterTactic.value;
    if (tactic) params.set("tactic", tactic);
    const dup = els.filterDuplicate.value;
    if (dup !== "") params.set("duplicate", dup);
    const df = els.filterDateFrom.value;
    if (df) params.set("date_from", df);
    const dt = els.filterDateTo.value;
    if (dt) params.set("date_to", dt);
    const search = els.filterSearch.value.trim();
    if (search) params.set("search", search);
    return params.toString();
  }

  // ---- API calls ----
  async function fetchStats() {
    try {
      const res = await fetch("/api/stats");
      if (!res.ok) return;
      const data = await res.json();

      // stats cards
      const total = Object.values(data.tactic_distribution || {}).reduce((a, b) => a + b, 0);
      els.statTotal.textContent = total.toLocaleString();
      els.statDupRate.textContent = (data.duplicate_rate * 100).toFixed(1) + "%";
      const sorted = Object.entries(data.tactic_distribution || {}).sort((a, b) => b[1] - a[1]);
      els.statTopTactic.textContent = sorted.length ? sorted[0][0].replace(/-/g, " ") : "--";

      // tactic bar chart
      const labels = sorted.map(([k]) => k.replace(/-/g, " "));
      const values = sorted.map(([, v]) => v);
      chartTacticBar.data.labels = labels;
      chartTacticBar.data.datasets[0].data = values;
      chartTacticBar.update();

      // doughnut
      const totalDup = Object.values(data.tactic_distribution || {}).reduce((a, b) => a + b, 0);
      const dupCount = Math.round(data.duplicate_rate * totalDup);
      chartDoughnut.data.datasets[0].data = [totalDup - dupCount, dupCount];
      chartDoughnut.update();

      // line chart
      const days = Object.keys(data.daily_volume || {}).sort();
      chartVolumeLine.data.labels = days.map((d) => {
        const parts = d.split("-");
        return parts[1] + "/" + parts[2];
      });
      chartVolumeLine.data.datasets[0].data = days.map((d) => data.daily_volume[d]);
      chartVolumeLine.update();

      // populate tactic filter dropdown
      const prevVal = els.filterTactic.value;
      els.filterTactic.innerHTML = '<option value="">All</option>';
      sorted.forEach(([k]) => {
        const opt = document.createElement("option");
        opt.value = k;
        opt.textContent = k.replace(/-/g, " ");
        els.filterTactic.appendChild(opt);
      });
      els.filterTactic.value = prevVal;

      // last updated
      const now = new Date();
      els.lastUpdated.textContent = now.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
      els.lastUpdated.title = now.toISOString();
    } catch (err) {
      console.error("fetchStats error:", err);
    }
  }

  async function fetchAlerts(overrides) {
    try {
      const qs = buildQueryString(overrides || {});
      const res = await fetch("/api/alerts?" + qs);
      if (!res.ok) {
        els.tbody.innerHTML = '<tr><td colspan="5" class="empty-state"><p>Error loading alerts</p></td></tr>';
        return;
      }
      const data = await res.json();
      state.total = data.total;
      state.page = data.page;
      renderTable(data.data);
      renderPagination();
    } catch (err) {
      console.error("fetchAlerts error:", err);
    }
  }

  // ---- Render ----
  function renderTable(alerts) {
    if (!alerts || alerts.length === 0) {
      els.tbody.innerHTML = '<tr><td colspan="5" class="empty-state"><p>No alerts found</p></td></tr>';
      return;
    }
    els.tbody.innerHTML = alerts
      .map(
        (a) => `
      <tr data-id="${a.alert_id}">
        <td style="font-family:var(--font-mono);font-size:0.78rem;white-space:nowrap;">${fmtDate(a.timestamp)}</td>
        <td><span style="font-size:0.78rem;text-transform:capitalize;">${(a.tactic_category || "unknown").replace(/-/g, " ")}</span></td>
        <td>${getConfidenceBadge(a.confidence_score)}</td>
        <td>${a.is_duplicate ? '<span class="pill-dup">DUP</span>' : '<span class="pill-unique">UNQ</span>'}</td>
        <td><span class="text-truncate" title="${escapeHtml(a.raw_text || "")}">${escapeHtml(a.raw_text || "")}</span></td>
      </tr>`
      )
      .join("");

    // click handlers
    els.tbody.querySelectorAll("tr[data-id]").forEach((tr) => {
      tr.addEventListener("click", () => openModal(tr.dataset.id));
    });
  }

  function renderPagination() {
    const totalPages = Math.max(1, Math.ceil(state.total / state.limit));
    els.pageInfo.textContent = "Page " + state.page + " / " + totalPages;
    els.btnPrev.disabled = state.page <= 1;
    els.btnNext.disabled = state.page >= totalPages;
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ---- Modal ----
  async function openModal(alertId) {
    els.modalOverlay.classList.add("active");
    els.modalBody.innerHTML = '<div class="spinner"></div> Loading...';
    try {
      const res = await fetch("/api/alert/" + alertId);
      if (!res.ok) {
        els.modalBody.innerHTML = "<p>Alert not found</p>";
        return;
      }
      const a = await res.json();
      const featHtml = (a.top_features || []).length
        ? '<div class="feature-tags">' +
          a.top_features.map((f) => '<span class="feature-tag" title="weight: ' + f.weight.toFixed(4) + '">' + escapeHtml(f.feature) + "</span>").join("") +
          "</div>"
        : '<span style="color:var(--text-muted)">Model not available</span>';

      els.modalBody.innerHTML = `
        <div class="detail-row"><div class="detail-label">Alert ID</div><div class="detail-value" style="font-family:var(--font-mono);font-size:0.75rem;">${escapeHtml(a.alert_id)}</div></div>
        <div class="detail-row"><div class="detail-label">Timestamp</div><div class="detail-value">${fmtDate(a.timestamp)}</div></div>
        <div class="detail-row"><div class="detail-label">Tactic</div><div class="detail-value" style="text-transform:capitalize;">${(a.tactic_category || "unknown").replace(/-/g, " ")}</div></div>
        <div class="detail-row"><div class="detail-label">Confidence</div><div class="detail-value">${getConfidenceBadge(a.confidence_score)}</div></div>
        <div class="detail-row"><div class="detail-label">Duplicate</div><div class="detail-value">${a.is_duplicate ? '<span class="pill-dup">Yes</span>' : '<span class="pill-unique">No</span>'}</div></div>
        <div class="detail-row"><div class="detail-label">Raw Text</div><div class="detail-value">${escapeHtml(a.raw_text || "")}</div></div>
        <div class="detail-row"><div class="detail-label">Top Features</div><div class="detail-value">${featHtml}</div></div>
      `;
    } catch {
      els.modalBody.innerHTML = "<p>Failed to load alert details</p>";
    }
  }

  function closeModal() {
    els.modalOverlay.classList.remove("active");
  }

  // ---- Events ----
  els.btnRefresh.addEventListener("click", () => {
    state.page = 1;
    fetchAlerts();
  });

  els.btnPrev.addEventListener("click", () => {
    if (state.page <= 1) return;
    state.page--;
    fetchAlerts();
  });

  els.btnNext.addEventListener("click", () => {
    const totalPages = Math.max(1, Math.ceil(state.total / state.limit));
    if (state.page >= totalPages) return;
    state.page++;
    fetchAlerts();
  });

  els.modalClose.addEventListener("click", closeModal);
  els.modalOverlay.addEventListener("click", (e) => {
    if (e.target === els.modalOverlay) closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
  });

  // search on Enter
  els.filterSearch.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      state.page = 1;
      fetchAlerts();
    }
  });

  // ---- Init ----
  fetchStats();
  fetchAlerts();
  state.refreshInterval = setInterval(() => {
    fetchStats();
    fetchAlerts();
  }, 30000);
})();
