"""مزايا إضافية: ترحيب وآيات، عملاء وديون، مرتجعات، إغلاق صندوق، رسوم، تصدير، نسخ احتياطي، سجل نشاط، PWA."""
import csv, glob, html as H, io, os, random, sqlite3, threading, time
from datetime import date, datetime
from flask import Response, abort, jsonify, redirect, render_template_string, request, session

LAUNCH = str(time.time())  # يتغير مع كل تشغيل للبرنامج
VERSES = [
    ("فَإِنَّ مَعَ الْعُسْرِ يُسْرًا ۝ إِنَّ مَعَ الْعُسْرِ يُسْرًا", "الشرح: 5-6"),
    ("وَمَن يَتَّقِ اللَّهَ يَجْعَل لَّهُ مَخْرَجًا ۝ وَيَرْزُقْهُ مِنْ حَيْثُ لَا يَحْتَسِبُ", "الطلاق: 2-3"),
    ("وَمَن يَتَوَكَّلْ عَلَى اللَّهِ فَهُوَ حَسْبُهُ", "الطلاق: 3"),
    ("وَأَن لَّيْسَ لِلْإِنسَانِ إِلَّا مَا سَعَىٰ", "النجم: 39"),
    ("وَقُلِ اعْمَلُوا فَسَيَرَى اللَّهُ عَمَلَكُمْ وَرَسُولُهُ وَالْمُؤْمِنُونَ", "التوبة: 105"),
    ("لَئِن شَكَرْتُمْ لَأَزِيدَنَّكُمْ", "إبراهيم: 7"),
    ("وَفِي السَّمَاءِ رِزْقُكُمْ وَمَا تُوعَدُونَ", "الذاريات: 22"),
    ("إِنَّ اللَّهَ مَعَ الصَّابِرِينَ", "البقرة: 153"),
    ("وَلَسَوْفَ يُعْطِيكَ رَبُّكَ فَتَرْضَىٰ", "الضحى: 5"),
    ("إِنَّ اللَّهَ لَا يُغَيِّرُ مَا بِقَوْمٍ حَتَّىٰ يُغَيِّرُوا مَا بِأَنفُسِهِمْ", "الرعد: 11"),
    ("رِجَالٌ لَّا تُلْهِيهِمْ تِجَارَةٌ وَلَا بَيْعٌ عَن ذِكْرِ اللَّهِ", "النور: 37"),
    ("وَأَوْفُوا الْكَيْلَ إِذَا كِلْتُمْ وَزِنُوا بِالْقِسْطَاسِ الْمُسْتَقِيمِ", "الإسراء: 35"),
    ("فَإِذَا عَزَمْتَ فَتَوَكَّلْ عَلَى اللَّهِ", "آل عمران: 159"),
    ("وَقُل رَّبِّ زِدْنِي عِلْمًا", "طه: 114"),
    ("وَأَحَلَّ اللَّهُ الْبَيْعَ وَحَرَّمَ الرِّبَا", "البقرة: 275"),
]
CHEER = [
    "كل فاتورة اليوم خطوة نحو متجر أكبر، واصل بحماس! 💪",
    "النجاح يصنعه من يبدأ يومه بنشاط وابتسامة، يومك سيكون رائعاً ✨",
    "عملك المنظّم اليوم هو أرباح الغد، أحسنت على اجتهادك 🌟",
    "الزبون الراضي أفضل إعلان، فابتسم وأبدع في خدمته 😊",
    "الصبر والإتقان يصنعان متجراً يثق به الناس، استمر! 🚀",
    "لا تستهِن بالخطوات الصغيرة، فالمبيعات الكبيرة تبدأ بقطعة واحدة 📚",
    "أنت تبني شيئاً جميلاً يوماً بعد يوم، فخورون بك 🏆",
    "ابدأ بنية طيبة وإتقان، والبركة تأتي بإذن الله 🌱",
    "يوم جديد وفرص جديدة، اجعله أفضل من الأمس 🌅",
    "التنظيم نصف النجاح، ومتجرك منظم بإذنه تعالى ✅",
]
LABELS = (("/api/sale", "بيع فاتورة"), ("/delete", "حذف"), ("/edit", "تعديل منتج"), ("/count", "تحديث جرد"), ("/returns", "مرتجع"),
          ("/pro/settings", "إعدادات/مستخدمون"), ("/pro/costs", "تحديث أسعار الشراء"), ("/pro/purchase", "تسجيل شراء"), ("/pro/close", "إغلاق صندوق"),
          ("/products", "إضافة منتج"), ("/settings", "إعدادات"), ("/backup", "نسخ احتياطي"))


