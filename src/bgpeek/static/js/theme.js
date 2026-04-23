/** Dark/light theme toggle for bgpeek.
 *
 * The visible toggle buttons live in `partials/header.html` and are tagged
 * `data-theme-toggle` (not `onclick="bgpeekToggleTheme()"`) so the page-wide
 * CSP can enforce `script-src 'self'` without allowing inline event handlers.
 */
(function () {
  "use strict";

  var STORAGE_KEY =
    document.documentElement.getAttribute("data-theme-storage-key") || "bgpeek-theme";

  function applyTheme(dark) {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem(STORAGE_KEY, dark ? "dark" : "light");
  }

  function toggle() {
    applyTheme(!document.documentElement.classList.contains("dark"));
  }

  // Kept for any extension / deep-link that still calls it.
  window.bgpeekToggleTheme = toggle;

  function wireToggleButtons() {
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      if (btn.dataset.themeToggleBound === "1") return;
      btn.dataset.themeToggleBound = "1";
      btn.addEventListener("click", toggle);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wireToggleButtons);
  } else {
    wireToggleButtons();
  }
  // Re-wire after htmx swaps, so header partials re-rendered out-of-band
  // pick up the listener.
  document.addEventListener("htmx:afterSwap", wireToggleButtons);

  // Apply stored preference (flash-prevention also runs `theme-init.js` from <head>).
  var stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "dark") {
    applyTheme(true);
  } else if (stored === "light") {
    applyTheme(false);
  }
})();
