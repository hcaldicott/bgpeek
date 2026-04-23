/** Flash-prevention: apply dark mode before first paint.
 *
 * Must run synchronously from <head> so the body never paints with the wrong
 * theme. Extracted from an inline <script> so the page-wide CSP can enforce
 * `script-src 'self'` without an `'unsafe-inline'` carve-out.
 */
(function () {
  "use strict";
  var k = document.documentElement.getAttribute("data-theme-storage-key") || "bgpeek-theme";
  var s = localStorage.getItem(k);
  if (s === "dark" || (!s && window.matchMedia("(prefers-color-scheme: dark)").matches)) {
    document.documentElement.classList.add("dark");
  }
})();
