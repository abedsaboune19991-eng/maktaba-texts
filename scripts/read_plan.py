"""يحدد الكتب التي يُستخرج لها نص القراءة بالخط الأميري: كل كتاب فيه طبقة نص ولم يُعالَج بهذا الإصدار بعد."""
import json, os, subprocess, sys, urllib.request
from common import book_id
from readpdf import VERSION

SOURCE = os.environ.get("SOURCE_URL", "https://abedelkareem1989.github.io/Islamicculture/4.index.html")
SHARDS = int(os.environ.get("SHARDS", "20"))

def main():
    req = urllib.request.Request(SOURCE + "?t=1", headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
    books = json.loads(subprocess.run(["node", "scripts/list_books.js"], input=html, capture_output=True, text=True, check=True).stdout)
    if os.path.exists("library.json"):
        for b in json.load(open("library.json", encoding="utf-8")):
            books.append({"title": b["title"], "link": b["link"]})
    man = json.load(open("manifest.json", encoding="utf-8"))["books"]
    idx = json.load(open("read/index.json", encoding="utf-8")) if os.path.exists("read/index.json") else {"books": {}}
    seen, todo = set(), []
    for b in books:
        b["id"] = book_id(b["link"])
        if b["id"] in seen: continue
        seen.add(b["id"])
        m = man.get(b["id"], {})
        if m.get("m") not in ("text", "mixed"): continue          # المصوَّرة لا نص لها يوثق به
        e = idx["books"].get(b["id"])
        if e and (e.get("v") == VERSION or e.get("src") == "docx"): continue
        todo.append(b)
    os.makedirs("work", exist_ok=True)
    n = max(1, min(SHARDS, len(todo)))
    for i in range(n):
        json.dump(todo[i::n], open(f"work/rshard_{i}.json", "w", encoding="utf-8"), ensure_ascii=False)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"matrix={json.dumps(list(range(n)))}\n")
            f.write(f"has_work={'true' if todo else 'false'}\n")
    print(f"books to process: {len(todo)} in {n} shards")

if __name__ == "__main__":
    main()
