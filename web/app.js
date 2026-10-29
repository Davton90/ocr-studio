/* OCR Studio - frontend controller */

const $ = (sel) => document.querySelector(sel);

const state = {
  files: [],
  activeId: null,
  pageIdx: 0,
  activeLine: null,
  hoverLine: null,
  variant: "tiny",
  useCls: false,
  busy: false,
};

const els = {
  queue: $("#queue"),
  queueCount: $("#queueCount"),
  dropzone: $("#dropzone"),
  fileInput: $("#fileInput"),
  clearAll: $("#clearAll"),
  sampleBtn: $("#sampleBtn"),
  stage: $("#stage"),
  stageImg: $("#stageImg"),
  overlay: $("#overlay"),
  viewerBody: $("#viewerBody"),
  emptyState: $("#emptyState"),
  busy: $("#busy"),
  busyText: $("#busyText"),
  fileTitle: $("#fileTitle"),
  pager: $("#pager"),
  prevPage: $("#prevPage"),
  nextPage: $("#nextPage"),
  pageLabel: $("#pageLabel"),
  stats: $("#stats"),
  textOut: $("#textOut"),
  lineList: $("#lineList"),
  copyBtn: $("#copyBtn"),
  dlBtn: $("#dlBtn"),
  dlMenu: $("#dlMenu"),
  variant: $("#variant"),
  useCls: $("#useCls"),
  status: $("#status"),
  statusText: $("#statusText"),
  toast: $("#toast"),
};

/* ------------------------------------------------------------------ utils */
let uid = 0;
const nextId = () => `f${++uid}`;

function toast(msg, ms = 2200) {
  els.toast.textContent = msg;
  els.toast.hidden = false;
  requestAnimationFrame(() => els.toast.classList.add("show"));
  clearTimeout(toast._t);
  toast._t = setTimeout(() => {
    els.toast.classList.remove("show");
    setTimeout(() => (els.toast.hidden = true), 220);
  }, ms);
}

