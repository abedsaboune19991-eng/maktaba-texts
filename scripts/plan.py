"""يحدد الكتب التي تحتاج استخراج نصوصها ويقسمها على أجزاء تُعالَج بالتوازي."""
import gzip, json, os, subprocess, sys, urllib.request
from common import book_id, letters

SOURCE = os.environ.get("SOURCE_URL", "https://abedelkareem1989.github.io/Islamicculture/4.index.html")
SHARDS = int(os.environ.get("SHARDS", "20"))
LIMIT = int(os.environ.get("LIMIT", "0") or 0)
MAX_RETRY = 3

def broken(bid):
    """هل في نص الكتب المستخرج سابقًا صفحات كثيرة مكسورة الحروف؟"""
    f = os.path.join("texts", bid + ".txt.gz")
    if not os.path.exists(f): return False
    bad = total = 0
    for p in gzip.open(f).read().decode("utf-8").split("\f"):
        ws = [w for w in (letters(x) for x in p.split()) if w]
        if len(ws) < 30: continue
        total += 1
        if sum(1 for w in ws if len(w) <= 1) / len(ws) > 0.25: bad += 1
    return total > 0 and bad / total > 0.1

def main():
    req = urllib.request.Request(SOURCE + "?t=1", headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
    books = json.loads(subprocess.run(["node", "scripts/list_books.js"], input=html, capture_output=True, text=True, check=True).stdout)
    if os.path.exists("library.json"):
        for b in json.load(open("library.json", encoding="utf-8")):
            books.append({"lib": "main", "title": b["title"], "link": b["link"]})
    seen, allb = set(), []
    for b in books:
        b["id"] = book_id(b["link"])
        if b["id"] in seen: continue
        seen.add(b["id"]); allb.append(b)
    man = json.load(open("manifest.json", encoding="utf-8")) if os.path.exists("manifest.json") else {"books": {}}
    todo = []
    for b in allb:
        e = man["books"].get(b["id"])
        if e is None or (e.get("m") == "err" and e.get("r", 0) < MAX_RETRY):
            todo.append(b)
        elif e.get("m") in ("text", "mixed") and e.get("v", 1) < 3 and broken(b["id"]):
            todo.append(b)
    if LIMIT: todo = todo[:LIMIT]
    os.makedirs("work", exist_ok=True)
    json.dump(allb, open("work/all_books.json", "w", encoding="utf-8"), ensure_ascii=False)
    n = max(1, min(SHARDS, len(todo)))
    shards = [todo[i::n] for i in range(n)] if todo else []
    for i, s in enumerate(shards):
        json.dump(s, open(f"work/shard_{i}.json", "w", encoding="utf-8"), ensure_ascii=False)
    print(f"books: {len(allb)}, indexed: {len(allb) - len(todo)}, todo: {len(todo)}, shards: {len(shards)}", file=sys.stderr)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write("matrix=" + json.dumps(list(range(len(shards)))) + "\n")
            f.write("has_work=" + ("true" if shards else "false") + "\n")

if __name__ == "__main__":
    main()
