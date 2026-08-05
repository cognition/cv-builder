(function () {
  "use strict";

  const personalGrid = document.getElementById("personal-assets");
  const iconGrid = document.getElementById("icon-assets");
  const assetCount = document.getElementById("asset-count");
  const inspectorEmpty = document.getElementById("inspector-empty");
  const inspectorDetail = document.getElementById("inspector-detail");
  const inspectorPreview = document.getElementById("inspector-preview");
  const inspectorName = document.getElementById("inspector-name");
  const inspectorMeta = document.getElementById("inspector-meta");
  const useAssetBtn = document.getElementById("use-asset");
  const filters = [...document.querySelectorAll("[data-asset-filter]")];
  const search = document.getElementById("asset-search");
  const modal = document.getElementById("asset-modal");
  const toast = document.getElementById("toast");

  // GitHub / GitLab use monochrome SVG brand marks so the tiles read as
  // real logos; other contact icons keep compact glyph labels.
  const GITHUB_MARK =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/></svg>';
  const GITLAB_MARK =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M23.955 13.209l-1.316-4.054-2.623-8.068a.455.455 0 00-.864-.003L16.5 9.147H7.504L4.852 1.084a.455.455 0 00-.863.003L1.366 9.145.046 13.21a.924.924 0 00.331 1.023L12.006 23l11.616-8.767a.92.92 0 00.333-1.024"/></svg>';

  const BUILT_IN_ICONS = [
    { name: "LinkedIn", cls: "linkedin", glyph: "in" },
    { name: "GitHub", cls: "github", glyph: GITHUB_MARK },
    { name: "GitLab", cls: "gitlab", glyph: GITLAB_MARK },
    { name: "Medium", cls: "medium", glyph: "M" },
    { name: "Instagram", cls: "instagram", glyph: "&#9678;" },
    { name: "Email", cls: "email", glyph: "&#9993;" },
    { name: "Website", cls: "website", glyph: "&#9678;" },
    { name: "Phone", cls: "phone", glyph: "&#9742;" },
  ];

  let images = [];
  let personPhotoPath = "";
  let selectedDataPath = null;

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

  function formatSize(bytes) {
    if (bytes > 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    return Math.round(bytes / 1024) + " KB";
  }

  function isProfilePhoto(image) {
    if (!personPhotoPath) return false;
    return personPhotoPath.replace(/^\.\.\/\.\.\//, "") === image.web_path.replace(/^\//, "");
  }

  function renderPersonalAssets() {
    personalGrid.querySelectorAll(".asset-card:not(.add-card)").forEach((el) => el.remove());
    const addCard = personalGrid.querySelector(".add-card");
    images.forEach((image) => {
      const kind = isProfilePhoto(image) ? "photo" : "logo";
      const card = document.createElement("button");
      card.type = "button";
      card.className = "asset-card";
      card.dataset.kind = kind;
      card.dataset.name = image.name;
      card.dataset.dataPath = image.data_path;
      card.dataset.webPath = image.web_path;
      card.innerHTML = `
        <span class="asset-preview"><img src="${escapeHtml(image.web_path)}" alt="${escapeHtml(image.name)}"></span>
        <b>${escapeHtml(image.name)}</b>
        <small>${kind === "photo" ? "Current profile photo" : formatSize(image.size)}</small>
      `;
      card.addEventListener("click", () => selectCard(card));
      personalGrid.insertBefore(card, addCard);
    });
    assetCount.textContent = images.length;
    applyFilter();
  }

  function renderIcons() {
    iconGrid.innerHTML = BUILT_IN_ICONS.map(
      (icon) => `
      <button type="button" class="asset-card" data-kind="icon" data-name="${escapeHtml(icon.name)}">
        <span class="asset-preview social ${icon.cls}">${icon.glyph}</span>
        <b>${escapeHtml(icon.name)}</b>
        <small>Built-in icon</small>
      </button>`
    ).join("");
    iconGrid.querySelectorAll(".asset-card").forEach((card) => {
      card.addEventListener("click", () => selectCard(card));
    });
  }

  function selectCard(card) {
    document.querySelectorAll(".asset-card").forEach((c) => c.classList.remove("selected"));
    card.classList.add("selected");
    inspectorEmpty.style.display = "none";
    inspectorDetail.classList.add("open");
    inspectorName.textContent = card.dataset.name;
    const source = card.querySelector(".asset-preview");
    inspectorPreview.className = source.className;
    inspectorPreview.innerHTML = source.innerHTML;
    if (card.dataset.kind === "icon") {
      inspectorMeta.textContent = "Built-in icon — always available, no upload needed.";
      useAssetBtn.style.display = "none";
      selectedDataPath = null;
    } else {
      inspectorMeta.textContent = card.dataset.kind === "photo" ? "Currently used as your profile photo." : "Uploaded logo or image.";
      useAssetBtn.style.display = "";
      useAssetBtn.disabled = card.dataset.kind === "photo";
      useAssetBtn.textContent = card.dataset.kind === "photo" ? "Already your profile photo" : "Use as profile photo";
      selectedDataPath = card.dataset.dataPath;
    }
  }

  function applyFilter() {
    const kind = document.querySelector("[data-asset-filter].active").dataset.assetFilter;
    const term = search.value.toLowerCase();
    document.querySelectorAll(".asset-card[data-kind]").forEach((card) => {
      const matchesKind = kind === "all" || card.dataset.kind === kind;
      const matchesTerm = card.dataset.name.toLowerCase().includes(term);
      card.hidden = !(matchesKind && matchesTerm);
    });
  }

  filters.forEach((button) =>
    button.addEventListener("click", () => {
      filters.forEach((b) => b.classList.remove("active"));
      button.classList.add("active");
      applyFilter();
    })
  );
  search.addEventListener("input", applyFilter);

  useAssetBtn.addEventListener("click", async () => {
    if (!selectedDataPath) return;
    useAssetBtn.disabled = true;
    try {
      const resp = await fetch("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify([{ path: "person.photo", value: selectedDataPath }]),
      });
      if (!resp.ok) throw new Error(await resp.text());
      showToast("Profile photo updated.");
      await loadPerson();
      renderPersonalAssets();
    } catch (err) {
      showToast("Error: " + err.message);
      useAssetBtn.disabled = false;
    }
  });

  async function loadPerson() {
    const resp = await fetch("/api/person");
    if (resp.ok) {
      const person = await resp.json();
      personPhotoPath = person.photo || "";
    }
  }

  async function loadImages() {
    const resp = await fetch("/api/images");
    if (!resp.ok) throw new Error("failed to load assets");
    images = await resp.json();
    renderPersonalAssets();
  }

  // ---------- upload modal ----------

  const dropZone = document.getElementById("drop-zone");
  const fileInput = document.getElementById("asset-file");
  const sourceTabs = [...document.querySelectorAll("[data-source]")];

  document.getElementById("upload-trigger").addEventListener("click", () => modal.classList.add("open"));
  document.getElementById("close-asset-modal").addEventListener("click", () => modal.classList.remove("open"));
  modal.addEventListener("click", (event) => {
    if (event.target === modal) modal.classList.remove("open");
  });

  sourceTabs.forEach((button) =>
    button.addEventListener("click", () => {
      sourceTabs.forEach((b) => b.classList.remove("active"));
      button.classList.add("active");
      document.querySelectorAll(".source-panel").forEach((p) => p.classList.remove("active"));
      document.getElementById("source-" + button.dataset.source).classList.add("active");
    })
  );

  document.getElementById("choose-file").addEventListener("click", () => fileInput.click());
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
  dropZone.addEventListener("drop", (event) => {
    if (event.dataTransfer.files.length) uploadFile(event.dataTransfer.files[0]);
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) uploadFile(fileInput.files[0]);
  });

  async function uploadFile(file) {
    const form = new FormData();
    form.append("file", file);
    try {
      const resp = await fetch("/api/images/upload", { method: "POST", body: form });
      const body = await resp.json();
      if (!resp.ok) throw new Error(body.error || "upload failed");
      modal.classList.remove("open");
      showToast(`${body.name} added.`);
      await loadImages();
    } catch (err) {
      showToast("Error: " + err.message);
    }
  }

  document.getElementById("import-url").addEventListener("click", async () => {
    const urlInput = document.getElementById("asset-url");
    const url = urlInput.value.trim();
    if (!url) {
      showToast("Enter an image URL first");
      return;
    }
    try {
      const resp = await fetch("/api/images/fetch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const body = await resp.json();
      if (!resp.ok) throw new Error(body.error || "fetch failed");
      modal.classList.remove("open");
      urlInput.value = "";
      showToast(`${body.name} imported.`);
      await loadImages();
    } catch (err) {
      showToast("Error: " + err.message);
    }
  });

  renderIcons();
  Promise.all([loadPerson(), loadImages()]).catch((err) => showToast("Error: " + err.message));
})();
