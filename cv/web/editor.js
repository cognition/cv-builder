(function () {
  "use strict";

  const btn = document.getElementById("btn-save");
  const status = document.getElementById("editor-status");
  const pane = document.getElementById("preview-pane");
  const frame = document.getElementById("preview-frame");

  /**
   * Update the editor status line.
   * @param {string} msg
   */
  function setStatus(msg) {
    status.textContent = msg;
  }

  /**
   * Collect in-place text edits from contenteditable nodes.
   * @returns {Array<{path:string, value:string}>}
   */
  function collectEdits() {
    const nodes = document.querySelectorAll("[data-path]");
    const edits = [];
    nodes.forEach((node) => {
      edits.push({
        path: node.getAttribute("data-path"),
        value: node.textContent.trim(),
      });
    });
    return edits;
  }

  /**
   * Persist current text edits to data.yaml.
   * @returns {Promise<void>}
   */
  async function saveEdits() {
    const edits = collectEdits();
    const saveResp = await fetch("/api/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(edits),
    });
    if (!saveResp.ok) throw new Error("save failed: " + (await saveResp.text()));
  }

  /**
   * Save text edits and refresh the PDF preview.
   * @returns {Promise<void>}
   */
  async function saveAndPreview() {
    btn.disabled = true;
    setStatus("Saving…");
    try {
      await saveEdits();
      setStatus("Rendering PDF…");
      const exportResp = await fetch("/api/export", { method: "POST" });
      if (!exportResp.ok) throw new Error("export failed: " + (await exportResp.text()));
      document.body.classList.add("preview-open");
      pane.classList.add("open");
      frame.src = "/api/preview.pdf?t=" + Date.now();
      setStatus("Saved. Preview updated.");
      schedulePageGuides();
    } catch (err) {
      setStatus("Error: " + err.message);
    } finally {
      btn.disabled = false;
    }
  }

  /**
   * Parent list path for an indexed item path.
   * @param {string} path
   * @returns {string|null}
   */
  function parentListPath(path) {
    const match = path.match(/^(.*)\[(\d+)\]$/);
    return match ? match[1] : null;
  }

  /**
   * Index of an indexed item path.
   * @param {string} path
   * @returns {number|null}
   */
  function itemIndex(path) {
    const match = path.match(/\[(\d+)\]$/);
    return match ? Number(match[1]) : null;
  }

  /**
   * Apply a structural op after saving pending text edits, then reload.
   * @param {object} payload
   * @returns {Promise<void>}
   */
  async function applyStructure(payload) {
    setStatus("Saving edits, then updating structure…");
    try {
      await saveEdits();
      const resp = await fetch("/api/structure", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await resp.json();
      if (!resp.ok) throw new Error(body.error || "structure update failed");
      setStatus("Structure updated. Reloading…");
      window.location.reload();
    } catch (err) {
      setStatus("Error: " + err.message);
    }
  }

  /**
   * Section list paths that can pull entries from the snippet database.
   * @type {Object<string, {query:string, title:string, prefer:?string}>}
   */
  const SNIPPET_SOURCES = {
    "skills.technical": {
      query: "category=skill",
      title: "Add a technical skill",
      prefer: "technical",
    },
    "skills.functional": {
      query: "category=skill",
      title: "Add a functional skill",
      prefer: "functional",
    },
    bio: { query: "category=bio", title: "Add a bio paragraph", prefer: null },
    education: {
      query: "tag=education",
      title: "Add an education entry",
      prefer: null,
    },
  };

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
   * Best content for a snippet, preferring the standard detail level.
   * @param {any} snippet
   * @returns {string}
   */
  function snippetContent(snippet) {
    const variants = snippet.variants || [];
    const order = ["standard", "brief", "detailed"];
    for (const level of order) {
      const found = variants.find((v) => v.detail_level === level);
      if (found) return found.content;
    }
    return variants[0] ? variants[0].content : "";
  }

  /**
   * Current values already present in a list (to flag duplicates).
   * @param {string} listPath
   * @returns {Set<string>}
   */
  function existingListValues(listPath) {
    const values = new Set();
    document.querySelectorAll("[data-path]").forEach((node) => {
      const path = node.getAttribute("data-path") || "";
      if (path.startsWith(listPath + "[")) {
        values.add(node.textContent.trim().toLowerCase());
      }
    });
    return values;
  }

  /**
   * Append per-level variant chips (brief/standard/detailed) to a row.
   * @param {HTMLElement} row
   * @param {Array<{detail_level:string, content:string}>} variants
   * @param {function(string): void} choose - called with the chip's content
   */
  function addLevelChips(row, variants, choose) {
    if (!variants || variants.length < 2) return;
    const strip = document.createElement("span");
    strip.className = "level-chips";
    variants.forEach((variant) => {
      const chip = document.createElement("span");
      chip.className = "level-chip";
      chip.textContent = variant.detail_level;
      chip.title = "Use the " + variant.detail_level + " variation";
      chip.addEventListener("click", (event) => {
        event.stopPropagation();
        choose(variant.content);
      });
      strip.appendChild(chip);
    });
    row.appendChild(strip);
  }

  /**
   * Open a picker that inserts or replaces a list entry from the database.
   * @param {string} listPath - target list (e.g. skills.technical)
   * @param {?number} index - insertion index, or null to append
   * @param {?string} replacePath - when set, replace this item instead of
   *   inserting into the list
   */
  function openSnippetPicker(listPath, index, replacePath) {
    const source = SNIPPET_SOURCES[listPath];
    if (!source) return;
    closeOverlay("snippet-picker");
    const replacing = Boolean(replacePath);
    const title = replacing
      ? source.title.replace(/^Add an?/, "Replace with a")
      : source.title;
    const overlay = document.createElement("div");
    overlay.id = "snippet-picker";
    overlay.className = "picker-overlay";
    overlay.innerHTML = `
      <div class="picker-panel">
        <div class="picker-head">
          <strong>${escapeHtml(title)}</strong>
          <button type="button" class="picker-close" title="Close">×</button>
        </div>
        <p class="picker-hint">${
          replacing
            ? "Pick a variation to swap in, or type a custom replacement. Chips select a specific detail level."
            : "Pick from the snippet database, or type a custom entry. Greyed-out rows are already on the CV."
        }</p>
        <input type="search" class="picker-search" placeholder="Filter…">
        <div class="picker-rows"></div>
        <div class="picker-actions">
          <input type="text" class="picker-url" placeholder="Custom entry…">
          <button type="button" class="picker-grab">${
            replacing ? "Replace with custom" : "Insert custom"
          }</button>
        </div>
        <p class="picker-status"></p>
      </div>
    `;
    document.body.appendChild(overlay);
    document.body.classList.add("overlay-open");

    const rowsEl = overlay.querySelector(".picker-rows");
    const searchEl = overlay.querySelector(".picker-search");
    const customEl = overlay.querySelector(".picker-url");
    const statusEl2 = overlay.querySelector(".picker-status");
    const existing = existingListValues(listPath);
    /** @type {Array<{content:string, kind:?string, variants:Array}>} */
    let entries = [];

    const say = (msg) => {
      statusEl2.textContent = msg;
    };

    const chooseValue = (value) => {
      const cleaned = value.trim();
      if (!cleaned) {
        say("Nothing to " + (replacing ? "replace with." : "insert."));
        return;
      }
      closeOverlay("snippet-picker");
      if (replacing) {
        applyStructure({ op: "replace", path: replacePath, value: cleaned });
      } else {
        applyStructure({
          op: "insert",
          path: listPath,
          index: index,
          value: cleaned,
        });
      }
    };

    const renderRows = () => {
      const filter = searchEl.value.trim().toLowerCase();
      rowsEl.innerHTML = "";
      const visible = entries.filter(
        (entry) => !filter || entry.content.toLowerCase().includes(filter)
      );
      if (!visible.length) {
        rowsEl.innerHTML = '<p class="picker-empty">No matching snippets.</p>';
        return;
      }
      visible.forEach((entry) => {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "picker-row";
        const added = existing.has(entry.content.trim().toLowerCase());
        if (added && !replacing) row.classList.add("already-added");
        row.innerHTML =
          (entry.kind ? `<span class="row-kind">${escapeHtml(entry.kind)}</span>` : "") +
          escapeHtml(entry.content.length > 220 ? entry.content.slice(0, 219) + "…" : entry.content);
        addLevelChips(row, entry.variants, chooseValue);
        row.addEventListener("click", () => {
          if (added && !replacing) {
            say("Already on the CV.");
            return;
          }
          chooseValue(entry.content);
        });
        rowsEl.appendChild(row);
      });
    };

    overlay.querySelector(".picker-close").addEventListener("click", () => {
      closeOverlay("snippet-picker");
    });
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) closeOverlay("snippet-picker");
    });
    searchEl.addEventListener("input", renderRows);
    overlay.querySelector(".picker-grab").addEventListener("click", () => {
      chooseValue(customEl.value);
    });
    customEl.addEventListener("keydown", (event) => {
      if (event.key === "Enter") chooseValue(customEl.value);
    });

    say("Loading snippets…");
    fetch("/api/snippets?" + source.query)
      .then(async (resp) => {
        if (!resp.ok) throw new Error(await resp.text());
        const snippets = await resp.json();
        entries = snippets
          .map((snippet) => ({
            content: snippetContent(snippet),
            kind: snippet.role || null,
            variants: snippet.variants || [],
          }))
          .filter((entry) => entry.content);
        if (source.prefer) {
          entries.sort((a, b) => {
            const aHit = a.kind === source.prefer ? 0 : 1;
            const bHit = b.kind === source.prefer ? 0 : 1;
            return aHit - bHit;
          });
        }
        say(entries.length + " snippets available.");
        renderRows();
        searchEl.focus();
      })
      .catch((err) => say("Error: " + err.message));
  }

  /**
   * Open a picker that replaces a whole experience subsection with a
   * variation from the snippet database.
   * @param {string} subPath - e.g. experience[1].subsections[0]
   * @param {string} company - company name used to scope the snippet list
   */
  function openSubsectionPicker(subPath, company) {
    closeOverlay("snippet-picker");
    const overlay = document.createElement("div");
    overlay.id = "snippet-picker";
    overlay.className = "picker-overlay";
    overlay.innerHTML = `
      <div class="picker-panel">
        <div class="picker-head">
          <strong>Replace subsection with a variation</strong>
          <button type="button" class="picker-close" title="Close">×</button>
        </div>
        <p class="picker-hint">Experience snippets for <b>${escapeHtml(company)}</b>. Clicking a row swaps the whole subsection; chips select a specific detail level.</p>
        <input type="search" class="picker-search" placeholder="Filter…">
        <div class="picker-rows"></div>
        <p class="picker-status"></p>
      </div>
    `;
    document.body.appendChild(overlay);
    document.body.classList.add("overlay-open");

    const rowsEl = overlay.querySelector(".picker-rows");
    const searchEl = overlay.querySelector(".picker-search");
    const statusEl2 = overlay.querySelector(".picker-status");
    /** @type {Array<{heading:string, content:string, variants:Array}>} */
    let entries = [];

    const say = (msg) => {
      statusEl2.textContent = msg;
    };

    const chooseValue = (heading, content) => {
      if (!content.trim()) {
        say("Nothing to replace with.");
        return;
      }
      closeOverlay("snippet-picker");
      applyStructure({
        op: "replace-subsection",
        path: subPath,
        heading: heading,
        content: content,
      });
    };

    const renderRows = () => {
      const filter = searchEl.value.trim().toLowerCase();
      rowsEl.innerHTML = "";
      const visible = entries.filter(
        (entry) =>
          !filter ||
          entry.heading.toLowerCase().includes(filter) ||
          entry.content.toLowerCase().includes(filter)
      );
      if (!visible.length) {
        rowsEl.innerHTML = '<p class="picker-empty">No matching snippets.</p>';
        return;
      }
      visible.forEach((entry) => {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "picker-row";
        row.innerHTML =
          `<span class="row-kind">${escapeHtml(entry.heading)}</span>` +
          escapeHtml(
            entry.content.length > 220
              ? entry.content.slice(0, 219) + "…"
              : entry.content
          );
        addLevelChips(row, entry.variants, (content) => {
          chooseValue(entry.heading, content);
        });
        row.addEventListener("click", () => {
          chooseValue(entry.heading, entry.content);
        });
        rowsEl.appendChild(row);
      });
    };

    overlay.querySelector(".picker-close").addEventListener("click", () => {
      closeOverlay("snippet-picker");
    });
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) closeOverlay("snippet-picker");
    });
    searchEl.addEventListener("input", renderRows);

    say("Loading variations…");
    fetch(
      "/api/snippets?category=experience&search=" + encodeURIComponent(company)
    )
      .then(async (resp) => {
        if (!resp.ok) throw new Error(await resp.text());
        const snippets = await resp.json();
        entries = snippets
          .map((snippet) => ({
            heading: snippet.heading || "(no heading)",
            content: snippetContent(snippet),
            variants: snippet.variants || [],
          }))
          .filter((entry) => entry.content);
        say(entries.length + " variations available.");
        renderRows();
        searchEl.focus();
      })
      .catch((err) => say("Error: " + err.message));
  }

  /**
   * Remove an overlay element by id, if present, and unlock page scroll
   * once no picker overlay remains open.
   * @param {string} id
   */
  function closeOverlay(id) {
    const existing = document.getElementById(id);
    if (existing) existing.remove();
    if (!document.querySelector(".picker-overlay")) {
      document.body.classList.remove("overlay-open");
    }
  }

  /**
   * Build a small control strip for a list item.
   * @param {string} path
   * @returns {HTMLElement}
   */
  function makeItemControls(path) {
    const listPath = parentListPath(path);
    const index = itemIndex(path);
    const wrap = document.createElement("span");
    wrap.className = "struct-controls";
    wrap.contentEditable = "false";
    if (listPath === null || index === null) return wrap;

    const actions = [
      { label: "+", title: "Add below", op: "insert" },
      { label: "↑", title: "Move up", op: "move-up" },
      { label: "↓", title: "Move down", op: "move-down" },
      { label: "×", title: "Delete", op: "delete" },
    ];
    if (SNIPPET_SOURCES[listPath]) {
      actions.splice(1, 0, {
        label: "⇄",
        title: "Replace with a variation",
        op: "replace",
      });
    }
    actions.forEach((action) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "struct-btn";
      button.title = action.title;
      button.textContent = action.label;
      button.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (action.op === "insert") {
          if (SNIPPET_SOURCES[listPath]) {
            openSnippetPicker(listPath, index + 1);
          } else {
            applyStructure({
              op: "insert",
              path: listPath,
              index: index + 1,
            });
          }
        } else if (action.op === "replace") {
          openSnippetPicker(listPath, null, path);
        } else if (action.op === "delete") {
          if (!confirm("Delete this item?")) return;
          applyStructure({ op: "delete", path: path });
        } else if (action.op === "move-up") {
          applyStructure({ op: "move", path: path, offset: -1 });
        } else if (action.op === "move-down") {
          applyStructure({ op: "move", path: path, offset: 1 });
        }
      });
      wrap.appendChild(button);
    });
    return wrap;
  }

  /**
   * Inject hover structure controls next to editable list leaves.
   */
  function injectStructureControls() {
    document.querySelectorAll("[data-path]").forEach((node) => {
      const path = node.getAttribute("data-path") || "";
      // Only paths ending in [n] are list items we manage with move/delete
      // controls (e.g. skills.technical[2]); nested leaf fields like
      // person.github.handle or experience[0].company are plain text edits.
      if (!/\[\d+\]$/.test(path)) return;
      const controls = makeItemControls(path);
      if (!controls.childNodes.length) return;
      if (node.tagName === "LI" || node.tagName === "P" || node.tagName === "H3" || node.tagName === "H4" || node.tagName === "SPAN") {
        node.insertAdjacentElement("afterend", controls);
      } else {
        node.appendChild(controls);
      }
    });

    // Section-level adders for skills, bio, experience, education.
    addSectionButton(
      document.querySelector(".skills-block ul"),
      "skills.technical",
      "+ skill"
    );
    const skillBlocks = document.querySelectorAll(".skills-block ul");
    if (skillBlocks[1]) {
      addSectionButton(skillBlocks[1], "skills.functional", "+ skill");
    }
    // Custom sidebar panels: always-visible add/move/delete toolbar, plus
    // per-panel item adds. Controls stay visible on the navy sidebar.
    document.querySelectorAll(".side-panel").forEach((panelEl) => {
      const titleNode = panelEl.querySelector("h2[data-path]");
      if (!titleNode) return;
      const match = (titleNode.getAttribute("data-path") || "").match(
        /^panels\[(\d+)\]\.title$/
      );
      if (!match) return;
      const index = Number(match[1]);
      const panelPath = "panels[" + index + "]";
      panelEl.insertBefore(makePanelToolbar(panelPath, index), titleNode);
      addSectionButton(panelEl.querySelector("ul"), panelPath + ".items", "+ item");
    });
    addSectionButton(document.querySelector(".sidebar"), "panels", "+ side panel");

    addSectionButton(document.querySelector(".bio-block"), "bio", "+ bio paragraph");
    addSectionButton(document.querySelector(".content"), "experience", "+ job");
    addSectionButton(document.querySelector(".education ul"), "education", "+ education");

    document.querySelectorAll(".job").forEach((jobEl) => {
      const companyNode = jobEl.querySelector(".job-title[data-path]");
      if (!companyNode) return;
      const companyPath = companyNode.getAttribute("data-path") || "";
      const jobMatch = companyPath.match(/^experience\[(\d+)\]\.company$/);
      if (!jobMatch) return;
      const jobPath = `experience[${jobMatch[1]}]`;
      const subsectionsPath = `${jobPath}.subsections`;
      addSectionButton(jobEl, subsectionsPath, "+ subsection");

      // Whole-job controls: only per-field leaves (company, role, ...) carry
      // a data-path, so the generic per-item pass in injectStructureControls
      // never sees the job itself. Attach the same +/↑/↓/× strip explicitly.
      companyNode.insertAdjacentElement("afterend", makeItemControls(jobPath));

      // Swap a whole subsection for a database variation.
      const company = companyNode.textContent.trim();
      jobEl.querySelectorAll(".subsection").forEach((subEl, subIndex) => {
        const subPath = `${subsectionsPath}[${subIndex}]`;

        // Whole-subsection controls, same reasoning as the job strip above:
        // the subsection itself carries no data-path, only its heading/
        // paragraphs/bullets do. Lead with it so it works whether or not
        // the subsection has a heading to anchor to.
        subEl.insertBefore(makeItemControls(subPath), subEl.firstChild);

        const button = document.createElement("button");
        button.type = "button";
        button.className = "struct-add-section swap-subsection";
        button.textContent = "⇄ variation";
        button.title = "Replace this subsection with a snippet variation";
        button.addEventListener("click", (event) => {
          event.preventDefault();
          openSubsectionPicker(subPath, company);
        });
        subEl.appendChild(button);
      });
    });
  }

  /**
   * Always-visible toolbar for a custom sidebar panel (add / move / delete).
   * @param {string} panelPath - e.g. panels[0]
   * @param {number} index - panel index within panels
   * @returns {HTMLElement}
   */
  function makePanelToolbar(panelPath, index) {
    const bar = document.createElement("div");
    bar.className = "panel-toolbar";
    bar.contentEditable = "false";

    const actions = [
      {
        label: "+ panel",
        title: "Add a side panel below",
        run: () =>
          applyStructure({
            op: "insert",
            path: "panels",
            index: index + 1,
          }),
      },
      {
        label: "↑",
        title: "Move panel up",
        run: () => applyStructure({ op: "move", path: panelPath, offset: -1 }),
      },
      {
        label: "↓",
        title: "Move panel down",
        run: () => applyStructure({ op: "move", path: panelPath, offset: 1 }),
      },
      {
        label: "×",
        title: "Remove this side panel",
        run: () => {
          if (!confirm("Remove this side panel?")) return;
          applyStructure({ op: "delete", path: panelPath });
        },
      },
    ];
    actions.forEach((action) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "struct-btn";
      button.title = action.title;
      button.textContent = action.label;
      button.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        action.run();
      });
      bar.appendChild(button);
    });
    return bar;
  }

  /**
   * Append an "add" button after ``anchor`` for inserting into ``listPath``.
   * @param {Element|null} anchor
   * @param {string} listPath
   * @param {string} label
   */
  function addSectionButton(anchor, listPath, label) {
    if (!anchor) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "struct-add-section";
    button.textContent = label;
    button.addEventListener("click", (event) => {
      event.preventDefault();
      if (SNIPPET_SOURCES[listPath]) {
        openSnippetPicker(listPath, null);
      } else {
        applyStructure({ op: "insert", path: listPath });
      }
    });
    anchor.appendChild(button);
  }

  /**
   * Set person.photo in data.yaml and reload the page.
   * @param {string} dataPath - path relative to cv/web/ (e.g. ../../assets/…)
   * @returns {Promise<void>}
   */
  async function setPhoto(dataPath) {
    setStatus("Updating photo…");
    const resp = await fetch("/api/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify([{ path: "person.photo", value: dataPath }]),
    });
    if (!resp.ok) throw new Error("photo update failed: " + (await resp.text()));
    setStatus("Photo updated. Reloading…");
    window.location.reload();
  }

  /**
   * Close the image picker overlay if open.
   */
  function closeImagePicker() {
    const existing = document.getElementById("image-picker");
    if (existing) existing.remove();
    if (!document.querySelector(".picker-overlay")) {
      document.body.classList.remove("overlay-open");
    }
  }

  /**
   * Render the image gallery inside the picker.
   * @param {HTMLElement} gallery
   * @returns {Promise<void>}
   */
  async function loadGallery(gallery) {
    const resp = await fetch("/api/images");
    if (!resp.ok) throw new Error("failed to list images");
    const images = await resp.json();
    gallery.innerHTML = "";
    if (!images.length) {
      gallery.innerHTML = '<p class="picker-empty">No images yet — upload or grab one below.</p>';
      return;
    }
    images.forEach((img) => {
      const tile = document.createElement("button");
      tile.type = "button";
      tile.className = "picker-tile";
      tile.title = img.name + " (" + Math.round(img.size / 1024) + " KB)";
      tile.innerHTML =
        '<img src="' + img.web_path + '" alt="' + img.name + '">' +
        "<span>" + img.name + "</span>";
      tile.addEventListener("click", () => {
        setPhoto(img.data_path).catch((err) => setStatus("Error: " + err.message));
      });
      gallery.appendChild(tile);
    });
  }

  /**
   * Open the photo/image picker overlay.
   */
  function openImagePicker() {
    closeImagePicker();
    const overlay = document.createElement("div");
    overlay.id = "image-picker";
    overlay.className = "picker-overlay";
    overlay.innerHTML = `
      <div class="picker-panel">
        <div class="picker-head">
          <strong>Choose a photo / manage images</strong>
          <button type="button" class="picker-close" title="Close">×</button>
        </div>
        <p class="picker-hint">Click an image to set it as the photo. Uploads and grabs land in <code>assets/images/</code>.</p>
        <div class="picker-gallery"></div>
        <div class="picker-actions">
          <label class="picker-upload">
            Upload image
            <input type="file" accept=".png,.jpg,.jpeg,.gif,.webp,.svg,.ico" hidden>
          </label>
          <input type="url" class="picker-url" placeholder="https://… image or icon URL">
          <button type="button" class="picker-grab">Grab from URL</button>
        </div>
        <p class="picker-status"></p>
      </div>
    `;
    document.body.appendChild(overlay);
    document.body.classList.add("overlay-open");

    const gallery = overlay.querySelector(".picker-gallery");
    const pickerStatus = overlay.querySelector(".picker-status");
    const fileInput = overlay.querySelector('input[type="file"]');
    const urlInput = overlay.querySelector(".picker-url");

    const say = (msg) => {
      pickerStatus.textContent = msg;
    };

    overlay.querySelector(".picker-close").addEventListener("click", closeImagePicker);
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) closeImagePicker();
    });

    fileInput.addEventListener("change", async () => {
      const file = fileInput.files && fileInput.files[0];
      if (!file) return;
      say("Uploading " + file.name + "…");
      try {
        const form = new FormData();
        form.append("file", file);
        const resp = await fetch("/api/images/upload", { method: "POST", body: form });
        const body = await resp.json();
        if (!resp.ok) throw new Error(body.error || "upload failed");
        say("Uploaded " + body.name + ".");
        await loadGallery(gallery);
      } catch (err) {
        say("Error: " + err.message);
      } finally {
        fileInput.value = "";
      }
    });

    overlay.querySelector(".picker-grab").addEventListener("click", async () => {
      const url = urlInput.value.trim();
      if (!url) {
        say("Enter an image URL first.");
        return;
      }
      say("Grabbing image…");
      try {
        const resp = await fetch("/api/images/fetch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: url }),
        });
        const body = await resp.json();
        if (!resp.ok) throw new Error(body.error || "grab failed");
        say("Saved " + body.name + ".");
        urlInput.value = "";
        await loadGallery(gallery);
      } catch (err) {
        say("Error: " + err.message);
      }
    });

    loadGallery(gallery).catch((err) => say("Error: " + err.message));
  }

  /**
   * Make the sidebar photo clickable to open the picker in edit mode.
   */
  function enablePhotoPicker() {
    const photo = document.querySelector(".sidebar .photo");
    if (!photo) return;
    photo.classList.add("photo-editable");
    photo.title = "Click to change photo";
    photo.addEventListener("click", openImagePicker);
  }

  /* ---------- page boundary and margin guides ---------- */

  const PAGE_HEIGHT_PX = 11 * 96; // CSS inches: 1in = 96px, Letter height
  const GUIDE_MARGIN_SIDE_PX = 0.65 * 96; // matches --content-pad
  const PRINT_VMARGIN_PX = 0.5 * 96; // matches @page top/bottom margin
  // Content pages hold 10in of flow: 11in minus the two 0.5in @page margins.
  const CONTENT_PAGE_HEIGHT_PX = PAGE_HEIGHT_PX - 2 * PRINT_VMARGIN_PX;
  const PAGE_FIT_TOLERANCE_PX = 4;
  const PAGE_GAP_PX = 24; // dark divider drawn between simulated pages
  const GUIDES_OFF_KEY = "cvEditorGuidesOff";
  let guidesTimer = null;

  /**
   * Append a dashed page-break line with a label to the guides container.
   * @param {HTMLElement} container
   * @param {number} topPx
   * @param {number} pageNumber
   */
  function addBoundaryLine(container, topPx, pageNumber) {
    const line = document.createElement("div");
    line.className = "page-boundary";
    line.style.top = topPx + "px";
    line.innerHTML = '<span class="pb-label">Page ' + pageNumber + "</span>";
    container.appendChild(line);
  }

  /**
   * Append a dashed printable-area box to the guides container.
   * @param {HTMLElement} container
   * @param {number} topPx
   * @param {number} heightPx
   * @param {number} sheetWidthPx
   */
  function addMarginBox(container, topPx, heightPx, sheetWidthPx) {
    const box = document.createElement("div");
    box.className = "page-margin-box";
    box.style.top = topPx + "px";
    box.style.left = GUIDE_MARGIN_SIDE_PX + "px";
    box.style.width = sheetWidthPx - 2 * GUIDE_MARGIN_SIDE_PX + "px";
    box.style.height = heightPx + "px";
    container.appendChild(box);
  }

  /**
   * Append a dark "page cut" band (the gap between simulated pages).
   * @param {HTMLElement} container
   * @param {number} topPx
   * @param {number} pageNumber
   */
  function addPageCut(container, topPx, pageNumber) {
    const band = document.createElement("div");
    band.className = "page-cut";
    band.style.top = topPx + "px";
    band.innerHTML = '<span class="pb-label">Page ' + pageNumber + "</span>";
    container.appendChild(band);
  }

  /**
   * Remove pagination pushes applied by a previous guide render.
   */
  function resetPagination() {
    document.querySelectorAll("[data-page-push]").forEach((el) => {
      el.style.marginTop = "";
      el.removeAttribute("data-page-push");
    });
  }

  /**
   * True for editor-only elements that never print.
   * @param {?Element} el
   * @returns {boolean}
   */
  function isEditorChrome(el) {
    return Boolean(
      el &&
        el.classList &&
        (el.classList.contains("struct-controls") ||
          el.classList.contains("struct-add-section") ||
          el.classList.contains("panel-toolbar"))
    );
  }

  /**
   * True for heading-like blocks that must not be orphaned at a page end.
   * @param {?Element} el
   * @returns {boolean}
   */
  function isHeadingLike(el) {
    if (!el || !el.tagName) return false;
    if (["H2", "H3", "H4"].indexOf(el.tagName) !== -1) return true;
    return el.tagName === "P" && el.classList.contains("role");
  }

  /**
   * Element that should receive the push for ``atom``: walks up past
   * adjacent headings (mirroring ``break-after: avoid``) so a heading is
   * never left alone at the bottom of a page.
   * @param {Element} atom
   * @param {Element} content
   * @returns {Element}
   */
  function pushTarget(atom, content) {
    let target = atom;
    for (let hops = 0; hops < 6; hops += 1) {
      let prev = target.previousElementSibling;
      while (prev && isEditorChrome(prev)) prev = prev.previousElementSibling;
      if (!prev) {
        const parent = target.parentElement;
        if (!parent || parent === content || parent === document.body) break;
        target = parent;
        continue;
      }
      if (!isHeadingLike(prev)) break;
      const gap =
        target.getBoundingClientRect().top -
        prev.getBoundingClientRect().bottom;
      if (gap > 40) break;
      target = prev;
    }
    return target;
  }

  /**
   * Blocks that must not straddle a page cut, in document order. Whole
   * subsections that fit on a page count as one atom (mirroring their
   * ``break-inside: avoid``); oversized ones contribute their children.
   * @param {Element} content
   * @param {number} chunkPx - page capacity in screen pixels
   * @returns {Array<Element>}
   */
  function collectAtoms(content, chunkPx) {
    const atoms = [];
    let fittedSubsection = null;
    content
      .querySelectorAll("h2, h3, h4, p, li, .subsection")
      .forEach((el) => {
        if (fittedSubsection && fittedSubsection.contains(el)) return;
        const rect = el.getBoundingClientRect();
        if (rect.height <= 0) return;
        if (el.classList.contains("subsection")) {
          if (rect.height <= chunkPx * 0.9) {
            fittedSubsection = el;
            atoms.push(el);
          }
          return;
        }
        atoms.push(el);
      });
    return atoms;
  }

  /**
   * Measure hero/content heights with editor-only chrome hidden, so page
   * estimates reflect what actually prints.
   * @param {Element} hero
   * @param {?Element} content
   * @returns {{hero: number, content: number}}
   */
  function measurePrintHeights(hero, content) {
    document.body.classList.add("guides-measuring");
    const heights = {
      hero: hero.getBoundingClientRect().height,
      content: content ? content.getBoundingClientRect().height : 0,
    };
    document.body.classList.remove("guides-measuring");
    return heights;
  }

  /**
   * Paginate the editing surface visually and draw the guides.
   *
   * The hero prints on full-bleed pages (11in each); the content block
   * prints on pages with 0.5in top/bottom margins, so each holds 10in of
   * flow. Blocks that would straddle a page cut are pushed below a visible
   * page gap (mirroring print's ``break-inside: avoid``), so text never
   * crosses a margin or cut on screen either. Page capacity is scaled by
   * the ratio of on-screen flow (which includes editor chrome) to print
   * flow (measured with chrome hidden).
   */
  function renderPageGuides() {
    const old = document.getElementById("page-guides");
    if (old) old.remove();
    resetPagination();
    if (document.body.classList.contains("guides-off")) return;
    const hero = document.querySelector(".hero");
    if (!hero) return;
    const content = document.querySelector(".content");
    const printHeights = measurePrintHeights(hero, content);

    const heroRect = hero.getBoundingClientRect();
    const left = heroRect.left + window.scrollX;
    const top = heroRect.top + window.scrollY;
    const width = heroRect.width;
    const heroPages = Math.max(
      1,
      Math.ceil((printHeights.hero - PAGE_FIT_TOLERANCE_PX) / PAGE_HEIGHT_PX)
    );
    const heroScale = printHeights.hero > 0
      ? heroRect.height / printHeights.hero
      : 1;

    const container = document.createElement("div");
    container.id = "page-guides";
    container.style.left = left + "px";
    container.style.top = top + "px";
    container.style.width = width + "px";

    let pageNumber = 1;
    for (let k = 0; k < heroPages; k += 1) {
      if (k > 0) {
        pageNumber += 1;
        addBoundaryLine(container, k * PAGE_HEIGHT_PX * heroScale, pageNumber);
      }
      addMarginBox(
        container,
        (k * PAGE_HEIGHT_PX + PRINT_VMARGIN_PX) * heroScale,
        (PAGE_HEIGHT_PX - 2 * PRINT_VMARGIN_PX) * heroScale,
        width
      );
    }

    let totalHeight = heroRect.height;
    if (content) {
      const contentRect = content.getBoundingClientRect();
      const contentTopRel = contentRect.top + window.scrollY - top;
      const screenTextHeight = Math.max(
        0,
        contentRect.height - 2 * PRINT_VMARGIN_PX
      );
      const printTextHeight = Math.max(
        0,
        printHeights.content - 2 * PRINT_VMARGIN_PX
      );
      const chunkPx = printTextHeight > 0
        ? CONTENT_PAGE_HEIGHT_PX * (screenTextHeight / printTextHeight)
        : CONTENT_PAGE_HEIGHT_PX;
      const gapTotalPx = 2 * PRINT_VMARGIN_PX + PAGE_GAP_PX;

      // Hero → content seam: the first content page starts here.
      pageNumber += 1;
      addPageCut(container, contentTopRel, pageNumber);
      const textTopAbs = contentRect.top + window.scrollY + PRINT_VMARGIN_PX;
      addMarginBox(container, textTopAbs - top, chunkPx, width);

      let pageEndAbs = textTopAbs + chunkPx;
      const atoms = collectAtoms(content, chunkPx);
      for (const atom of atoms) {
        let rect = atom.getBoundingClientRect();
        let atomTop = rect.top + window.scrollY;
        const atomBottom = atomTop + rect.height;
        if (atomBottom <= pageEndAbs + PAGE_FIT_TOLERANCE_PX) continue;

        if (rect.height > chunkPx) {
          // Too tall for any page: it will split in print too, so just
          // mark the cuts it crosses without pushing.
          while (pageEndAbs < atomBottom - PAGE_FIT_TOLERANCE_PX) {
            pageNumber += 1;
            addBoundaryLine(container, pageEndAbs - top, pageNumber);
            pageEndAbs += chunkPx;
          }
          continue;
        }

        // Push the atom (or its attached heading) below a visible gap.
        const target = pushTarget(atom, content);
        const targetTop =
          target.getBoundingClientRect().top + window.scrollY;
        const push = Math.max(0, pageEndAbs + gapTotalPx - targetTop);
        if (push > 0) {
          const current = parseFloat(target.style.marginTop) || 0;
          target.style.marginTop = current + push + "px";
          target.setAttribute("data-page-push", "1");
        }
        const newStartAbs =
          target.getBoundingClientRect().top + window.scrollY;
        pageNumber += 1;
        addPageCut(
          container,
          newStartAbs - PRINT_VMARGIN_PX - PAGE_GAP_PX - top,
          pageNumber
        );
        addMarginBox(container, newStartAbs - top, chunkPx, width);
        pageEndAbs = newStartAbs + chunkPx;
      }
      totalHeight =
        content.getBoundingClientRect().bottom + window.scrollY - top;
    }

    container.style.height = totalHeight + "px";
    document.body.appendChild(container);
  }

  /**
   * Re-render guides after layout settles (debounced).
   */
  function schedulePageGuides() {
    if (guidesTimer) clearTimeout(guidesTimer);
    guidesTimer = setTimeout(renderPageGuides, 300);
  }

  /**
   * Wire up the guides: initial render, toolbar toggle, and re-render on
   * resize or content changes so the boundaries track the live layout.
   */
  function setupPageGuides() {
    if (localStorage.getItem(GUIDES_OFF_KEY) === "1") {
      document.body.classList.add("guides-off");
    }
    renderPageGuides();
    window.addEventListener("resize", schedulePageGuides);

    const observer = new MutationObserver((mutations) => {
      const guides = document.getElementById("page-guides");
      const relevant = mutations.some((m) => {
        // Body class flips are our own doing (measuring, guides toggle);
        // preview open/close re-renders explicitly.
        if (m.target === document.body && m.type === "attributes") {
          return false;
        }
        if (guides && guides.contains(m.target)) return false;
        if (m.type === "childList") {
          const nodes = Array.from(m.addedNodes).concat(
            Array.from(m.removedNodes)
          );
          if (nodes.length && nodes.every((n) => n.id === "page-guides")) {
            return false;
          }
        }
        return true;
      });
      if (relevant) schedulePageGuides();
    });
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["class", "src"],
    });

    const toolbarEl = document.getElementById("editor-toolbar");
    if (toolbarEl) {
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.id = "btn-guides";
      const label = () =>
        document.body.classList.contains("guides-off")
          ? "Show page guides"
          : "Hide page guides";
      toggle.textContent = label();
      toggle.addEventListener("click", () => {
        const off = document.body.classList.toggle("guides-off");
        localStorage.setItem(GUIDES_OFF_KEY, off ? "1" : "0");
        toggle.textContent = label();
        if (off) {
          resetPagination();
        } else {
          renderPageGuides();
        }
      });
      toolbarEl.insertBefore(toggle, toolbarEl.querySelector(".editor-links"));
    }
  }

  /* ---------- undo / redo ---------- */

  let undoBtn = null;
  let redoBtn = null;
  let historyBusy = false;

  /**
   * Refresh Undo/Redo button enabled state from the server.
   * @returns {Promise<void>}
   */
  async function refreshHistoryButtons() {
    if (!undoBtn || !redoBtn) return;
    try {
      const resp = await fetch("/api/history");
      if (!resp.ok) return;
      const status = await resp.json();
      undoBtn.disabled = !status.can_undo || historyBusy;
      redoBtn.disabled = !status.can_redo || historyBusy;
    } catch (_err) {
      // Leave buttons as-is if the status check fails.
    }
  }

  /**
   * True when on-screen contenteditable values differ from their initial load.
   * @returns {boolean}
   */
  function hasUnsavedEdits() {
    let dirty = false;
    document.querySelectorAll("[data-path][data-initial]").forEach((node) => {
      if (node.textContent.trim() !== (node.getAttribute("data-initial") || "")) {
        dirty = true;
      }
    });
    return dirty;
  }

  /**
   * Remember the loaded text of each editable node for dirty detection.
   */
  function captureInitialEdits() {
    document.querySelectorAll("[data-path]").forEach((node) => {
      node.setAttribute("data-initial", node.textContent.trim());
    });
  }

  /**
   * Undo or redo a persisted data.yaml change, saving any dirty typing first.
   * @param {"undo"|"redo"} direction
   * @returns {Promise<void>}
   */
  async function runHistory(direction) {
    if (historyBusy) return;
    historyBusy = true;
    if (undoBtn) undoBtn.disabled = true;
    if (redoBtn) redoBtn.disabled = true;
    setStatus(direction === "undo" ? "Undoing…" : "Redoing…");
    try {
      if (hasUnsavedEdits()) {
        await saveEdits();
      }
      const resp = await fetch("/api/" + direction, { method: "POST" });
      const body = await resp.json();
      if (!resp.ok) throw new Error(body.error || direction + " failed");
      setStatus(
        (direction === "undo" ? "Undid" : "Redid") +
          " " +
          (body.label || "edit") +
          ". Reloading…"
      );
      window.location.reload();
    } catch (err) {
      setStatus("Error: " + err.message);
      historyBusy = false;
      refreshHistoryButtons();
    }
  }

  /**
   * Wire Undo/Redo toolbar buttons and keyboard shortcuts.
   */
  function setupHistoryControls() {
    const toolbarEl = document.getElementById("editor-toolbar");
    if (!toolbarEl) return;

    undoBtn = document.createElement("button");
    undoBtn.type = "button";
    undoBtn.id = "btn-undo";
    undoBtn.title = "Undo (Ctrl/⌘Z)";
    undoBtn.textContent = "Undo";
    undoBtn.disabled = true;
    undoBtn.addEventListener("click", () => runHistory("undo"));

    redoBtn = document.createElement("button");
    redoBtn.type = "button";
    redoBtn.id = "btn-redo";
    redoBtn.title = "Redo (Ctrl/⌘⇧Z or Ctrl/⌘Y)";
    redoBtn.textContent = "Redo";
    redoBtn.disabled = true;
    redoBtn.addEventListener("click", () => runHistory("redo"));

    const saveBtn = document.getElementById("btn-save");
    if (saveBtn && saveBtn.nextSibling) {
      toolbarEl.insertBefore(redoBtn, saveBtn.nextSibling);
      toolbarEl.insertBefore(undoBtn, redoBtn);
    } else {
      toolbarEl.appendChild(undoBtn);
      toolbarEl.appendChild(redoBtn);
    }

    document.addEventListener("keydown", (event) => {
      const key = (event.key || "").toLowerCase();
      const mod = event.metaKey || event.ctrlKey;
      if (!mod) return;
      // Let the browser handle in-field typing undo while focused in an
      // editable node and there are local unsaved keystrokes — except when
      // the user presses Undo with no local dirty state, then hit the server.
      const inField =
        document.activeElement &&
        document.activeElement.isContentEditable;
      if (key === "z" && !event.shiftKey) {
        if (inField && hasUnsavedEdits()) return; // native typing undo
        event.preventDefault();
        runHistory("undo");
      } else if ((key === "z" && event.shiftKey) || key === "y") {
        event.preventDefault();
        runHistory("redo");
      }
    });

    captureInitialEdits();
    refreshHistoryButtons();
  }

  // Link back to the rest of the app from the toolbar.
  const toolbar = document.getElementById("editor-toolbar");
  if (toolbar) {
    const links = document.createElement("span");
    links.className = "editor-links";
    links.innerHTML =
      '<a href="/cv/web/">Home</a> · <a href="/cv/web/build">Tailor</a> · ' +
      '<a href="/cv/web/library">Library</a> · <a href="/cv/web/variants">Versions</a> · ' +
      '<a href="/cv/web/docs">How to use</a>';
    toolbar.appendChild(links);
  }

  btn.addEventListener("click", saveAndPreview);
  injectStructureControls();
  enablePhotoPicker();
  setupPageGuides();
  setupHistoryControls();
})();
