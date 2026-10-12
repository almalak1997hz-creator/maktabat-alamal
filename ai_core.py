"""منطق المساعد الذكي (بدون واجهة): فهم الجُمل العربية، الاستعلامات، واستدعاء Ollama.

الأمان: النموذج لا يكتب SQL أبداً. دوره فهم الجملة فقط، وبايثون هو الذي ينفّذ
الاستعلامات الجاهزة. وأي تعديل على البيانات يمرّ عبر تأكيد من المستخدم.
"""
import json
import re
from datetime import date, datetime, timedelta

MODEL = "qwen2.5:3b"   # غيّره إلى qwen2.5:7b إن سمح جهازك

# ------------------------------------------------------------------
# تنظيف النص
# ------------------------------------------------------------------
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789..")
_DIAC = re.compile(r"[\u064B-\u0652\u0640]")


def norm(text):
    """يوحّد الأرقام والهمزات والتاء المربوطة ويحذف التشكيل."""
    t = (text or "").translate(_AR_DIGITS)
    t = _DIAC.sub("", t)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t).strip().lower()


def strip_al(word):
    return word[2:] if word.startswith("ال") and len(word) > 4 else word


def has_any(t, words):
    return any(w in t for w in words)


# ------------------------------------------------------------------
# فهم الفترات الزمنية
# ------------------------------------------------------------------
_MONTHS = {
    "يناير": 1, "كانون الثاني": 1, "فبراير": 2, "شباط": 2, "مارس": 3, "اذار": 3,
    "ابريل": 4, "نيسان": 4, "مايو": 5, "ايار": 5, "يونيو": 6, "حزيران": 6,
    "يوليو": 7, "تموز": 7, "اغسطس": 8, "سبتمبر": 9, "ايلول": 9,
    "اكتوبر": 10, "تشرين الاول": 10, "نوفمبر": 11, "تشرين الثاني": 11,
    "ديسمبر": 12, "كانون الاول": 12,
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))


def week_start(d):
    """بداية الأسبوع الأحد (كما في سلطنة عمان)."""
    return d - timedelta(days=(d.weekday() + 1) % 7)


def _mk(y, m, d):
    try:
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def fmt_range(s, e):
    return f"{s:%Y-%m-%d}" if s == e else f"من {s:%Y-%m-%d} إلى {e:%Y-%m-%d}"


