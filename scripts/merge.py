"""يدمج نتائج الأجزاء في المستودع ويحدّث manifest.json."""
import glob, json, os, shutil, sys, time

def main():
    src = sys.argv[1]
    man = json.load(open("manifest.json", encoding="utf-8")) if os.path.exists("manifest.json") else {"books": {}}
    os.makedirs("texts", exist_ok=True)
    added = 0
    for mf in glob.glob(os.path.join(src, "**", "meta", "*.json"), recursive=True):
        m = json.load(open(mf, encoding="utf-8"))
        bid = m.pop("id")
        if m.get("m") == "err":
            prev = man["books"].get(bid, {})
            if prev.get("m") not in (None, "err"): continue
            m["r"] = prev.get("r", 0) + 1
        else:
            tf = os.path.join(os.path.dirname(os.path.dirname(mf)), "texts", bid + ".txt.gz")
            shutil.copy(tf, os.path.join("texts", bid + ".txt.gz"))
            added += 1
        m.pop("rev", None)
        man["books"][bid] = m
    man["version"] = man.get("version", 0) + 1
    man["updated"] = int(time.time())
    ok = [b for b in man["books"].values() if b.get("m") != "err"]
    man["count"] = len(ok)
    man["bytes"] = sum(b.get("b", 0) for b in ok)
    json.dump(man, open("manifest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0, sort_keys=True)
    print(f"merged: {added} new texts; indexed books: {len(ok)}; errors: {len(man['books']) - len(ok)}")

if __name__ == "__main__":
    main()
