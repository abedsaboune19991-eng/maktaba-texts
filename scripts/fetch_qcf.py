"""يجلب من واجهة Quran.com رموز خط مصحف المدينة (QCF V1) لكل صفحة مع نص الكلمة المقابلة،
ليُفك بها نص الآيات المكتوبة بخطوط QCF_Pxxx في ملفات الكتب."""
import json, time, urllib.request
out = {}
for p in range(1, 605):
    url = f"https://api.quran.com/api/v4/verses/by_page/{p}?words=true&word_fields=code_v1,text_uthmani,page_number,line_number&per_page=50"
    for attempt in range(5):
        try:
            d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read())
            break
        except Exception as e:
            time.sleep(3 * (attempt + 1))
    else:
        raise SystemExit(f"failed page {p}")
    words = []
    for v in d["verses"]:
        for w in v["words"]:
            words.append({"c": w.get("code_v1"), "t": w.get("text_uthmani") or w.get("text"), "k": v["verse_key"], "ty": w.get("char_type_name"), "pg": w.get("page_number"), "ln": w.get("line_number")})
    out[p] = words
    if p % 50 == 0: print(p, flush=True)
json.dump(out, open("qcf_v1.json", "w", encoding="utf-8"), ensure_ascii=False)
print("done", sum(len(v) for v in out.values()))
