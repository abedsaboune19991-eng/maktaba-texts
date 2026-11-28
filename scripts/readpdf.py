"""نص القراءة بالخط الأميري من ملفات PDF التي فيها طبقة نص.

يُقرأ كل حرف من الصفحة بموضعه وعرضه ولونه، مع احترام ActualText (الحرف وحركاته مجموعين كما في الأصل)،
وتُبنى الكلمات من محارف المسافة المرسومة فعلًا في الصفحة، ويُرتَّب السطر من اليمين إلى اليسار.

ثم تُفحص كل صفحة فحصًا صارمًا، ولا تُقبل إلا إذا:
  - طابقت حروفها حروفَ الصفحة نفسها كما يستخرجها برنامج مستقل (pdftotext) حرفًا بحرف في العدد،
  - وإن وُجد للكتاب أصل Word: وُجدت حروفها متتابعة في الأصل كما هي،
  - وسلمت كل كلماتها من علامات الخلل المعروفة (حركة في أول الكلمة، حرف منفرد، حروف مقلوبة…).
وكل صفحة لا تجتاز الفحص تُكتب null، فيعرض التطبيق صورتها الأصلية بدلًا من نصها.
"""
VERSION = 1

import re, sys, subprocess, unicodedata
from collections import Counter
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import PDFLayoutAnalyzer
from common import letters

MARK = r"ؐ-ًؚ-ٰٟۖ-ۭ"
MARKS = re.compile("[" + MARK + "]")
ARL = r"ء-غف-يٱ-ۓ"
LTR_CORE = re.compile(r"[0-9A-Za-z٠-٩۰-۹]")
NEUTRAL_IN_LTR = set(".,:/%+-")
# حرف التطويل (الكشيدة) الذي تمدّ به الكلمة عند ضبط السطر يُرسم في بعض الخطوط برمز لا معنى له (@ أو � أو E أو رقم مكرر) بين حرفين
JOIN = "\u0626\u0628\u062a-\u062e\u0633-\u063a\u0641-\u0647\u064a\u0640"  # حروف تتصل بما بعدها (والتطويل)
_KASH = re.compile(r"([" + JOIN + r"][" + MARK + r"]*)(?:[@\ufffd]+|([A-Za-z0-9])\2*)(?=[" + ARL + "\u0640" + r"])")
# أقواس وعلامات تنصيص بين حرف متصل وحرف (بلا تطويل حولها) لا تكون إلا كشيدة مرسومة برمز خاطئ
_KASH2 = re.compile(r"([" + JOIN.replace("\u0640", "") + r"][" + MARK + r"]*)[^\s" + ARL + MARK + r"\u0640\u0621-\u064a()\[\]{}.,،؛:!؟\-–\"'0-9A-Za-z*/]+(?=[" + ARL + r"])")


class _Kash:
    def sub(self, _rep, s):
        prev = None
        while prev != s:
            prev, s = s, _KASH2.sub(lambda m: m.group(1), _KASH.sub(lambda m: m.group(1), s))
        return s


KASHIDA = _Kash()
ONLY_MARKS = re.compile("^[" + MARK + "]+$")
PRES = re.compile("[\ufb50-\ufd3d\ufd40-\ufdef\ufe70-\ufefc]")
KEEP_LIG = set(chr(c) for c in range(0xFDF0, 0xFDFE))


def norm_text(t):
    out = []
    for ch in t:
        if ch in KEEP_LIG: out.append(ch)
        elif PRES.match(ch): out.append(unicodedata.normalize("NFKC", ch))
        else: out.append(ch)
    t = unicodedata.normalize("NFC", "".join(out))
    return re.sub(r"[‎‏‪-‮⁦-⁩﻿­]", "", t)


