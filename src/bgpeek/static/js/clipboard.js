/**
 * Copy text to clipboard with fallback for plain HTTP.
 * Tries navigator.clipboard first (HTTPS + localhost),
 * falls back to execCommand('copy') with a temporary textarea.
 *
 * @param {string} text - Text to copy.
 * @returns {Promise<boolean>} Resolves true on success.
 */
function bgpeekCopyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        return navigator.clipboard.writeText(text).then(
            function () { return true; },
            function () { return bgpeekCopyFallback(text); }
        );
    }
    return Promise.resolve(bgpeekCopyFallback(text));
}

function bgpeekCopyFallback(text) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    var ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { /* ignore */ }
    document.body.removeChild(ta);
    return ok;
}

/**
 * Copy a permalink and show visual feedback on the button.
 *
 * @param {HTMLElement} btn - The button element.
 * @param {string} url - URL to copy.
 * @param {string} copiedLabel - Translated "Copied!" text.
 * @param {string} defaultLabel - Translated "Share" text.
 */
/**
 * Copy the sibling ".bgp-line" element's text. Used by per-line copy
 * buttons in detailed BGP output.
 *
 * @param {HTMLElement} btn - The copy button element.
 */
function bgpeekCopyLine(btn) {
    var row = btn.parentElement;
    if (!row) return;
    var line = row.querySelector(".bgp-line");
    if (!line) return;
    bgpeekCopyText(line.textContent).then(function (ok) {
        if (!ok) return;
        var icon = btn.querySelector(".copy-icon");
        var check = btn.querySelector(".copy-check");
        if (icon) icon.classList.add("hidden");
        if (check) check.classList.remove("hidden");
        setTimeout(function () {
            if (icon) icon.classList.remove("hidden");
            if (check) check.classList.add("hidden");
        }, 1200);
    });
}

function bgpeekShare(btn, url, copiedLabel, defaultLabel) {
    bgpeekCopyText(url).then(function (ok) {
        if (!ok) return;
        var icon = btn.querySelector(".share-icon");
        var check = btn.querySelector(".share-check");
        var label = btn.querySelector(".share-label");
        if (label) label.textContent = copiedLabel;
        if (icon) icon.classList.add("hidden");
        if (check) check.classList.remove("hidden");
        setTimeout(function () {
            if (label) label.textContent = defaultLabel;
            if (icon) icon.classList.remove("hidden");
            if (check) check.classList.add("hidden");
        }, 2000);
    });
}
