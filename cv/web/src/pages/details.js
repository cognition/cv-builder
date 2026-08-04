(function () {
  "use strict";

  const PROVIDERS = ["linkedin", "github", "gitlab", "medium", "instagram", "website"];
  const PROVIDER_LABELS = {
    linkedin: "LinkedIn",
    github: "GitHub",
    gitlab: "GitLab",
    medium: "Medium",
    instagram: "Instagram",
    website: "Website",
  };
  const PROVIDER_GLYPHS = {
    linkedin: "in",
    github: "GH",
    gitlab: "GL",
    medium: "M",
    instagram: "IG",
    website: "&#9678;",
  };

  const toast = document.getElementById("toast");
  const statusEl = document.getElementById("details-status");
  const profileList = document.getElementById("profile-list");

  const fields = {
    "first-name": "first",
    "last-name": "last",
    headline: "headline",
    email: "email",
    phone: "phone",
  };

  let profiles = [];
  let photoWebPath = "";

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => toast.classList.remove("show"), 2100);
  }

  function setStatus(message) {
    statusEl.textContent = message;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function toWebPath(dataPath) {
    // person.photo is stored relative to cv/web/ (e.g. "../../assets/images/x.jpg").
    if (!dataPath) return "";
    if (/^https?:\/\//i.test(dataPath)) return dataPath;
    return "/" + dataPath.replace(/^(\.\.\/)+/, "");
  }

  function updatePreview() {
    Object.entries(fields).forEach(([id, key]) => {
      document.getElementById("preview-" + key).textContent = document.getElementById(id).value;
    });
    const mode = document.querySelector('[name="address-display"]:checked').value;
    const city = document.getElementById("city").value;
    const region = document.getElementById("region").value;
    const country = document.getElementById("country").value;
    const street = document.getElementById("street").value;
    const row = document.getElementById("preview-location-row");
    if (mode === "hide") {
      row.hidden = true;
    } else {
      row.hidden = false;
      document.getElementById("preview-location").textContent =
        mode === "full" ? [street, city, region, country].filter(Boolean).join(", ") : [city, country].filter(Boolean).join(", ");
    }
    const socials = document.getElementById("preview-socials");
    socials.innerHTML = profiles
      .filter((p) => p.visible && p.handle)
      .map((p) => `<span>${PROVIDER_GLYPHS[p.provider] || "?"} ${escapeHtml(p.handle)}</span>`)
      .join("");
  }

  function renderProfiles() {
    profileList.innerHTML = "";
    profiles.forEach((profile, index) => {
      const row = document.createElement("div");
      row.className = "profile-row";
      row.innerHTML = `
        <span class="profile-logo ${profile.provider}">${PROVIDER_GLYPHS[profile.provider] || "?"}</span>
        <select>${PROVIDERS.map((p) => `<option value="${p}" ${p === profile.provider ? "selected" : ""}>${PROVIDER_LABELS[p]}</option>`).join("")}</select>
        <input class="social-url" placeholder="Profile URL or username" value="${escapeHtml(profile.handle || "")}">
        <label class="show-toggle"><input type="checkbox" ${profile.visible ? "checked" : ""}><i></i></label>
        <button type="button" class="remove-profile">&times;</button>
      `;
      const select = row.querySelector("select");
      const urlInput = row.querySelector(".social-url");
      const toggle = row.querySelector('input[type="checkbox"]');
      const logo = row.querySelector(".profile-logo");
      select.addEventListener("change", () => {
        profile.provider = select.value;
        logo.className = "profile-logo " + profile.provider;
        logo.innerHTML = PROVIDER_GLYPHS[profile.provider] || "?";
        updatePreview();
      });
      urlInput.addEventListener("input", () => {
        profile.handle = urlInput.value;
        updatePreview();
      });
      toggle.addEventListener("change", () => {
        profile.visible = toggle.checked;
        updatePreview();
      });
      row.querySelector(".remove-profile").addEventListener("click", () => {
        profiles.splice(index, 1);
        renderProfiles();
        updatePreview();
      });
      profileList.appendChild(row);
    });
  }

  async function load() {
    const resp = await fetch("/api/person");
    if (!resp.ok) throw new Error("failed to load personal details");
    const person = await resp.json();

    document.getElementById("first-name").value = person.first_name || "";
    document.getElementById("last-name").value = person.last_name || "";
    document.getElementById("headline").value = person.tagline || "";
    document.getElementById("email").value = person.email || "";
    document.getElementById("phone").value = person.mobile || "";

    const address = person.address || {};
    document.getElementById("city").value = address.city || "";
    document.getElementById("region").value = address.region || "";
    document.getElementById("country").value = address.country || "";
    document.getElementById("postal-code").value = address.postal_code || "";
    document.getElementById("street").value = address.street || "";
    const mode = address.display || "city";
    const radio = document.querySelector(`[name="address-display"][value="${mode}"]`);
    if (radio) radio.checked = true;

    profiles = (person.profiles || []).map((p) => ({ ...p }));
    renderProfiles();

    photoWebPath = toWebPath(person.photo);
    if (photoWebPath) {
      document.getElementById("photo-thumb").style.backgroundImage = `url(${photoWebPath})`;
      document.getElementById("preview-photo").style.backgroundImage = `url(${photoWebPath})`;
    }

    updatePreview();
    setStatus("Loaded.");
  }

  document.querySelectorAll(".preview-field, [name='address-display'], #city, #region, #country, #street").forEach((input) => {
    input.addEventListener("input", updatePreview);
    input.addEventListener("change", updatePreview);
  });

  document.getElementById("add-profile").addEventListener("click", () => {
    profiles.push({ provider: "website", handle: "", url: "", visible: true });
    renderProfiles();
    const inputs = profileList.querySelectorAll(".social-url");
    if (inputs.length) inputs[inputs.length - 1].focus();
  });

  document.getElementById("save-details").addEventListener("click", async () => {
    setStatus("Saving…");
    const edits = [
      { path: "person.first_name", value: document.getElementById("first-name").value.trim() },
      { path: "person.last_name", value: document.getElementById("last-name").value.trim() },
      { path: "person.tagline", value: document.getElementById("headline").value.trim() },
      { path: "person.email", value: document.getElementById("email").value.trim() },
      { path: "person.mobile", value: document.getElementById("phone").value.trim() },
      {
        path: "person.address",
        value: {
          city: document.getElementById("city").value.trim(),
          region: document.getElementById("region").value.trim(),
          country: document.getElementById("country").value.trim(),
          postal_code: document.getElementById("postal-code").value.trim(),
          street: document.getElementById("street").value.trim(),
          display: document.querySelector('[name="address-display"]:checked').value,
        },
      },
      {
        path: "person.profiles",
        value: profiles.map((p) => ({
          provider: p.provider,
          handle: p.handle,
          url: p.url || "",
          visible: Boolean(p.visible),
        })),
      },
    ];
    try {
      const resp = await fetch("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(edits),
      });
      if (!resp.ok) throw new Error(await resp.text());
      showToast("Personal details saved.");
      setStatus("Saved.");
    } catch (err) {
      setStatus("Error: " + err.message);
      showToast("Save failed — see status line.");
    }
  });

  load().catch((err) => setStatus("Error: " + err.message));
})();
