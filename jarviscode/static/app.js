(function () {
  const state = {
    mode: "ask",
    provider: null,
    model: null,
    effort: "medium",
  };

  const chatEl = document.getElementById("chat");
  const treeEl = document.getElementById("file-tree");
  const projectNameEl = document.getElementById("project-name");
  const providerSelect = document.getElementById("provider-select");
  const modelSelect = document.getElementById("model-select");
  const effortSelect = document.getElementById("effort-select");
  const effortWrap = document.getElementById("effort-wrap");

  function addMsg(role, text) {
    const div = document.createElement("div");
    div.className = "msg " + role;
    div.textContent = text;
    chatEl.appendChild(div);
    chatEl.scrollTop = chatEl.scrollHeight;
    return div;
  }

  async function api(path, opts) {
    const r = await fetch(path, opts);
    return r.json();
  }

  async function refreshState() {
    const s = await api("/api/state");
    providerSelect.innerHTML = "";
    s.providers.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.label + (p.free ? "" : " (paid)");
      if (p.id === s.active_provider) opt.selected = true;
      providerSelect.appendChild(opt);
    });
    state.provider = s.active_provider;
    state.effort = s.active_effort || "medium";
    populateModels(s.models, s.active_model);
    populateEffort(s.effort_levels, s.active_effort);

    if (s.project_root) {
      projectNameEl.textContent = s.project_root;
      loadTree();
    } else {
      projectNameEl.textContent = "No project open";
      treeEl.innerHTML = "";
    }
  }

  function populateModels(models, active) {
    modelSelect.innerHTML = "";
    (models || ["default"]).forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      if (m === active) opt.selected = true;
      modelSelect.appendChild(opt);
    });
  }

  function populateEffort(levels, active) {
    if (!levels || !levels.length) {
      effortWrap.classList.add("hidden");
      return;
    }
    effortWrap.classList.remove("hidden");
    effortSelect.innerHTML = "";
    levels.forEach((lvl) => {
      const opt = document.createElement("option");
      opt.value = lvl;
      opt.textContent = lvl[0].toUpperCase() + lvl.slice(1);
      if (lvl === active) opt.selected = true;
      effortSelect.appendChild(opt);
    });
  }

  async function loadTree() {
    const s = await api("/api/tree");
    treeEl.innerHTML = "";
    (s.entries || []).forEach((e) => {
      const row = document.createElement("div");
      row.className = "tree-entry " + e.type;
      const depth = (e.path.match(/\//g) || []).length;
      row.style.paddingLeft = 8 + depth * 14 + "px";
      row.textContent = (e.type === "dir" ? "▸ " : "") + e.path.split("/").pop();
      treeEl.appendChild(row);
    });
  }

  document.getElementById("open-folder-btn").addEventListener("click", async () => {
    const picked = await api("/api/browse_folder");
    if (!picked.path) return;
    const res = await api("/api/open_folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: picked.path }),
    });
    if (res.ok) {
      addMsg("system", "Opened project: " + res.project_root);
      refreshState();
    } else {
      addMsg("error", "Couldn't open that folder: " + (res.error || "unknown error"));
    }
  });

  document.querySelectorAll(".mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".mode-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.mode = btn.dataset.mode;
    });
  });

  async function applyProviderChange() {
    await api("/api/set_provider", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: providerSelect.value,
        model: modelSelect.value,
        effort: effortSelect.value || "medium",
      }),
    });
    const m = await api("/api/models?provider=" + encodeURIComponent(providerSelect.value));
    populateModels(m.models, null);
    populateEffort(m.effort_levels, "medium");
  }

  providerSelect.addEventListener("change", applyProviderChange);
  modelSelect.addEventListener("change", applyProviderChange);
  effortSelect.addEventListener("change", applyProviderChange);

  async function send() {
    const input = document.getElementById("message-input");
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    addMsg("user", text);
    const thinking = addMsg("assistant", "Thinking...");

    try {
      const res = await api("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, mode: state.mode }),
      });
      thinking.remove();
      if (res.ok) {
        addMsg("assistant", res.reply || "(no reply)");
      } else {
        addMsg("error", res.error || "Something went wrong.");
      }
    } catch (e) {
      thinking.remove();
      addMsg("error", String(e));
    }
  }

  document.getElementById("send-btn").addEventListener("click", send);
  document.getElementById("message-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });

  const diffPanel = document.getElementById("diff-panel");
  document.getElementById("diff-btn").addEventListener("click", async () => {
    const d = await api("/api/diff");
    if (!d.available) {
      addMsg("system", "No git repo open -- diff view needs the project to be a git repository.");
      return;
    }
    document.getElementById("diff-content").textContent = d.diff || "(no changes)";
    diffPanel.classList.remove("hidden");
  });
  document.getElementById("close-diff-btn").addEventListener("click", () => {
    diffPanel.classList.add("hidden");
  });
  document.getElementById("rollback-btn").addEventListener("click", async () => {
    if (!confirm("Roll back ALL uncommitted changes in this project? This cannot be undone.")) return;
    const res = await api("/api/rollback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (res.ok) {
      addMsg("system", "Rolled back all uncommitted changes.");
      diffPanel.classList.add("hidden");
    } else {
      addMsg("error", res.error || "Rollback failed.");
    }
  });

  refreshState();
})();
