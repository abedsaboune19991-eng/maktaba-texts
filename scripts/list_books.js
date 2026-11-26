// يقرأ صفحة الموقع من stdin ويطبع قائمة الكتب JSON
const E = require("./extract.js");
let html = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", d => html += d);
process.stdin.on("end", () => {
  const r = E.extractLibraries(html);
  if (!r) { console.error("no libraries found"); process.exit(1); }
  const out = [];
  for (const k of Object.keys(r.libs)) for (const b of r.libs[k]) out.push({ lib: k, title: b.title, link: b.link });
  process.stdout.write(JSON.stringify(out));
});
