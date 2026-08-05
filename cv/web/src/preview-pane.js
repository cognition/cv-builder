/**
 * Shared PDF preview chrome: Close, Expand/Collapse, Pop out.
 *
 * Expects ``#preview-pane`` with ``#preview-frame`` (toolbar is injected
 * when missing). Optional ``onClose`` restores page-specific layout.
 */
(function () {
  "use strict";

  /** @type {{ onClose: ?Function }} */
  const state = { onClose: null };

  /**
   * @returns {?HTMLElement}
   */
  function paneEl() {
    return document.getElementById("preview-pane");
  }

  /**
   * @returns {?HTMLIFrameElement}
   */
  function frameEl() {
    return /** @type {?HTMLIFrameElement} */ (
      document.getElementById("preview-frame")
    );
  }

  /**
   * Ensure the shared toolbar exists above the iframe.
   * @param {HTMLElement} pane
   * @returns {void}
   */
  function ensureToolbar(pane) {
    if (pane.querySelector(".preview-toolbar")) return;
    const legacyClose = pane.querySelector("#preview-close");
    if (legacyClose) legacyClose.remove();
    const toolbar = document.createElement("div");
    toolbar.className = "preview-toolbar";
    toolbar.innerHTML = [
      '<button type="button" data-preview-action="popout" title="Pop out" aria-label="Pop out preview">Pop out</button>',
      '<button type="button" data-preview-action="expand" title="Expand" aria-label="Expand preview">Expand</button>',
      '<button type="button" data-preview-action="close" title="Close" aria-label="Close preview">Close</button>',
    ].join("");
    const frame = frameEl();
    if (frame && frame.parentElement === pane) {
      pane.insertBefore(toolbar, frame);
    } else {
      pane.prepend(toolbar);
    }
  }

  /**
   * Sync Expand button label with the current size state.
   * @param {HTMLElement} pane
   * @returns {void}
   */
  function syncExpandLabel(pane) {
    const button = pane.querySelector('[data-preview-action="expand"]');
    if (!(button instanceof HTMLElement)) return;
    const expanded = pane.classList.contains("expanded");
    button.textContent = expanded ? "Collapse" : "Expand";
    button.setAttribute("title", expanded ? "Collapse" : "Expand");
    button.setAttribute(
      "aria-label",
      expanded ? "Collapse preview" : "Expand preview"
    );
  }

  /**
   * Close the preview and clear the iframe.
   * @returns {void}
   */
  function closePreview() {
    const pane = paneEl();
    const frame = frameEl();
    if (!pane) return;
    pane.classList.remove("open", "expanded");
    pane.setAttribute("aria-hidden", "true");
    syncExpandLabel(pane);
    if (frame) frame.src = "about:blank";
    document.body.classList.remove("preview-expanded");
    if (typeof state.onClose === "function") state.onClose();
  }

  /**
   * Toggle fullscreen overlay (covers the whole viewport including sidebar).
   * @returns {void}
   */
  function toggleExpand() {
    const pane = paneEl();
    if (!pane || !pane.classList.contains("open")) return;
    const next = !pane.classList.contains("expanded");
    pane.classList.toggle("expanded", next);
    document.body.classList.toggle("preview-expanded", next);
    syncExpandLabel(pane);
  }

  /**
   * Open the current PDF URL in a new browser tab.
   * @returns {void}
   */
  function popOut() {
    const frame = frameEl();
    const src = frame && frame.src ? String(frame.src) : "";
    if (!src || src === "about:blank") return;
    window.open(src, "_blank", "noopener,noreferrer");
  }

  /**
   * Show the pane with a PDF URL (does not clear expand unless opening fresh).
   * @param {string} url
   * @returns {void}
   */
  function openPreview(url) {
    const pane = paneEl();
    const frame = frameEl();
    if (!pane || !frame) return;
    ensureToolbar(pane);
    frame.src = url;
    pane.classList.add("open");
    pane.setAttribute("aria-hidden", "false");
    syncExpandLabel(pane);
  }

  /**
   * Wire toolbar clicks and Escape once.
   * @param {{ onClose?: Function }} [options]
   * @returns {void}
   */
  function init(options) {
    const pane = paneEl();
    if (!pane || pane.dataset.previewChrome === "1") {
      if (options && typeof options.onClose === "function") {
        state.onClose = options.onClose;
      }
      return;
    }
    pane.dataset.previewChrome = "1";
    if (options && typeof options.onClose === "function") {
      state.onClose = options.onClose;
    }
    ensureToolbar(pane);
    syncExpandLabel(pane);
    pane.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const button = target.closest("[data-preview-action]");
      if (!button || !pane.contains(button)) return;
      const action = button.getAttribute("data-preview-action");
      if (action === "close") closePreview();
      else if (action === "expand") toggleExpand();
      else if (action === "popout") popOut();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      if (!pane.classList.contains("open")) return;
      if (pane.classList.contains("expanded")) {
        pane.classList.remove("expanded");
        document.body.classList.remove("preview-expanded");
        syncExpandLabel(pane);
        return;
      }
      closePreview();
    });
  }

  window.CvPreviewPane = {
    init: init,
    open: openPreview,
    close: closePreview,
    toggleExpand: toggleExpand,
    popOut: popOut,
  };
})();