def parse_range(text, today=None):
    """يعيد (بداية، نهاية) أو None إن لم يجد فترة في الجملة."""
    today = today or date.today()
    t = norm(text)

    # 1) تواريخ صريحة
    found = []
    for m in re.finditer(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", t):
        d = _mk(m[1], m[2], m[3])
        if d:
            found.append((m.start(), d))
    for m in re.finditer(r"(?<!\d)(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", t):
        d = _mk(m[3], m[2], m[1])
        if d:
            found.append((m.start(), d))
    for m in re.finditer(r"(?<!\d)(\d{1,2})\s*(" + _MONTH_RE + r")(?:\s*(\d{4}))?", t):
        y = int(m[3]) if m[3] else today.year
        d = _mk(y, _MONTHS[m[2]], m[1])
        if d:
            found.append((m.start(), d))
    if found:
        ds = sorted(d for _, d in found)
        return ds[0], ds[-1]

    # 2) اسم شهر فقط (مثل: جرد شهر مارس)
    m = re.search(r"(" + _MONTH_RE + r")(?:\s*(\d{4}))?", t)
    if m:
        mon = _MONTHS[m[1]]
        y = int(m[2]) if m[2] else (today.year if mon <= today.month else today.year - 1)
        s = date(y, mon, 1)
        e = (date(y + (mon == 12), mon % 12 + 1, 1)) - timedelta(days=1)
        return s, e

    # 3) آخر N يوم/أسبوع/شهر
    m = re.search(r"اخر\s*(\d+)?\s*(يوم|ايام|اسبوع|اسابيع|شهر|اشهر|شهور|سنه|سنوات)", t)
    if m:
        n = int(m[1]) if m[1] else 1
        unit = {"يوم": 1, "ايام": 1, "اسبوع": 7, "اسابيع": 7, "شهر": 30,
                "اشهر": 30, "شهور": 30, "سنه": 365, "سنوات": 365}[m[2]]
        n = max(1, min(n, 3650))
        return today - timedelta(days=n * unit - 1), today

    past = r".{0,8}(?:ماض|سابق)"
    if re.search(r"اسبوع" + past, t):
        s = week_start(today) - timedelta(days=7)
        return s, s + timedelta(days=6)
    if re.search(r"شهر" + past, t):
        e = today.replace(day=1) - timedelta(days=1)
        return e.replace(day=1), e
    if re.search(r"(?:سنه|عام)" + past, t):
        y = today.year - 1
        return date(y, 1, 1), date(y, 12, 31)
    if "امس" in t:
        y = today - timedelta(days=1)
        return y, y
    if "اليوم" in t:
        return today, today
    if "اسبوع" in t:
        return week_start(today), today
    if "شهر" in t:
        return today.replace(day=1), today
    if "السنه" in t or "العام" in t or "هذه السنه" in t:
        return date(today.year, 1, 1), today
    return None


def extract_limit(text, default=10):
    t = norm(text)
    m = (re.search(r"(?<![\d/.-])(\d{1,2})\s*(?:منتج|منتجات|صنف|اصناف)", t)
         or re.search(r"(?:اكثر|اعلى|افضل|اقل|اشهر)\s*(\d{1,2})(?![\d/.-])", t))
    return max(1, min(int(m[1]), 50)) if m else default


# ------------------------------------------------------------------
# تحديد النيّة (قواعد بسيطة أولاً، ثم النموذج إن لم تكفِ)
# ------------------------------------------------------------------
INTENTS = ("top_products", "bottom_products", "sales_summary", "inventory",
           "low_stock", "reorder", "stagnant", "lookup", "add_product",
           "set_price", "help", "gen_barcodes", "bulk_price", "min_stock",
           "add_stock", "undo", "analysis", "free")

_LOOKUP_WORDS = ("سعر", "كم ", "موجود", "متوفر", "مخزون", "كميه", "عندنا",
                 "باركود", "ابحث", "بحث", "وين", "عن ")
_STOP = {"كم", "سعر", "ما", "هو", "هي", "هل", "في", "عن", "من", "الى", "الي",
         "عندنا", "عندي", "موجود", "متوفر", "كميه", "مخزون", "المخزون",
         "الكميه", "باركود", "ابحث", "بحث", "وين", "لدينا", "عنده", "المنتج", "منتج"}


def get_products(conn):
    return conn.execute("SELECT id, name, price, stock, min_stock, barcode FROM products").fetchall()


def find_products(conn, query, limit=8):
    """بحث بالاسم: يطابق الجملة كلها أولاً ثم كلمات الجملة."""
    q = norm(query)
    rows = get_products(conn)
    exact = [r for r in rows if norm(r[1]) and norm(r[1]) in q]
    if exact:
        best = max(len(norm(r[1])) for r in exact)
        return [r for r in exact if len(norm(r[1])) == best][:limit]
    tokens = [strip_al(w) for w in q.split() if w not in _STOP and len(w) >= 3]
    tokens = [w for w in tokens if not re.fullmatch(r"[\d.]+", w)]
    if not tokens:
        return []
    hits = [r for r in rows if all(tok in norm(r[1]) for tok in tokens)]
    if not hits:
        hits = [r for r in rows if any(tok in norm(r[1]) for tok in tokens)]
    return hits[:limit]


_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|٪|بالمئه|بالمائه|بالميه|في المئه)")
_DOWN = ("خفض", "تخفيض", "انقص", "نزل", "انزل", "خصم", "قلل", "تقليل")
_UP = ("ارفع", "رفع", "زد", "زيد", "زياده", "زود")


