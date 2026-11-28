"""ينزّل ملفات PDF لكتب محددة (للفحص وتطوير الاستخراج) إلى مجلد samples/."""
import json, os, subprocess, sys, urllib.request
from common import book_id
from process import download, direct

SOURCE = os.environ.get("SOURCE_URL", "https://abedelkareem1989.github.io/Islamicculture/4.index.html")
ids = set(sys.argv[1].split(","))
req = urllib.request.Request(SOURCE + "?t=1", headers={"User-Agent": "Mozilla/5.0"})
html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
books = json.loads(subprocess.run(["node", "scripts/list_books.js"], input=html, capture_output=True, text=True, check=True).stdout)
os.makedirs("samples", exist_ok=True)
for b in books:
    bid = book_id(b["link"])
    if bid in ids:
        ids.discard(bid)
        try:
            download(direct(b["link"]), f"samples/{bid}.pdf"); print("ok", bid, b["title"])
        except Exception as e:
            print("fail", bid, e)
print("missing", ids)
