(function () {
  "use strict";

  const list = document.getElementById("version-list");
  const statusEl = document.getElementById("versions-status");
  const previewPane = document.getElementById("preview-pane");
  const previewFrame = document.getElementById("preview-frame");
  const toast = document.getElementById("toast");

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

  function formatWhen(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
    } catch (_err) {
      return iso;
    }
  }

  async function loadVariants() {
    setStatus("Loading…");
    const resp = await fetch("/api/variants");
    if (!resp.ok) throw new Error("failed to load variants");
    const variants = await resp.json();
    list.innerHTML = "";
    if (!variants.length) {
      list.innerHTML =
        '<p class="empty-row">No composed versions yet. <a href="/build">Tailor a new CV</a> to create one.</p>';
      setStatus("No versions.");
      return;
    }
    variants.forEach((item) => {
      const row = document.createElement("div");
      row.className = "version-row";
      row.innerHTML = `
        <label class="pill ${item.pdf ? "" : "draft"}">${item.pdf ? "READY" : "DRAFT"}</label>
        <div>
          <b>${escapeHtml(item.name)}</b><br>
          <span class="meta">Updated ${escapeHtml(formatWhen(item.updated_at))}</span>
        </div>
        <div class="row-actions">
          <button type="button" data-action="preview" ${item.pdf ? "" : "disabled"}>Preview</button>
          <button type="button" data-action="render">Re-render</button>
          <button type="button" data-action="delete">Delete</button>
        </div>
      `;
      row.querySelectorAll("button").forEach((btn) => {
        btn.addEventListener("click", () => {
          const action = btn.getAttribute("data-action");
          if (action === "preview") {
            previewPane.classList.add("open");
            previewFrame.src = "/" + item.pdf + "?t=" + Date.now();
          } else if (action === "render") {
            renderVariant(item.name).catch((err) => setStatus("Error: " + err.message));
          } else if (action === "delete") {
            deleteVariant(item.name).catch((err) => setStatus("Error: " + err.message));
          }
        });
      });
      list.appendChild(row);
    });
    setStatus(`${variants.length} version(s).`);
  }

  async function renderVariant(name) {
    setStatus(`Rendering ${name}…`);
    const resp = await fetch(
      "/api/variants/" + encodeURIComponent(name) + "/render",
      { method: "POST" }
    );
    const result = await resp.json();
    if (!resp.ok) throw new Error(result.error || "render failed");
    if (result.pdf) {
      previewPane.classList.add("open");
      previewFrame.src = "/" + result.pdf + "?t=" + Date.now();
    }
    await loadVariants();
    showToast(`Re-rendered ${name}.`);
  }

  async function deleteVariant(name) {
    if (!confirm(`Delete version “${name}”? This removes its folder.`)) return;
    const resp = await fetch("/api/variants/" + encodeURIComponent(name), {
      method: "DELETE",
    });
    const result = await resp.json();
    if (!resp.ok) throw new Error(result.error || "delete failed");
    await loadVariants();
    showToast(`Deleted ${name}.`);
  }

  loadVariants().catch((err) => setStatus("Error: " + err.message));
})();
