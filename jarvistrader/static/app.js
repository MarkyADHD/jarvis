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
