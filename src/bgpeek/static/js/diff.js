/** Line-based diff highlighting for bgpeek multi-device results. */
(function () {
  "use strict";

  /**
   * Compare two pre elements line-by-line and apply diff highlighting.
   * Lines in A but not B get bg-green-900/30; lines in B but not A get bg-red-900/30.
   */
  function computeDiff(preA, preB) {
    var linesA = (preA.textContent || "").split("\n");
    var linesB = (preB.textContent || "").split("\n");

    var setA = new Set(linesA.map(function (l) { return l.trimEnd(); }));
    var setB = new Set(linesB.map(function (l) { return l.trimEnd(); }));

    preA.innerHTML = linesA.map(function (line) {
      var trimmed = line.trimEnd();
      if (trimmed === "") return escapeHtml(line);
      if (!setB.has(trimmed)) {
        return '<span class="block bg-green-900/30">' + escapeHtml(line) + '</span>';
      }
      return escapeHtml(line);
    }).join("\n");

    preB.innerHTML = linesB.map(function (line) {
      var trimmed = line.trimEnd();
      if (trimmed === "") return escapeHtml(line);
      if (!setA.has(trimmed)) {
        return '<span class="block bg-red-900/30">' + escapeHtml(line) + '</span>';
      }
      return escapeHtml(line);
    }).join("\n");
  }

  /** Remove diff highlighting, restoring plain text. */
  function clearDiff(pre) {
    pre.textContent = pre.textContent;
  }

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
  }

  window.bgpeekDiff = { compute: computeDiff, clear: clearDiff };
})();