def register(app, db, login_required, base_dir, currency, my_perms):
    c = db()
    def col(t, n, d):
        if n not in {r[1] for r in c.execute(f"PRAGMA table_info({t})")}: c.execute(f"ALTER TABLE {t} ADD COLUMN {n} {d}")
    for q in (              "CREATE TABLE IF NOT EXISTS returns(id INTEGER PRIMARY KEY AUTOINCREMENT,sale_id INT,product_id INT,qty INT,amount REAL,ts TEXT,user TEXT)",
              "CREATE TABLE IF NOT EXISTS closings(id INTEGER PRIMARY KEY AUTOINCREMENT,day TEXT,cash REAL,transfer REAL,counted REAL,diff REAL,user TEXT,ts TEXT)",
              "CREATE TABLE IF NOT EXISTS purchases(id INTEGER PRIMARY KEY AUTOINCREMENT,ts TEXT,product_id INT,name TEXT,qty INT,unit_cost REAL,supplier TEXT,user TEXT)",
              "CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY AUTOINCREMENT,ts TEXT,user TEXT,action TEXT)"): c.execute(q)
    col("sales", "discount", "REAL DEFAULT 0"); col("sales", "user", "TEXT"); col("products", "cost", "REAL DEFAULT 0"); col("sale_items", "cost", "REAL")
    c.commit(); c.close()

    can = lambda k: bool({"all", k} & my_perms())
    need = lambda k: None if can(k) else abort(403)
    e, f = H.escape, (lambda v: f"{(v or 0):,.3f}")
    NOW = lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def page(title, body):
        return render_template_string("{% extends 'base.html' %}{% block content %}{{ body|safe }}{% endblock %}", title=title, body=body)

    def one(sql, *a):
        k = db(); r = k.execute(sql, a).fetchone(); k.close(); return r[0] or 0

    def rows(sql, *a):
        k = db(); r = k.execute(sql, a).fetchall(); k.close(); return r

    # ---------- ترحيب وآية متغيرة ----------
    def quote():
        r = random.Random(date.today().isoformat() + LAUNCH)
        v = r.choice(VERSES); return {"cheer": r.choice(CHEER), "verse": v[0], "src": v[1]}
    app.jinja_env.globals.update(pro_quote=quote, pro_admin=lambda: "all" in my_perms(), pro_can=can)

    # ---------- لوحة المعلومات والرسوم ----------
    @app.get("/pro/api/dash")
    @login_required
    def dash():
        days = {r["d"]: r["t"] for r in rows("SELECT date(sale_date) d,SUM(total) t FROM sales WHERE date(sale_date)>=date('now','localtime','-13 days') GROUP BY d")}
        out = {"days": [], "low": [], "top": []}
        for i in range(13, -1, -1):
            d = rows("SELECT date('now','localtime',?)", f"-{i} days")[0][0]; out["days"].append([d[5:], round(days.get(d, 0), 3)])
        out["low"] = [dict(name=r["name"], stock=r["stock"]) for r in rows("SELECT name,stock FROM products WHERE stock<=min_stock ORDER BY stock LIMIT 8")]
        out["top"] = [dict(name=r["product_name"], qty=r["q"]) for r in rows("SELECT product_name,SUM(quantity) q FROM sale_items GROUP BY product_id ORDER BY q DESC LIMIT 5")]
        if can("reports"):
            prof = lambda w: one("SELECT SUM(si.subtotal-si.quantity*COALESCE(si.cost,p.cost,0)) FROM sale_items si JOIN sales s ON s.id=si.sale_id LEFT JOIN products p ON p.id=si.product_id WHERE " + w) \
                - one("SELECT SUM(discount) FROM sales WHERE " + w.replace("s.sale_date", "sale_date"))
            out["profit"] = {"week": round(prof("strftime('%Y-%W',s.sale_date)=strftime('%Y-%W','now','localtime')"), 3),
                             "month": round(prof("strftime('%Y-%m',s.sale_date)=strftime('%Y-%m','now','localtime')"), 3)}
        return jsonify(out)

    # ---------- المرتجعات ----------
    @app.route("/returns", methods=["GET", "POST"])
    @login_required
    def returns():
        need("sales"); msg = ""
        if request.method == "POST":
            k = db(); sid = int(request.form["sale_id"]); done = 0
            for it in k.execute("SELECT * FROM sale_items WHERE sale_id=?", (sid,)).fetchall():
                q = min(int(request.form.get(f"q{it['id']}") or 0), it["quantity"])
                if q > 0:
                    amt = q * it["price"]
                    k.execute("UPDATE sale_items SET quantity=quantity-?,subtotal=subtotal-? WHERE id=?", (q, amt, it["id"]))
                    k.execute("UPDATE sales SET total=MAX(0,total-?) WHERE id=?", (amt, sid))
                    k.execute("UPDATE products SET stock=stock+? WHERE id=?", (q, it["product_id"]))
                    k.execute("INSERT INTO returns(sale_id,product_id,qty,amount,ts,user) VALUES(?,?,?,?,?,?)", (sid, it["product_id"], q, amt, NOW(), session.get("username")))
                    done += 1
            k.commit(); k.close()
            try:
                import pro_features; pro_features.save_invoice(sid)
            except Exception: pass
            msg = f'<div class="alert ok">تم تسجيل المرتجع وتحديث المخزون ({done} صنف).</div>' if done else ""
        sid = request.args.get("sale_id") or request.form.get("sale_id") if request.method == "POST" else request.args.get("sale_id")
        form = ""
        if sid and str(sid).isdigit():
            its = rows("SELECT * FROM sale_items WHERE sale_id=?", int(sid))
            form = (f'<div class="panel"><h3>فاتورة #{int(sid)}</h3><form method=post><input type=hidden name=sale_id value={int(sid)}><table><tr><th>الصنف</th><th>المباع</th><th>كمية المرتجع</th></tr>'
                    + "".join(f'<tr><td>{e(i["product_name"])}</td><td>{i["quantity"]}</td><td><input name="q{i["id"]}" type=number min=0 max={i["quantity"]} value=0></td></tr>' for i in its)
                    + '</table><p><button class="btn">تأكيد المرتجع</button></p></form></div>') if its else '<div class="alert bad">الفاتورة غير موجودة.</div>'
        return page("المرتجعات", f'{msg}<div class="panel"><form class="form" method=get><input name=sale_id type=number placeholder="رقم الفاتورة" required><button class="btn">بحث</button></form></div>{form}')

    # ---------- إغلاق الصندوق (للمدير فقط) ----------
    @app.route("/pro/close", methods=["GET", "POST"])
    @login_required
    def close_day():
        if "all" not in my_perms(): abort(403)
        W = "date(sale_date)=date('now','localtime')"
        cash = one(f"SELECT SUM(CASE WHEN pay_method='transfer' THEN 0 ELSE MIN(paid,total) END) FROM sales WHERE {W}")
        tr = one(f"SELECT SUM(total) FROM sales WHERE pay_method='transfer' AND {W}")
        ret = one("SELECT SUM(amount) FROM returns WHERE date(ts)=date('now','localtime')")
        exp = cash - ret; info = ""
        if request.method == "POST":
            counted = float(request.form.get("counted") or 0); k = db()
            k.execute("INSERT INTO closings(day,cash,transfer,counted,diff,user,ts) VALUES(?,?,?,?,?,?,?)", (date.today().isoformat(), exp, tr, counted, counted - exp, session.get("username"), NOW()))
            k.commit(); k.close(); d = counted - exp
            info = f'<div class="alert {"ok" if abs(d) < 0.0005 else "bad"}">تم الإغلاق. الفرق: {f(d)} {currency} ({"مطابق ✓" if abs(d) < 0.0005 else "زيادة" if d > 0 else "عجز"})</div>'
        hist = "".join(f'<tr><td>{r["day"]}</td><td>{f(r["cash"])}</td><td>{f(r["transfer"])}</td><td>{f(r["counted"])}</td><td>{f(r["diff"])}</td><td>{e(r["user"] or "")}</td></tr>' for r in rows("SELECT * FROM closings ORDER BY id DESC LIMIT 10"))
        return page("إغلاق الصندوق", f'{info}<div class="cards"><div><small>كاش اليوم</small><b>{f(cash)}</b></div><div><small>تحويلات اليوم</small><b>{f(tr)}</b></div>'
                    f'<div><small>مرتجعات</small><b>{f(ret)}</b></div><div><small>المتوقع في الصندوق</small><b>{f(exp)}</b></div></div>'
                    f'<div class="panel"><form class="form" method=post><input name=counted type=number step=.001 placeholder="الكاش الفعلي الموجود الآن" required><button class="btn">إغلاق اليوم</button></form></div>'
                    f'<div class="panel"><h3>آخر الإغلاقات</h3><div class="tablewrap"><table><tr><th>اليوم</th><th>المتوقع</th><th>تحويل</th><th>الفعلي</th><th>الفرق</th><th>بواسطة</th></tr>{hist}</table></div></div>')

    # ---------- أسعار الشراء والبيع (لحساب الربح بدقة) ----------
    @app.route("/pro/costs", methods=["GET", "POST"])
    @login_required
    def costs():
        need("costs")
        if request.method == "POST":
            k = db()
            for kk, v in request.form.items():
                try:
                    if kk[0] == "c" and kk[1:].isdigit(): k.execute("UPDATE products SET cost=? WHERE id=?", (max(0.0, float(v or 0)), int(kk[1:])))
                    elif kk[0] == "p" and kk[1:].isdigit() and v != "": k.execute("UPDATE products SET price=? WHERE id=?", (max(0.0, float(v)), int(kk[1:])))
                except ValueError: pass
            k.commit(); k.close(); return redirect("/pro/costs")
        ps = rows("SELECT * FROM products ORDER BY name"); vc = sum((r["cost"] or 0) * max(r["stock"], 0) for r in ps); vs = sum(r["price"] * max(r["stock"], 0) for r in ps)
        def line(r):
            cst, pr = r["cost"] or 0, r["price"]; gain = pr - cst; mg = (gain / pr * 100) if pr else 0
            st = '<b class="bad">⚠ تبيع بخسارة</b>' if (cst and gain < 0) else ('<span class="muted">أدخل سعر الشراء</span>' if not cst else f'<b class="ok">{mg:.0f}%</b>')
            return (f'<tr><td>{e(r["name"])}</td><td><input name="c{r["id"]}" type=number step=.001 min=0 value="{cst}"></td>'
                    f'<td><input name="p{r["id"]}" type=number step=.001 min=0 value="{pr}"></td><td>{f(gain) if cst else "—"}</td><td>{st}</td></tr>')
        return page("أسعار الشراء والبيع", f'<div class="cards"><div><small>قيمة المخزون بسعر الشراء</small><b>{f(vc)}</b></div><div><small>قيمته بسعر البيع</small><b>{f(vs)}</b></div><div><small>الربح المتوقع</small><b>{f(vs - vc)}</b></div></div>'
                    f'<div class="panel"><p class="muted">سعر الشراء = كم اشتريتَ القطعة. يُسجَّل مع كل بيع فتبقى أرباح الفواتير القديمة صحيحة حتى لو تغيّر السعر لاحقاً. للتوريدات الجديدة استخدم «🛍 تسجيل شراء».</p>'
                    f'<form method=post><div class="tablewrap"><table><tr><th>المنتج</th><th>سعر الشراء</th><th>سعر البيع</th><th>الربح للقطعة</th><th>الهامش</th></tr>{"".join(line(r) for r in ps)}</table></div><p><button class="btn">حفظ</button></p></form></div>')

    @app.route("/pro/purchase", methods=["GET", "POST"])
    @login_required
    def purchase():
        need("costs"); msg = ""
        if request.method == "POST":
            try:
                pid, q, uc = int(request.form["pid"]), int(request.form["qty"]), float(request.form["unit_cost"])
                if q <= 0 or uc < 0: raise ValueError
                k = db(); pr = k.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
                old = max(pr["stock"], 0); new_cost = round(((old * (pr["cost"] or 0)) + q * uc) / (old + q), 3)
                k.execute("UPDATE products SET stock=stock+?,cost=? WHERE id=?", (q, new_cost, pid))
                k.execute("INSERT INTO purchases(ts,product_id,name,qty,unit_cost,supplier,user) VALUES(?,?,?,?,?,?,?)", (NOW(), pid, pr["name"], q, uc, request.form.get("supplier", "").strip(), session.get("username")))
                k.commit(); k.close()
                msg = f'<div class="alert success">تم تسجيل الشراء. المخزون زاد {q} ومتوسط سعر الشراء الجديد {f(new_cost)}.</div>'
            except Exception: msg = '<div class="alert danger">تحقق من البيانات (الكمية أكبر من صفر والسعر رقم صحيح).</div>'
        opts = "".join(f'<option value={r["id"]}>{e(r["name"])} (المخزون {r["stock"]})</option>' for r in rows("SELECT id,name,stock FROM products ORDER BY name"))
        hist = "".join(f'<tr><td>{r["ts"]}</td><td>{e(r["name"])}</td><td>{r["qty"]}</td><td>{f(r["unit_cost"])}</td><td>{f(r["qty"] * r["unit_cost"])}</td><td>{e(r["supplier"] or "")}</td><td>{e(r["user"] or "")}</td></tr>' for r in rows("SELECT * FROM purchases ORDER BY id DESC LIMIT 25"))
        month = one("SELECT SUM(qty*unit_cost) FROM purchases WHERE strftime('%Y-%m',ts)=strftime('%Y-%m','now','localtime')")
        return page("تسجيل شراء", f'{msg}<div class="cards"><div><small>مشتريات هذا الشهر</small><b>{f(month)}</b></div></div><div class="panel"><h3>🛍 توريد جديد</h3><form class="form" method=post>'
                    f'<select name=pid class="search">{opts}</select><input name=qty type=number min=1 placeholder="الكمية المشتراة" required><input name=unit_cost type=number step=.001 min=0 placeholder="سعر شراء القطعة" required>'
                    f'<input name=supplier placeholder="المورّد (اختياري)"><button class="btn">تسجيل</button></form></div>'
                    f'<div class="panel"><h3>آخر المشتريات</h3><div class="tablewrap"><table><tr><th>الوقت</th><th>المنتج</th><th>الكمية</th><th>سعر القطعة</th><th>الإجمالي</th><th>المورّد</th><th>بواسطة</th></tr>{hist or "<tr><td colspan=7>—</td></tr>"}</table></div></div>')

    # ---------- تصدير ----------
    def table(what):
        if what == "sales":
            return (["الفاتورة", "التاريخ", "الإجمالي", "المدفوع", "الخصم", "الدفع"],
                    [[r["id"], r["sale_date"], r["total"], r["paid"], r["discount"] or 0, r["pay_method"]] for r in rows("SELECT * FROM sales ORDER BY id DESC")])
        if what in ("products", "inventory"):
            return (["المنتج", "الباركود", "السعر", "الكمية", "الحد", "التكلفة"],
                    [[r["name"], r["barcode"] or "", r["price"], r["stock"], r["min_stock"], r["cost"] or 0] for r in rows("SELECT * FROM products ORDER BY name")])
        abort(404)

    @app.get("/pro/export/<what>.csv")
    @login_required
    def export(what):
        need("sales" if what == "sales" else "stock"); h, r = table(what); b = io.StringIO(); w = csv.writer(b); w.writerow(h); w.writerows(r)
        return Response("\ufeff" + b.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={what}_{date.today()}.csv"})

    @app.get("/pro/print/<what>")
    @login_required
    def printable(what):
        need("sales" if what == "sales" else "stock"); h, r = table(what)
        return (f'<!doctype html><meta charset=utf-8><title>{what}</title><style>body{{font:13px Tahoma;direction:rtl}}table{{width:100%;border-collapse:collapse}}td,th{{border:1px solid #999;padding:5px}}'
                f'@media print{{button{{display:none}}}}</style><button onclick=print()>🖨 طباعة / حفظ PDF</button><table><tr>{"".join(f"<th>{x}</th>" for x in h)}</tr>'
                + "".join("<tr>" + "".join(f"<td>{e(str(x))}</td>" for x in row) + "</tr>" for row in r) + "</table>")

    # ---------- سجل النشاط ----------
    @app.after_request
    def log_it(resp):
        try:
            if request.method == "POST" and session.get("user_id") and resp.status_code < 400 and not request.path.startswith(("/static", "/pro/api", "/api/ai")):
                lab = next((t for k, t in LABELS if k in request.path), request.path)
                k = db(); k.execute("INSERT INTO activity(ts,user,action) VALUES(?,?,?)", (NOW(), session.get("username"), f"{lab} — {request.path}")); k.commit(); k.close()
        except Exception: pass
        return resp

    @app.get("/pro/log")
    @login_required
    def log_page():
        if "all" not in my_perms(): abort(403)
        tr = "".join(f'<tr><td>{r["ts"]}</td><td>{e(r["user"] or "")}</td><td>{e(r["action"])}</td></tr>' for r in rows("SELECT * FROM activity ORDER BY id DESC LIMIT 300"))
        return page("سجل النشاط", f'<div class="panel"><div class="tablewrap"><table><tr><th>الوقت</th><th>المستخدم</th><th>العملية</th></tr>{tr}</table></div></div>')

    # ---------- ملخص المدير: من يبيع أكثر ----------
    @app.get("/pro/summary")
    @login_required
    def pro_summary():
        need("reports")
        P = {"today": ("اليوم", "date(sale_date)=date('now','localtime')"), "week": ("هذا الأسبوع", "strftime('%Y-%W',sale_date)=strftime('%Y-%W','now','localtime')"),
             "month": ("هذا الشهر", "strftime('%Y-%m',sale_date)=strftime('%Y-%m','now','localtime')"), "all": ("كل الوقت", "1=1")}
        key = request.args.get("p") if request.args.get("p") in P else "today"; label, W = P[key]
        tot = one(f"SELECT SUM(total) FROM sales WHERE {W}"); n = one(f"SELECT COUNT(*) FROM sales WHERE {W}")
        cash = one(f"SELECT SUM(total) FROM sales WHERE pay_method!='transfer' AND {W}"); tr = one(f"SELECT SUM(total) FROM sales WHERE pay_method='transfer' AND {W}")
        disc = one(f"SELECT SUM(discount) FROM sales WHERE {W}")
        prof = {r["u"]: r["pr"] or 0 for r in rows(f"SELECT COALESCE(s.user,'غير معروف') u,SUM(si.subtotal-si.quantity*COALESCE(si.cost,p.cost,0)) pr FROM sale_items si JOIN sales s ON s.id=si.sale_id LEFT JOIN products p ON p.id=si.product_id WHERE {W.replace('sale_date','s.sale_date')} GROUP BY u")}
        us = rows(f"SELECT COALESCE(user,'غير معروف') u,COUNT(*) n,SUM(total) t,SUM(discount) d FROM sales WHERE {W} GROUP BY u ORDER BY t DESC")
        mx = max([r["t"] or 0 for r in us] + [1]); medals = ["🥇", "🥈", "🥉"]
        ut = "".join(f'<tr><td>{medals[i] if i < 3 else i + 1}</td><td><b>{e(r["u"])}</b></td><td>{r["n"]}</td><td>{f(r["t"])}</td><td>{f((r["t"] or 0) / r["n"])}</td>'
                     f'<td>{f(prof.get(r["u"], 0) - (r["d"] or 0))}</td><td style="min-width:120px"><div style="background:#eee;border-radius:8px"><div style="height:10px;border-radius:8px;background:#2E7D5B;width:{int((r["t"] or 0) / mx * 100)}%"></div></div></td></tr>' for i, r in enumerate(us))
        pt = "".join(f'<tr><td>{e(r["product_name"])}</td><td>{r["q"]}</td><td>{f(r["a"])}</td></tr>' for r in rows(
            f"SELECT si.product_name,SUM(si.quantity) q,SUM(si.subtotal) a FROM sale_items si JOIN sales s ON s.id=si.sale_id WHERE {W.replace('sale_date','s.sale_date')} GROUP BY si.product_id ORDER BY q DESC LIMIT 8"))
        tabs = "".join(f'<a class="mini" style="{"background:#2E7D5B;color:#fff" if k == key else ""}" href="/pro/summary?p={k}">{v[0]}</a> ' for k, v in P.items())
        return page("ملخص المدير", f'<div class="panel">{tabs}</div><div class="cards"><div><small>المبيعات {label}</small><b>{f(tot)}</b></div><div><small>عدد الفواتير</small><b>{n}</b></div>'
                    f'<div><small>كاش</small><b>{f(cash)}</b></div><div><small>تحويلات</small><b>{f(tr)}</b></div><div><small>الخصومات</small><b>{f(disc)}</b></div></div>'
                    f'<div class="panel"><h3>🏆 ترتيب المستخدمين حسب المبيعات ({label})</h3><div class="tablewrap"><table><tr><th>#</th><th>المستخدم</th><th>الفواتير</th><th>المبيعات</th><th>متوسط الفاتورة</th><th>الربح*</th><th></th></tr>'
                    f'{ut or "<tr><td colspan=7>لا توجد مبيعات</td></tr>"}</table></div><p class="muted">*الربح يحتاج إدخال تكلفة المنتجات. المبيعات القديمة قبل هذا التحديث تظهر باسم «غير معروف».</p></div>'
                    f'<div class="panel"><h3>الأكثر مبيعاً ({label})</h3><div class="tablewrap"><table><tr><th>المنتج</th><th>الكمية</th><th>القيمة</th></tr>{pt or "<tr><td colspan=3>—</td></tr>"}</table></div></div>')

    # ---------- نسخ احتياطي يومي تلقائي ----------
    def backup_loop():
        while True:
            try:
                d = os.path.join(base_dir, "backups"); os.makedirs(d, exist_ok=True); fn = os.path.join(d, f"auto_{date.today()}.db")
                if not os.path.exists(fn):
                    s = db(); t = sqlite3.connect(fn); s.backup(t); t.close(); s.close()
                    for old in sorted(glob.glob(os.path.join(d, "auto_*.db")))[:-14]: os.remove(old)
            except Exception as ex: print("[backup]", ex)
            time.sleep(3600)
    threading.Thread(target=backup_loop, daemon=True).start()

    # ---------- PWA ----------
    @app.get("/manifest.webmanifest")
    def manifest():
        return jsonify(name="مكتبة الأمل", short_name="مكتبة الأمل", start_url="/", display="standalone", background_color="#EDE1D4", theme_color="#7b4f2c", dir="rtl", lang="ar",
                       icons=[{"src": "/static/logo.png", "sizes": "512x512", "type": "image/png"}])

    @app.get("/sw.js")
    def sw(): return Response("self.addEventListener('fetch',function(){});", mimetype="application/javascript")

    # ---------- حقائق حيّة للمساعد الذكي ----------
    def facts():
        low = ", ".join(r["name"] for r in rows("SELECT name FROM products WHERE stock<=min_stock LIMIT 6")) or "لا يوجد"
        top = ", ".join(f'{r["product_name"]} ({r["q"]})' for r in rows("SELECT product_name,SUM(quantity) q FROM sale_items GROUP BY product_id ORDER BY q DESC LIMIT 3")) or "لا يوجد"
        today = one("SELECT SUM(total) FROM sales WHERE date(sale_date)=date('now','localtime')")
        month = one("SELECT SUM(total) FROM sales WHERE strftime('%Y-%m',sale_date)=strftime('%Y-%m','now','localtime')")
        return f"مبيعات اليوم: {today:.3f}؛ مبيعات الشهر: {month:.3f}. منتجات ناقصة: {low}. الأكثر مبيعاً: {top}."
    globals()["_facts"] = facts


def facts():
    f = globals().get("_facts")
    return f() if f else ""
