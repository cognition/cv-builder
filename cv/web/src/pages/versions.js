(function () {
  "use strict";

  const list = document.getElementById("version-list");
  const statusEl = document.getElementById("versions-status");
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

  async function loadPins() {
    setStatus("Loading…");
    const resp = await fetch("/api/pins?document=working");
    if (!resp.ok) throw new Error("failed to load pins");
    const pins = await resp.json();
    list.innerHTML = "";
    if (!pins.length) {
      list.innerHTML =
        '<p class="empty-row">No pinned versions yet. <a href="/cv/web/build">Tailor a CV</a> and save with a pin label.</p>';
      setStatus("No versions.");
      return;
    }
    pins.forEach((item) => {
      const row = document.createElement("div");
      row.className = "version-row";
      const selectionCount = (item.selections || []).length;
      row.innerHTML = `
          <label class="pill">PIN</label>
        <div>
          <b>${escapeHtml(item.label)}</b><br>
          <span class="meta">Pinned ${escapeHtml(formatWhen(item.created_at))}
            · ${selectionCount} tailor selection(s)</span>
        </div>
        <div class="row-actions">
          <button type="button" data-action="start">Use as starting point</button>
          <button type="button" data-action="delete">Delete</button>
        </div>
      `;
      row.querySelectorAll("button").forEach((btn) => {
        btn.addEventListener("click", () => {
          const action = btn.getAttribute("data-action");
          if (action === "start") {
            loadIntoDraft(item.id, item.label).catch((err) =>
              setStatus("Error: " + err.message)
            );
          } else if (action === "delete") {
            deletePin(item.id, item.label).catch((err) =>
              setStatus("Error: " + err.message)
            );
          }
        });
      });
      list.appendChild(row);
    });
    setStatus(`${pins.length} version(s).`);
  }

  async function loadIntoDraft(pinId, label) {
    setStatus(`Loading ${label} into Tailor…`);
    const resp = await fetch("/api/pins/" + encodeURIComponent(pinId) + "/load-into-draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const body = await resp.json();
    if (!resp.ok) throw new Error(body.error || "load failed");
    showToast(
      body.warning
        ? body.warning
        : `Draft "${body.draft_name}" ready — opening Tailor.`
    );
    window.location.href = "/cv/web/build";
  }

  async function deletePin(pinId, label) {
    if (!confirm(`Delete pin “${label}”?`)) return;
    const resp = await fetch("/api/pins/" + encodeURIComponent(pinId), {
      method: "DELETE",
    });
    const result = await resp.json();
    if (!resp.ok) throw new Error(result.error || "delete failed");
    await loadPins();
    showToast(`Deleted ${label}.`);
  }

  loadPins().catch((err) => setStatus("Error: " + err.message));
})();
