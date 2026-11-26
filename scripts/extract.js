/* يستخرج بيانات الكتب من صفحة الموقع (const libraries = {...}) */
(function (root) {
  function findObject(src, marker) {
    var at = src.indexOf(marker);
    if (at < 0) return null;
    var i = src.indexOf("{", at + marker.length);
    if (i < 0) return null;
    var depth = 0, q = null, esc = false, lineC = false, blockC = false;
    for (var k = i; k < src.length; k++) {
      var c = src[k], n = src[k + 1];
      if (lineC) { if (c === "\n") lineC = false; continue; }
      if (blockC) { if (c === "*" && n === "/") { blockC = false; k++; } continue; }
      if (q) {
        if (esc) { esc = false; continue; }
        if (c === "\\") { esc = true; continue; }
        if (c === q) q = null;
        continue;
      }
      if (c === "/" && n === "/") { lineC = true; k++; continue; }
      if (c === "/" && n === "*") { blockC = true; k++; continue; }
      if (c === '"' || c === "'" || c === "`") { q = c; continue; }
      if (c === "{" || c === "[") depth++;
      else if (c === "}" || c === "]") {
        depth--;
        if (depth === 0) return src.slice(i, k + 1);
      }
    }
    return null;
  }

  function evalObject(text) {
    if (!text) return null;
    if (/\$\{/.test(text.replace(/"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'/g, ""))) return null;
    try { return new Function('"use strict";return (' + text + ");")(); } catch (e) { return null; }
  }

  function extractLibraries(html) {
    var libs = evalObject(findObject(html, "const libraries"));
    if (!libs || typeof libs !== "object") return null;
    var out = {}, count = 0;
    Object.keys(libs).forEach(function (key) {
      var arr = libs[key];
      if (!Array.isArray(arr)) return;
      var clean = arr.filter(function (b) {
        return b && typeof b.title === "string" && b.title.trim() && typeof b.link === "string" && /^https?:\/\//.test(b.link);
      }).map(function (b) {
        return {
          title: String(b.title).trim(),
          author: b.author ? String(b.author).trim() : "",
          description: b.description ? String(b.description).trim() : "",
          cover: b.cover && /^https?:\/\//.test(b.cover) ? String(b.cover) : "",
          link: String(b.link).trim(),
          category: b.category ? String(b.category).trim() : "متفرقات"
        };
      });
      if (clean.length) { out[key] = clean; count += clean.length; }
    });
    if (!count) return null;
    var meta = {};
    var m = evalObject(findObject(html, "const libraryMeta"));
    if (m && typeof m === "object") {
      Object.keys(m).forEach(function (k) {
        if (m[k] && (m[k].shortName || m[k].name)) meta[k] = String(m[k].shortName || m[k].name);
      });
    }
    return { libs: out, meta: meta, count: count };
  }

  root.MaktabaExtract = { extractLibraries: extractLibraries, findObject: findObject };
  if (typeof module !== "undefined") module.exports = root.MaktabaExtract;
})(typeof window !== "undefined" ? window : globalThis);