def detect_intent(text, conn=None):
    """يعيد اسم النيّة أو None إن لم تُفهم."""
    t = norm(text)
    words = set(t.split())
    has_digit = bool(re.search(r"\d", t))
    sold = has_any(t, ("مبيع", "بيع", "مبيعا", "طلبا", "رواج"))
    pct = bool(_PCT_RE.search(t)) or "نسبه" in t

    if has_any(t, ("مساعده", "ماذا تستطيع", "ماذا تقدر", "وش تقدر", "شو تقدر",
                   "ماذا يمكنك", "help", "ايش تسوي", "كيف استخدمك")):
        return "help"
    if has_any(t, ("تراجع", "الغاء اخر", "الغي اخر", "ارجع اخر")):
        return "undo"
    if "باركود" in t and (has_any(t, ("ضيف", "اضف", "انشئ", "ولد", "سوي", "اعمل", "توليد", "اصدر"))
                          or has_any(t, ("لكل", "جميع", "بدون", "ناقص", "ليس", "مفقود"))):
        return "gen_barcodes"
    if pct and has_any(t, _UP + _DOWN) and (has_any(t, ("سعر", "اسعار")) or has_any(t, ("كل", "جميع", "منتجات"))):
        return "bulk_price"
    if has_digit and has_any(t, ("حد التنبيه", "الحد الادنى", "حد الطلب")) and \
            has_any(t, ("اجعل", "غير", "عدل", "حدد", "ضبط", "خلي", "ضع")):
        return "min_stock"
    if "سعر" in t and has_any(t, ("غير", "عدل", "حدث", "بدل", "اجعل", "رفع", "خفض")):
        return "set_price"
    if has_digit and (
            (has_any(t, ("زد", "زيد", "زود", "اضف", "ضيف")) and has_any(t, ("مخزون", "كميه")))
            or has_any(t, ("وصل", "استلمت", "جاني"))
            or (has_any(t, ("زد", "زيد", "زود")) and has_any(t, ("قطعه", "قطع")))):
        return "add_stock"
    if has_any(t, ("اضف", "ضيف", "اضافه منتج", "سجل منتج", "ادخل")) or \
            (has_digit and "بسعر" in t and not has_any(t, ("غير", "عدل", "حدث"))):
        return "add_product"
    if has_any(t, ("حلل", "تحليل", "نصائح", "نصيحه", "ملخص تنفيذي", "كيف حال المبيعات", "كيف حال المكتبه", "كيف حال الشغل", "كيف المبيعات",
                   "كيف الشغل", "كيف احسن", "كيف ازيد", "كيف اطور", "زياده المبيعات", "وضع المكتبه", "اداء", "قارن", "مقارنه", "تقرير شامل", "كيف وضعنا")):
        return "analysis"
    if has_any(t, ("اطلب", "طلبيه", "اشتري", "شراء", "اعاده الطلب", "اعادة الطلب")):
        return "reorder"
    if has_any(t, ("اكثر", "افضل", "اعلى", "اشهر", "الاكثر")) and sold:
        return "top_products"
    if "اقل" in t and sold:
        return "bottom_products"
    if has_any(t, ("راكد", "لم يبع", "ما انباع", "لا يباع", "بدون مبيعات",
                   "ما تحرك", "كاسد", "ما اتباع")) or "ركود" in words:
        return "stagnant"
    if "جرد" in t and not has_any(t, ("ناقص", "نواقص")):
        return "inventory"
    if has_any(t, ("ناقص", "نواقص", "منخفض", "قارب", "نفد", "نفذ", "خلص", "خالص",
                   "ينقص", "قليل", "تنبيه")):
        return "low_stock"
    if has_any(t, ("مبيعات", "ايراد", "دخل", "فواتير", "فاتوره", "اجمالي", "حصيله",
                   "بعنا", "مبيع")):
        return "sales_summary"
    if conn is not None and has_any(t + " ", _LOOKUP_WORDS) and find_products(conn, text):
        return "lookup"
    return None


# ------------------------------------------------------------------
# النموذج المحلي (Ollama)
# ------------------------------------------------------------------
PREFERRED = ["qwen3:8b", "qwen3:14b", "qwen3:4b", "qwen3", "qwen2.5:7b", "qwen2.5:3b", "llama3.1:8b", "gemma3"]


def pick_model():
    """يختار تلقائياً أفضل نموذج مثبّت عندك (أو المحدد في المتغير OLLAMA_MODEL)."""
    import os
    forced = os.environ.get("OLLAMA_MODEL", "").strip()
    if forced:
        return forced
    try:
        import ollama
        have = [m.get("model") or m.get("name") for m in ollama.Client(timeout=5).list()["models"]]
    except Exception as e:
        print("[AI] لا أستطيع الوصول إلى Ollama:", e)
        return MODEL
    for want in PREFERRED:
        for h in have:
            if h and (h == want or h.split(":")[0] == want and ":" not in want):
                return h
    return have[0] if have else MODEL


def _chat(**kw):
    """استدعاء Ollama مع تعطيل «التفكير» لنماذج qwen3 وطباعة الخطأ الحقيقي في الطرفية."""
    import ollama
    client = ollama.Client(timeout=120)
    kw["model"] = pick_model()
    try:
        return client.chat(think=False, **kw)
    except TypeError:
        return client.chat(**kw)
    except Exception as e:
        if "think" in str(e).lower():
            return client.chat(**kw)
        print("[AI] خطأ Ollama:", e)
        raise



class AIConnectionError(Exception):
    pass


