(function () {
  "use strict";

  const toast = document.getElementById("toast");
  const sourceList = document.getElementById("source-list");
  const questionList = document.getElementById("question-list");
  const answerEmpty = document.getElementById("answer-empty");
  const answerBody = document.getElementById("answer-body");
  const evidenceList = document.getElementById("evidence-list");
  const evidencePicker = document.getElementById("evidence-picker");
  const evidenceResults = document.getElementById("evidence-results");
  const evidenceSearch = document.getElementById("evidence-search");
  const answerCopy = document.getElementById("answer-copy");
  const sourceModal = document.getElementById("source-modal");

  const SOURCE_ICON = { job: "JD", form: "Q", matrix: "&#9638;" };
  const SOURCE_LABEL = { job: "Job description", form: "Questionnaire", matrix: "Competency matrix" };
  const STATUS_LABEL = { complete: "COMPLETE", in_progress: "IN PROGRESS", needs_evidence: "NEEDS EVIDENCE" };

  let sources = [];
  let questions = [];
  let activeSourceId = null;
  let activeFilter = "all";
  let activeQuestionId = null;
  let selectedSourceType = "job";

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

  async function loadAll() {
    const [sourcesResp, questionsResp] = await Promise.all([
      fetch("/api/question-sources"),
      fetch("/api/questions"),
    ]);
    sources = await sourcesResp.json();
    questions = await questionsResp.json();
    renderStats();
    renderSources();
    renderQuestions();
  }

  function renderStats() {
    const total = questions.length;
    const complete = questions.filter((q) => q.status === "complete").length;
    const progress = questions.filter((q) => q.status === "in_progress").length;
    const needs = questions.filter((q) => q.status === "needs_evidence").length;
    document.getElementById("stat-total").textContent = total;
    document.getElementById("stat-complete").textContent = complete;
    document.getElementById("stat-progress").textContent = progress;
    document.getElementById("stat-needs").textContent = needs;
    const pct = total ? Math.round((complete / total) * 100) : 0;
    document.getElementById("progress-bar").value = pct;
    document.getElementById("progress-label").textContent = `${pct}% complete`;
  }

  function renderSources() {
    sourceList.innerHTML = "";
    if (!sources.length) {
      sourceList.innerHTML = '<p class="empty-row">No sources yet.</p>';
      return;
    }
    sources.forEach((source) => {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "source-row" + (source.id === activeSourceId ? " active" : "");
      row.innerHTML = `
        <i class="source-icon ${source.source_type}">${SOURCE_ICON[source.source_type] || "?"}</i>
        <span><b>${escapeHtml(source.title)}</b><small>${SOURCE_LABEL[source.source_type] || source.source_type} &middot; ${source.question_count} question(s)</small></span>
        <button type="button" class="remove-source" title="Delete source">&times;</button>
      `;
      row.addEventListener("click", () => {
        activeSourceId = activeSourceId === source.id ? null : source.id;
        renderSources();
        renderQuestions();
      });
      row.querySelector(".remove-source").addEventListener("click", async (event) => {
        event.stopPropagation();
        if (!confirm(`Delete source "${source.title}" and all its questions?`)) return;
        const resp = await fetch(`/api/question-sources/${source.id}`, { method: "DELETE" });
        if (!resp.ok) {
          showToast("Delete failed");
          return;
        }
        if (activeSourceId === source.id) activeSourceId = null;
        if (activeQuestionId && questions.find((q) => q.id === activeQuestionId)?.source_id === source.id) {
          closeAnswerEditor();
        }
        await loadAll();
        showToast("Source deleted.");
      });
      sourceList.appendChild(row);
    });
  }

  function filteredQuestions() {
    return questions.filter((q) => {
      if (activeSourceId !== null && q.source_id !== activeSourceId) return false;
      if (activeFilter === "needs") return q.status !== "complete";
      if (activeFilter === "complete") return q.status === "complete";
      return true;
    });
  }

  function renderQuestions() {
    const items = filteredQuestions();
    questionList.innerHTML = "";
    if (!items.length) {
      questionList.innerHTML = '<p class="empty-row">No questions here yet. Add a source to get started.</p>';
      return;
    }
    items.forEach((question) => {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "question-row" + (question.id === activeQuestionId ? " active" : "");
      row.innerHTML = `
        <span class="q-status ${question.status}">${STATUS_LABEL[question.status]}</span>
        <div><h3>${escapeHtml(question.prompt)}</h3><p>${escapeHtml(question.source_title)} &middot; ${SOURCE_LABEL[question.source_type] || ""}</p></div>
      `;
      row.addEventListener("click", () => openQuestion(question.id));
      questionList.appendChild(row);
    });
  }

  function closeAnswerEditor() {
    activeQuestionId = null;
    answerEmpty.style.display = "";
    answerBody.classList.remove("open");
  }

  async function openQuestion(id) {
    activeQuestionId = id;
    renderQuestions();
    const resp = await fetch(`/api/questions/${id}`);
    if (!resp.ok) return;
    const question = await resp.json();
    answerEmpty.style.display = "none";
    answerBody.classList.add("open");
    document.getElementById("answer-title").textContent = question.prompt;
    document.getElementById("answer-source").textContent =
      `${question.source_title} · ${SOURCE_LABEL[question.source_type] || ""}`;
    answerCopy.value = question.answer || "";
    updateWordCount();
    renderEvidence(question.evidence || []);
    evidencePicker.classList.remove("open");
  }

  function updateWordCount() {
    const text = answerCopy.value.trim();
    const words = text ? text.split(/\s+/).length : 0;
    document.getElementById("answer-words").textContent = `${words} words`;
  }

  function renderEvidence(evidence) {
    evidenceList.innerHTML = "";
    if (!evidence.length) {
      evidenceList.innerHTML = '<p class="empty-row">No evidence linked yet.</p>';
      return;
    }
    evidence.forEach((item) => {
      const chip = document.createElement("div");
      chip.className = "evidence-chip";
      chip.innerHTML = `
        <span>&#9638;</span>
        <div><b>${escapeHtml(item.heading || "Snippet #" + item.snippet_id)}</b><small>${escapeHtml(item.company || "")} &middot; ${escapeHtml(item.detail_level)}</small></div>
        <button type="button">&times;</button>
      `;
      chip.querySelector("button").addEventListener("click", async () => {
        await fetch(`/api/questions/${activeQuestionId}/evidence/${item.snippet_id}`, { method: "DELETE" });
        await refreshActiveQuestionChrome();
      });
      evidenceList.appendChild(chip);
    });
  }

  async function refreshActiveQuestionChrome() {
    // Re-fetch just enough to keep the list's status pill and the open
    // evidence panel in sync after a mutation, without losing in-progress
    // answer text the user hasn't saved yet.
    const [listResp, oneResp] = await Promise.all([
      fetch("/api/questions"),
      activeQuestionId ? fetch(`/api/questions/${activeQuestionId}`) : Promise.resolve(null),
    ]);
    questions = await listResp.json();
    renderStats();
    renderSources();
    renderQuestions();
    if (oneResp) {
      const question = await oneResp.json();
      renderEvidence(question.evidence || []);
    }
  }

  document.querySelectorAll(".question-tabs button").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".question-tabs button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeFilter = btn.dataset.filter;
      renderQuestions();
    });
  });

  answerCopy.addEventListener("input", updateWordCount);

  document.getElementById("save-answer").addEventListener("click", async () => {
    if (!activeQuestionId) return;
    const resp = await fetch(`/api/questions/${activeQuestionId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer: answerCopy.value }),
    });
    if (!resp.ok) {
      showToast("Save failed.");
      return;
    }
    showToast("Answer saved.");
    await refreshActiveQuestionChrome();
  });

  document.getElementById("suggest-answer").addEventListener("click", async () => {
    if (!activeQuestionId) return;
    const resp = await fetch(`/api/questions/${activeQuestionId}/suggest`, { method: "POST" });
    if (!resp.ok) {
      showToast("Nothing to suggest from — link or add matching snippets first.");
      return;
    }
    const body = await resp.json();
    answerCopy.value = body.answer || "";
    updateWordCount();
    renderEvidence(body.evidence || []);
    showToast(body.answer ? "Drafted from linked evidence." : "No matching evidence found.");
    await refreshActiveQuestionChrome();
  });

  document.getElementById("link-evidence").addEventListener("click", () => {
    evidencePicker.classList.toggle("open");
    evidenceSearch.value = "";
    evidenceResults.innerHTML = "";
    if (evidencePicker.classList.contains("open")) evidenceSearch.focus();
  });

  let searchTimer = null;
  evidenceSearch.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(runEvidenceSearch, 200);
  });

  async function runEvidenceSearch() {
    const term = evidenceSearch.value.trim();
    if (!term) {
      evidenceResults.innerHTML = "";
      return;
    }
    const resp = await fetch("/api/snippets?search=" + encodeURIComponent(term));
    const snippets = await resp.json();
    evidenceResults.innerHTML = snippets
      .slice(0, 8)
      .map((snippet) => {
        const label = [snippet.company, snippet.heading].filter(Boolean).join(" — ") || `Snippet #${snippet.id}`;
        return `<div class="evidence-result"><span>${escapeHtml(label)}</span><button type="button" data-id="${snippet.id}" data-level="${(snippet.variants[0] || {}).detail_level || "standard"}">Add</button></div>`;
      })
      .join("") || '<p class="empty-row">No matches.</p>';
    evidenceResults.querySelectorAll("button[data-id]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await fetch(`/api/questions/${activeQuestionId}/evidence`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ snippet_id: Number(btn.dataset.id), detail_level: btn.dataset.level }),
        });
        evidencePicker.classList.remove("open");
        await refreshActiveQuestionChrome();
        showToast("Evidence linked.");
      });
    });
  }

  // ---------- add-source modal ----------

  function openSourceModal() {
    sourceModal.classList.add("open");
    document.getElementById("source-title").value = "";
    document.getElementById("source-text").value = "";
  }
  document.getElementById("new-source").addEventListener("click", openSourceModal);
  document.getElementById("add-source-link").addEventListener("click", openSourceModal);
  document.getElementById("close-source-modal").addEventListener("click", () =>
    sourceModal.classList.remove("open")
  );
  sourceModal.addEventListener("click", (event) => {
    if (event.target === sourceModal) sourceModal.classList.remove("open");
  });

  document.querySelectorAll(".source-type-grid button").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".source-type-grid button").forEach((b) => b.classList.remove("selected"));
      btn.classList.add("selected");
      selectedSourceType = btn.dataset.type;
    });
  });

  document.getElementById("extract-questions").addEventListener("click", async () => {
    const title = document.getElementById("source-title").value.trim();
    if (!title) {
      showToast("Give this source a title first.");
      return;
    }
    const text = document.getElementById("source-text").value;
    const resp = await fetch("/api/question-sources", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, source_type: selectedSourceType, text }),
    });
    const body = await resp.json();
    if (!resp.ok) {
      showToast(body.error || "Could not create source.");
      return;
    }
    sourceModal.classList.remove("open");
    activeSourceId = body.id;
    await loadAll();
    showToast(
      body.question_count
        ? `Found ${body.question_count} question(s).`
        : "Source created — add questions by pasting text next time, or they'll show up empty."
    );
  });

  loadAll().catch((err) => showToast("Error: " + err.message));
})();
