(function () {
  "use strict";

  const STORAGE_KEY = "cvbuilder.draft.v1";

  const snippetList = document.getElementById("snippet-list");
  const snippetForm = document.getElementById("snippet-form");
  const draftList = document.getElementById("draft-list");
  const statusEl = document.getElementById("builder-status");
  const categoryFilter = document.getElementById("filter-category");
  const searchFilter = document.getElementById("filter-search");
  const defaultLevel = document.getElementById("default-level");
  const variantName = document.getElementById("variant-name");
  const draftSelect = document.getElementById("draft-select");
  const btnCompose = document.getElementById("btn-compose");
  const btnReseed = document.getElementById("btn-reseed");
  const btnNewSnippet = document.getElementById("btn-new-snippet");
  const btnDraftLoad = document.getElementById("btn-draft-load");
  const btnDraftSave = document.getElementById("btn-draft-save");
  const btnDraftDelete = document.getElementById("btn-draft-delete");
  const btnMatch = document.getElementById("btn-match");
  const btnAddTop = document.getElementById("btn-add-top");
  const btnClearMatch = document.getElementById("btn-clear-match");
  const postingText = document.getElementById("posting-text");
  const matchLimit = document.getElementById("match-limit");
  const matchSummary = document.getElementById("match-summary");
  const previewPane = document.getElementById("preview-pane");
  const previewFrame = document.getElementById("preview-frame");

  /** @type {Array<any>} */
  let snippets = [];
  /** @type {Array<{snippet_id:number, detail_level:string, section:?string, label:string, preview:string}>} */
  let draft = [];
  /** @type {Map<number, {score:number, matched_terms:string[]}>} */
  let matchMeta = new Map();
  /** @type {number[]} */
  let matchOrder = [];
  /** @type {number|null} */
  let editingId = null;

  /**
   * Update the status line.
   * @param {string} message
   */
  function setStatus(message) {
    statusEl.textContent = message;
  }

  /**
   * Escape text for safe HTML insertion.
   * @param {string} value
   * @returns {string}
   */
  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /**
   * Pick the best available variant for a preferred detail level.
   * @param {any} snippet
   * @param {string} preferred
   * @returns {any|null}
   */
  function pickVariant(snippet, preferred) {
    const variants = snippet.variants || [];
    const exact = variants.find((v) => v.detail_level === preferred);
    if (exact) return exact;
    const order = ["standard", "detailed", "brief"];
    for (const level of order) {
      const found = variants.find((v) => v.detail_level === level);
      if (found) return found;
    }
    return variants[0] || null;
  }

  /**
   * Truncate preview text for cards.
   * @param {string} text
   * @param {number} max
   * @returns {string}
   */
  function truncate(text, max) {
    const cleaned = String(text || "").replace(/\s+/g, " ").trim();
    if (cleaned.length <= max) return cleaned;
    return cleaned.slice(0, max - 1) + "…";
  }

  /**
   * Build a display label for a snippet.
   * @param {any} snippet
   * @returns {string}
   */
  function snippetLabel(snippet) {
    const bits = [];
    if (snippet.company) bits.push(snippet.company);
    if (snippet.heading) bits.push(snippet.heading);
    else if (snippet.role) bits.push(snippet.role);
    return bits.join(" — ") || `Snippet #${snippet.id}`;
  }

  /**
   * Persist the current draft to localStorage.
   */
  function autosaveLocal() {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          name: variantName.value,
          draft: draft,
        })
      );
    } catch (_err) {
      /* ignore quota / private-mode failures */
    }
  }

  /**
   * Restore a draft from localStorage if present.
   */
  function restoreLocal() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (parsed && Array.isArray(parsed.draft)) {
        draft = parsed.draft;
        if (parsed.name) variantName.value = parsed.name;
      }
    } catch (_err) {
      /* ignore corrupt storage */
    }
  }

  /**
   * Load snippets from the API using current filters.
   * @returns {Promise<void>}
   */
  async function loadSnippets() {
    const params = new URLSearchParams();
    if (categoryFilter.value) params.set("category", categoryFilter.value);
    if (searchFilter.value.trim()) params.set("search", searchFilter.value.trim());
    setStatus("Loading snippets…");
    const resp = await fetch("/api/snippets?" + params.toString());
    if (!resp.ok) throw new Error("failed to load snippets: " + (await resp.text()));
    snippets = await resp.json();
    renderLibrary();
    setStatus(`Loaded ${snippets.length} snippets.`);
  }

  /**
   * Refresh the saved-drafts dropdown.
   * @returns {Promise<void>}
   */
  async function loadDraftOptions() {
    const resp = await fetch("/api/drafts");
    if (!resp.ok) throw new Error("failed to load drafts");
    const drafts = await resp.json();
    const current = draftSelect.value;
    draftSelect.innerHTML = '<option value="">— select —</option>';
    drafts.forEach((item) => {
      const opt = document.createElement("option");
      opt.value = item.name;
      opt.textContent = item.name;
      draftSelect.appendChild(opt);
    });
    if (current) draftSelect.value = current;
  }

  /**
   * Content for one detail level on a snippet.
   * @param {any} snippet
   * @param {string} level
   * @returns {string}
   */
  function levelContent(snippet, level) {
    const variant = (snippet.variants || []).find((v) => v.detail_level === level);
    return variant ? variant.content : "";
  }

  /**
   * Show the create/edit snippet form.
   * @param {any|null} snippet
   */
  function openSnippetForm(snippet) {
    editingId = snippet ? snippet.id : null;
    const levels = ["brief", "standard", "detailed"];
    snippetForm.classList.remove("hidden");
    snippetForm.innerHTML = `
      <h3>${snippet ? "Edit snippet" : "New snippet"}</h3>
      <label>Category
        <select id="form-category">
          ${["bio", "skill", "experience", "part", "requirement"]
            .map(
              (c) =>
                `<option value="${c}" ${
                  (snippet ? snippet.category : "experience") === c ? "selected" : ""
                }>${c}</option>`
            )
            .join("")}
        </select>
      </label>
      <label>Heading <input id="form-heading" type="text" value="${escapeHtml(
        (snippet && snippet.heading) || ""
      )}"></label>
      <label>Company <input id="form-company" type="text" value="${escapeHtml(
        (snippet && snippet.company) || ""
      )}"></label>
      <label>Role <input id="form-role" type="text" value="${escapeHtml(
        (snippet && snippet.role) || ""
      )}"></label>
      <label>Tags (comma-separated) <input id="form-tags" type="text" value="${escapeHtml(
        ((snippet && snippet.tags) || []).join(", ")
      )}"></label>
      ${levels
        .map(
          (level) => `
        <label>${level}
          <textarea id="form-${level}" placeholder="${level} content">${escapeHtml(
            snippet ? levelContent(snippet, level) : ""
          )}</textarea>
        </label>
        ${
          snippet && levelContent(snippet, level)
            ? `<button type="button" class="btn-del-level" data-level="${level}">Delete ${level} variant</button>`
            : ""
        }
      `
        )
        .join("")}
      <div class="form-actions">
        <button type="button" id="form-save">Save snippet</button>
        <button type="button" id="form-cancel">Cancel</button>
      </div>
    `;
    snippetForm.querySelector("#form-save").addEventListener("click", () => {
      saveSnippetForm().catch((err) => setStatus("Error: " + err.message));
    });
    snippetForm.querySelector("#form-cancel").addEventListener("click", closeSnippetForm);
    snippetForm.querySelectorAll(".btn-del-level").forEach((btn) => {
      btn.addEventListener("click", () => {
        const level = btn.getAttribute("data-level");
        if (!editingId || !level) return;
        if (!confirm(`Delete the ${level} variant?`)) return;
        fetch(`/api/snippets/${editingId}/variants/${level}`, { method: "DELETE" })
          .then(async (resp) => {
            if (!resp.ok) throw new Error(await resp.text());
            setStatus(`Deleted ${level} variant.`);
            const refreshed = await fetch(`/api/snippets/${editingId}`);
            const body = await refreshed.json();
            openSnippetForm(body);
            await loadSnippets();
          })
          .catch((err) => setStatus("Error: " + err.message));
      });
    });
    snippetForm.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  /**
   * Hide the snippet form.
   */
  function closeSnippetForm() {
    editingId = null;
    snippetForm.classList.add("hidden");
    snippetForm.innerHTML = "";
  }

  /**
   * Persist the snippet form via create or update.
   * @returns {Promise<void>}
   */
  async function saveSnippetForm() {
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
    const method = wasEdit ? "PUT" : "POST";
    const resp = await fetch(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await resp.json();
    if (!resp.ok) throw new Error(body.error || "save failed");
    closeSnippetForm();
    await loadSnippets();
    setStatus(wasEdit ? "Snippet updated." : `Created snippet #${body.id}.`);
  }

  /**
   * Ordered snippet list honouring match ranking when present.
   * @returns {Array<any>}
   */
  function orderedSnippets() {
    if (!matchOrder.length) return snippets;
    const byId = new Map(snippets.map((s) => [s.id, s]));
    const ranked = matchOrder.map((id) => byId.get(id)).filter(Boolean);
    const rankedIds = new Set(matchOrder);
    const rest = snippets.filter((s) => !rankedIds.has(s.id));
    return ranked.concat(rest);
  }

  /**
   * Render the left-pane snippet library.
   */
  function renderLibrary() {
    snippetList.innerHTML = "";
    const items = orderedSnippets();
    if (!items.length) {
      snippetList.innerHTML = '<p class="empty">No snippets match these filters.</p>';
      return;
    }
    const preferred = defaultLevel.value;
    items.forEach((snippet) => {
      const card = document.createElement("article");
      card.className = "snippet-card";
      const levels = (snippet.variants || []).map((v) => v.detail_level);
      const selectedLevel = levels.includes(preferred)
        ? preferred
        : levels[0] || preferred;
      const variant = pickVariant(snippet, selectedLevel);
      const meta = matchMeta.get(snippet.id);
      const options = ["brief", "standard", "detailed"]
        .map((level) => {
          const disabled = levels.length && !levels.includes(level) ? " disabled" : "";
          const sel = level === selectedLevel ? " selected" : "";
          return `<option value="${level}"${sel}${disabled}>${level}</option>`;
        })
        .join("");
      card.innerHTML = `
        <h3>${escapeHtml(snippetLabel(snippet))}</h3>
        <div class="meta">
          <span class="badge">${escapeHtml(snippet.category || "")}</span>
          ${
            meta
              ? `<span class="badge score-badge">score ${escapeHtml(
                  String(meta.score)
                )}</span>`
              : ""
          }
          ${(snippet.tags || [])
            .slice(0, 4)
            .map((t) => `<span class="badge">${escapeHtml(t)}</span>`)
            .join("")}
        </div>
        ${
          meta && meta.matched_terms.length
            ? `<p class="match-terms">Matched: ${escapeHtml(
                meta.matched_terms.slice(0, 8).join(", ")
              )}</p>`
            : ""
        }
        <p class="preview-text">${escapeHtml(truncate(variant ? variant.content : "", 280))}</p>
        <div class="card-actions">
          <select class="level-select" data-id="${snippet.id}">${options}</select>
          <button type="button" class="btn-add" data-id="${snippet.id}">Add to draft</button>
          <button type="button" class="btn-edit" data-id="${snippet.id}">Edit</button>
          <button type="button" class="btn-delete" data-id="${snippet.id}">Delete</button>
        </div>
      `;
      const levelSelect = card.querySelector(".level-select");
      levelSelect.addEventListener("change", () => {
        const next = pickVariant(snippet, levelSelect.value);
        card.querySelector(".preview-text").textContent = truncate(
          next ? next.content : "",
          280
        );
      });
      card.querySelector(".btn-add").addEventListener("click", () => {
        addToDraft(snippet, levelSelect.value);
      });
      card.querySelector(".btn-edit").addEventListener("click", () => {
        openSnippetForm(snippet);
      });
      card.querySelector(".btn-delete").addEventListener("click", () => {
        if (!confirm(`Delete snippet “${snippetLabel(snippet)}”?`)) return;
        fetch(`/api/snippets/${snippet.id}`, { method: "DELETE" })
          .then(async (resp) => {
            if (!resp.ok) throw new Error(await resp.text());
            setStatus("Snippet deleted.");
            return loadSnippets();
          })
          .catch((err) => setStatus("Error: " + err.message));
      });
      snippetList.appendChild(card);
    });
  }

  /**
   * Add a snippet to the draft list.
   * @param {any} snippet
   * @param {string} detailLevel
   */
  function addToDraft(snippet, detailLevel) {
    const variant = pickVariant(snippet, detailLevel);
    if (!variant) {
      setStatus("That snippet has no content at any detail level.");
      return;
    }
    draft.push({
      snippet_id: snippet.id,
      detail_level: variant.detail_level,
      section: snippet.category,
      label: snippetLabel(snippet),
      preview: truncate(variant.content, 160),
    });
    renderDraft();
    autosaveLocal();
    setStatus(`Added “${snippetLabel(snippet)}” (${variant.detail_level}).`);
  }

  /**
   * Render the draft CV selection list.
   */
  function renderDraft() {
    draftList.innerHTML = "";
    if (!draft.length) {
      draftList.innerHTML = '<li class="empty">No snippets selected yet.</li>';
      return;
    }
    draft.forEach((item, index) => {
      const li = document.createElement("li");
      li.className = "draft-item";
      li.innerHTML = `
        <h3>${escapeHtml(item.label)}</h3>
        <div class="meta">
          <span class="badge">${escapeHtml(item.section || "")}</span>
          <span class="badge">${escapeHtml(item.detail_level)}</span>
        </div>
        <p class="preview-text">${escapeHtml(item.preview)}</p>
        <div class="card-actions">
          <button type="button" data-action="up" data-index="${index}" ${index === 0 ? "disabled" : ""}>↑</button>
          <button type="button" data-action="down" data-index="${index}" ${index === draft.length - 1 ? "disabled" : ""}>↓</button>
          <button type="button" data-action="remove" data-index="${index}">×</button>
        </div>
      `;
      li.querySelectorAll("button").forEach((btn) => {
        btn.addEventListener("click", () => {
          const action = btn.getAttribute("data-action");
          const idx = Number(btn.getAttribute("data-index"));
          if (action === "remove") {
            draft.splice(idx, 1);
          } else if (action === "up" && idx > 0) {
            const tmp = draft[idx - 1];
            draft[idx - 1] = draft[idx];
            draft[idx] = tmp;
          } else if (action === "down" && idx < draft.length - 1) {
            const tmp = draft[idx + 1];
            draft[idx + 1] = draft[idx];
            draft[idx] = tmp;
          }
          renderDraft();
          autosaveLocal();
        });
      });
      draftList.appendChild(li);
    });
  }

  /**
   * Compose the draft into a named variant and show the PDF.
   * @returns {Promise<void>}
   */
  async function composeDraft() {
    const name = variantName.value.trim();
    if (!name) {
      setStatus("Please enter a variant name.");
      return;
    }
    if (!draft.length) {
      setStatus("Add at least one snippet to the draft.");
      return;
    }
    btnCompose.disabled = true;
    setStatus("Composing variant and rendering PDF…");
    try {
      const payload = {
        name: name,
        selections: draft.map((item) => ({
          snippet_id: item.snippet_id,
          detail_level: item.detail_level,
          section: item.section,
        })),
      };
      const resp = await fetch("/api/compose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await resp.json();
      if (!resp.ok) throw new Error(body.error || "compose failed");
      if (body.pdf) {
        previewPane.classList.add("open");
        previewFrame.src = "/" + body.pdf + "?t=" + Date.now();
      }
      setStatus(
        `Saved ${body.data_yaml}` + (body.pdf ? ` and ${body.pdf}` : "") + "."
      );
    } catch (err) {
      setStatus("Error: " + err.message);
    } finally {
      btnCompose.disabled = false;
    }
  }

  /**
   * Save the current draft to the database.
   * @returns {Promise<void>}
   */
  async function saveDraftRemote() {
    const name = variantName.value.trim();
    if (!name) {
      setStatus("Enter a name before saving a draft.");
      return;
    }
    const resp = await fetch("/api/drafts/" + encodeURIComponent(name), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        selections: draft.map((item) => ({
          snippet_id: item.snippet_id,
          detail_level: item.detail_level,
          section: item.section,
          label: item.label,
          preview: item.preview,
        })),
      }),
    });
    const body = await resp.json();
    if (!resp.ok) throw new Error(body.error || "draft save failed");
    await loadDraftOptions();
    draftSelect.value = name;
    autosaveLocal();
    setStatus(`Draft “${name}” saved.`);
  }

  /**
   * Load the selected remote draft into the UI.
   * @returns {Promise<void>}
   */
  async function loadDraftRemote() {
    const name = draftSelect.value || variantName.value.trim();
    if (!name) {
      setStatus("Select or enter a draft name to load.");
      return;
    }
    const resp = await fetch("/api/drafts/" + encodeURIComponent(name));
    const body = await resp.json();
    if (!resp.ok) throw new Error(body.error || "draft load failed");
    variantName.value = body.name;
    draft = (body.selections || []).map((item) => ({
      snippet_id: item.snippet_id,
      detail_level: item.detail_level || "standard",
      section: item.section || null,
      label: item.label || `Snippet #${item.snippet_id}`,
      preview: item.preview || "",
    }));
    renderDraft();
    autosaveLocal();
    setStatus(`Loaded draft “${body.name}” (${draft.length} items).`);
  }

  /**
   * Delete the selected remote draft.
   * @returns {Promise<void>}
   */
  async function deleteDraftRemote() {
    const name = draftSelect.value || variantName.value.trim();
    if (!name) {
      setStatus("Select a draft to delete.");
      return;
    }
    if (!confirm(`Delete draft “${name}”?`)) return;
    const resp = await fetch("/api/drafts/" + encodeURIComponent(name), {
      method: "DELETE",
    });
    if (!resp.ok) {
      const body = await resp.json();
      throw new Error(body.error || "draft delete failed");
    }
    await loadDraftOptions();
    setStatus(`Deleted draft “${name}”.`);
  }

  /**
   * Rank snippets against the pasted posting.
   * @returns {Promise<void>}
   */
  async function runMatch() {
    const text = postingText.value.trim();
    if (!text) {
      setStatus("Paste a job posting first.");
      return;
    }
    const limit = Number(matchLimit.value) || 15;
    const payload = { text: text, limit: limit };
    if (categoryFilter.value) payload.category = categoryFilter.value;
    setStatus("Matching snippets…");
    const resp = await fetch("/api/match", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await resp.json();
    if (!resp.ok) throw new Error(body.error || "match failed");
    matchMeta = new Map();
    matchOrder = [];
    body.forEach((item) => {
      matchOrder.push(item.snippet_id);
      matchMeta.set(item.snippet_id, {
        score: item.score,
        matched_terms: item.matched_terms || [],
      });
    });
    // Prefer matched snippets in the library even if filters hid some — merge in.
    const known = new Set(snippets.map((s) => s.id));
    body.forEach((item) => {
      if (!known.has(item.snippet_id) && item.snippet) {
        snippets.push(item.snippet);
        known.add(item.snippet_id);
      }
    });
    renderLibrary();
    matchSummary.textContent = `Ranked ${body.length} snippets. Top score: ${
      body[0] ? body[0].score : 0
    }.`;
    setStatus(`Matched ${body.length} snippets to the posting.`);
  }

  /**
   * Add the top N matched snippets to the draft.
   */
  function addTopMatches() {
    if (!matchOrder.length) {
      setStatus("Run Suggest snippets first.");
      return;
    }
    const limit = Number(matchLimit.value) || 15;
    const byId = new Map(snippets.map((s) => [s.id, s]));
    let added = 0;
    matchOrder.slice(0, limit).forEach((id) => {
      const snippet = byId.get(id);
      if (!snippet) return;
      addToDraft(snippet, defaultLevel.value);
      added += 1;
    });
    setStatus(`Added ${added} matched snippets to the draft.`);
  }

  /**
   * Clear match ranking and restore default library order.
   */
  function clearMatch() {
    matchMeta = new Map();
    matchOrder = [];
    matchSummary.textContent = "";
    renderLibrary();
    setStatus("Cleared ranking.");
  }

  /**
   * Re-seed the database from YAML and markdown sources.
   * @returns {Promise<void>}
   */
  async function reseed() {
    btnReseed.disabled = true;
    setStatus("Re-seeding database…");
    try {
      const resp = await fetch("/api/seed", { method: "POST" });
      const body = await resp.json();
      if (!resp.ok) throw new Error(body.error || "seed failed");
      const total = Object.values(body).reduce((a, b) => a + Number(b || 0), 0);
      setStatus(`Seeded ${total} snippets. Reloading…`);
      clearMatch();
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
  defaultLevel.addEventListener("change", renderLibrary);
  variantName.addEventListener("input", autosaveLocal);
  btnCompose.addEventListener("click", () => {
    composeDraft().catch((err) => setStatus("Error: " + err.message));
  });
  btnReseed.addEventListener("click", () => {
    reseed().catch((err) => setStatus("Error: " + err.message));
  });
  btnNewSnippet.addEventListener("click", () => openSnippetForm(null));
  btnDraftSave.addEventListener("click", () => {
    saveDraftRemote().catch((err) => setStatus("Error: " + err.message));
  });
  btnDraftLoad.addEventListener("click", () => {
    loadDraftRemote().catch((err) => setStatus("Error: " + err.message));
  });
  btnDraftDelete.addEventListener("click", () => {
    deleteDraftRemote().catch((err) => setStatus("Error: " + err.message));
  });
  btnMatch.addEventListener("click", () => {
    runMatch().catch((err) => setStatus("Error: " + err.message));
  });
  btnAddTop.addEventListener("click", addTopMatches);
  btnClearMatch.addEventListener("click", clearMatch);

  restoreLocal();
  renderDraft();
  loadDraftOptions().catch((err) => setStatus("Error: " + err.message));
  loadSnippets().catch((err) => setStatus("Error: " + err.message));
})();