def color_hex(c):
    try:
        if c is None: return None
        if isinstance(c, (int, float)): v = [c, c, c]
        else: v = list(c)
        if len(v) == 1: v = v * 3
        if len(v) == 4:  # CMYK
            C, M, Y, K = v
            v = [(1 - C) * (1 - K), (1 - M) * (1 - K), (1 - Y) * (1 - K)]
        r, g, b = [max(0, min(255, int(round(float(x) * 255)))) for x in v[:3]]
        if r < 60 and g < 60 and b < 60: return None  # أسود أو قريب منه
        return "#%02x%02x%02x" % (r, g, b)
    except Exception:
        return None


class Dev(PDFLayoutAnalyzer):
    def __init__(self, rsrc):
        super().__init__(rsrc, pageno=1, laparams=None)
        self.reset()

    def reset(self):
        self.stack, self.items, self.seq, self.at = [], [], 0, 0

    def begin_tag(self, tag, props=None):
        at = None
        if isinstance(props, dict) and "ActualText" in props:
            v = props["ActualText"]
            if isinstance(v, bytes):
                at = v[2:].decode("utf-16-be", "replace") if v[:2] == b"\xfe\xff" else v.decode("latin1")
            else:
                at = str(v)
        self.stack.append([at, []])

    def end_tag(self):
        if not self.stack: return
        at, chars = self.stack.pop()
        if at is not None and chars:
            self.at += 1
            base = max(chars, key=lambda c: c[1] - c[0])
            self._put((min(c[0] for c in chars), max(c[1] for c in chars), base[2], base[3], at, base[5], base[6]))
        else:
            for c in chars: self._put(c)

    def _put(self, item):
        for fr in reversed(self.stack):
            if fr[0] is not None:
                fr[1].append(item); return
        self.items.append(item)

    def render_char(self, matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate):
        try: text = font.to_unichr(cid)
        except Exception: text = "�"
        adv = font.char_width(cid) * fontsize * scaling
        a, b, c, d, e, f = matrix
        x1 = e + adv * a
        size = fontsize * (abs(d) if d else 1)
        col = None
        try: col = graphicstate.ncolor
        except Exception: pass
        self.seq += 1
        self._put((min(e, x1), max(e, x1), f, size, text, color_hex(col), self.seq))
        return adv

    def receive_layout(self, ltpage): pass


def iter_pages(path):
    with open(path, "rb") as fp:
        doc = PDFDocument(PDFParser(fp))
        rs = PDFResourceManager(caching=True)
        dev = Dev(rs)
        it = PDFPageInterpreter(rs, dev)
        for page in PDFPage.create_pages(doc):
            dev.reset()
            try:
                it.process_page(page)
                yield list(dev.items), page.mediabox, dev.at
            except Exception:
                yield None, page.mediabox, 0


def dedupe(items):
    seen, out = set(), []
    for it in items:
        k = (it[4], round(it[0] * 2), round(it[2] * 2))
        if k in seen: continue
        seen.add(k); out.append(it)
    return out


def rows_of(items):
    """الأسطر من الحروف الظاهرة أولًا، ثم تُلحق المسافات والحركات المنفردة بأقرب سطر إليها
    (قد يُرسم محرف المسافة أو الحركة على خط قاعدة مرفوع قليلًا عن سطره)."""
    vis = [i for i in items if i[4] and not i[4].isspace() and not ONLY_MARKS.match(i[4])]
    loose = [i for i in items if i[4] and (i[4].isspace() or ONLY_MARKS.match(i[4]))]
    rows = _rows(vis)
    for it in loose:
        best, bd = None, 1e9
        for r in rows:
            d = abs(r["y"] - it[2])
            if d < bd: best, bd = r, d
        if best is not None and bd <= 0.9 * best["size"]:
            best["items"].append(it)
    return _merge_small(rows)


