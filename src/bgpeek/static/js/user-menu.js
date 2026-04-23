/** User-menu dropdown clamping.
 *
 * When the panel would overflow the viewport on narrow screens, shift it
 * inward so it stays clickable. Pure layout behaviour — extracted from an
 * inline <script> so the page-wide CSP can stay strict.
 */
(function () {
  "use strict";

  function wire(details) {
    if (!details || details.dataset.userMenuBound === "1") return;
    var panel = details.querySelector("[data-user-menu-panel]");
    if (!panel) return;
    details.dataset.userMenuBound = "1";

    function clampMenuToViewport() {
      panel.style.transform = "";
      var rect = panel.getBoundingClientRect();
      var gutter = 8;
      var shift = 0;
      if (rect.right > window.innerWidth - gutter) {
        shift = window.innerWidth - gutter - rect.right;
      }
      if (rect.left + shift < gutter) {
        shift += gutter - (rect.left + shift);
      }
      if (shift !== 0) {
        panel.style.transform = "translateX(" + shift + "px)";
      }
    }

    function resetMenuClamp() {
      panel.style.transform = "";
    }

    details.addEventListener("toggle", function () {
      if (details.open) {
        clampMenuToViewport();
      } else {
        resetMenuClamp();
      }
    });

    window.addEventListener("resize", function () {
      if (details.open) clampMenuToViewport();
    });
  }

  function wireAll() {
    document.querySelectorAll("details[data-user-menu]").forEach(wire);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wireAll);
  } else {
    wireAll();
  }
  // Re-wire after htmx swaps so partial re-renders pick up the listener.
  document.addEventListener("htmx:afterSwap", wireAll);
})();
