"""أدوات مشتركة: معرّف الكتاب (مطابق لما في التطبيق) وتطبيع النص العربي."""
import re, unicodedata

def book_id(link: str) -> str:
    h = 0x811c9dc5
    data = link.encode("utf-16-le")
    for i in range(0, len(data), 2):
        h ^= data[i] | (data[i + 1] << 8)
        h = (h + ((h << 1) & 0xffffffff) + ((h << 4) & 0xffffffff) + ((h << 7) & 0xffffffff)
             + ((h << 8) & 0xffffffff) + ((h << 24) & 0xffffffff)) & 0xffffffff
    return "b" + format(h, "x")

DIAC = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")

def letters(s: str) -> str:
    """حروف فقط بلا تشكيل ولا مسافات، لمطابقة النصوص."""
    s = unicodedata.normalize("NFKC", s)
    s = DIAC.sub("", s)
    s = re.sub("[أإآٱ]", "ا", s).replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    return re.sub(r"[^ء-ي]", "", s)
