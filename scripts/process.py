"""يحمّل كتب جزء واحد، ويستخرج نص كل صفحة: من طبقة النص إن وُجدت، وإلا بالتعرّف الضوئي (OCR)."""
import gzip, json, os, re, shutil, subprocess, sys, tempfile, time, unicodedata, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from common import letters

UA = "Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
DEADLINE = time.time() + float(os.environ.get("TIME_BUDGET", str(5 * 3600)))
WORKERS = os.cpu_count() or 2
BIDI = re.compile(r"[‎‏‪-‮⁦-⁩﻿]")
AR = re.compile(r"[ء-ي]")
COMMON = ["في", "من", "على", "الله", "الى", "عن", "الذي", "التي", "هذا", "ان"]

def direct(link):
    m = re.search(r"drive\.google\.com/(?:file/d/|.*[?&]id=)([\w-]{10,})", link)
    if m: return f"https://drive.usercontent.google.com/download?id={m.group(1)}&export=download&confirm=t"
    return link

def safe_url(url):
    return urllib.parse.quote(url.strip(), safe=":/?&=%#@+,;~!$'()*[]")

def download(url, dest):
    req = urllib.request.Request(safe_url(url), headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    with open(dest, "rb") as f:
        head = f.read(1024)
    if b"%PDF" not in head: raise ValueError("notpdf")

def clean(t):
    t = unicodedata.normalize("NFKC", BIDI.sub("", t))
    t = re.sub(r"(?<=[؀-ۿ])@+|@+(?=[؀-ۿ])", "", t)
    t = re.sub(r"[ \t ]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()

def fix_reversed(pages):
    words = " ".join(pages).split()
    norm = [letters(w) for w in words[:20000]]
    fwd = sum(1 for w in norm if w in COMMON)
    rev = sum(1 for w in norm if w[::-1] in COMMON and w not in COMMON)
    if rev > 20 and rev > 2 * fwd:
        return ["\n".join(line[::-1] for line in p.split("\n")) for p in pages], True
    return pages, False

def fragmented(t):
    """طبقة نص مكسورة: حروف متفرقة بدل كلمات (شائع في الكتب المشكولة)."""
    ws = [w for w in (letters(x) for x in t.split()) if w]
    return len(ws) >= 30 and sum(1 for w in ws if len(w) <= 1) / len(ws) > 0.25

def good_text(t):
    ar = len(AR.findall(t))
    other = len(re.findall(r"[A-Za-zÀ-ɏ]", t))
    return ar >= 40 and ar > 2 * other and not fragmented(t)

def ocr_page(pdf, n, tmp):
    base = os.path.join(tmp, f"p{n}")
    subprocess.run(["pdftoppm", "-r", "300", "-gray", "-f", str(n), "-l", str(n), "-singlefile", pdf, base],
                   check=True, capture_output=True, timeout=300)
    img = base + ".pgm"
    r = subprocess.run(["tesseract", img, "stdout", "-l", "ara", "--psm", "3"], capture_output=True, timeout=600)
    os.remove(img)
    return r.stdout.decode("utf-8", "ignore")

def process(book, outdir):
    tmp = tempfile.mkdtemp()
    pdf = os.path.join(tmp, "b.pdf")
    try:
        download(direct(book["link"]), pdf)
        info = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True, timeout=120).stdout
        npages = int(re.search(r"Pages:\s+(\d+)", info).group(1))
        raw = subprocess.run(["pdftotext", "-enc", "UTF-8", pdf, "-"], capture_output=True, timeout=1800).stdout.decode("utf-8", "ignore")
        pages = [clean(p) for p in raw.split("\f")][:npages]
        pages += [""] * (npages - len(pages))
        pages, reversed_ = fix_reversed(pages)
        need = [i for i, p in enumerate(pages) if not good_text(p)]
        if need:
            if time.time() > DEADLINE: raise TimeoutError("budget")
            with ThreadPoolExecutor(WORKERS) as ex:
                res = list(ex.map(lambda i: (i, ocr_page(pdf, i + 1, tmp)), need))
            for i, t in res:
                t = clean(t)
                if len(AR.findall(t)) > len(AR.findall(pages[i])): pages[i] = t
        mode = "text" if not need else ("ocr" if len(need) == npages else "mixed")
        data = "\f".join(pages).encode("utf-8")
        gz = gzip.compress(data, 9)
        with open(os.path.join(outdir, "texts", book["id"] + ".txt.gz"), "wb") as f:
            f.write(gz)
        meta = {"id": book["id"], "p": npages, "m": mode, "b": len(gz), "o": len(need), "rev": reversed_, "v": 3}
    except Exception as e:
        meta = {"id": book["id"], "m": "err", "e": str(e)[:200]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    meta["t"] = book["title"]
    json.dump(meta, open(os.path.join(outdir, "meta", book["id"] + ".json"), "w", encoding="utf-8"), ensure_ascii=False)
    return meta

def main():
    shard, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(os.path.join(outdir, "texts"), exist_ok=True)
    os.makedirs(os.path.join(outdir, "meta"), exist_ok=True)
    books = json.load(open(shard, encoding="utf-8"))
    for i, b in enumerate(books):
        if time.time() > DEADLINE:
            print("time budget reached; the rest will be handled next run", flush=True)
            break
        t0 = time.time()
        m = process(b, outdir)
        print(f"[{i+1}/{len(books)}] {b['title'][:50]} -> {m.get('m')} p={m.get('p')} ocr={m.get('o')} {m.get('e','')} ({time.time()-t0:.0f}s)", flush=True)

if __name__ == "__main__":
    main()
