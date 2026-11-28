"""مسح الخطوط في الكتب غير المحوَّلة: اسم كل خط وترميزه وأسماء رموزه، لمعرفة الخطوط ذات الترميز الخاص."""
import json, os, subprocess, sys, tempfile, shutil, urllib.request, io
from concurrent.futures import ThreadPoolExecutor
from common import book_id
from process import download, direct

SOURCE = "https://abedelkareem1989.github.io/Islamicculture/4.index.html"
html = urllib.request.urlopen(urllib.request.Request(SOURCE, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read().decode()
books = json.loads(subprocess.run(["node", "scripts/list_books.js"], input=html, capture_output=True, text=True, check=True).stdout)
if os.path.exists("library.json"):
    books += [{"title": b["title"], "link": b["link"]} for b in json.load(open("library.json", encoding="utf-8"))]
man = json.load(open("manifest.json", encoding="utf-8"))["books"]
idx = json.load(open("read/index.json", encoding="utf-8"))["books"]
todo, seen = [], set()
for b in books:
    bid = book_id(b["link"])
    if bid in seen: continue
    seen.add(bid)
    e = idx.get(bid, {})
    if e.get("n") and e.get("ok", 0) >= 0.8 * e["n"]: continue
    todo.append((bid, b))

def one(arg):
    bid, b = arg
    tmp = tempfile.mkdtemp()
    try:
        pdf = os.path.join(tmp, "b.pdf"); download(direct(b["link"]), pdf)
        info = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout
        fonts = subprocess.run(["pdffonts", pdf], capture_output=True, text=True, timeout=600).stdout.splitlines()[2:]
        names = sorted(set(l.split()[0].split("+")[-1] for l in fonts if l.strip()))
        # نسبة الصفحات المصورة: صفحات بلا نص في طبقة PDF
        return bid, {"t": b["title"], "m": man.get(bid, {}).get("m"), "p": man.get(bid, {}).get("p"),
                     "prod": [l for l in info.splitlines() if l.startswith(("Producer", "Creator"))], "fonts": names}
    except Exception as e:
        return bid, {"t": b["title"], "err": str(e)[:100]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

with ThreadPoolExecutor(8) as ex:
    res = dict(ex.map(one, todo))
os.makedirs("survey", exist_ok=True)
json.dump(res, open("survey/fonts.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(res))
