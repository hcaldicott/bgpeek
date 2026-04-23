/** Delegated event handlers for UI widgets that were previously wired via
 * inline `onclick=` / `onsubmit=` attributes. The page-wide CSP is
 * `script-src 'self'` — inline attribute handlers are blocked, so templates
 * now tag the interactive element with a `data-action` + supporting
 * `data-*` attributes and this single delegated listener dispatches.
 *
 * Kept deliberately compact; per-page logic that needs closures / module
 * state (index.js, multi-result.js, admin-devices-form.js, etc.) lives in
 * its own file.
 */
(function () {
  "use strict";

  function handleClick(evt) {
    var trigger = evt.target.closest("[data-action]");
    if (!trigger) return;
    var action = trigger.dataset.action;

    if (action === "dismiss-parent") {
      var parent = trigger.parentElement;
      if (parent) parent.remove();
      return;
    }

    if (action === "copy") {
      var value = trigger.dataset.copyValue || "";
      if (window.bgpeekCopyText) {
        window.bgpeekCopyText(value);
      } else if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(value);
      }
      var confirmed = trigger.dataset.copiedLabel;
      if (confirmed) {
        var original = trigger.textContent;
        trigger.textContent = confirmed;
        setTimeout(function () {
          trigger.textContent = original;
        }, 1500);
      }
      return;
    }

    if (action === "share-permalink") {
      var base = trigger.dataset.shareUrl || "";
      // Support relative paths; resolve against the current origin.
      var url = /^https?:/.test(base) ? base : window.location.origin + base;
      if (window.bgpeekShare) {
        window.bgpeekShare(
          trigger,
          url,
          trigger.dataset.copiedLabel || "Copied",
          trigger.dataset.shareLabel || "Share",
        );
      }
      return;
    }

    if (action === "copy-permalink") {
      var pathOrUrl = trigger.dataset.shareUrl || "";
      var finalUrl = /^https?:/.test(pathOrUrl)
        ? pathOrUrl
        : window.location.origin + pathOrUrl;
      var copiedLabel = trigger.dataset.copiedLabel || "Copied";
      var shareLabel = trigger.dataset.shareLabel || "Share";
      if (!window.bgpeekCopyText) return;
      window.bgpeekCopyText(finalUrl).then(function () {
        trigger.textContent = copiedLabel;
        setTimeout(function () {
          trigger.textContent = shareLabel;
        }, 1500);
      });
      return;
    }
  }

  function handleSubmit(evt) {
    var form = evt.target;
    if (!form || form.tagName !== "FORM") return;
    var prompt = form.dataset.confirm;
    if (!prompt) return;
    if (!window.confirm(prompt)) {
      evt.preventDefault();
      evt.stopPropagation();
    }
  }

  document.addEventListener("click", handleClick);
  document.addEventListener("submit", handleSubmit, true);
})();