function fmtBytes(n) {
  if (!n) return "—";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n < 10 && i > 0 ? 1 : 0)} ${u[i]}`;
}

function setBusy(on, text = "Memproses…") {
  state.busy = on;
  els.busy.hidden = !on;
  els.busyText.textContent = text;
}

const currentFile = () => state.files.find((f) => f.id === state.activeId) || null;
const currentPage = () => {
  const f = currentFile();
  return f && f.pages.length ? f.pages[state.pageIdx] || null : null;
};

/* ------------------------------------------------------------------ status */
async function refreshStatus() {
  try {
    const r = await fetch("/api/status");
    const s = await r.json();
    els.variant.value = s.variant;
    els.useCls.checked = s.use_cls;
    state.variant = s.variant;
    state.useCls = s.use_cls;

    if (s.state === "ready") {
      els.status.className = "status ready";
      els.statusText.textContent =
        `siap · ${s.variants[s.variant].label} · ${s.host.cpu} core · v${s.engine.rapidocr}`;
    } else if (s.state === "loading") {
      els.status.className = "status busy";
      els.statusText.textContent = "memuat model…";
    } else if (s.state === "error") {
      els.status.className = "status error";
      els.statusText.textContent = s.error || "gagal memuat model";
    } else {
      els.status.className = "status";
      els.statusText.textContent = "model belum dimuat";
    }
  } catch {
    els.status.className = "status error";
    els.statusText.textContent = "server tidak merespons";
  }
}

/* ------------------------------------------------------------------- queue */
function addFiles(fileList) {
  const incoming = Array.from(fileList).filter((f) => {
    const ok = f.type.startsWith("image/") || f.type === "application/pdf" ||
      /\.(png|jpe?g|webp|bmp|tiff?|gif|pdf)$/i.test(f.name);
    if (!ok) toast(`"${f.name}" bukan gambar/PDF`);
    return ok;
  });
  if (!incoming.length) return;

  for (const f of incoming) {
    const entry = {
      id: nextId(),
      file: f,
      name: f.name || "tempelan.png",
      kind: f.type === "application/pdf" || /\.pdf$/i.test(f.name) ? "pdf" : "image",
      size: f.size,
      status: "pending",
      pages: [],
      error: null,
    };
    state.files.unshift(entry);
    processFile(entry);
  }
  renderQueue();
  if (!state.activeId) selectFile(state.files[0].id);
}

async function processFile(entry) {
  entry.status = "running";
  renderQueue();
  const active = entry.id === state.activeId;
  if (active || !state.activeId) setBusy(true, `Membaca ${entry.name}…`);

  const fd = new FormData();
  fd.append("file", entry.file, entry.name);
  try {
    const r = await fetch("/api/ocr", { method: "POST", body: fd });
    if (!r.ok) {
      const detail = await r.json().catch(() => ({}));
      throw new Error(detail.detail || `HTTP ${r.status}`);
    }
    const data = await r.json();
    entry.pages = data.pages;
    entry.kind = data.kind;
    entry.status = "done";
    if (!state.activeId || entry.id === state.activeId) {
      state.activeId = entry.id;
      state.pageIdx = 0;
      renderAll();
    }
  } catch (err) {
    entry.status = "error";
    entry.error = err.message;
    toast(`Gagal: ${entry.name} — ${err.message}`, 4000);
  } finally {
    setBusy(false);
    renderQueue();
    if (state.activeId === entry.id) renderViewer();
  }
}

function selectFile(id) {
  state.activeId = id;
  state.pageIdx = 0;
  state.activeLine = null;
  renderAll();
}

function renderQueue() {
  els.queueCount.textContent = state.files.length;
  if (!state.files.length) {
    els.queue.innerHTML = '<li class="queue-empty">Belum ada berkas.</li>';
    return;
  }
  els.queue.innerHTML = "";
  for (const f of state.files) {
    const li = document.createElement("li");
    li.className = "queue-item" + (f.id === state.activeId ? " active" : "");

    const icon = document.createElement("div");
    icon.className = "qi-icon";
    if (f.pages.length && f.pages[0].image) {
      const img = document.createElement("img");
      img.src = f.pages[0].image;
      img.alt = "";
      icon.appendChild(img);
    } else {
      icon.textContent = f.kind === "pdf" ? "PDF" : "IMG";
    }

    const body = document.createElement("div");
    body.className = "qi-body";
    const name = document.createElement("div");
    name.className = "qi-name";
    name.textContent = f.name;
    const meta = document.createElement("div");
    meta.className = "qi-meta";
    meta.textContent = f.status === "done"
      ? `${f.pages.length} halaman · ${fmtBytes(f.size)}`
      : fmtBytes(f.size);
    body.append(name, meta);

    const st = document.createElement("div");
    st.className = "qi-state " + (f.status === "done" ? "ok" : f.status === "error" ? "err" : f.status === "running" ? "run" : "");
    st.textContent = f.status === "done" ? "✓" : f.status === "error" ? "!" : f.status === "running" ? "…" : "•";

    li.append(icon, body, st);
    li.onclick = () => selectFile(f.id);
    els.queue.appendChild(li);
  }
}

/* ------------------------------------------------------------------ viewer */
function renderAll() {
  renderQueue();
  renderViewer();
  renderResults();
}

function renderViewer() {
  const f = currentFile();
  const page = currentPage();

  if (!f || !page) {
    els.emptyState.hidden = false;
    els.stage.hidden = true;
    els.fileTitle.textContent = f ? f.name : "Belum ada berkas dipilih";
    els.pager.hidden = true;
    els.stats.innerHTML = '<span class="chip muted">siap</span>';
    return;
  }

  els.emptyState.hidden = true;
  els.stage.hidden = false;
  els.fileTitle.textContent = f.name;

  const multi = f.pages.length > 1;
  els.pager.hidden = !multi;
  els.pageLabel.textContent = `${state.pageIdx + 1} / ${f.pages.length}`;
  els.prevPage.disabled = state.pageIdx === 0;
  els.nextPage.disabled = state.pageIdx >= f.pages.length - 1;

  if (els.stageImg.src !== page.image) {
    els.stageImg.src = page.image;
  }
  els.stageImg.onload = () => drawOverlay();

  const avg = page.lines.length
    ? page.lines.reduce((a, l) => a + l.score, 0) / page.lines.length
    : 0;
  const stages = Object.entries(page.stages_ms || {})
    .map(([k, v]) => `${k} ${v}ms`).join(" · ");

  els.stats.innerHTML = `
    <span class="chip"><b>${page.elapsed_ms}</b> ms</span>
    <span class="chip">${page.lines.length} baris</span>
    <span class="chip">akurasi ${(avg * 100).toFixed(1)}%</span>
    <span class="chip">${page.width}×${page.height}</span>
    ${stages ? `<span class="chip muted">${stages}</span>` : ""}
  `;
}

/* --------------------------------------------------------------- overlay */
function fitStage() {
  const img = els.stageImg;
  if (!img.naturalWidth) return;
  const pad = 28;
  const availW = Math.max(els.viewerBody.clientWidth - pad, 80);
  const availH = Math.max(els.viewerBody.clientHeight - pad, 80);
  const scale = Math.min(availW / img.naturalWidth, availH / img.naturalHeight, 1.6);
  img.style.width = `${Math.round(img.naturalWidth * scale)}px`;
  img.style.height = `${Math.round(img.naturalHeight * scale)}px`;
}

function drawOverlay() {
  const page = currentPage();
  const img = els.stageImg;
  const canvas = els.overlay;
  if (!page || !img.clientWidth) return;

  fitStage();

  const dpr = window.devicePixelRatio || 1;
  const w = img.clientWidth;
  const h = img.clientHeight;
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);

  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  if (!page.boxes_ready && !page.lines.length) return;

  const sx = w / page.width;
  const sy = h / page.height;

  page.lines.forEach((ln, i) => {
    if (!ln.box) return;
    const isActive = state.activeLine === i;
    const isHover = state.hoverLine === i;
    const score = ln.score;
    const base = score >= 0.9 ? "74,222,128" : score >= 0.7 ? "251,191,36" : "248,113,113";

    ctx.beginPath();
    ln.box.forEach(([x, y], k) => {
      const px = x * sx;
      const py = y * sy;
      if (k === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.closePath();

    if (isActive || isHover) {
      ctx.fillStyle = `rgba(${base},0.22)`;
      ctx.fill();
      ctx.strokeStyle = `rgba(${base},0.95)`;
      ctx.lineWidth = 2;
    } else {
      ctx.fillStyle = `rgba(${base},0.06)`;
      ctx.fill();
      ctx.strokeStyle = `rgba(${base},0.55)`;
      ctx.lineWidth = 1;
    }
    ctx.stroke();
  });
}

function hitTest(clientX, clientY) {
  const page = currentPage();
  if (!page) return null;
  const rect = els.overlay.getBoundingClientRect();
  const x = (clientX - rect.left) / rect.width * page.width;
  const y = (clientY - rect.top) / rect.height * page.height;

  for (let i = page.lines.length - 1; i >= 0; i--) {
    const box = page.lines[i].box;
    if (!box) continue;
    let inside = false;
    for (let a = 0, b = box.length - 1; a < box.length; b = a++) {
      const [xi, yi] = box[a];
      const [xj, yj] = box[b];
      if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
    }
    if (inside) return i;
  }
  return null;
}

let tipEl = null;
function showTip(clientX, clientY, idx) {
  const page = currentPage();
  if (!page) return;
  if (!tipEl) {
    tipEl = document.createElement("div");
    tipEl.className = "box-tip";
    els.stage.appendChild(tipEl);
  }
  if (idx === null) { tipEl.style.display = "none"; return; }
  const ln = page.lines[idx];
  tipEl.textContent = `${ln.text}  ·  ${(ln.score * 100).toFixed(1)}%`;
  const rect = els.stage.getBoundingClientRect();
  tipEl.style.display = "block";
  const x = Math.min(clientX - rect.left + 12, rect.width - tipEl.offsetWidth - 4);
  const y = Math.max(clientY - rect.top - tipEl.offsetHeight - 8, 4);
  tipEl.style.left = `${Math.max(4, x)}px`;
  tipEl.style.top = `${y}px`;
}

/* --------------------------------------------------------------- results */
function renderResults() {
  const page = currentPage();
  const f = currentFile();
  if (!page || !f) {
    els.textOut.value = "";
    els.lineList.innerHTML = '<li class="queue-empty">Belum ada hasil.</li>';
    return;
  }

  els.textOut.value = page.text || "";
  els.lineList.innerHTML = "";
  if (!page.lines.length) {
    els.lineList.innerHTML = '<li class="queue-empty">Tidak ada teks terdeteksi.</li>';
    return;
  }

  page.lines.forEach((ln, i) => {
    const li = document.createElement("li");
    li.className = "line" + (state.activeLine === i ? " active" : "");
    const cls = ln.score >= 0.9 ? "hi" : ln.score >= 0.7 ? "mid" : "lo";
    li.innerHTML = `
      <span class="ln-idx">${String(i + 1).padStart(2, "0")}</span>
      <span class="ln-text"></span>
      <span class="ln-score ${cls}">${(ln.score * 100).toFixed(0)}</span>`;
    li.querySelector(".ln-text").textContent = ln.text;
    li.onclick = () => {
      state.activeLine = state.activeLine === i ? null : i;
      renderResults();
      drawOverlay();
    };
    els.lineList.appendChild(li);
  });
}

/* ---------------------------------------------------------------- exports */
function exportPayload() {
  const f = currentFile();
  if (!f || !f.pages.length) return null;
  return f;
}

function buildExport(fmt) {
  const f = exportPayload();
  if (!f) return null;
  const base = f.name.replace(/\.[^.]+$/, "") || "ocr";
  const multi = f.pages.length > 1;

  if (fmt === "txt") {
    const body = f.pages.map((p) => (multi ? `=== Halaman ${p.index} ===\n${p.text}` : p.text)).join("\n\n");
    return { name: `${base}.txt`, mime: "text/plain;charset=utf-8", body };
  }
  if (fmt === "md") {
    const body = `# ${f.name}\n\n` + f.pages.map((p) => `## Halaman ${p.index}\n\n${p.text}`).join("\n\n");
    return { name: `${base}.md`, mime: "text/markdown;charset=utf-8", body };
  }
  if (fmt === "json") {
    const body = JSON.stringify({
      name: f.name,
      kind: f.kind,
      pages: f.pages.map((p) => ({
        index: p.index, width: p.width, height: p.height,
        elapsed_ms: p.elapsed_ms, text: p.text, lines: p.lines,
      })),
    }, null, 2);
    return { name: `${base}.json`, mime: "application/json;charset=utf-8", body };
  }
  if (fmt === "csv") {
    const esc = (s) => `"${String(s).replace(/"/g, '""')}"`;
    const rows = [["page", "line", "score", "text", "x0", "y0", "x1", "y1"]];
    for (const p of f.pages) {
      p.lines.forEach((ln, i) => {
        const b = ln.box || [];
        const xs = b.map((pt) => pt[0]);
        const ys = b.map((pt) => pt[1]);
        rows.push([p.index, i + 1, ln.score, ln.text,
          Math.min(...xs).toFixed(0), Math.min(...ys).toFixed(0),
          Math.max(...xs).toFixed(0), Math.max(...ys).toFixed(0)]);
      });
    }
    const body = rows.map((r) => r.map(esc).join(",")).join("\r\n");
    return { name: `${base}.csv`, mime: "text/csv;charset=utf-8", body: "\uFEFF" + body };
  }
  return null;
}