def _rows(items):
    its = sorted(items, key=lambda c: -c[2])
    rows = []
    for it in its:
        tol = 0.35 * (it[3] or 12)
        if rows and abs(rows[-1]["y"] - it[2]) <= tol:
            r = rows[-1]; r["items"].append(it)
            if not it[4].isspace() and (it[1] - it[0]) > 0.5:
                r["ys"].append(it[2]); r["y"] = sorted(r["ys"])[len(r["ys"]) // 2]
        else:
            rows.append({"y": it[2], "ys": [it[2]], "items": [it]})
    for r in rows:
        sz = sorted(i[3] for i in r["items"] if not i[4].isspace())
        r["size"] = sz[len(sz) // 2] if sz else 12
    return rows


def _merge_small(rows):
    # الأرقام المرفوعة (إشارات الحواشي) تُضم إلى سطرها
    merged = []
    for r in rows:
        txt = "".join(i[4] for i in r["items"]).strip()
        small = len(txt) <= 8 and re.fullmatch(r"[\s()\[\]0-9٠-٩*]+", txt or "x")
        if small and merged and abs(merged[-1]["y"] - r["y"]) <= 0.9 * merged[-1]["size"]:
            merged[-1]["items"].extend(r["items"]); continue
        merged.append(r)
    # وإن كان الرقم المرفوع فوق أول سطر
    out = []
    for r in merged:
        if out:
            txt = "".join(i[4] for i in out[-1]["items"]).strip()
            if len(txt) <= 8 and re.fullmatch(r"[\s()\[\]0-9٠-٩*]+", txt or "x") and abs(out[-1]["y"] - r["y"]) <= 0.9 * r["size"]:
                r["items"].extend(out[-1]["items"]); out[-1] = r; continue
        out.append(r)
    return out


def word_text(w):
    """حروف الكلمة مرتبة من اليمين إلى اليسار، مع إعادة الأرقام والحروف اللاتينية إلى ترتيبها."""
    segs, buf = [], []

    def flush():
        if not buf: return
        b = list(reversed(buf))  # منطقيًّا من اليسار إلى اليمين
        # العلامات المحايدة في طرفي المقطع لا تنعكس
        lead, trail = [], []
        while b and not LTR_CORE.search(b[0][4]): lead.append(b.pop(0))
        while b and not LTR_CORE.search(b[-1][4]): trail.insert(0, b.pop())
        # ما كان في يسار المقطع بصريًّا يأتي بعده منطقيًّا
        segs.extend(x[4] for x in reversed(trail))
        segs.append("".join(x[4] for x in b))
        segs.extend(x[4] for x in reversed(lead))
        buf.clear()

    for c in w:
        ch = c[4]
        if LTR_CORE.search(ch) and not re.search("[" + ARL + "]", ch): buf.append(c)
        elif buf and len(ch) == 1 and ch in NEUTRAL_IN_LTR: buf.append(c)
        else:
            flush(); segs.append(ch)
    flush()
    return "".join(segs)


def attach_marks(items):
    """الحركات المرسومة رموزًا مستقلة تُلحق بالحرف الذي فوقه أو تحته (بحسب موضعها الأفقي)،
    فتصير مع حرفها وحدة واحدة كما في ActualText."""
    bases = [list(i) for i in items if not ONLY_MARKS.match(i[4] or "")]
    marks = [i for i in items if ONLY_MARKS.match(i[4] or "")]
    if not marks or not bases: return items
    cand = [b for b in bases if not b[4].isspace()]
    extra = {}
    for m in marks:
        cx = (m[0] + m[1]) / 2
        fs = m[3] or 12
        best, bd = None, 1e9
        for k, b in enumerate(cand):
            if abs(b[2] - m[2]) > 1.2 * (b[3] or 12): continue
            d = -1 if b[0] - 0.5 <= cx <= b[1] + 0.5 else min(abs(b[0] - cx), abs(b[1] - cx))
            if d < bd: best, bd = k, d
        if best is None or bd > 0.6 * fs: return None
        extra.setdefault(best, []).append(m)
    for k, ms in extra.items():
        ms.sort(key=lambda m: m[6])
        cand[k][4] = cand[k][4] + "".join(m[4] for m in ms)
    return [tuple(b) for b in bases]


def order_rtl(items):
    """ترتيب عناصر السطر من اليمين إلى اليسار. وإذا تراكب عنصران أفقيًّا (حروف مركّبة فوق بعضها)
    يُحتكم إلى ترتيب رسمها في الملف، باتجاهه الغالب في هذا السطر."""
    row = sorted(items, key=lambda c: -(c[0] + c[1]) / 2)
    pairs = [(a, b) for a, b in zip(row, row[1:]) if (a[1] - a[0]) > 0.5 and (b[1] - b[0]) > 0.5 and not a[4].isspace() and not b[4].isspace()]
    agree = sum(1 for a, b in pairs if a[6] > b[6]); dis = len(pairs) - agree
    rtl_stream_desc = agree >= dis          # العنصر الأيمن رُسم بعد الأيسر (ترتيب بصري من اليسار)
    changed = True; guard = 0
    while changed and guard < 3:
        changed = False; guard += 1
        for i in range(len(row) - 1):
            a, b = row[i], row[i + 1]
            wa, wb = a[1] - a[0], b[1] - b[0]
            if wa <= 0.5 or wb <= 0.5 or a[4].isspace() or b[4].isspace(): continue
            ov = min(a[1], b[1]) - max(a[0], b[0])
            if ov > 0.6 * min(wa, wb):
                want_a_first = (a[6] > b[6]) if rtl_stream_desc else (a[6] < b[6])
                if not want_a_first:
                    row[i], row[i + 1] = b, a; changed = True
    return row


def build_row(r):
    its = attach_marks(r["items"])
    if its is None: return {"y": r["y"], "size": r["size"], "x0": 0, "x1": 0, "words": [("\ufffd", None)]}
    row = order_rtl(its)
    words, cur, left = [], [], None
    for c in row:
        if c[4].isspace():
            if cur: words.append(cur); cur = []
            left = None
            continue
        # فراغ أفقي كبير بلا محرف مسافة (كما بين شطري البيت): حد كلمة
        if cur and left is not None and (c[1] - c[0]) > 0.3 and left - c[1] > 1.5 * (c[3] or 12):
            words.append(cur); cur = []
        cur.append(c)
        if (c[1] - c[0]) > 0.3: left = c[0] if left is None else min(left, c[0])
    if cur: words.append(cur)
    out = []
    for w in words:
        t = norm_text(word_text(w))
        t = KASHIDA.sub("", t)
        if t.strip():
            cols = Counter(c[5] for c in w)
            out.append((t, cols.most_common(1)[0][0]))
    xs0 = [c[0] for c in row if not c[4].isspace()]
    xs1 = [c[1] for c in row if not c[4].isspace()]
    return {"y": r["y"], "size": r["size"], "x0": min(xs0) if xs0 else 0, "x1": max(xs1) if xs1 else 0, "words": out}


PAGE_NUM = re.compile(r"^[\(\[\-–]?\s*[0-9٠-٩]{1,4}\s*[\)\]\-–]?$")


def paragraphs(lines, width):
    """يجمع الأسطر في فقرات: تنتهي الفقرة بسطر قصير، أو بفراغ رأسي أكبر، أو بتغير حجم الخط."""
    lines = [l for l in lines if l["words"]]
    if not lines: return []
    # رقم الصفحة المطبوع في أعلى الصفحة أو أسفلها لا يدخل في النص
    for k in (0, -1):
        if lines and len(lines[k]["words"]) == 1 and PAGE_NUM.match(lines[k]["words"][0][0]):
            lines.pop(k)
    if not lines: return []
    right = max(l["x1"] for l in lines); left = min(l["x0"] for l in lines)
    span = max(1.0, right - left)
    sizes = sorted(l["size"] for l in lines); body = sizes[len(sizes) // 2]
    gaps = sorted(lines[i]["y"] - lines[i + 1]["y"] for i in range(len(lines) - 1) if lines[i]["size"] == lines[i + 1]["size"])
    lg = gaps[len(gaps) // 2] if gaps else body * 1.5
    paras, cur = [], None
    for i, l in enumerate(lines):
        kind = "f" if l["size"] < 0.9 * body else "p"
        start = cur is None
        if not start:
            prev = lines[i - 1]
            gap = prev["y"] - l["y"]
            if kind != cur["k"] or abs(l["size"] - prev["size"]) > 0.6: start = True
            elif gap > 1.45 * lg: start = True
            elif prev["x0"] - left > 0.12 * span: start = True          # السطر السابق قصير فانتهت فقرته
        if start:
            cur = {"k": kind, "w": []}
            cen = (right - l["x1"]) > 0.06 * span and (l["x0"] - left) > 0.06 * span and abs((right - l["x1"]) - (l["x0"] - left)) < 0.08 * span
            if cen and kind == "p": cur["k"] = "c"
            paras.append(cur)
        cur["w"].extend(l["words"])
    out = []
    for p in paras:
        runs = []
        for t, c in p["w"]:
            if runs and runs[-1][1] == c: runs[-1][0] += " " + t
            else: runs.append([t, c])
        out.append([p["k"], [[t, c] if c else [t] for t, c in runs]])
    return out


PAIRS = [("(", ")"), ("[", "]"), ("{", "}"), ("«", "»")]


def fix_mirror(paras):
    """في الاستخراج البصري قد تأتي الأقواس وعلامات التنصيص معكوسة. يُحكم على كل زوج في الصفحة
    بموقعه من الكلام: القوس الفاتح يسبقه فراغ ويليه حرف، والغالق عكسه؛ فإن غلب العكس قُلب الزوج."""
    text = " " + " ".join(r[0] for _, runs in paras for r in runs) + " "
    swap = {}
    for o, c in PAIRS:
        def opens(ch): return len(re.findall(r"(?:^|\s)" + re.escape(ch) + r"\S", text))
        def closes(ch): return len(re.findall(r"\S" + re.escape(ch) + r"(?=[\s.,،؛:!؟]|$)", text))
        good = opens(o) + closes(c); bad = opens(c) + closes(o)
        if bad > good: swap[o], swap[c] = c, o
    if not swap: return paras
    tr = str.maketrans(swap)
    return [[k, [[r[0].translate(tr)] + r[1:] for r in runs]] for k, runs in paras]


SINGLE_OK = set("وأ")
BAD_SEQ = re.compile(r"اهلل|(^|\s)إال(\s|$)|(^|\s)اال[^ا-ي]|�|@")


def page_problem(paras):
    words = [w for _, runs in paras for r in runs for w in r[0].split()]
    if not words: return "empty"
    text = " ".join(words)
    if len(re.findall("[" + ARL + "]", text)) < 30: return "short"
    if BAD_SEQ.search(text): return "badseq"
    if PRES.search("".join(ch for ch in text if ch not in KEEP_LIG)): return "presentation"
    for w in words:
        core = w.strip("()[]{}«»﴿﴾\"'.,،؛:!؟…-–*")
        if not core: continue
        if MARKS.match(core): return "mark-start"
        if re.search(r"[^" + ARL + MARK + r"\u0640]" + "[" + MARK + "]", core): return "mark-after-nonletter"
        if re.search(r"[A-Za-z]", core) and re.search("[" + ARL + "]", core): return "mixed-token"
        bare = MARKS.sub("", core)
        if len(bare) == 1 and re.match("[" + ARL + "]", bare) and bare not in SINGLE_OK: return "single-letter"
        if re.search("[" + MARK + "]{4,}", core): return "mark-run"
    return None


def skel(s):
    """الحروف العربية وحركاتها، وبين الكلمات مسافة واحدة (كل ما ليس حرفًا أو حركة فاصل)، بترتيب قانوني ثابت.
    فالمطابقة بها تتحقق من الحروف والحركات وحدود الكلمات معًا."""
    s = unicodedata.normalize("NFC", norm_text(s)).replace("\u0640", "")
    s = re.sub("[^" + ARL + MARK + "\u0621-\u064a()\\[\\]{}«»]+", " ", s)
    s = re.sub(r" ?([()\[\]{}«»]) ?", r"\1", s)
    s = re.sub(r"[(\[{][)\]}]", " ", s)          # إشارات الحواشي: أرقامها حُذفت فبقيت أقواسها فارغة
    s = re.sub(r" ?([()\[\]{}«»]) ?", r"\1", re.sub(" +", " ", s))
    return " " + s.strip() + " "


BOUND = set(" ()[]{}«»")


def find_word(S, core, lo, hi):
    """موضع core في S على حدود كلمات (لا يبدأ ولا ينتهي في وسط كلمة)."""
    p = S.find(core, lo, hi)
    while p >= 0:
        before = S[p - 1] if p > 0 else " "
        after = S[p + len(core)] if p + len(core) < len(S) else " "
        if (before in BOUND or core[0] in BOUND) and (after in BOUND or core[-1] in BOUND): return p
        p = S.find(core, p + 1, hi)
    return -1


def pdftotext_pages(pdf):
    raw = subprocess.run(["pdftotext", "-enc", "UTF-8", pdf, "-"], capture_output=True, timeout=3600).stdout.decode("utf-8", "ignore")
    return raw.split("\f")


def extract_book(pdf, source_letters=None, log=None):
    """يعيد قائمة الصفحات (فقرات أو None) وإحصاء أسباب الرفض."""
    ref = pdftotext_pages(pdf)
    pages, reasons = [], Counter()
    src_pos = 0
    for n, (items, mb, at) in enumerate(iter_pages(pdf)):
        if items is None: pages.append(None); reasons["error"] += 1; continue
        items = dedupe(items)
        width = (mb[2] - mb[0]) if mb else 600
        lines = [build_row(r) for r in rows_of(items)]
        paras = fix_mirror(paragraphs(lines, width))
        why = page_problem(paras)
        if not why and not at and source_letters is None:
            # بلا ActualText ولا أصل Word: الحركات المستقلة قد تُنسب إلى غير حرفها، فلا تُقبل إلا الصفحة غير المشكولة
            allt = " ".join(r[0] for _, runs in paras for r in runs)
            if len(MARKS.findall(allt)) > 0.01 * max(1, len(re.findall("[" + ARL + "]", allt))): why = "vocalized-noAT"
        if not why:
            mine = letters(" ".join(r[0] for _, runs in paras for r in runs))
            other = letters(KASHIDA.sub("", ref[n].replace("@", ""))) if n < len(ref) else ""
            # رقم الصفحة المطبوع يُحذف من النص، فلا يدخل في المقارنة
            if Counter(mine) != Counter(other):
                diff = (Counter(mine) - Counter(other)) + (Counter(other) - Counter(mine))
                if sum(v for k, v in diff.items() if not k.isdigit()) > 0: why = "letters-mismatch"
        if source_letters is not None and why in (None, "mark-start", "mark-after-nonletter", "mixed-token", "single-letter", "mark-run"):
            # للكتاب أصل Word: كل فقرة يجب أن توجد حروفها وحركاتها متتابعة في الأصل كما هي تمامًا،
            # فإن وُجدت فهي مطابقة للأصل ولو كان في الأصل نفسه خطأ مطبعي.
            why = None
            for _, runs in paras:
                core = skel(" ".join(r[0] for r in runs)).strip()
                if len(core) < 4: continue
                p = find_word(source_letters, core, max(0, src_pos - 5000), src_pos + 300000)
                if p < 0: p = find_word(source_letters, core, 0, len(source_letters))
                if p < 0: why = "source-mismatch"; break
                if src_pos - 5000 <= p < src_pos + 300000: src_pos = p + len(core)
        if why:
            reasons[why] += 1; pages.append(None)
        else:
            pages.append(paras)
    return pages, reasons
