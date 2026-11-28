"""يستخرج نص القراءة لكتب جزء واحد ويكتب read/<id>.json.gz مع ملف وصف."""
import gzip, json, os, shutil, sys, tempfile, time
from process import download, direct
from readpdf import extract_book, VERSION

DEADLINE = time.time() + float(os.environ.get("TIME_BUDGET", str(5 * 3600)))

def main():
    shard, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(os.path.join(outdir, "read"), exist_ok=True)
    os.makedirs(os.path.join(outdir, "rmeta"), exist_ok=True)
    for i, b in enumerate(json.load(open(shard, encoding="utf-8"))):
        if time.time() > DEADLINE: print("time budget reached", flush=True); break
        t0 = time.time(); tmp = tempfile.mkdtemp()
        meta = {"id": b["id"], "v": VERSION}
        try:
            pdf = os.path.join(tmp, "b.pdf")
            download(direct(b["link"]), pdf)
            pages, reasons = extract_book(pdf)
            ok = sum(1 for p in pages if p)
            data = json.dumps({"v": VERSION, "pages": pages}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            gz = gzip.compress(data, 9)
            if ok:
                with open(os.path.join(outdir, "read", b["id"] + ".json.gz"), "wb") as f: f.write(gz)
            meta.update({"n": len(pages), "ok": ok, "b": len(gz) if ok else 0, "why": dict(reasons)})
        except Exception as e:
            meta.update({"err": str(e)[:200]})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        json.dump(meta, open(os.path.join(outdir, "rmeta", b["id"] + ".json"), "w", encoding="utf-8"), ensure_ascii=False)
        print(f"[{i+1}] {b['title'][:50]} -> ok={meta.get('ok')}/{meta.get('n')} {meta.get('err','')} ({time.time()-t0:.0f}s)", flush=True)

if __name__ == "__main__":
    main()