def chat_json(system, user):
    try:
        r = _chat(format="json", options={"temperature": 0},
                        messages=[{"role": "system", "content": system},
                                  {"role": "user", "content": user}])
    except Exception as e:
        raise AIConnectionError(str(e))
    try:
        data = json.loads(r["message"]["content"])
        if not isinstance(data, dict):
            raise ValueError
        return data
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise ValueError("لم أستطع فهم الجملة.")


SYSTEM_ADD = """أنت مساعد لإدخال المنتجات في نظام مبيعات مكتبة.
استخرج من جملة المستخدم بيانات المنتج، وأعد JSON فقط بهذه الحقول:
{"name": اسم المنتج كما ذكره المستخدم, "quantity": عدد صحيح, "price": سعر القطعة الواحدة}
لا تشرح ولا تحسب شيئاً. وإن لم تجد قيمة فاجعلها null.

أمثلة:
الجملة: عندي قلم أزرق 50 قطعة بسعر 2 ريال
الناتج: {"name": "قلم أزرق", "quantity": 50, "price": 2}
الجملة: أضف منتج آلة حاسبة تتوفر منه 10 قطع بسعر 1 ريال عماني
الناتج: {"name": "آلة حاسبة", "quantity": 10, "price": 1}
"""

SYSTEM_PRICE = """استخرج اسم المنتج والسعر الجديد من الجملة، وأعد JSON فقط:
{"product": اسم المنتج, "price": السعر الجديد كرقم}
مثال: غيّر سعر المسطرة إلى 0.3 -> {"product": "المسطرة", "price": 0.3}
"""

SYSTEM_INTENT = """صنّف طلب المستخدم (صاحب مكتبة) وأعد JSON فقط: {"intent": "..."}
القيم الممكنة:
top_products = أكثر المنتجات مبيعاً
bottom_products = أقل المنتجات مبيعاً
sales_summary = ملخص المبيعات والإيرادات
inventory = جرد لفترة
low_stock = المنتجات الناقصة أو المنخفضة
reorder = ماذا أطلب من المورد
stagnant = المنتجات الراكدة التي لا تباع
lookup = سؤال عن سعر أو كمية منتج محدد
add_product = إضافة منتج جديد
set_price = تغيير سعر منتج
help = طلب مساعدة
gen_barcodes = توليد باركود للمنتجات
bulk_price = رفع أو خفض الأسعار بنسبة مئوية
min_stock = تغيير حد التنبيه
add_stock = زيادة مخزون منتج
undo = التراجع عن آخر تعديل
analysis = تحليل أداء المبيعات ونصائح
free = سؤال عام أو حوار آخر
"""


def parse_product(text):
    data = chat_json(SYSTEM_ADD, text)
    try:
        name = str(data.get("name") or "").strip()
        qty = int(float(data.get("quantity")))
        price = float(data.get("price"))
    except (ValueError, TypeError):
        raise ValueError("لم أستطع فهم الجملة. اكتبها بصيغة: أضف قلم أزرق 50 قطعة بسعر 2 ريال.")
    return {"name": name, "quantity": qty, "price": price}


def parse_price_change(text):
    """بايثون أولاً (سريع ومضمون)، ثم النموذج إن لم تنجح القاعدة."""
    t = norm(text)
    m = re.search(r"سعر\s+(.+?)\s+(?:الي|ل|ب|=|ليصبح|يصير)\s*(\d+(?:\.\d+)?)", t)
    if m:
        return {"product": m[1].strip(), "price": float(m[2])}
    data = chat_json(SYSTEM_PRICE, text)
    try:
        return {"product": str(data.get("product") or "").strip(),
                "price": float(data.get("price"))}
    except (ValueError, TypeError):
        raise ValueError("لم أفهم الطلب. اكتب مثلاً: غيّر سعر المسطرة إلى 0.3")


def llm_intent(text):
    data = chat_json(SYSTEM_INTENT, text)
    intent = str(data.get("intent") or "")
    return intent if intent in INTENTS else "free"


def chat_text(system, user):
    """رد نصي حر من النموذج (ليس JSON)."""
    try:
        from pro_more import facts
        system += "\nحقائق حيّة من النظام الآن: " + facts() + "\nتحدّث بأسلوب ودّي وطبيعي كصديق خبير، ولا تكن آلياً."
    except Exception:
        pass
    try:
        r = _chat(options={"temperature": 0.3},
                        messages=[{"role": "system", "content": system},
                                  {"role": "user", "content": user}])
        return str(r["message"]["content"]).strip()
    except Exception as e:
        raise AIConnectionError(str(e))


