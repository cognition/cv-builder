(function () {
  "use strict";

  const body = document.getElementById("variants-body");
  const statusEl = document.getElementById("variants-status");
  const btnRefresh = document.getElementById("btn-refresh");
  const previewPane = document.getElementById("preview-pane");
  const previewFrame = document.getElementById("preview-frame");

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
   * Format an ISO timestamp for display.
   * @param {string|null} iso
   * @returns {string}
   */
  function formatWhen(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString();
    } catch (_err) {
      return iso;
    }
  }

  /**
   * Load and render the variants table.
   * @returns {Promise<void>}
   */
  async function loadVariants() {
    setStatus("Loading variants…");
    const resp = await fetch("/api/variants");
    if (!resp.ok) throw new Error("failed to load variants");
    const variants = await resp.json();
    body.innerHTML = "";
    if (!variants.length) {
      body.innerHTML =
        '<tr><td colspan="4" class="empty">No composed variants yet. Use the builder to create one.</td></tr>';
      setStatus("No variants.");
      return;
    }
    variants.forEach((item) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(item.name)}</strong><br>
          <small>${escapeHtml(item.data_yaml || "")}</small></td>
        <td>${escapeHtml(formatWhen(item.updated_at))}</td>
        <td>${item.pdf ? escapeHtml(item.pdf) : "—"}</td>
        <td class="row-actions">
          <button type="button" data-action="preview" ${item.pdf ? "" : "disabled"}>Preview</button>
          <button type="button" data-action="render">Re-render</button>
          <button type="button" data-action="delete">Delete</button>
        </td>
      `;
      tr.querySelectorAll("button").forEach((btn) => {
        btn.addEventListener("click", () => {
          const action = btn.getAttribute("data-action");
          if (action === "preview") {
            previewPane.classList.add("open");
            previewFrame.src = "/" + item.pdf + "?t=" + Date.now();
            setStatus(`Previewing ${item.name}.`);
          } else if (action === "render") {
            renderVariant(item.name).catch((err) => setStatus("Error: " + err.message));
          } else if (action === "delete") {
            deleteVariant(item.name).catch((err) => setStatus("Error: " + err.message));
          }
        });
      });
      body.appendChild(tr);
    });
    setStatus(`${variants.length} variant(s).`);
  }

  /**
   * Re-render a variant PDF from its data.yaml.
   * @param {string} name
   * @returns {Promise<void>}
   */
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
    setStatus(`Re-rendered ${name}.`);
  }

  /**
   * Delete a composed variant directory after confirmation.
   * @param {string} name
   * @returns {Promise<void>}
   */
  async function deleteVariant(name) {
    if (!confirm(`Delete variant “${name}”? This removes its folder.`)) return;
    const resp = await fetch("/api/variants/" + encodeURIComponent(name), {
      method: "DELETE",
    });
    const result = await resp.json();
    if (!resp.ok) throw new Error(result.error || "delete failed");
    await loadVariants();
    setStatus(`Deleted ${name}.`);
  }

  btnRefresh.addEventListener("click", () => {
    loadVariants().catch((err) => setStatus("Error: " + err.message));
  });

  loadVariants().catch((err) => setStatus("Error: " + err.message));
})();
