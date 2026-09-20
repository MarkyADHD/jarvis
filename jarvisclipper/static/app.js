(() => {
  const generateBtn = document.getElementById("generate-btn");
  const generatePanel = document.getElementById("generate-panel");
  const generateCancel = document.getElementById("generate-cancel");
  const generateSubmit = document.getElementById("generate-submit");
  const vodSelect = document.getElementById("vod-select");
  const vodUrl = document.getElementById("vod-url");
  const maxClips = document.getElementById("max-clips");
  const optCaptions = document.getElementById("opt-captions");
  const optVertical = document.getElementById("opt-vertical");
  const jobProgress = document.getElementById("job-progress");
  const jobProgressLog = document.getElementById("job-progress-log");
  const foldersEl = document.getElementById("folders");
  const emptyState = document.getElementById("empty-state");
  const previewOverlay = document.getElementById("preview-overlay");
  const previewVideo = document.getElementById("preview-video");
  const previewTitle = document.getElementById("preview-title");
  const previewMeta = document.getElementById("preview-meta");
  const previewClose = document.getElementById("preview-close");

  function fmtDuration(seconds) {
    seconds = Math.round(seconds || 0);
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  function fmtTimestamp(seconds) {
    seconds = Math.round(seconds || 0);
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  async function loadVods() {
    try {
      const r = await fetch("/api/vods?limit=10");
      const data = await r.json();
      vodSelect.innerHTML = "";
      for (const v of (data.vods || [])) {
        const opt = document.createElement("option");
        opt.value = v.id;
        opt.textContent = v.title || v.id;
        vodSelect.appendChild(opt);
      }
      if (!data.vods || !data.vods.length) {
        const opt = document.createElement("option");
        opt.textContent = "No recent VODs found";
        opt.disabled = true;
        vodSelect.appendChild(opt);
      }
    } catch (e) {
      vodSelect.innerHTML = '<option disabled>Couldn\'t load VODs</option>';
    }
  }

  function openGeneratePanel() {
    generatePanel.classList.remove("hidden");
    jobProgress.classList.add("hidden");
    jobProgressLog.innerHTML = "";
    generateSubmit.disabled = false;
    generateSubmit.textContent = "Start";
    loadVods();
  }

  function closeGeneratePanel() {
    generatePanel.classList.add("hidden");
  }

  generateBtn.addEventListener("click", openGeneratePanel);
  generateCancel.addEventListener("click", closeGeneratePanel);

  generateSubmit.addEventListener("click", async () => {
    generateSubmit.disabled = true;
    generateSubmit.textContent = "Starting...";
    jobProgress.classList.remove("hidden");
    jobProgressLog.innerHTML = "<div>Starting...</div>";

    const body = {
      max_clips: parseInt(maxClips.value, 10) || 25,
      captions: optCaptions.checked,
      vertical: optVertical.checked,
    };
    const url = vodUrl.value.trim();
    if (url) {
      body.vod_url = url;
    } else if (vodSelect.value) {
      body.vod_id = vodSelect.value;
    }

    try {
      const r = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (!r.ok || data.error) {
        jobProgressLog.innerHTML = `<div style="color:#ff6b6b">${data.error || "Couldn't start."}</div>`;
        generateSubmit.disabled = false;
        generateSubmit.textContent = "Start";
        return;
      }
      pollJob(data.job_id);
    } catch (e) {
      jobProgressLog.innerHTML = `<div style="color:#ff6b6b">${e}</div>`;
      generateSubmit.disabled = false;
      generateSubmit.textContent = "Start";
    }
  });

  function pollJob(jobId) {
    let shownCount = 0;
    const interval = setInterval(async () => {
      try {
        const r = await fetch(`/api/jobs/${jobId}`);
        const job = await r.json();
        const messages = job.messages || [];
        for (let i = shownCount; i < messages.length; i++) {
          const div = document.createElement("div");
          div.textContent = messages[i];
          jobProgressLog.appendChild(div);
        }
        shownCount = messages.length;
        jobProgressLog.scrollTop = jobProgressLog.scrollHeight;

        if (job.status === "done") {
          clearInterval(interval);
          const div = document.createElement("div");
          div.textContent = `Done -- found ${job.clips.length} clip(s).`;
          jobProgressLog.appendChild(div);
          generateSubmit.textContent = "Done";
          setTimeout(() => { closeGeneratePanel(); loadClips(); }, 1200);
        } else if (job.status === "failed") {
          clearInterval(interval);
          const div = document.createElement("div");
          div.style.color = "#ff6b6b";
          div.textContent = `Failed: ${job.error}`;
          jobProgressLog.appendChild(div);
          generateSubmit.disabled = false;
          generateSubmit.textContent = "Start";
        }
      } catch (e) {
        // transient -- keep polling
      }
    }, 1500);
  }

  function scoreClass(score) {
    if (score === null || score === undefined) return "";
    return score >= 8 ? "hot" : "";
  }

  function clipCard(folder, clip) {
    const card = document.createElement("div");
    card.className = "clip-card";

    const thumb = document.createElement("div");
    thumb.className = "clip-thumb" + (clip.vertical ? " vertical" : "");
    thumb.style.backgroundImage = `url('/api/thumbnail/${encodeURIComponent(folder)}/${encodeURIComponent(clip.file)}')`;

    if (clip.virality_score !== null && clip.virality_score !== undefined) {
      const score = document.createElement("div");
      score.className = "clip-score " + scoreClass(clip.virality_score);
      score.textContent = clip.virality_score + "/10";
      thumb.appendChild(score);
    }

    const duration = document.createElement("div");
    duration.className = "clip-duration";
    duration.textContent = fmtDuration(clip.duration_seconds);
    thumb.appendChild(duration);

    const body = document.createElement("div");
    body.className = "clip-body";
    const title = document.createElement("div");
    title.className = "clip-title";
    title.textContent = clip.title || `Clip at ${fmtTimestamp(clip.timestamp_seconds)}`;
    const transcript = document.createElement("div");
    transcript.className = "clip-transcript";
    transcript.textContent = clip.transcript_snippet || "";
    body.appendChild(title);
    body.appendChild(transcript);

    const actions = document.createElement("div");
    actions.className = "clip-actions";
    const openBtn = document.createElement("button");
    openBtn.textContent = "Open Folder";
    openBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      fetch("/api/open_folder", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder }),
      });
    });
    const deleteBtn = document.createElement("button");
    deleteBtn.className = "danger";
    deleteBtn.textContent = "Delete";
    deleteBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!confirm("Delete this clip?")) return;
      await fetch("/api/delete_clip", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder, file: clip.file }),
      });
      loadClips();
    });
    actions.appendChild(openBtn);
    actions.appendChild(deleteBtn);

    card.appendChild(thumb);
    card.appendChild(body);
    card.appendChild(actions);

    card.addEventListener("click", () => openPreview(folder, clip));

    return card;
  }

  function openPreview(folder, clip) {
    previewVideo.src = `/api/video/${encodeURIComponent(folder)}/${encodeURIComponent(clip.file)}`;
    previewTitle.textContent = clip.title || `Clip at ${fmtTimestamp(clip.timestamp_seconds)}`;
    const scoreText = (clip.virality_score !== null && clip.virality_score !== undefined)
      ? `Score ${clip.virality_score}/10 -- ` : "";
    previewMeta.textContent = `${scoreText}${clip.vod_title || ""}`;
    previewOverlay.classList.remove("hidden");
    previewVideo.play().catch(() => {});
  }

  function closePreview() {
    previewVideo.pause();
    previewVideo.src = "";
    previewOverlay.classList.add("hidden");
  }

  previewClose.addEventListener("click", closePreview);
  previewOverlay.addEventListener("click", (e) => {
    if (e.target === previewOverlay) closePreview();
  });

  async function loadClips() {
    try {
      const r = await fetch("/api/clips");
      const data = await r.json();
      const folders = data.folders || [];
      foldersEl.innerHTML = "";

      if (!folders.length) {
        emptyState.classList.remove("hidden");
        return;
      }
      emptyState.classList.add("hidden");

      for (const f of folders) {
        if (!f.clips || !f.clips.length) continue;
        const group = document.createElement("div");
        group.className = "folder-group";

        const title = document.createElement("div");
        title.className = "folder-title";
        title.textContent = f.clips[0].vod_title || f.folder;
        group.appendChild(title);

        const grid = document.createElement("div");
        grid.className = "clip-grid";
        for (const clip of f.clips) {
          grid.appendChild(clipCard(f.folder, clip));
        }
        group.appendChild(grid);
        foldersEl.appendChild(group);
      }
    } catch (e) {
      // leave whatever was already showing
    }
  }

  loadClips();
})();