SYSTEM_CHAT = """أنت مساعد ذكي لمكتبة صغيرة في سلطنة عمان. أجب بالعربية بإيجاز (3 جمل كحد أقصى).
اعتمد فقط على بيانات المكتبة المعطاة لك. إن لم تكفِ البيانات فقل ذلك بصراحة واقترح أمراً مثل:
«جرد هذا الشهر» أو «أكثر المنتجات مبيعاً» أو «حلل مبيعاتي». لا تخترع أرقاماً أبداً."""


# ------------------------------------------------------------------
# التحقق من القيم
# ------------------------------------------------------------------
def validate_product(name, qty, price):
    name = (name or "").strip()
    if not name or len(name) > 100:
        raise ValueError("اسم المنتج غير صالح.")
    if not (0 < qty <= 1_000_000):
        raise ValueError("الكمية يجب أن تكون رقماً موجباً.")
    if not (0 <= price <= 1_000_000):
        raise ValueError("السعر غير صالح.")
    return name, int(qty), round(float(price), 3)


# ------------------------------------------------------------------
# الاستعلامات (كلها قراءة فقط)
# ------------------------------------------------------------------
def _sold_sql():
    return ("SELECT si.product_id AS pid, SUM(si.quantity) AS q, SUM(si.subtotal) AS r "
            "FROM sale_items si JOIN sales s ON s.id = si.sale_id "
            "WHERE date(s.sale_date) BETWEEN ? AND ? GROUP BY si.product_id")


def q_top(conn, s, e, n=10, by="qty", asc=False):
    order = "q" if by == "qty" else "r"
    sql = ("SELECT si.product_name, SUM(si.quantity) AS q, SUM(si.subtotal) AS r "
           "FROM sale_items si JOIN sales s ON s.id = si.sale_id "
           "WHERE date(s.sale_date) BETWEEN ? AND ? "
           "GROUP BY si.product_id, si.product_name "
           f"ORDER BY {order} {'ASC' if asc else 'DESC'} LIMIT ?")
    return conn.execute(sql, (str(s), str(e), n)).fetchall()


def q_totals(conn, s, e):
    total, count = conn.execute(
        "SELECT COALESCE(SUM(total),0), COUNT(*) FROM sales WHERE date(sale_date) BETWEEN ? AND ?",
        (str(s), str(e))).fetchone()
    items = conn.execute(
        "SELECT COALESCE(SUM(si.quantity),0) FROM sale_items si JOIN sales s ON s.id=si.sale_id "
        "WHERE date(s.sale_date) BETWEEN ? AND ?", (str(s), str(e))).fetchone()[0]
    return {"total": total, "count": count, "items": items,
            "avg": (total / count) if count else 0}


def q_daily(conn, s, e):
    return conn.execute(
        "SELECT date(sale_date) AS d, SUM(total) FROM sales "
        "WHERE date(sale_date) BETWEEN ? AND ? GROUP BY d ORDER BY d", (str(s), str(e))).fetchall()


def q_inventory(conn, s, e):
    rows = conn.execute(
        "SELECT p.name, p.stock, p.min_stock, COALESCE(x.q,0), COALESCE(x.r,0), p.price "
        f"FROM products p LEFT JOIN ({_sold_sql()}) x ON x.pid = p.id "
        "ORDER BY COALESCE(x.q,0) DESC, p.name", (str(s), str(e))).fetchall()
    kpis = {
        "products": len(rows),
        "stock_value": sum(max(r[1], 0) * r[5] for r in rows),
        "sold_qty": sum(r[3] for r in rows),
        "revenue": sum(r[4] for r in rows),
    }
    return rows, kpis


def q_low_stock(conn):
    return conn.execute(
        "SELECT name, stock, min_stock FROM products WHERE stock <= min_stock "
        "ORDER BY stock ASC, name").fetchall()


def q_reorder(conn, today=None, days=30):
    today = today or date.today()
    s = today - timedelta(days=days - 1)
    rows = conn.execute(
        "SELECT p.name, p.stock, p.min_stock, COALESCE(x.q,0) "
        f"FROM products p LEFT JOIN ({_sold_sql()}) x ON x.pid = p.id", (str(s), str(today))).fetchall()
    out = []
    for name, stock, mn, sold in rows:
        target = max(sold, mn * 2)
        need = target - stock
        if need > 0 and (stock <= mn or stock < sold):
            out.append((name, stock, sold, int(need)))
    out.sort(key=lambda r: (-r[3], r[0]))
    return out


