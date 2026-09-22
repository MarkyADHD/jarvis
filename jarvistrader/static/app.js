function fmtGbp(value) {
  if (value === null || value === undefined) return "—";
  return "£" + Number(value).toFixed(2);
}

function renderLimits(limits) {
  const grid = document.getElementById("limitsGrid");
  grid.innerHTML = "";
  const rows = [
    ["Starting allocation", fmtGbp(limits.starting_capital_allocation_gbp)],
    ["Max single position", fmtGbp(limits.max_single_position_value_gbp)],
    ["Max total exposure", fmtGbp(limits.max_total_market_exposure_gbp)],
    ["Max open positions", limits.max_open_positions],
    ["Max daily loss", fmtGbp(limits.max_daily_realised_loss_gbp)],
    ["Max weekly loss", fmtGbp(limits.max_weekly_realised_loss_gbp)],
    ["Equity floor", fmtGbp(limits.minimum_equity_before_shutdown_gbp)],
    ["Max trades / hour", limits.max_new_trades_per_hour],
    ["Max trades / day", limits.max_new_trades_per_day],
    ["Leverage", limits.leverage_disabled ? "DISABLED" : "enabled"],
    ["CFDs", limits.cfds_disabled ? "DISABLED" : "enabled"],
    ["Short selling", limits.short_selling_disabled ? "DISABLED" : "enabled"],
  ];
  for (const [k, v] of rows) {
    const row = document.createElement("div");
    row.className = "limit-row";
    row.innerHTML = `<span class="k">${k}</span><span class="v">${v}</span>`;
    grid.appendChild(row);
  }
}

function fmtQty(value) {
  if (value === null || value === undefined) return "—";
  return Number(value).toFixed(4).replace(/\.?0+$/, "");
}

async function refreshCredentialStatus() {
  try {
    const r = await fetch("/api/credentials/status");
    const s = await r.json();
    document.getElementById("connectStatusDemo").textContent =
      "Demo: " + (s.demo ? "connected" : "not connected");
    document.getElementById("connectStatusLive").textContent =
      "Live: " + (s.live ? "connected" : "not connected");
    if (s.demo || s.live) {
      loadAccount(s.live ? "live" : "demo");
    }
  } catch (e) {
    // credentials status is best-effort; leave the default labels
  }
}

async function loadAccount(environment) {
  const panel = document.getElementById("accountPanel");
  try {
    const r = await fetch("/api/account?environment=" + encodeURIComponent(environment));
    const snap = await r.json();
    if (!snap || snap.ok === false) {
      return;
    }
    panel.classList.remove("hidden");
    document.getElementById("accountEnvLabel").textContent = environment.toUpperCase();

    const grid = document.getElementById("accountGrid");
    grid.innerHTML = "";
    const stats = [];
    if (snap.summary && snap.summary.ok) {
      const s = snap.summary.data || {};
      for (const [k, v] of Object.entries(s)) {
        if (typeof v === "number") stats.push([k, v]);
      }
    } else if (snap.summary) {
      stats.push(["summary error", snap.summary.error]);
    }
    if (snap.cash && snap.cash.ok) {
      const c = snap.cash.data || {};
      for (const [k, v] of Object.entries(c)) {
        if (typeof v === "number") stats.push([k, v]);
      }
    } else if (snap.cash) {
      stats.push(["cash error", snap.cash.error]);
    }
    for (const [k, v] of stats) {
      const el = document.createElement("div");
      el.className = "stat";
      el.innerHTML = `<div class="k">${k}</div><div class="v">${v}</div>`;
      grid.appendChild(el);
    }

    const posList = document.getElementById("positionsList");
    posList.innerHTML = "";
    if (snap.positions && snap.positions.ok && Array.isArray(snap.positions.data) && snap.positions.data.length) {
      for (const p of snap.positions.data) {
        const row = document.createElement("div");
        row.className = "position-row";
        row.innerHTML = `<span>${p.ticker || "?"}</span><span>qty ${fmtQty(p.quantity)}</span>`;
        posList.appendChild(row);
      }
    } else {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = (snap.positions && snap.positions.ok) ? "No open positions." :
        ((snap.positions && snap.positions.error) || "Couldn't load positions.");
      posList.appendChild(empty);
    }
  } catch (e) {
    // leave the panel hidden/unchanged on a network failure
  }
}

document.getElementById("connectForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const environment = document.getElementById("connectEnv").value;
  const api_key = document.getElementById("connectApiKey").value.trim();
  const api_secret = document.getElementById("connectApiSecret").value.trim();
  const msg = document.getElementById("connectMsg");
  msg.textContent = "Connecting...";
  msg.className = "connect-msg";
  try {
    const r = await fetch("/api/credentials", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ environment, api_key, api_secret }),
    });
    const data = await r.json();
    if (data.ok) {
      msg.textContent = "Connected.";
      msg.className = "connect-msg ok";
      document.getElementById("connectApiKey").value = "";
      document.getElementById("connectApiSecret").value = "";
      refreshCredentialStatus();
    } else {
      msg.textContent = data.error || "Couldn't save credentials.";
      msg.className = "connect-msg error";
    }
  } catch (e) {
    msg.textContent = "Couldn't reach JarvisTrader's own server.";
    msg.className = "connect-msg error";
  }
});

document.getElementById("disconnectBtn").addEventListener("click", async () => {
  const environment = document.getElementById("connectEnv").value;
  const msg = document.getElementById("connectMsg");
  try {
    const r = await fetch("/api/credentials/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ environment }),
    });
    const data = await r.json();
    if (data.ok) {
      msg.textContent = "Disconnected.";
      msg.className = "connect-msg ok";
      refreshCredentialStatus();
    }
  } catch (e) {
    msg.textContent = "Couldn't reach JarvisTrader's own server.";
    msg.className = "connect-msg error";
  }
});

refreshCredentialStatus();
setInterval(refreshCredentialStatus, 15000);

async function refresh() {
  try {
    const r = await fetch("/api/state");
    const s = await r.json();

    document.getElementById("modeBadge").textContent = "MODE: " + s.mode;
    document.getElementById("stateBadge").textContent = "STATUS: " + s.state;

    const modeBadge = document.getElementById("modeBadge");
    const liveBanner = document.getElementById("liveBanner");
    if (s.mode === "LIVE") {
      modeBadge.classList.add("live");
      liveBanner.classList.remove("hidden");
    } else {
      modeBadge.classList.remove("live");
      liveBanner.classList.add("hidden");
    }

    document.getElementById("lastDecision").textContent = s.last_decision || "—";
    document.getElementById("dailyLossRemaining").textContent =
      fmtGbp(s.protected_limits.max_daily_realised_loss_gbp);
    document.getElementById("weeklyLossRemaining").textContent =
      fmtGbp(s.protected_limits.max_weekly_realised_loss_gbp);

    renderLimits(s.protected_limits);
  } catch (e) {
    document.getElementById("stateBadge").textContent = "STATUS: OFFLINE";
  }
}

refresh();
setInterval(refresh, 5000);
