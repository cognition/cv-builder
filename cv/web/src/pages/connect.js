(function () {
  "use strict";

  const toast = document.getElementById("toast");

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => toast.classList.remove("show"), 2100);
  }

  document.querySelectorAll(".copy").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(button.dataset.copy);
        showToast("Copied to clipboard");
      } catch (_err) {
        showToast("Copy unavailable in this browser");
      }
    });
  });

  const MCP_HTTP_URL = "http://127.0.0.1:8765/mcp";

  document.getElementById("test-mcp").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const result = document.getElementById("test-result");
    button.textContent = "Checking…";
    button.disabled = true;
    result.className = "";
    result.textContent = "";
    try {
      // Any settled response (even an opaque/CORS-blocked one) means the
      // MCP server accepted a TCP connection on that port; a thrown
      // TypeError means nothing is listening there.
      await fetch(MCP_HTTP_URL, { mode: "no-cors" });
      result.className = "ok";
      result.textContent = "✓ Something is responding on " + MCP_HTTP_URL;
    } catch (_err) {
      result.className = "fail";
      result.textContent =
        "✗ No response from " + MCP_HTTP_URL + " (only checks the Docker HTTP transport, not stdio)";
    } finally {
      button.textContent = "Test HTTP connection";
      button.disabled = false;
    }
  });
})();