def q_stagnant(conn, since, limit=50):
    return conn.execute(
        "SELECT p.name, p.stock, p.price * p.stock AS val, "
        "(SELECT MAX(date(s.sale_date)) FROM sale_items si JOIN sales s ON s.id=si.sale_id "
        " WHERE si.product_id = p.id) AS last_sale "
        "FROM products p WHERE p.stock > 0 AND NOT EXISTS ("
        " SELECT 1 FROM sale_items si JOIN sales s ON s.id=si.sale_id "
        " WHERE si.product_id = p.id AND date(s.sale_date) >= ?) "
        "ORDER BY val DESC LIMIT ?", (str(since), limit)).fetchall()


def q_product_card(conn, pid, s, e):
    p = conn.execute("SELECT id, name, price, stock, min_stock, barcode FROM products WHERE id=?",
                     (pid,)).fetchone()
    sold = conn.execute(
        "SELECT COALESCE(SUM(si.quantity),0) FROM sale_items si JOIN sales s ON s.id=si.sale_id "
        "WHERE si.product_id=? AND date(s.sale_date) BETWEEN ? AND ?", (pid, str(s), str(e))).fetchone()[0]
    return p, sold


# ------------------------------------------------------------------
# استعلامات التحليل
# ------------------------------------------------------------------
WEEKDAYS = {0: "الأحد", 1: "الاثنين", 2: "الثلاثاء", 3: "الأربعاء", 4: "الخميس", 5: "الجمعة", 6: "السبت"}


def q_weekday(conn, s, e):
    rows = conn.execute(
        "SELECT CAST(strftime('%w', sale_date) AS INTEGER), SUM(total), COUNT(*) FROM sales "
        "WHERE date(sale_date) BETWEEN ? AND ? GROUP BY 1", (str(s), str(e))).fetchall()
    return [(WEEKDAYS[r[0]], r[1], r[2]) for r in rows]


def q_hours(conn, s, e):
    return conn.execute(
        "SELECT CAST(strftime('%H', sale_date) AS INTEGER), SUM(total), COUNT(*) FROM sales "
        "WHERE date(sale_date) BETWEEN ? AND ? GROUP BY 1", (str(s), str(e))).fetchall()


def snapshot_text(conn, today=None):
    """ملخص قصير لبيانات المكتبة يُعطى للنموذج عند الأسئلة الحرة."""
    today = today or date.today()
    m0 = today.replace(day=1)
    td = q_totals(conn, today, today)
    mo = q_totals(conn, m0, today)
    top = q_top(conn, m0, today, 5)
    low = q_low_stock(conn)[:8]
    n = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    lines = [f"التاريخ: {today}",
             f"عدد المنتجات: {n}",
             f"مبيعات اليوم: {td['total']:.3f} ({td['count']} فاتورة)",
             f"مبيعات هذا الشهر: {mo['total']:.3f} ({mo['count']} فاتورة)"]
    if top:
        lines.append("الأكثر مبيعاً هذا الشهر: " + "، ".join(f"{r[0]} ({r[1]})" for r in top))
    if low:
        lines.append("منتجات ناقصة: " + "، ".join(f"{r[0]} ({r[1]})" for r in low))
    return "\n".join(lines)


