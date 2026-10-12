"""محرّك المساعد المشترك بين برنامج سطح المكتب وصفحة الويب.

يحوّل الجملة إلى «كتل عرض» (blocks) بسيطة: نص، أرقام، مخطط، جدول، بطاقة تأكيد...
وكل واجهة (Tkinter أو المتصفح) تعرض هذه الكتل بطريقتها. بهذا تُكتب كل ميزة مرة واحدة.

كتل العرض (dict):
  {"type":"text","text":...}
  {"type":"note","text":...}
  {"type":"stats","tiles":[{"label","value","tone"}]}
  {"type":"bars","items":[{"label","value","text"}]}
  {"type":"table","columns":[...],"rows":[[...]],"tags":[...],"widths":[...]}
  {"type":"op","title","fields":[{"key","label","value","width"}],"table":{...}|None,
        "buttons":[{"label","op":{...},"tone"}],"note"}
  {"type":"actions","buttons":[{"label","send"|"fill"|"export":{"title","columns","rows"}}]}
"""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

import ai_core as core


@dataclass
class Reply:
    blocks: list = field(default_factory=list)
    task: tuple = None      # (work, then): work() بطيء بلا قاعدة بيانات، then(value) -> Reply
    changed: bool = False   # هل تغيّرت البيانات؟ (لتحديث الصفحة المفتوحة)


# ---------------- مُنشئات الكتل ----------------
def text(t):
    return {"type": "text", "text": t}


def note(t):
    return {"type": "note", "text": t}


def stats(tiles):
    return {"type": "stats", "tiles": [{"label": a, "value": b, "tone": c} for a, b, c in tiles]}


def bars(items):
    return {"type": "bars", "items": [{"label": a, "value": b, "text": c} for a, b, c in items]}


def table(columns, rows, tags=None, widths=None):
    return {"type": "table", "columns": columns, "rows": [list(r) for r in rows],
            "tags": tags or [""] * len(rows), "widths": widths}


def export(title, columns, rows):
    return {"label": "💾 حفظ كملف Excel", "export": {"title": title, "columns": columns, "rows": [list(r) for r in rows]}}


def actions(buttons):
    return {"type": "actions", "buttons": buttons}


def op(title, buttons, fields=None, tbl=None, note_text=None):
    return {"type": "op", "title": title, "fields": fields or [], "table": tbl,
            "buttons": buttons, "note": note_text}


def _num(v):
    return core.norm(str(v)).replace(",", ".")


