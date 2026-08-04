(function () {
  "use strict";

  const grid = document.getElementById("library-grid");
  const statusEl = document.getElementById("library-status");
  const categoryFilter = document.getElementById("filter-category");
  const searchFilter = document.getElementById("filter-search");
  const btnNewSnippet = document.getElementById("btn-new-snippet");
  const btnReseed = document.getElementById("btn-reseed");
  const modal = document.getElementById("snippet-modal");
  const dialog = document.getElementById("snippet-dialog");
  const toast = document.getElementById("toast");

  const LEVELS = ["brief", "standard", "detailed"];
  let snippets = [];
  let editingId = null;

  function setStatus(message) {
    statusEl.textContent = message;
  }

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => toast.classList.remove("show"), 2100);
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function truncate(text, max) {
    const cleaned = String(text || "").replace(/\s+/g, " ").trim();
    if (cleaned.length <= max) return cleaned;
    return cleaned.slice(0, max - 1) + "…";
  }

  function snippetLabel(snippet) {
    const bits = [];
    if (snippet.company) bits.push(snippet.company);
    if (snippet.heading) bits.push(snippet.heading);
    else if (snippet.role) bits.push(snippet.role);
    return bits.join(" — ") || `Snippet #${snippet.id}`;
  }

  function levelContent(snippet, level) {
    const variant = (snippet.variants || []).find((v) => v.detail_level === level);
    return variant ? variant.content : "";
  }

  async function loadSnippets() {
    const params = new URLSearchParams();
    if (categoryFilter.value) params.set("category", categoryFilter.value);
    if (searchFilter.value.trim()) params.set("search", searchFilter.value.trim());
    setStatus("Loading…");
    const resp = await fetch("/api/snippets?" + params.toString());
    if (!resp.ok) throw new Error("failed to load snippets");
    snippets = await resp.json();
    renderGrid();
    setStatus(`${snippets.length} snippet(s).`);
  }

  function renderGrid() {
    grid.innerHTML = "";
    if (!snippets.length) {
      grid.innerHTML = '<p class="empty-row">No snippets match these filters.</p>';
      return;
    }
    snippets.forEach((snippet) => {
      const levels = LEVELS.filter((l) => levelContent(snippet, l));
      const startLevel = levels.includes("standard") ? "standard" : levels[0] || "standard";
      const card = document.createElement("article");
      card.dataset.level = startLevel;
      card.innerHTML = `
        <div class="card-top">
          <span class="badge">${escapeHtml(snippet.category || "")}</span>
          <span>${levels.length} variation${levels.length === 1 ? "" : "s"}</span>
        </div>
        <h3>${escapeHtml(snippetLabel(snippet))}</h3>
        <div class="level-tabs">
          ${LEVELS.map(
            (level) =>
              `<button type="button" data-level="${level}" class="${level === startLevel ? "active" : ""}" ${
                levels.includes(level) ? "" : "disabled"
              }>${level[0].toUpperCase()}${level.slice(1)}</button>`
          ).join("")}
        </div>
        <p class="variant-copy">${escapeHtml(truncate(levelContent(snippet, startLevel), 220))}</p>
        <footer>
          <span class="word-count"></span>
          <div class="row-actions">
            <button type="button" data-action="edit">Edit</button>
            <button type="button" class="danger" data-action="delete">Delete</button>
          </div>
        </footer>
      `;
      function updateWordCount(level) {
        const content = levelContent(snippet, level);
        const words = content.trim() ? content.trim().split(/\s+/).length : 0;
        card.querySelector(".word-count").textContent = `${words} words`;
      }
      updateWordCount(startLevel);
      card.querySelectorAll(".level-tabs button").forEach((btn) => {
        btn.addEventListener("click", () => {
          if (btn.disabled) return;
          const level = btn.getAttribute("data-level");
          card.querySelectorAll(".level-tabs button").forEach((b) => b.classList.remove("active"));
          btn.classList.add("active");
          card.querySelector(".variant-copy").textContent = truncate(levelContent(snippet, level), 220);
          updateWordCount(level);
        });
      });
      card.querySelector('[data-action="edit"]').addEventListener("click", () => openForm(snippet));
      card.querySelector('[data-action="delete"]').addEventListener("click", () => {
        if (!confirm(`Delete snippet "${snippetLabel(snippet)}"?`)) return;
        fetch(`/api/snippets/${snippet.id}`, { method: "DELETE" })
          .then(async (resp) => {
            if (!resp.ok) throw new Error(await resp.text());
            showToast("Snippet deleted.");
            return loadSnippets();
          })
          .catch((err) => setStatus("Error: " + err.message));
      });
      grid.appendChild(card);
    });
  }

  function openForm(snippet) {
    editingId = snippet ? snippet.id : null;
    dialog.innerHTML = `
      <div class="drawer-head">
        <div><small>${snippet ? "EDIT SNIPPET" : "NEW SNIPPET"}</small><h2>${
      snippet ? escapeHtml(snippetLabel(snippet)) : "New snippet"
    }</h2></div>
        <button type="button" id="form-close">&times;</button>
      </div>
      <label>Category
        <select id="form-category">
          ${["bio", "skill", "experience", "part", "requirement"]
            .map(
              (c) =>
                `<option value="${c}" ${(snippet ? snippet.category : "experience") === c ? "selected" : ""}>${c}</option>`
            )
            .join("")}
        </select>
      </label>
      <label>Heading <input id="form-heading" type="text" value="${escapeHtml((snippet && snippet.heading) || "")}"></label>
      <label>Company <input id="form-company" type="text" value="${escapeHtml((snippet && snippet.company) || "")}"></label>
      <label>Role <input id="form-role" type="text" value="${escapeHtml((snippet && snippet.role) || "")}"></label>
      <label>Tags (comma-separated) <input id="form-tags" type="text" value="${escapeHtml(
        ((snippet && snippet.tags) || []).join(", ")
      )}"></label>
      ${LEVELS.map(
        (level) => `
        <div class="level-field">
          <label style="flex:1;margin-top:12px">${level}
            <textarea id="form-${level}" placeholder="${level} content">${escapeHtml(
          snippet ? levelContent(snippet, level) : ""
        )}</textarea>
          </label>
          ${
            snippet && levelContent(snippet, level)
              ? `<button type="button" class="btn-del-level" data-level="${level}">Delete</button>`
              : ""
          }
        </div>`
      ).join("")}
      <div class="form-actions">
        <button type="button" id="form-cancel">Cancel</button>
        <button type="button" class="primary" id="form-save">Save snippet</button>
      </div>
    `;
    modal.classList.add("open");
    dialog.querySelector("#form-close").addEventListener("click", closeForm);
    dialog.querySelector("#form-cancel").addEventListener("click", closeForm);
    dialog.querySelector("#form-save").addEventListener("click", () => {
      saveForm().catch((err) => setStatus("Error: " + err.message));
    });
    dialog.querySelectorAll(".btn-del-level").forEach((btn) => {
      btn.addEventListener("click", () => {
        const level = btn.getAttribute("data-level");
        if (!editingId || !confirm(`Delete the ${level} variant?`)) return;
        fetch(`/api/snippets/${editingId}/variants/${level}`, { method: "DELETE" })
          .then(async (resp) => {
            if (!resp.ok) throw new Error(await resp.text());
            const refreshed = await fetch(`/api/snippets/${editingId}`);
            openForm(await refreshed.json());
            await loadSnippets();
          })
          .catch((err) => setStatus("Error: " + err.message));
      });
    });
  }

  function closeForm() {
    editingId = null;
    modal.classList.remove("open");
    dialog.innerHTML = "";
  }

  async function saveForm() {
    const payload = {
      category: document.getElementById("form-category").value,
      heading: document.getElementById("form-heading").value.trim() || null,
      company: document.getElementById("form-company").value.trim() || null,
      role: document.getElementById("form-role").value.trim() || null,
      tags: document.getElementById("form-tags").value,
      variants: {
        brief: document.getElementById("form-brief").value,
        standard: document.getElementById("form-standard").value,
        detailed: document.getElementById("form-detailed").value,
      },
    };
    const wasEdit = Boolean(editingId);
    const url = wasEdit ? `/api/snippets/${editingId}` : "/api/snippets";
    const resp = await fetch(url, {
      method: wasEdit ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await resp.json();
    if (!resp.ok) throw new Error(body.error || "save failed");
    closeForm();
    await loadSnippets();
    showToast(wasEdit ? "Snippet updated." : `Created snippet #${body.id}.`);
  }

  async function reseed() {
    btnReseed.disabled = true;
    setStatus("Re-seeding database…");
    try {
      const resp = await fetch("/api/seed", { method: "POST" });
      const body = await resp.json();
      if (!resp.ok) throw new Error(body.error || "seed failed");
      const total = Object.values(body).reduce((a, b) => a + Number(b || 0), 0);
      showToast(`Seeded ${total} snippets.`);
      await loadSnippets();
    } catch (err) {
      setStatus("Error: " + err.message);
    } finally {
      btnReseed.disabled = false;
    }
  }

  let searchTimer = null;
  categoryFilter.addEventListener("change", () => {
    loadSnippets().catch((err) => setStatus("Error: " + err.message));
  });
  searchFilter.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      loadSnippets().catch((err) => setStatus("Error: " + err.message));
    }, 250);
  });
  btnNewSnippet.addEventListener("click", () => openForm(null));
  btnReseed.addEventListener("click", () => {
    reseed().catch((err) => setStatus("Error: " + err.message));
  });
  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeForm();
  });

  loadSnippets().catch((err) => setStatus("Error: " + err.message));
})();
