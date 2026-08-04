(function () {
  "use strict";

  const dropZone = document.getElementById("resume-drop");
  const fileInput = document.getElementById("resume-file");
  const dropTitle = document.getElementById("drop-title");
  const chooseBtn = document.getElementById("choose-resume");
  const stageFile = document.getElementById("stage-file");
  const stageReview = document.getElementById("stage-review");
  const stepFile = document.getElementById("step-file");
  const stepReview = document.getElementById("step-review");
  const toast = document.getElementById("toast");

  let state = null; // { token, filename, file_type, counts, candidates }

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => toast.classList.remove("show"), 2400);
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setStage(name) {
    stageFile.classList.toggle("active", name === "file");
    stageReview.classList.toggle("active", name === "review");
    stepFile.classList.toggle("active", true);
    stepReview.classList.toggle("active", name === "review");
  }

  // ---------- stage 1: upload ----------

  chooseBtn.addEventListener("click", () => fileInput.click());
  ["dragenter", "dragover"].forEach((name) =>
    dropZone.addEventListener(name, (event) => {
      event.preventDefault();
      dropZone.classList.add("dragging");
    })
  );
  ["dragleave", "drop"].forEach((name) =>
    dropZone.addEventListener(name, (event) => {
      event.preventDefault();
      dropZone.classList.remove("dragging");
    })
  );
  document.querySelectorAll('input[name="import-mode"]').forEach((input) => {
    input.addEventListener("change", () => {
      document.querySelectorAll(".import-choice").forEach((el) =>
        el.classList.remove("selected")
      );
      input.closest(".import-choice").classList.add("selected");
    });
  });
  dropZone.addEventListener("drop", (event) => {
    if (event.dataTransfer.files.length) uploadFile(event.dataTransfer.files[0]);
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) uploadFile(fileInput.files[0]);
    fileInput.value = "";
  });

  async function uploadFile(file) {
    dropTitle.textContent = "Reading your resume…";
    chooseBtn.disabled = true;
    const form = new FormData();
    form.append("file", file);
    try {
      const resp = await fetch("/api/imports", { method: "POST", body: form });
      const body = await resp.json();
      if (!resp.ok) throw new Error(body.error || "import failed");
      state = body;
      renderReview();
      setStage("review");
    } catch (err) {
      showToast("Error: " + err.message);
    } finally {
      dropTitle.textContent = "Drop your resume here";
      chooseBtn.disabled = false;
    }
  }

  // ---------- stage 2: review ----------

  const SECTION_LABELS = {
    profile: "Profile",
    experience: "Work experience",
    skills: "Skills",
    education: "Education",
  };

  function pluralNoun(section, count) {
    if (section === "experience") return count === 1 ? "role" : "roles";
    if (section === "education") return count === 1 ? "entry" : "entries";
    return count === 1 ? "item" : "items";
  }

  function sectionPreview(section, items) {
    if (!items.length) return "Nothing found in this file.";
    if (section === "experience") {
      const companies = items.map((c) => c.company || c.heading).filter(Boolean);
      return companies.slice(0, 3).join(" · ") + (companies.length > 3 ? ", and more" : "");
    }
    if (section === "skills") {
      const names = items.map((c) => c.heading);
      return names.slice(0, 6).join(" · ") + (names.length > 6 ? `, and ${names.length - 6} more` : "");
    }
    const text = items[0].content;
    return text.length > 160 ? text.slice(0, 160) + "…" : text;
  }

  function renderReview() {
    document.getElementById("review-file-name").textContent =
      `${state.filename} · ${state.file_type.toUpperCase()}`;
    document.getElementById("count-profile").textContent = state.counts.profile;
    document.getElementById("count-experience").textContent = state.counts.experience;
    document.getElementById("count-skills").textContent = state.counts.skills;
    document.getElementById("count-education").textContent = state.counts.education;

    const bySection = { profile: [], experience: [], skills: [], education: [] };
    let duplicates = 0;
    state.candidates.forEach((c) => {
      bySection[c.section].push(c);
      if (c.duplicate) duplicates += 1;
    });

    const sections = document.getElementById("extracted-sections");
    sections.innerHTML = Object.keys(SECTION_LABELS)
      .map((section) => {
        const items = bySection[section];
        const noun = pluralNoun(section, items.length);
        return `
        <article class="${items.length ? "" : "empty"}">
          <header><b>${SECTION_LABELS[section]}</b><span>${items.length} ${noun} found</span></header>
          <p>${escapeHtml(sectionPreview(section, items))}</p>
        </article>`;
      })
      .join("");

    const note = document.getElementById("duplicate-note");
    if (duplicates > 0) {
      note.hidden = false;
      document.getElementById("duplicate-count").textContent =
        `${duplicates} possible duplicate${duplicates === 1 ? "" : "s"}`;
    } else {
      note.hidden = true;
    }

    document.querySelectorAll("#stage-review [data-section]").forEach((box) => {
      box.checked = true;
    });
  }

  document.getElementById("replace-file").addEventListener("click", resetToFileStage);
  document.getElementById("cancel-import").addEventListener("click", resetToFileStage);

  function resetToFileStage() {
    if (state) {
      fetch(`/api/imports/staging/${state.token}`, { method: "DELETE" }).catch(() => {});
    }
    state = null;
    setStage("file");
  }

  document.getElementById("complete-import").addEventListener("click", async () => {
    if (!state) return;
    const sections = {};
    document.querySelectorAll("#stage-review [data-section]").forEach((box) => {
      sections[box.dataset.section] = box.checked;
    });
    const modeInput = document.querySelector('input[name="import-mode"]:checked');
    const uiMode = modeInput ? modeInput.value : "library";
    const mode = uiMode === "new" ? "master" : "library";
    const btn = document.getElementById("complete-import");
    btn.disabled = true;
    if (
      mode === "master" &&
      state.counts &&
      Object.values(state.counts).every((n) => n === 0)
    ) {
      if (
        !confirm(
          "No content was extracted. Continuing will clear enabled master sections. Continue?"
        )
      ) {
        btn.disabled = false;
        return;
      }
    }
    try {
      const resp = await fetch(`/api/imports/${state.token}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sections, mode }),
      });
      const body = await resp.json();
      if (!resp.ok) throw new Error(body.error || "import failed");
      const noun = body.snippet_count === 1 ? "snippet" : "snippets";
      if (body.mode === "master" && body.master_updated) {
        showToast(
          `Master CV updated · ${body.snippet_count} ${noun} added. Open Master CV to review.`
        );
      } else {
        showToast(`${body.snippet_count} ${noun} added to your library.`);
      }
      state = null;
      setStage("file");
      await loadHistory();
    } catch (err) {
      showToast("Error: " + err.message);
    } finally {
      btn.disabled = false;
    }
  });

  // ---------- recent imports ----------

  function formatDate(iso) {
    if (!iso) return "";
    const date = new Date(iso.replace(" ", "T") + "Z");
    if (Number.isNaN(date.getTime())) return iso;
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  async function loadHistory() {
    const history = document.getElementById("import-history");
    try {
      const resp = await fetch("/api/imports");
      const items = await resp.json();
      if (!items.length) {
        history.innerHTML = `<div class="empty-row">No resumes imported yet.</div>`;
        return;
      }
      history.innerHTML = items
        .map((item) => {
          const noun = item.snippet_count === 1 ? "snippet" : "snippets";
          return `
        <div>
          <span class="file-type ${item.file_type}">${item.file_type.toUpperCase()}</span>
          <span><b>${escapeHtml(item.filename)}</b><p>Imported ${formatDate(item.created_at)} · ${item.snippet_count} ${noun} created</p></span>
          <button type="button" data-action="download" data-id="${item.id}">Download source</button>
          <button type="button" data-action="remove" data-id="${item.id}">Remove</button>
        </div>`;
        })
        .join("");
    } catch (err) {
      history.innerHTML = `<div class="empty-row">Could not load recent imports.</div>`;
    }
  }

  document.getElementById("import-history").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const id = button.dataset.id;
    if (button.dataset.action === "download") {
      window.open(`/api/imports/${id}/source`, "_blank");
      return;
    }
    if (button.dataset.action === "remove") {
      if (!confirm("Remove this import record and its stored file?")) return;
      await fetch(`/api/imports/${id}`, { method: "DELETE" });
      await loadHistory();
    }
  });

  loadHistory();
})();