# ------------------------------------------------------------------
# سجل التعديلات والتراجع
# ------------------------------------------------------------------
def ensure_audit(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS ai_log("
                 "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, summary TEXT, "
                 "undo TEXT, undone INTEGER DEFAULT 0)")
    conn.commit()


_AUDIT_DDL = ("CREATE TABLE IF NOT EXISTS ai_log("
              "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, summary TEXT, "
              "undo TEXT, undone INTEGER DEFAULT 0)")


def log_action(conn, kind, summary, undo):
    conn.execute(_AUDIT_DDL)   # آمن حتى لو لم يُنشأ الجدول بعد
    conn.execute("INSERT INTO ai_log(ts,kind,summary,undo) VALUES(?,?,?,?)",
                 (datetime.now().isoformat(" ", timespec="seconds"), kind, summary,
                  json.dumps(undo, ensure_ascii=False)))


def last_log(conn):
    r = conn.execute("SELECT id, kind, summary, ts FROM ai_log WHERE undone=0 ORDER BY id DESC LIMIT 1").fetchone()
    return tuple(r) if r else None


def undo_last(conn):
    """يتراجع عن آخر تعديل نفّذه المساعد ويعيد وصفه (أو None إن لم يوجد)."""
    row = conn.execute("SELECT id, kind, summary, undo FROM ai_log WHERE undone=0 ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None
    lid, kind, summary, raw = row[0], row[1], row[2], row[3]
    u = json.loads(raw)
    try:
        if kind == "prices":
            conn.executemany("UPDATE products SET price=? WHERE id=?", [(o, p) for p, o in u["old"]])
        elif kind == "min_stock":
            conn.executemany("UPDATE products SET min_stock=? WHERE id=?", [(o, p) for p, o in u["old"]])
        elif kind == "barcodes":
            conn.executemany("UPDATE products SET barcode=NULL WHERE id=?", [(p,) for p in u["ids"]])
        elif kind == "stock":
            conn.execute("UPDATE products SET stock = MAX(stock - ?, 0) WHERE id=?", (u["qty"], u["pid"]))
        elif kind == "new_product":
            used = conn.execute("SELECT 1 FROM sale_items WHERE product_id=? LIMIT 1", (u["pid"],)).fetchone()
            if used:
                raise ValueError("لا يمكن حذف المنتج لأنه تم بيعه بعد إضافته.")
            conn.execute("DELETE FROM products WHERE id=?", (u["pid"],))
        conn.execute("UPDATE ai_log SET undone=1 WHERE id=?", (lid,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return summary


# ------------------------------------------------------------------
# الباركود
# ------------------------------------------------------------------
def ean13(body12):
    s = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(body12))
    return body12 + str((10 - s % 10) % 10)


def plan_barcodes(conn):
    """يقترح باركود EAN-13 داخلياً (يبدأ بـ 20) للمنتجات التي بلا باركود."""
    rows = conn.execute("SELECT id, name, barcode FROM products").fetchall()
    used = {str(r[2]) for r in rows if r[2]}
    seq = 0
    for code in used:
        if len(code) == 13 and code.isdigit() and code.startswith("20"):
            seq = max(seq, int(code[2:12]))
    plan = []
    for pid, name, code in rows:
        if code:
            continue
        while True:
            seq += 1
            new = ean13("20" + str(seq).zfill(10))
            if new not in used:
                break
        used.add(new)
        plan.append((pid, name, new))
    return plan


def apply_barcodes(conn):
    plan = plan_barcodes(conn)
    if not plan:
        raise ValueError("كل المنتجات لديها باركود بالفعل.")
    try:
        conn.executemany("UPDATE products SET barcode=? WHERE id=?", [(c, p) for p, _, c in plan])
        log_action(conn, "barcodes", f"توليد باركود لـ {len(plan)} منتج", {"ids": [p for p, _, _ in plan]})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(plan)


# ------------------------------------------------------------------
# تعديلات جماعية (نسبة مئوية، حد التنبيه)
# ------------------------------------------------------------------
_SCOPE_ALL = {"كل", "لكل", "جميع", "لجميع", "كافه", "الكل", "كلها"}
_SCOPE_STOP = {"ارفع", "رفع", "زد", "زيد", "زياده", "زود", "خفض", "تخفيض", "انقص", "نزل", "انزل",
               "خصم", "قلل", "تقليل", "اسعار", "سعر", "الاسعار", "السعر", "بنسبه", "نسبه", "المئه",
               "المائه", "حد", "التنبيه", "الحد", "الادنى", "اجعل", "غير", "عدل", "حدد", "ضبط",
               "خلي", "ضع", "منتج", "المنتجات", "منتجات", "الى", "الي", "على", "هذا", "هذه", "بمقدار"}


def parse_scope(conn, text):
    """يعيد قائمة المنتجات المقصودة. يرفع ValueError إن لم يتحدد النطاق."""
    t = norm(text)
    words = t.split()
    if any(w in _SCOPE_ALL for w in words):
        return conn.execute("SELECT id, name, price, stock, min_stock, barcode FROM products").fetchall()
    tokens = [w for w in words if w not in _SCOPE_STOP and len(w) >= 3
              and not re.search(r"[\d%٪]", w)]
    rows = find_products(conn, " ".join(tokens), limit=500) if tokens else []
    if not rows:
        raise ValueError("حدّد المنتج المقصود باسمه، أو قل: «كل المنتجات».")
    return rows


def parse_pct(text):
    """يعيد النسبة موقّعة (سالبة للخفض) أو يرفع ValueError."""
    t = norm(text)
    m = _PCT_RE.search(t) or re.search(r"(?:بنسبه|نسبه)\s*(\d+(?:\.\d+)?)", t)
    if not m:
        raise ValueError("اكتب النسبة، مثل: ارفع أسعار كل المنتجات 10%")
    pct = float(m[1])
    down = has_any(t, _DOWN)
    if pct <= 0 or (down and pct >= 100) or pct > 300:
        raise ValueError("النسبة غير منطقية.")
    return -pct if down else pct


def _round_price(x):
    return max(round(round(x / 0.005) * 0.005, 3), 0.0)   # أقرب 5 بيسات


def plan_price_change(rows, pct):
    out = []
    for r in rows:
        pid, name, price = r[0], r[1], float(r[2])
        new = _round_price(price * (1 + pct / 100))
        if abs(new - price) > 1e-9:
            out.append((pid, name, price, new))
    return out


def apply_price_change(conn, ids, pct):
    ids = _clean_ids(ids)
    rows = conn.execute(f"SELECT id, name, price FROM products WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall()
    plan = plan_price_change(rows, pct)
    if not plan:
        raise ValueError("لن يتغير أي سعر.")
    try:
        conn.executemany("UPDATE products SET price=? WHERE id=?", [(n, p) for p, _, _, n in plan])
        log_action(conn, "prices", f"تغيير أسعار {len(plan)} منتج بنسبة {pct:+g}%",
                   {"old": [[p, o] for p, _, o, _ in plan]})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(plan)


def plan_min_stock(rows, value):
    return [(r[0], r[1], r[4], value) for r in rows if r[4] != value]


def apply_min_stock(conn, ids, value):
    if not (0 <= value <= 100000):
        raise ValueError("القيمة غير صالحة.")
    ids = _clean_ids(ids)
    rows = conn.execute(f"SELECT id, name, price, stock, min_stock FROM products WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall()
    plan = plan_min_stock(rows, value)
    if not plan:
        raise ValueError("حد التنبيه مطابق للقيمة المطلوبة بالفعل.")
    try:
        conn.executemany("UPDATE products SET min_stock=? WHERE id=?", [(value, p) for p, _, _, _ in plan])
        log_action(conn, "min_stock", f"ضبط حد التنبيه إلى {value} لـ {len(plan)} منتج",
                   {"old": [[p, o] for p, _, o, _ in plan]})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(plan)


def _clean_ids(ids):
    try:
        out = sorted({int(i) for i in ids})
    except (TypeError, ValueError):
        raise ValueError("بيانات غير صالحة.")
    if not out or len(out) > 2000:
        raise ValueError("بيانات غير صالحة.")
    return out


# ------------------------------------------------------------------
# تعديلات فردية (تُستدعى فقط بعد تأكيد المستخدم)
# ------------------------------------------------------------------
def name_exists(conn, name):
    n = norm(name)
    return next((r for r in get_products(conn) if norm(r[1]) == n), None)


def db_add_product(conn, name, qty, price):
    name, qty, price = validate_product(name, qty, price)
    try:
        cur = conn.execute("INSERT INTO products(name,barcode,price,stock,min_stock,image) VALUES(?,?,?,?,?,?)",
                           (name, None, price, qty, 5, ""))
        log_action(conn, "new_product", f"إضافة المنتج «{name}»", {"pid": cur.lastrowid})
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def db_add_stock(conn, pid, qty):
    if not (0 < qty <= 1_000_000):
        raise ValueError("الكمية يجب أن تكون رقماً موجباً.")
    try:
        cur = conn.execute("UPDATE products SET stock = stock + ? WHERE id=?", (qty, pid))
        if cur.rowcount != 1:
            raise ValueError("المنتج غير موجود.")
        name = conn.execute("SELECT name FROM products WHERE id=?", (pid,)).fetchone()[0]
        log_action(conn, "stock", f"زيادة مخزون «{name}» بمقدار {qty}", {"pid": pid, "qty": qty})
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def db_set_price(conn, pid, price):
    if not (0 <= price <= 1_000_000):
        raise ValueError("السعر غير صالح.")
    try:
        old = conn.execute("SELECT name, price FROM products WHERE id=?", (pid,)).fetchone()
        if not old:
            raise ValueError("المنتج غير موجود.")
        conn.execute("UPDATE products SET price=? WHERE id=?", (round(price, 3), pid))
        log_action(conn, "prices", f"تغيير سعر «{old[0]}» إلى {round(price, 3):.3f}", {"old": [[pid, old[1]]]})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
