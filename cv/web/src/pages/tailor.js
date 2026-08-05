(function () {
  "use strict";

  const STORAGE_KEY = "cvbuilder.draft.v1";

  const suggestions = document.getElementById("suggestions");
  const draftList = document.getElementById("draft-list");
  const statusEl = document.getElementById("builder-status");
  const categoryFilter = document.getElementById("filter-category");
  const searchFilter = document.getElementById("filter-search");
  const defaultLevel = document.getElementById("default-level");
  const variantName = document.getElementById("variant-name");
  const draftSelect = document.getElementById("draft-select");
  const btnCompose = document.getElementById("btn-compose");
  const btnDraftLoad = document.getElementById("btn-draft-load");
  const btnDraftSave = document.getElementById("btn-draft-save");
  const btnDraftDelete = document.getElementById("btn-draft-delete");
  const btnMatch = document.getElementById("btn-match");
  const btnAddTop = document.getElementById("btn-add-top");
  const btnClearMatch = document.getElementById("btn-clear-match");
  const postingText = document.getElementById("posting-text");
  const postingCount = document.getElementById("posting-count");
  const matchLimit = document.getElementById("match-limit");
  const matchSummary = document.getElementById("match-summary");
  const selectedCount = document.getElementById("selected-count");
  const metric = document.getElementById("metric");
  const metricHint = document.getElementById("metric-hint");
  const previewPane = document.getElementById("preview-pane");
  const previewFrame = document.getElementById("preview-frame");
  const toast = document.getElementById("toast");

  /** @type {Array<any>} */
  let snippets = [];
  /** @type {Array<{snippet_id:number, detail_level:string, section:?string, label:string, preview:string}>} */
  let draft = [];
  /** @type {Map<number, {score:number, matched_terms:string[]}>} */
  let matchMeta = new Map();
  /** @type {number[]} */
  let matchOrder = [];

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

  function autosaveLocal() {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ name: variantName.value, draft: draft })
      );
    } catch (_err) {
      /* ignore quota / private-mode failures */
    }
  }

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

  async function loadSnippets() {
    const params = new URLSearchParams();
    if (categoryFilter.value) params.set("category", categoryFilter.value);
    if (searchFilter.value.trim()) params.set("search", searchFilter.value.trim());
    setStatus("Loading snippets…");
    const resp = await fetch("/api/snippets?" + params.toString());
    if (!resp.ok) throw new Error("failed to load snippets: " + (await resp.text()));
    snippets = await resp.json();
    renderSuggestions();
    setStatus(`Loaded ${snippets.length} snippets.`);
  }

  async function loadDraftOptions() {
    const resp = await fetch("/api/drafts");
    if (!resp.ok) throw new Error("failed to load drafts");
    const drafts = await resp.json();
    const current = draftSelect.value;
    draftSelect.innerHTML = '<option value="">Saved drafts — select…</option>';
    drafts.forEach((item) => {
      const opt = document.createElement("option");
      opt.value = item.name;
      opt.textContent = item.name;
      draftSelect.appendChild(opt);
    });
    if (current) draftSelect.value = current;
  }

  function orderedSnippets() {
    if (!matchOrder.length) return snippets;
    const byId = new Map(snippets.map((s) => [s.id, s]));
    const ranked = matchOrder.map((id) => byId.get(id)).filter(Boolean);
    const rankedIds = new Set(matchOrder);
    const rest = snippets.filter((s) => !rankedIds.has(s.id));
    return ranked.concat(rest);
  }

  function isInDraft(snippetId) {
    return draft.some((item) => item.snippet_id === snippetId);
  }

  function renderSuggestions() {
    suggestions.innerHTML = "";
    const items = orderedSnippets();
    if (!items.length) {
      suggestions.innerHTML = '<p class="empty-row">No snippets match these filters.</p>';
      return;
    }
    const preferred = defaultLevel.value;
    items.forEach((snippet) => {
      const row = document.createElement("label");
      const levels = (snippet.variants || []).map((v) => v.detail_level);
      const selectedLevel = levels.includes(preferred) ? preferred : levels[0] || preferred;
      const variant = pickVariant(snippet, selectedLevel);
      const meta = matchMeta.get(snippet.id);
      const checked = isInDraft(snippet.id);
      row.className = "suggestion" + (checked ? " selected" : "");
      const options = ["brief", "standard", "detailed"]
        .map((level) => {
          const disabled = levels.length && !levels.includes(level) ? " disabled" : "";
          const sel = level === selectedLevel ? " selected" : "";
          return `<option value="${level}"${sel}${disabled}>${level}</option>`;
        })
        .join("");
      row.innerHTML = `
        <input type="checkbox" ${checked ? "checked" : ""}>
        <div>
          <h3>${escapeHtml(snippetLabel(snippet))}</h3>
          <p>${escapeHtml(truncate(variant ? variant.content : "", 200))}</p>
          ${meta && meta.matched_terms.length ? `<p class="match-terms">Matched: ${escapeHtml(meta.matched_terms.slice(0, 6).join(", "))}</p>` : ""}
        </div>
        <div class="row-meta">
          ${meta ? `<span class="badge">score ${escapeHtml(String(meta.score))}</span>` : `<span class="badge">${escapeHtml(snippet.category || "")}</span>`}
          <select class="level-select">${options}</select>
        </div>
      `;
      const checkbox = row.querySelector('input[type="checkbox"]');
      const levelSelect = row.querySelector(".level-select");
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) {
          addToDraft(snippet, levelSelect.value);
        } else {
          removeFromDraft(snippet.id);
        }
        row.classList.toggle("selected", checkbox.checked);
      });
      levelSelect.addEventListener("click", (event) => event.stopPropagation());
      levelSelect.addEventListener("change", () => {
        if (checkbox.checked) {
          removeFromDraft(snippet.id);
          addToDraft(snippet, levelSelect.value);
        }
      });
      suggestions.appendChild(row);
    });
  }

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
    setStatus(`Added "${snippetLabel(snippet)}" (${variant.detail_level}).`);
  }

  function removeFromDraft(snippetId) {
    draft = draft.filter((item) => item.snippet_id !== snippetId);
    renderDraft();
    autosaveLocal();
  }

  function renderDraft() {
    draftList.innerHTML = "";
    selectedCount.textContent = draft.length;
    metric.textContent = draft.length;
    metricHint.textContent = draft.length
      ? `About ${Math.max(1, Math.ceil(draft.length / 6))} page(s)`
      : "Add content to begin";
    if (!draft.length) {
      draftList.innerHTML = '<li class="empty-row">No snippets selected yet.</li>';
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
          <button type="button" data-action="up" data-index="${index}" ${index === 0 ? "disabled" : ""}>&uarr;</button>
          <button type="button" data-action="down" data-index="${index}" ${index === draft.length - 1 ? "disabled" : ""}>&darr;</button>
          <button type="button" data-action="remove" data-index="${index}">&times;</button>
        </div>
      `;
      li.querySelectorAll("button").forEach((btn) => {
        btn.addEventListener("click", () => {
          const action = btn.getAttribute("data-action");
          const idx = Number(btn.getAttribute("data-index"));
          if (action === "remove") {
            draft.splice(idx, 1);
          } else if (action === "up" && idx > 0) {
            [draft[idx - 1], draft[idx]] = [draft[idx], draft[idx - 1]];
          } else if (action === "down" && idx < draft.length - 1) {
            [draft[idx + 1], draft[idx]] = [draft[idx], draft[idx + 1]];
          }
          renderDraft();
          renderSuggestions();
          autosaveLocal();
        });
      });
      draftList.appendChild(li);
    });
  }

  async function composeDraft() {
    if (!draft.length) {
      setStatus("Add at least one snippet to the draft.");
      return;
    }
    const pinLabel = variantName.value.trim();
    const draftName = pinLabel || draftSelect.value || "working-draft";
    btnCompose.disabled = true;
    setStatus("Updating Working Draft CV…");
    try {
      const payload = {
        selections: draft.map((item) => ({
          snippet_id: item.snippet_id,
          detail_level: item.detail_level,
          section: item.section,
        })),
        apply: true,
        pin_label: pinLabel || null,
      };
      const resp = await fetch("/api/drafts/" + encodeURIComponent(draftName), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await resp.json();
      if (!resp.ok) throw new Error(body.error || "apply failed");
      await fetch("/api/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ format: "pdf", document: "master" }),
      });
      previewPane.classList.add("open");
      previewFrame.src = "/api/preview.pdf?t=" + Date.now();
      await loadDraftOptions();
      draftSelect.value = draftName;
      const pinNote =
        body.apply && body.apply.pin
          ? ` Pin “${body.apply.pin.label}” saved.`
          : "";
      showToast(`Working Draft CV updated.${pinNote}`);
      setStatus("Ready.");
    } catch (err) {
      setStatus("Error: " + err.message);
    } finally {
      btnCompose.disabled = false;
    }
  }

  async function saveDraftRemote() {
    const name = variantName.value.trim() || draftSelect.value;
    if (!name) {
      setStatus("Enter a draft name before saving.");
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
        apply: true,
        pin_label: variantName.value.trim() || null,
      }),
    });
    const body = await resp.json();
    if (!resp.ok) throw new Error(body.error || "draft save failed");
    await loadDraftOptions();
    draftSelect.value = name;
    autosaveLocal();
    showToast(
      body.applied
        ? `Draft "${name}" saved and applied to Working Draft CV.`
        : `Draft "${name}" saved.`
    );
  }

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
    renderSuggestions();
    autosaveLocal();
    if (draft.length) {
      const applyResp = await fetch(
        "/api/drafts/" + encodeURIComponent(name) + "/apply",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        }
      );
      const applyBody = await applyResp.json();
      if (!applyResp.ok) {
        throw new Error(applyBody.error || "draft apply failed");
      }
      showToast(
        `Loaded and applied draft "${body.name}" (${draft.length} items).`
      );
    } else {
      showToast(`Loaded draft "${body.name}" (empty).`);
    }
  }

  async function deleteDraftRemote() {
    const name = draftSelect.value || variantName.value.trim();
    if (!name) {
      setStatus("Select a draft to delete.");
      return;
    }
    if (!confirm(`Delete draft "${name}"?`)) return;
    const resp = await fetch("/api/drafts/" + encodeURIComponent(name), { method: "DELETE" });
    if (!resp.ok) {
      const body = await resp.json();
      throw new Error(body.error || "draft delete failed");
    }
    await loadDraftOptions();
    showToast(`Deleted draft "${name}".`);
  }

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
      matchMeta.set(item.snippet_id, { score: item.score, matched_terms: item.matched_terms || [] });
    });
    const known = new Set(snippets.map((s) => s.id));
    body.forEach((item) => {
      if (!known.has(item.snippet_id) && item.snippet) {
        snippets.push(item.snippet);
        known.add(item.snippet_id);
      }
    });
    renderSuggestions();
    matchSummary.textContent = `Ranked ${body.length} snippets. Top score: ${body[0] ? body[0].score : 0}.`;
    setStatus(`Matched ${body.length} snippets to the posting.`);
  }

  function addTopMatches() {
    if (!matchOrder.length) {
      setStatus("Run Suggest snippets first.");
      return;
    }
    const limit = Number(matchLimit.value) || 15;
    const byId = new Map(snippets.map((s) => [s.id, s]));
    let added = 0;
    matchOrder.slice(0, limit).forEach((id) => {
      if (isInDraft(id)) return;
      const snippet = byId.get(id);
      if (!snippet) return;
      addToDraft(snippet, defaultLevel.value);
      added += 1;
    });
    renderSuggestions();
    setStatus(`Added ${added} matched snippets to the draft.`);
  }

  function clearMatch() {
    matchMeta = new Map();
    matchOrder = [];
    matchSummary.textContent = "";
    renderSuggestions();
    setStatus("Cleared ranking.");
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
  defaultLevel.addEventListener("change", renderSuggestions);
  variantName.addEventListener("input", autosaveLocal);
  postingText.addEventListener("input", () => {
    postingCount.textContent = postingText.value.length + " characters";
  });
  btnCompose.addEventListener("click", () => {
    composeDraft().catch((err) => setStatus("Error: " + err.message));
  });
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
  postingText.dispatchEvent(new Event("input"));
  loadDraftOptions().catch((err) => setStatus("Error: " + err.message));
  loadSnippets().catch((err) => setStatus("Error: " + err.message));
})();