function download(fmt) {
  const out = buildExport(fmt);
  if (!out) { toast("Belum ada hasil untuk diunduh"); return; }
  const blob = new Blob([out.body], { type: out.mime });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = out.name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  toast(`Diunduh: ${out.name}`);
}

/* ----------------------------------------------------------------- events */
function bind() {
  els.dropzone.onclick = () => els.fileInput.click();
  els.dropzone.onkeydown = (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); els.fileInput.click(); }
  };
  els.fileInput.onchange = (e) => {
    addFiles(e.target.files);
    e.target.value = "";
  };

  let dragDepth = 0;
  window.addEventListener("dragenter", (e) => {
    e.preventDefault();
    dragDepth++;
    document.body.classList.add("dragging");
  });
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("dragleave", (e) => {
    e.preventDefault();
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) document.body.classList.remove("dragging");
  });
  window.addEventListener("drop", (e) => {
    e.preventDefault();
    dragDepth = 0;
    document.body.classList.remove("dragging");
    if (e.dataTransfer?.files?.length) addFiles(e.dataTransfer.files);
  });

  document.addEventListener("paste", (e) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    const files = [];
    for (const it of items) {
      if (it.kind === "file") {
        const f = it.getAsFile();
        if (f) files.push(f);
      }
    }
    if (files.length) {
      e.preventDefault();
      addFiles(files);
    }
  });

  els.clearAll.onclick = () => {
    state.files = [];
    state.activeId = null;
    state.pageIdx = 0;
    state.activeLine = null;
    renderAll();
  };

  els.sampleBtn.onclick = async () => {
    try {
      const r = await fetch("/api/sample");
      const blob = await r.blob();
      addFiles([new File([blob], "contoh-ocr.png", { type: "image/png" })]);
    } catch {
      toast("Gagal memuat contoh");
    }
  };

  els.prevPage.onclick = () => {
    if (state.pageIdx > 0) { state.pageIdx--; state.activeLine = null; renderViewer(); renderResults(); }
  };
  els.nextPage.onclick = () => {
    const f = currentFile();
    if (f && state.pageIdx < f.pages.length - 1) { state.pageIdx++; state.activeLine = null; renderViewer(); renderResults(); }
  };

  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT") return;
    if (e.key === "ArrowLeft") els.prevPage.click();
    if (e.key === "ArrowRight") els.nextPage.click();
  });

  els.overlay.addEventListener("mousemove", (e) => {
    const idx = hitTest(e.clientX, e.clientY);
    if (idx !== state.hoverLine) {
      state.hoverLine = idx;
      drawOverlay();
    }
    showTip(e.clientX, e.clientY, idx);
  });
  els.overlay.addEventListener("mouseleave", () => {
    state.hoverLine = null;
    showTip(0, 0, null);
    drawOverlay();
  });
  els.overlay.addEventListener("click", (e) => {
    const idx = hitTest(e.clientX, e.clientY);
    if (idx === null) return;
    state.activeLine = state.activeLine === idx ? null : idx;
    renderResults();
    drawOverlay();
    const row = els.lineList.children[idx];
    if (row) row.scrollIntoView({ block: "nearest", behavior: "smooth" });
  });

  window.addEventListener("resize", () => drawOverlay());

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.onclick = () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      const name = tab.dataset.tab;
      $("#tabText").hidden = name !== "text";
      $("#tabLines").hidden = name !== "lines";
    };
  });

  els.copyBtn.onclick = async () => {
    const page = currentPage();
    if (!page || !page.text) { toast("Belum ada teks"); return; }
    try {
      await navigator.clipboard.writeText(page.text);
      toast("Teks disalin ke clipboard");
    } catch {
      els.textOut.select();
      document.execCommand("copy");
      toast("Teks disalin");
    }
  };

  els.dlBtn.onclick = (e) => {
    e.stopPropagation();
    els.dlMenu.hidden = !els.dlMenu.hidden;
  };
  els.dlMenu.querySelectorAll("button").forEach((b) => {
    b.onclick = () => { download(b.dataset.fmt); els.dlMenu.hidden = true; };
  });
  document.addEventListener("click", () => { els.dlMenu.hidden = true; });

  els.variant.onchange = () => applyConfig({ variant: els.variant.value });
  els.useCls.onchange = () => applyConfig({ use_cls: els.useCls.checked });
}

async function applyConfig(payload) {
  setBusy(true, "Memuat model… (unduhan pertama bisa lama)");
  els.status.className = "status busy";
  els.statusText.textContent = "memuat model…";
  try {
    const r = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await r.json();
    if (!data.ok) throw new Error(data.error || "gagal");
    toast(`Model ${data.variant} siap (${Math.round(data.loaded_ms)} ms)`);
  } catch (err) {
    toast(`Gagal ganti model: ${err.message}`, 4000);
  } finally {
    setBusy(false);
    refreshStatus();
  }
}

/* ------------------------------------------------------------------- init */
bind();
refreshStatus();
setInterval(refreshStatus, 15000);
