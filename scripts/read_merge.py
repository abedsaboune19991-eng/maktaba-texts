"""يدمج نتائج نص القراءة في read/ ويحدّث read/index.json."""
import glob, json, os, shutil, sys, time

def main():
    src = sys.argv[1]
    os.makedirs("read", exist_ok=True)
    idx = json.load(open("read/index.json", encoding="utf-8")) if os.path.exists("read/index.json") else {"books": {}}
    n = 0
    for mf in glob.glob(os.path.join(src, "**", "rmeta", "*.json"), recursive=True):
        m = json.load(open(mf, encoding="utf-8")); bid = m.pop("id")
        if "err" in m:
            prev = idx["books"].get(bid)
            if prev and prev.get("ok"): continue
            idx["books"][bid] = {"v": m["v"], "n": 0, "ok": 0, "err": m["err"]}; continue
        f = os.path.join(os.path.dirname(os.path.dirname(mf)), "read", bid + ".json.gz")
        if m.get("ok") and os.path.exists(f):
            shutil.copy(f, os.path.join("read", bid + ".json.gz")); n += 1
        elif os.path.exists(os.path.join("read", bid + ".json.gz")):
            os.remove(os.path.join("read", bid + ".json.gz"))
        idx["books"][bid] = m
    idx["updated"] = int(time.time())
    json.dump(idx, open("read/index.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0, sort_keys=True)
    print(f"merged {n} reading texts; books with text: {sum(1 for b in idx['books'].values() if b.get('ok'))}")

if __name__ == "__main__":
    main()