class Engine:
    def __init__(self, conn, currency="ر.ع"):
        self.conn = conn
        self.currency = currency
        core.ensure_audit(conn)

    # ------------------------------------------------------------------
    def money(self, v):
        return f"{v:,.3f} {self.currency}"

    def resolve(self, reply):
        """تنفيذ متزامن للمهام البطيئة (يستخدمه الويب)."""
        while reply.task:
            work, then = reply.task
            try:
                value = work()
            except core.AIConnectionError:
                return Reply(self.conn_error())
            except ValueError as e:
                return Reply([text(str(e))])
            reply = then(value)
        return reply

    @staticmethod
    def conn_error():
        return [text("تعذّر الاتصال بالنموذج المحلي (Ollama).\n"
                     "تأكد أن Ollama يعمل وأن النموذج محمّل، ثم أعد المحاولة.\n"
                     "ويمكنك في الأثناء استخدام الأوامر التي لا تحتاج النموذج "
                     "(مثل: جرد، مبيعات اليوم، المنتجات الناقصة).")]

    # ------------------------------------------------------------------
    def welcome(self):
        today = date.today()
        try:
            t = core.q_totals(self.conn, today, today)
            low = len(core.q_low_stock(self.conn))
            extra = (f"\nمبيعات اليوم حتى الآن: {self.money(t['total'])} ({t['count']} فاتورة).\n" +
                     (f"⚠ هناك {low} منتج عند حد التنبيه أو أقل." if low else "✔ لا توجد منتجات ناقصة."))
        except Exception:
            extra = ""
        return [text("مرحباً 👋 أنا مساعدك الذكي في مكتبة الأمل." + extra +
                     "\nاضغط أحد الأزرار، أو اكتب طلبك بالعربية بحرية.")]

    def respond(self, message):
        message = (message or "").strip()
        if not message:
            return Reply()
        intent = core.detect_intent(message, self.conn)
        if intent:
            return self.dispatch(intent, message)

        def then(it):
            return self.dispatch(it, message)
        return Reply(task=(lambda: core.llm_intent(message), then))

    def dispatch(self, intent, msg):
        h = {
            "top_products": lambda: self.h_top(msg, False),
            "bottom_products": lambda: self.h_top(msg, True),
            "sales_summary": lambda: self.h_summary(msg),
            "inventory": lambda: self.h_inventory(msg),
            "low_stock": self.h_low,
            "reorder": self.h_reorder,
            "stagnant": lambda: self.h_stagnant(msg),
            "lookup": lambda: self.h_lookup(msg),
            "add_product": lambda: self.h_add(msg),
            "set_price": lambda: self.h_set_price(msg),
            "help": self.h_help,
            "gen_barcodes": self.h_barcodes,
            "bulk_price": lambda: self.h_bulk_price(msg),
            "min_stock": lambda: self.h_min_stock(msg),
            "add_stock": lambda: self.h_add_stock(msg),
            "undo": self.h_undo,
            "analysis": self.h_analysis,
            "free": lambda: self.h_free(msg),
        }.get(intent)
        return h() if h else self.h_free(msg)

    # ------------------------------------------------------------------
    def period(self, msg, default_days=None):
        today = date.today()
        r = core.parse_range(msg, today)
        if r:
            return r[0], r[1], core.fmt_range(*r), False
        s = today - timedelta(days=default_days - 1) if default_days else today.replace(day=1)
        return s, today, core.fmt_range(s, today), True

    # ---------------- التقارير ----------------
    def h_top(self, msg, asc):
        s, e, label, default = self.period(msg)
        n = core.extract_limit(msg, 10)
        by = "rev" if core.has_any(core.norm(msg), ("ايراد", "دخل", "قيمه")) else "qty"
        rows = core.q_top(self.conn, s, e, n, by, asc)
        if not rows:
            return Reply([text(f"لا توجد مبيعات في الفترة ({label}).")])
        kind = "أقل" if asc else "أكثر"
        suffix = "إيراداً" if by == "rev" else "مبيعاً"
        out = [text(f"{kind} {len(rows)} منتجات {suffix} — {label}"),
               bars([(r[0], r[1] if by == "qty" else r[2], f"{r[1]} قطعة • {self.money(r[2])}") for r in rows])]
        if default:
            out.append(note("عرضتُ هذا الشهر افتراضياً. يمكنك تحديد فترة، مثل: أكثر المنتجات مبيعاً آخر 7 أيام."))
        data = [(r[0], r[1], f"{r[2]:.3f}") for r in rows]
        out.append(actions([export(f"{kind}_مبيعا_{s}_{e}", ["المنتج", "الكمية المباعة", "الإيراد"], data)]))
        if not asc:
            out.append(text(f"🏆 الأفضل: «{rows[0][0]}» بمبيعات {rows[0][1]} قطعة."))
        return Reply(out)

    def h_summary(self, msg):
        today = date.today()
        r = core.parse_range(msg, today)
        if not r:
            tiles = []
            for name, s, e in (("اليوم", today, today), ("هذا الأسبوع", core.week_start(today), today),
                               ("هذا الشهر", today.replace(day=1), today)):
                t = core.q_totals(self.conn, s, e)
                tiles.append((f"{name} • {t['count']} فاتورة", self.money(t["total"]), None))
            return Reply([text("ملخص المبيعات:"), stats(tiles)])
        s, e = r
        t = core.q_totals(self.conn, s, e)
        if t["count"] == 0:
            return Reply([text(f"لا توجد مبيعات في الفترة ({core.fmt_range(s, e)}).")])
        out = [text(f"مبيعات {core.fmt_range(s, e)}:"),
               stats([("إجمالي المبيعات", self.money(t["total"]), "good"), ("عدد الفواتير", str(t["count"]), None),
                      ("متوسط الفاتورة", self.money(t["avg"]), None), ("القطع المباعة", str(t["items"]), None)])]
        daily = core.q_daily(self.conn, s, e)
        if len(daily) > 1 and (e - s).days <= 31:
            out.append(bars([(d[5:], v, self.money(v)) for d, v in daily]))
            out.append(note("المبيعات اليومية"))
        if daily:
            best = max(daily, key=lambda x: x[1])
            out.append(text(f"📌 أفضل يوم: {best[0]} بمبيعات {self.money(best[1])}."))
        return Reply(out)

    def h_inventory(self, msg):
        s, e, label, _ = self.period(msg)
        rows, k = core.q_inventory(self.conn, s, e)
        if not rows:
            return Reply([text("لا توجد منتجات مسجلة بعد.")])

        def status(stock, mn):
            return "نفد" if stock <= 0 else ("منخفض" if stock <= mn else "جيد")
        data = [(r[0], r[1], r[3], f"{r[4]:.3f}", status(r[1], r[2])) for r in rows]
        tags = [{"نفد": "bad", "منخفض": "warn"}.get(d[4], "") for d in data]
        full = [(r[0], r[1], r[2], f"{r[5]:.3f}", r[3], f"{r[4]:.3f}", status(r[1], r[2])) for r in rows]
        return Reply([
            text(f"جرد المنتجات — {label}"),
            stats([("عدد المنتجات", str(k["products"]), None), ("قيمة المخزون الحالي", self.money(k["stock_value"]), None),
                   ("القطع المباعة في الفترة", str(k["sold_qty"]), None), ("إيرادات الفترة", self.money(k["revenue"]), "good")]),
            table(["المنتج", "المخزون الحالي", "المباع في الفترة", "الإيراد", "الحالة"], data, tags, [240, 110, 120, 110, 80]),
            note("ملاحظة: النظام لا يحتفظ بسجل لحركة المخزون السابقة، لذلك يظهر المخزون الحالي مع مبيعات الفترة المحددة."),
            actions([export(f"جرد_{s}_{e}", ["المنتج", "المخزون الحالي", "حد التنبيه", "السعر", "المباع في الفترة",
                                              "الإيراد", "الحالة"], full)]),
        ])

    def h_low(self):
        rows = core.q_low_stock(self.conn)
        if not rows:
            return Reply([text("👍 لا توجد منتجات ناقصة، المخزون كله فوق حد التنبيه.")])
        cols = ["المنتج", "المخزون", "حد التنبيه", "الحالة"]
        data = [(r[0], r[1], r[2], "نفد" if r[1] <= 0 else "منخفض") for r in rows]
        return Reply([
            text(f"⚠ هناك {len(rows)} منتج عند حد التنبيه أو أقل:"),
            table(cols, data, ["bad" if d[3] == "نفد" else "warn" for d in data], [260, 100, 100, 100]),
            actions([{"label": "🛒 اقترح كميات الطلب", "send": "ماذا اطلب من المورد"}, export("المنتجات_الناقصة", cols, data)]),
        ])

    def h_reorder(self):
        rows = core.q_reorder(self.conn)
        if not rows:
            return Reply([text("👍 مخزونك يغطي مبيعات آخر 30 يوماً، لا حاجة لطلب الآن.")])
        cols = ["المنتج", "المخزون الحالي", "مبيع آخر 30 يوماً", "الكمية المقترحة"]
        return Reply([
            text("🛒 اقتراح قائمة الطلب من المورد:"),
            table(cols, rows, None, [250, 110, 130, 120]),
            note("الاقتراح = ما يغطي مبيعات 30 يوماً (أو ضعف حد التنبيه) ناقص ما لديك الآن. عدّل الكميات حسب خبرتك."),
            actions([export("قائمة_الطلب", cols, rows)]),
        ])

    def h_stagnant(self, msg):
        s, e, label, _ = self.period(msg, default_days=30)
        rows = core.q_stagnant(self.conn, s)
        if not rows:
            return Reply([text(f"👍 كل المنتجات المتوفرة بِيعت منها قطع منذ {s}.")])
        total = sum(r[2] for r in rows)
        cols = ["المنتج", "المخزون", "قيمة المخزون", "آخر بيع"]
        data = [(r[0], r[1], f"{r[2]:.3f}", r[3] or "لم يُبع بعد") for r in rows]
        return Reply([
            text(f"🐢 منتجات لم تُبَع منذ {s} ({len(rows)} منتج):"),
            stats([("قيمة المخزون الراكد", self.money(total), "warn"), ("عدد المنتجات", str(len(rows)), None)]),
            table(cols, data, None, [250, 90, 120, 130]),
            note("فكّر بتخفيض السعر أو تجميعها في عرض لتحريك هذه الأصناف."),
            actions([export("المنتجات_الراكدة", cols, data)]),
        ])

    def h_lookup(self, msg):
        matches = core.find_products(self.conn, msg)
        if not matches:
            return Reply([text("لم أجد منتجاً بهذا الاسم. تأكد من الاسم أو اكتب جزءاً منه.")])
        if len(matches) > 1:
            return Reply([text(f"وجدتُ {len(matches)} منتجات مطابقة:"),
                          table(["المنتج", "السعر", "المخزون"], [(m[1], f"{m[2]:.3f}", m[3]) for m in matches], None, [260, 100, 100])])
        today = date.today()
        p, sold = core.q_product_card(self.conn, matches[0][0], today.replace(day=1), today)
        _, name, price, stock, mn, barcode = p
        tone = "bad" if stock <= 0 else ("warn" if stock <= mn else "good")
        out = [text(f"«{name}»"),
               stats([("السعر", self.money(price), None), ("المخزون", str(stock), tone),
                      ("حد التنبيه", str(mn), None), ("مبيع هذا الشهر", str(sold), None)])]
        if barcode:
            out.append(note(f"الباركود: {barcode}"))
        out.append(actions([{"label": "✏ تغيير السعر", "fill": f"غيّر سعر {name} إلى "},
                            {"label": "📦 زيادة المخزون", "fill": f"زد مخزون {name} "}]))
        return Reply(out)

    def h_analysis(self):
        today = date.today()
        s = today.replace(day=1)
        elapsed = (today - s).days
        prev_end = s - timedelta(days=1)
        prev_s = prev_end.replace(day=1)
        prev_e = min(prev_s + timedelta(days=elapsed), prev_end)
        cur, prev = core.q_totals(self.conn, s, today), core.q_totals(self.conn, prev_s, prev_e)
        s90 = today - timedelta(days=89)
        t90 = core.q_totals(self.conn, s90, today)
        if t90["count"] == 0:
            return Reply([text("لا توجد مبيعات كافية للتحليل بعد. سجّل بعض الفواتير ثم أعد المحاولة.")])

        growth = ((cur["total"] - prev["total"]) / prev["total"] * 100) if prev["total"] > 0 else None
        out = [text("📊 تحليل أداء المكتبة"),
               stats([("مبيعات هذا الشهر", self.money(cur["total"]), None),
                      ("نفس الفترة من الشهر الماضي", self.money(prev["total"]), None),
                      ("التغيّر", "—" if growth is None else f"{growth:+.0f}%",
                       None if growth is None else ("good" if growth >= 0 else "bad")),
                      ("متوسط الفاتورة", self.money(cur["avg"]), None)])]
        tips = []
        if growth is not None:
            if growth <= -10:
                tips.append(f"المبيعات أقل بنحو {abs(growth):.0f}% من نفس الفترة الماضية؛ راجع توفر الأصناف الأكثر طلباً.")
            elif growth >= 10:
                tips.append(f"المبيعات أعلى بنحو {growth:.0f}% من نفس الفترة الماضية، استمر وحافظ على توفر المخزون.")

        wd = sorted(core.q_weekday(self.conn, s90, today), key=lambda r: -r[1])
        if len(wd) > 1:
            out.append(bars([(n, v, f"{self.money(v)} • {c} فاتورة") for n, v, c in wd[:7]]))
            out.append(note("المبيعات حسب أيام الأسبوع (آخر 90 يوماً)"))
            tips.append(f"أفضل أيامك مبيعاً: {wd[0][0]}، وأضعفها: {wd[-1][0]}. جهّز المخزون قبل اليوم الأقوى.")
        hrs = sorted(core.q_hours(self.conn, s90, today), key=lambda r: -r[1])[:5]
        if len(hrs) > 1:
            out.append(bars([(f"{h:02d}:00 - {h + 1:02d}:00", v, self.money(v)) for h, v, _ in hrs]))
            out.append(note("أوقات الذروة (آخر 90 يوماً)"))
            tips.append(f"ساعة الذروة حول {hrs[0][0]:02d}:00؛ تأكد من وجود كاشير جاهز وفكّة كافية.")

        top3 = core.q_top(self.conn, s90, today, 3)
        if top3 and t90["total"] > 0:
            share = sum(r[2] for r in top3) / t90["total"] * 100
            if share >= 60:
                tips.append(f"أكثر من {share:.0f}% من إيراداتك تأتي من 3 منتجات فقط؛ لا تدع مخزونها ينفد وفكّر بتنويع الأصناف.")
        low = len(core.q_low_stock(self.conn))
        if low:
            tips.append(f"هناك {low} منتج ناقص؛ اكتب «ماذا أطلب؟» لقائمة طلب جاهزة.")
        stag = core.q_stagnant(self.conn, today - timedelta(days=29))
        if stag:
            val = sum(r[2] for r in stag)
            if val > 0:
                tips.append(f"نحو {self.money(val)} عالقة في {len(stag)} منتج راكد (بلا مبيعات 30 يوماً)؛ جرّب عرضاً أو خصماً.")
        if tips:
            out.append(text("💡 توصيات:\n" + "\n".join("• " + t for t in tips)))
        out.append(actions([{"label": "📈 الأكثر مبيعاً", "send": "أكثر المنتجات مبيعا هذا الشهر"},
                            {"label": "🐢 المنتجات الراكدة", "send": "المنتجات الراكدة"},
                            {"label": "🛒 ماذا أطلب؟", "send": "ماذا اطلب من المورد"}]))
        return Reply(out)

    def h_help(self):
        return Reply([
            text("أستطيع مساعدتك في:\n"
                 "• المبيعات: «مبيعات اليوم»، «مبيعات من 1/10/2026 إلى 15/10/2026»\n"
                 "• الأكثر مبيعاً: «أكثر 5 منتجات مبيعاً آخر 7 أيام»\n"
                 "• الجرد: «جرد من 1/10/2026 إلى 31/10/2026» مع حفظه كملف Excel\n"
                 "• التحليل: «حلل مبيعاتي» (مقارنة، أوقات الذروة، توصيات)\n"
                 "• التنبيهات: «المنتجات الناقصة»، «ماذا أطلب؟»، «المنتجات الراكدة»\n"
                 "• الاستعلام: «كم سعر المساحة؟»\n"
                 "• تعديلات بتأكيد منك وقابلة للتراجع:\n"
                 "   «ضيف باركود لكل المنتجات»، «ارفع أسعار كل المنتجات 10%»،\n"
                 "   «اجعل حد التنبيه 10 لكل المنتجات»، «زد مخزون المساحة 50»،\n"
                 "   «أضف قلم أزرق 50 قطعة بسعر 0.2»، «غيّر سعر المساحة إلى 0.1»، «تراجع»"),
            actions([{"label": "حلل مبيعاتي", "send": "حلل مبيعاتي"},
                     {"label": "ضيف باركود لكل المنتجات", "send": "ضيف باركود لكل المنتجات"},
                     {"label": "جرد هذا الشهر", "send": "جرد هذا الشهر"}]),
        ])

    def h_free(self, msg):
        snap = core.snapshot_text(self.conn)
        user = f"بيانات المكتبة:\n{snap}\n\nسؤال المستخدم: {msg}"

        def then(ans):
            return Reply([text(ans or "لم أستطع الإجابة. جرّب «ماذا تستطيع؟».")])
        return Reply(task=(lambda: core.chat_text(core.SYSTEM_CHAT, user), then))

    # ---------------- التعديلات (كلها بتأكيد) ----------------
    def h_barcodes(self):
        plan = core.plan_barcodes(self.conn)
        if not plan:
            return Reply([text("✔ كل المنتجات لديها باركود بالفعل.")])
        rows = [(n, c) for _, n, c in plan]
        return Reply([
            text(f"وجدتُ {len(plan)} منتج بدون باركود. هذه الأكواد المقترحة (صيغة EAN-13 داخلية تبدأ بـ 20، "
                 "جاهزة للطباعة والمسح بقارئ الباركود):"),
            op("اعتماد الباركود", [{"label": f"✔ اعتمد الباركود لـ {len(plan)} منتج", "op": {"kind": "bulk_barcodes"}, "tone": "green"}],
               tbl=table(["المنتج", "الباركود المقترح"], rows, None, [300, 180]),
               note_text="يمكنك التراجع بعد الاعتماد بقول: تراجع"),
            actions([export("باركود_المنتجات", ["المنتج", "الباركود"], rows)]),
        ])

    def h_bulk_price(self, msg):
        try:
            pct = core.parse_pct(msg)
            rows = core.parse_scope(self.conn, msg)
        except ValueError as e:
            return Reply([text(str(e))])
        plan = core.plan_price_change(rows, pct)
        if not plan:
            return Reply([text("لن يتغير أي سعر بهذه النسبة.")])
        data = [(n, f"{o:.3f}", f"{nw:.3f}") for _, n, o, nw in plan]
        word = "رفع" if pct > 0 else "خفض"
        return Reply([
            text(f"سأقوم بـ{word} سعر {len(plan)} منتج بنسبة {abs(pct):g}% (مع التقريب لأقرب 5 بيسات). راجع التغييرات:"),
            op("تغيير الأسعار",
               [{"label": f"✔ طبّق على {len(plan)} منتج", "op": {"kind": "bulk_price", "pct": pct, "ids": [p[0] for p in plan]}, "tone": "green"}],
               tbl=table(["المنتج", "السعر الحالي", "السعر الجديد"], data, None, [260, 110, 110]),
               note_text="يمكنك التراجع بعد التطبيق بقول: تراجع"),
        ])

    def h_min_stock(self, msg):
        t = core.norm(msg)
        m = re.search(r"(?:حد التنبيه|الحد الادنى|حد الطلب)\D{0,20}(\d+)", t) or re.search(r"(\d+)", t)
        try:
            if not m:
                raise ValueError("اكتب القيمة، مثل: اجعل حد التنبيه 10 لكل المنتجات")
            value = int(m[1])
            rows = core.parse_scope(self.conn, re.sub(r"\d+", " ", t))
        except ValueError as e:
            return Reply([text(str(e))])
        plan = core.plan_min_stock(rows, value)
        if not plan:
            return Reply([text("حد التنبيه مطابق للقيمة المطلوبة بالفعل.")])
        return Reply([
            text(f"سأضبط حد التنبيه إلى {value} لـ {len(plan)} منتج:"),
            op("ضبط حد التنبيه",
               [{"label": f"✔ طبّق على {len(plan)} منتج", "op": {"kind": "min_stock", "value": value, "ids": [p[0] for p in plan]}, "tone": "green"}],
               tbl=table(["المنتج", "الحد الحالي", "الحد الجديد"], [(n, o, v) for _, n, o, v in plan], None, [260, 110, 110]),
               note_text="يمكنك التراجع بعد التطبيق بقول: تراجع"),
        ])

    def h_add_stock(self, msg):
        t = core.norm(msg)
        name = qty = None
        for pat, order in ((r"(?:زد|زيد|زود|اضف|ضيف)\s+(?:مخزون|كميه)\s+(.+?)\s+(?:ب|بمقدار)?\s*(\d+)\b", (1, 2)),
                           (r"(?:وصل(?:ت|ني)?|استلمت|جاني)\s+(\d+)\s*(?:قطعه|قطع|حبه|حبات|كرتون)?\s+(?:من\s+)?(.+)", (2, 1)),
                           (r"(?:زد|زيد|زود)\s+(\d+)\s*(?:قطعه|قطع)?\s+(?:ل|الى|الي)?\s*(.+)", (2, 1))):
            m = re.search(pat, t)
            if m:
                name, qty = m[order[0]].strip(), int(m[order[1]])
                break
        if not name or not qty:
            return Reply([text("اكتب اسم المنتج والكمية، مثل: «زد مخزون المساحة 50»")])
        matches = core.find_products(self.conn, name)
        if not matches:
            return Reply([text(f"لم أجد منتجاً باسم «{name}». تأكد من الاسم.")])
        if len(matches) > 1:
            return Reply([text("وجدتُ أكثر من منتج مطابق، اكتب الاسم بدقة أكبر:"),
                          table(["المنتج", "المخزون"], [(m_[1], m_[3]) for m_ in matches], None, [300, 100])])
        pid, pname, _, stock = matches[0][0], matches[0][1], matches[0][2], matches[0][3]
        return Reply([op(f"زيادة مخزون «{pname}» (الحالي: {stock})",
                         [{"label": "✔ تأكيد الزيادة", "op": {"kind": "add_stock", "pid": pid}, "tone": "green"}],
                         fields=[{"key": "quantity", "label": "الكمية المضافة", "value": str(qty), "width": 10}])])

    def h_add(self, msg):
        if not re.search(r"\d", core.norm(msg)):
            return Reply([text("لإضافة منتج اكتب الاسم والكمية والسعر، مثل:\n«أضف قلم أزرق 50 قطعة بسعر 0.2»")])
        return Reply(task=(lambda: core.parse_product(msg), self.add_form))

    def add_form(self, p):
        ex = core.name_exists(self.conn, p["name"])
        buttons = [{"label": "✔ أضف كمنتج جديد", "op": {"kind": "add_product"}, "tone": "green"}]
        note_text = None
        if ex:
            note_text = f"يوجد منتج بنفس الاسم (مخزونه الحالي: {ex[3]}). يمكنك زيادة مخزونه بدل تكراره."
            buttons = [{"label": "📦 زِد مخزون الموجود", "op": {"kind": "add_stock", "pid": ex[0]}, "tone": "primary"},
                       {"label": "أضف كمنتج مكرر", "op": {"kind": "add_product", "force": True}, "tone": "ghost"}]
        return Reply([op("فهمتُ الطلب. راجع البيانات وعدّلها إن لزم، ثم أكّد:", buttons, fields=[
            {"key": "name", "label": "اسم المنتج", "value": p["name"], "width": 30},
            {"key": "quantity", "label": "الكمية", "value": str(p["quantity"]), "width": 8},
            {"key": "price", "label": "سعر القطعة", "value": str(p["price"]), "width": 8}], note_text=note_text)])

    def h_set_price(self, msg):
        return Reply(task=(lambda: core.parse_price_change(msg), self.price_form))

    def price_form(self, p):
        matches = core.find_products(self.conn, p["product"])
        if not matches:
            return Reply([text(f"لم أجد منتجاً باسم «{p['product']}». تأكد من الاسم.")])
        if len(matches) > 1:
            return Reply([text("وجدتُ أكثر من منتج مطابق، اكتب الاسم بدقة أكبر:"),
                          table(["المنتج", "السعر الحالي"], [(m[1], f"{m[2]:.3f}") for m in matches], None, [300, 120])])
        pid, name, old = matches[0][0], matches[0][1], matches[0][2]
        return Reply([op(f"سأغيّر سعر «{name}» من {self.money(old)} إلى:",
                         [{"label": "✔ تأكيد التغيير", "op": {"kind": "set_price", "pid": pid}, "tone": "green"}],
                         fields=[{"key": "price", "label": "السعر الجديد", "value": str(p["price"]), "width": 10}])])

    def h_undo(self):
        last = core.last_log(self.conn)
        if not last:
            return Reply([text("لا توجد تعديلات سابقة من المساعد للتراجع عنها.")])
        return Reply([op(f"آخر تعديل: {last[2]} ({last[3]})",
                         [{"label": "↩ تراجع عن هذا التعديل", "op": {"kind": "undo"}, "tone": "green"}])])

    # ------------------------------------------------------------------
    # تنفيذ التعديلات بعد التأكيد (كل القيم تُتحقق هنا مهما كان مصدرها)
    # ------------------------------------------------------------------
    def execute(self, o):
        try:
            return self._execute(o or {})
        except ValueError as e:
            return Reply([text(f"⚠ {e}")])
        except Exception:
            return Reply([text("⚠ تعذّر تنفيذ العملية. لم يتغير شيء.")])

    def _execute(self, o):
        kind = o.get("kind")
        c = self.conn
        if kind == "add_product":
            try:
                qty = int(float(_num(o.get("quantity"))))
                price = float(_num(o.get("price")))
            except ValueError:
                raise ValueError("تأكد من إدخال الكمية والسعر كأرقام.")
            name, qty, price = core.validate_product(o.get("name"), qty, price)
            if core.name_exists(c, name) and not o.get("force"):
                raise ValueError("يوجد منتج بنفس الاسم بالفعل.")
            core.db_add_product(c, name, qty, price)
            return Reply([text(f"✔ تمت إضافة «{name}» — الكمية {qty} — السعر {self.money(price)}")], changed=True)
        if kind == "add_stock":
            try:
                qty = int(float(_num(o.get("quantity"))))
                pid = int(o.get("pid"))
            except (ValueError, TypeError):
                raise ValueError("تأكد من إدخال الكمية كرقم.")
            core.db_add_stock(c, pid, qty)
            return Reply([text(f"✔ تمت زيادة المخزون بمقدار {qty}")], changed=True)
        if kind == "set_price":
            try:
                price = float(_num(o.get("price")))
                pid = int(o.get("pid"))
            except (ValueError, TypeError):
                raise ValueError("أدخل السعر كرقم صحيح.")
            core.db_set_price(c, pid, price)
            return Reply([text(f"✔ تم تغيير السعر إلى {self.money(price)}")], changed=True)
        if kind == "bulk_barcodes":
            n = core.apply_barcodes(c)
            return Reply([text(f"✔ تم توليد الباركود لـ {n} منتج. اكتب «تراجع» إن أردت إلغاءه.")], changed=True)
        if kind == "bulk_price":
            try:
                pct = float(o.get("pct"))
            except (ValueError, TypeError):
                raise ValueError("النسبة غير صالحة.")
            if pct == 0 or not (-100 < pct <= 300):
                raise ValueError("النسبة غير منطقية.")
            n = core.apply_price_change(c, o.get("ids"), pct)
            return Reply([text(f"✔ تم تغيير أسعار {n} منتج. اكتب «تراجع» إن أردت إلغاءه.")], changed=True)
        if kind == "min_stock":
            try:
                value = int(o.get("value"))
            except (ValueError, TypeError):
                raise ValueError("القيمة غير صالحة.")
            n = core.apply_min_stock(c, o.get("ids"), value)
            return Reply([text(f"✔ تم ضبط حد التنبيه لـ {n} منتج. اكتب «تراجع» إن أردت إلغاءه.")], changed=True)
        if kind == "undo":
            s = core.undo_last(c)
            if s is None:
                raise ValueError("لا يوجد تعديل للتراجع عنه.")
            return Reply([text(f"↩ تم التراجع عن: {s}")], changed=True)
        raise ValueError("عملية غير معروفة.")
