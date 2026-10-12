"""مزايا مكتبة الأمل الاحترافية: فاتورة عُمانية (حراري 58/80مم + A4)، صلاحيات، مشاركة الرابط، ثيمات، تأثيرات.
التركيب في app.py قبل if __name__ == "__main__":
    import pro_features
    pro_features.register(app, db, login_required, BASE_DIR, APP_NAME, CURRENCY)
"""
import html as H, os
from datetime import datetime
from flask import request, session, jsonify, redirect, abort, flash, get_flashed_messages
from werkzeug.security import generate_password_hash

PERMS = {"pos": "نقطة البيع", "stock": "المنتجات والجرد", "sales": "الفواتير", "reports": "التقارير والأرباح", "costs": "أسعار الشراء والتكلفة"}
DEFAULTS = {"shop": "", "vatin": "", "phone": "", "addr": "", "vat": "5", "logo": "1", "show_vat": "1",
            "barcode": "1", "qr": "1", "footer": "شكراً لزيارتكم", "paper": "80", "autoprint": "1"}
GUARD = (("/products", "stock"), ("/count", "stock"), ("/inventory", "stock"), ("/reports", "reports"),
         ("/sales", "sales"), ("/pos", "pos"), ("/api/sale", "pos"))


_SAVE = {}


def has_perm(k):
    f = _SAVE.get("perm")
    return bool(f and f(k))


def save_invoice(sid):
    f = _SAVE.get("f")
    if f: f(sid)


def register(app, db, login_required, base_dir, app_name, currency):
    c = db()
    c.execute("CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT)")
    cols = {r[1] for r in c.execute("PRAGMA table_info(users)")}
    if "perms" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN perms TEXT")
    c.commit(); c.close()

    def cfg():
        c = db(); d = dict(DEFAULTS); d["shop"] = app_name
        d.update({r["k"]: r["v"] for r in c.execute("SELECT * FROM kv")}); c.close(); return d

    def my_perms():
        c = db(); u = c.execute("SELECT id,username,perms FROM users WHERE id=?", (session.get("user_id"),)).fetchone(); c.close()
        if not u: return set()
        if u["username"] == "admin" or u["perms"] == "all": return {"all"}
        return set((u["perms"] or "pos").split(","))

    def is_admin(): return "all" in my_perms()

    @app.before_request
    def gate():
        if not session.get("user_id"): return
        p = request.path
        for pre, perm in GUARD:
            if p.startswith(pre):
                ps = my_perms()
                if "all" not in ps and perm not in ps:
                    return ("ليست لديك صلاحية لهذه الصفحة.", 403)
        if p.startswith(("/pro/settings", "/pro/log", "/pro/close")) and not is_admin(): abort(403)

    # ---------------- الفاتورة ----------------
    def render_invoice(sid, args, logo_src="/static/logo.png", auto=True):
        s, g = cfg(), args.get
        paper = g("paper", s["paper"]); paper = paper if paper in ("58", "80", "a4") else "80"
        on = lambda k: (g(k) if g(k) is not None else s[k]) == "1"
        c = db(); sale = c.execute("SELECT * FROM sales WHERE id=?", (sid,)).fetchone()
        items = c.execute("SELECT * FROM sale_items WHERE sale_id=?", (sid,)).fetchall(); c.close()
        if not sale: abort(404)
        rate = float(s["vat"] or 0) if s["vatin"] else 0.0
        total = sale["total"]; vat = total * rate / (100 + rate) if rate else 0.0
        e = H.escape; f = lambda v: f"{v:,.3f}"
        logo = os.path.join(base_dir, "static", "logo.png")
        head = (f'<img class="lg" src="{logo_src}">' if on("logo") and os.path.exists(logo) else "")
        kind = "فاتورة ضريبية مبسّطة" if rate else "فاتورة مبيعات"
        rows = "".join(f"<tr><td>{e(i['product_name'])}</td><td>{i['quantity']}</td><td>{f(i['price'])}</td><td>{f(i['subtotal'])}</td></tr>" for i in items)
        vrow = (f"<tr><td colspan=3>المبلغ قبل الضريبة</td><td>{f(total - vat)}</td></tr>"
                f"<tr><td colspan=3>ضريبة القيمة المضافة {rate:g}%</td><td>{f(vat)}</td></tr>") if rate and on("show_vat") else ""
        bc = f'<div class="bc">{sid:08d}</div>' if on("barcode") else ""
        qr = ""
        if on("qr"):
            try:
                import segno
                pay = f"{s['shop']}|{s['vatin']}|{sale['sale_date']}|{total:.3f}|{vat:.3f}|{sid}"
                qr = '<div class=c style="margin-top:6px">' + segno.make(pay, error="m").svg_inline(scale=3, border=1) + "</div>"
            except Exception: qr = ""
        pmk = sale["pay_method"] if "pay_method" in sale.keys() else "cash"
        pm = {"transfer": "تحويل إلكتروني"}.get(pmk, "كاش")
        dis = (sale["discount"] if "discount" in sale.keys() else 0) or 0
        drow = f"<tr><td colspan=3>الخصم</td><td>-{dis:,.3f}</td></tr>" if dis > 0 else ""
        width = {"58": "52mm", "80": "76mm", "a4": "190mm"}[paper]
        size = "A4" if paper == "a4" else f"{paper}mm auto"
        fs = {"58": 10, "80": 12, "a4": 15}[paper]
        opts = "".join(f'<label><input type=checkbox {"checked" if on(k) else ""} data-k={k}> {t}</label>'
                       for k, t in (("logo", "الشعار"), ("show_vat", "تفصيل الضريبة"), ("barcode", "رقم الفاتورة"), ("qr", "QR")))
        return f"""<!doctype html><meta charset=utf-8><title>فاتورة {sid}</title><style>
@page{{size:{size};margin:{0 if paper != 'a4' else 12}mm}}*{{box-sizing:border-box}}
body{{font:{fs}px Tahoma,Arial;direction:rtl;margin:0;color:#000;background:#eee}}
.p{{width:{width};margin:8px auto;background:#fff;padding:{3 if paper != 'a4' else 10}mm}}
.c{{text-align:center}}.lg{{max-height:{70 if paper == 'a4' else 45}px}}h2{{margin:2px;font-size:{fs + 4}px}}
table{{width:100%;border-collapse:collapse}}th,td{{padding:2px;border-bottom:1px dashed #888;text-align:center}}td:first-child,th:first-child{{text-align:right}}
.t td{{font-weight:700;border-top:2px solid #000}}.bc{{font:700 {fs + 6}px monospace;letter-spacing:3px;margin:6px;text-align:center}}
.bar{{background:#2E7D5B;color:#fff;padding:8px;text-align:center;font-size:13px}}.bar a,.bar button,.bar select{{margin:0 5px}}
@media print{{.bar{{display:none}}body{{background:#fff}}.p{{margin:0;width:auto}}}}</style>
<div class=bar><select id=pp>{''.join(f'<option value={v} {"selected" if v == paper else ""}>{t}</option>' for v, t in (("58", "حراري 58مم"), ("80", "حراري 80مم"), ("a4", "A4")))}</select>{opts}
<button onclick=print()>🖨 طباعة</button></div>
<div class=p><div class=c>{head}<h2>{e(s['shop'])}</h2>{f'<div>الرقم الضريبي: {e(s["vatin"])}</div>' if s['vatin'] else ''}
<div>{e(s['addr'])} {e(s['phone'])}</div><b>{kind}</b><div>رقم: {sid} • {e(str(sale['sale_date']))}</div></div><hr>
<table><tr><th>الصنف</th><th>الكمية</th><th>السعر</th><th>المجموع</th></tr>{rows}{vrow}
{drow}<tr class=t><td colspan=3>الإجمالي ({e(currency)})</td><td>{f(total)}</td></tr>
<tr><td colspan=3>المدفوع</td><td>{f(sale['paid'])}</td></tr><tr><td colspan=3>المتبقي</td><td>{f(sale['change_amount'])}</td></tr>
<tr><td colspan=3>طريقة الدفع</td><td>{pm}</td></tr></table>
{bc}{qr}<div class=c>{e(s['footer'])}</div></div><script>
var q=new URLSearchParams(location.search);document.getElementById('pp').onchange=function(){{q.set('paper',this.value);location.search=q}};
document.querySelectorAll('[data-k]').forEach(function(x){{x.onchange=function(){{q.set(x.dataset.k,x.checked?1:0);location.search=q}}}});
{"setTimeout(print,400)" if (auto and s['autoprint'] == '1' and 'noprint' not in args) else ""}</script>"""

    @app.get("/invoice/<int:sid>")
    @login_required
    def invoice(sid): return render_invoice(sid, request.args)

    def _save(sid):
        d = os.path.join(base_dir, "invoices"); os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"invoice_{sid}.html"), "w", encoding="utf-8") as fh:
            fh.write(render_invoice(sid, {}, "../static/logo.png", False))
    _SAVE["f"] = _save
    _SAVE["perm"] = lambda k: ("all" in my_perms()) or (k in my_perms())

    # ---------------- الإعدادات والمستخدمون ----------------
    @app.route("/pro/settings", methods=["GET", "POST"])
    @login_required
    def pro_settings():
        if request.method == "POST":
            c = db(); f = request.form; a = f.get("action")
            if a == "invoice":
                for k in DEFAULTS:
                    v = f.get(k, "0") if k in ("logo", "show_vat", "barcode", "qr", "autoprint") else f.get(k, "").strip()
                    c.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (k, v))
                up = request.files.get("logofile")
                if up and up.filename:
                    os.makedirs(os.path.join(base_dir, "static"), exist_ok=True)
                    up.save(os.path.join(base_dir, "static", "logo.png"))
            elif a == "user" and f.get("username", "").strip() and len(f.get("password", "")) >= 6:
                try:
                    c.execute("INSERT INTO users(username,password_hash,created_at,perms) VALUES(?,?,?,?)",
                              (f["username"].strip(), generate_password_hash(f["password"]), datetime.now().isoformat(timespec="seconds"),
                               ",".join(k for k in PERMS if f.get("p_" + k)) or "pos"))
                except Exception: pass
            elif a == "perms":
                c.execute("UPDATE users SET perms=? WHERE id=? AND username!='admin'",
                          (",".join(k for k in PERMS if f.get("p_" + k)) or "pos", int(f["uid"])))
            elif a == "del":
                c.execute("DELETE FROM users WHERE id=? AND username!='admin'", (int(f["uid"]),))
            c.commit(); c.close(); return redirect("/pro/settings")
        s = cfg(); c = db(); us = c.execute("SELECT * FROM users").fetchall(); c.close()
        chk = lambda n, on, t: f'<label><input type=checkbox name="{n}" value=1 {"checked" if on else ""}> {t}</label> '
        pc = lambda p: "".join(chk("p_" + k, k in p, t) for k, t in PERMS.items())
        inp = lambda k, t: f'<label>{t}<input name={k} value="{H.escape(s[k])}"></label>'
        urows = "".join(f'<form method=post class=r><input type=hidden name=action value=perms><input type=hidden name=uid value={u["id"]}>'
                        f'<b>{H.escape(u["username"])}</b>' + ("<i>مدير النظام</i>" if u["username"] == "admin" else
                        pc((u["perms"] or "pos").split(",")) + f'<button>حفظ</button><button name=action value=del onclick="return confirm(\'حذف؟\')">🗑</button>') + "</form>" for u in us)
        return f"""<!doctype html><meta charset=utf-8><title>الإعدادات المتقدمة</title><style>
body{{font:15px Tahoma;direction:rtl;max-width:760px;margin:20px auto;padding:0 12px;background:#EDE1D4}}
section{{background:#fff;border-radius:14px;padding:16px;margin:14px 0;box-shadow:0 2px 8px #0002}}
input:not([type=checkbox]),select{{display:block;width:100%;padding:8px;margin:4px 0 10px;border:1px solid #ccb;border-radius:8px}}
button{{background:#2E7D5B;color:#fff;border:0;border-radius:8px;padding:8px 16px;cursor:pointer}}.r{{padding:8px 0;border-bottom:1px solid #eee}}</style>
<a href=/>← الرئيسية</a><section><h3>🧾 الفاتورة (نظام ضريبة القيمة المضافة العُماني)</h3>
<form method=post enctype=multipart/form-data><input type=hidden name=action value=invoice>
{inp('shop', 'اسم المنشأة')}{inp('vatin', 'الرقم الضريبي VATIN (اتركه فارغاً إن لم تكن مسجلاً)')}{inp('vat', 'نسبة الضريبة %')}{inp('phone', 'الهاتف')}{inp('addr', 'العنوان')}{inp('footer', 'عبارة أسفل الفاتورة')}
<label>الورق الافتراضي<select name=paper>{''.join(f'<option value={v} {"selected" if v == s["paper"] else ""}>{t}</option>' for v, t in (("58", "حراري 58مم"), ("80", "حراري 80مم"), ("a4", "A4")))}</select></label>
<label>شعار (PNG)<input type=file name=logofile accept=image/png></label>
{chk('logo', s['logo'] == '1', 'إظهار الشعار')}{chk('show_vat', s['show_vat'] == '1', 'تفصيل الضريبة')}{chk('barcode', s['barcode'] == '1', 'رقم الفاتورة')}{chk('qr', s['qr'] == '1', 'رمز QR')}{chk('autoprint', s['autoprint'] == '1', 'فتح الفاتورة وطباعتها بعد كل بيع')}
<p><button>حفظ</button></p></form></section>
<section><h3>👥 المستخدمون والصلاحيات</h3>{urows}<h4>مستخدم جديد</h4><form method=post><input type=hidden name=action value=user>
<input name=username placeholder="اسم المستخدم"><input name=password type=password placeholder="كلمة المرور (6+)">{pc(['pos', 'stock'])}<p><button>إضافة</button></p></form></section>"""

    import pro_more
    pro_more.register(app, db, login_required, base_dir, currency, my_perms)

    @app.get("/pro/share")
    @login_required
    def share():
        p = os.path.join(base_dir, "رابط_مكتبة_الأمل.txt")
        url = open(p, encoding="utf-8").read().strip() if os.path.exists(p) else ""
        return jsonify(url=url, fresh=datetime.fromtimestamp(os.path.getmtime(p)).strftime("%H:%M") if url else "")

    # ---------------- الثيمات + التأثيرات + المشاركة ----------------
    @app.after_request
    def inject(resp):
        try:
            if (resp.status_code != 200 or resp.mimetype != "text/html" or resp.direct_passthrough or not session.get("user_id")
                    or request.path.startswith(("/invoice", "/api", "/pro/share", "/static")) or b"pro-root" in resp.get_data()):
                return resp
            h = resp.get_data(as_text=True); i = h.lower().rfind("</body>")
            resp.set_data(h + PRO if i < 0 else h[:i] + PRO + h[i:])
        except Exception: pass
        return resp


PRO = r"""<style>
:root{--g1:#2E7D5B;--g2:#7b4f2c}
aside{background:linear-gradient(180deg,#3b2a1e,#5a3d27)!important;box-shadow:4px 0 24px #0003}
nav a{border-radius:12px;transition:.2s}nav a:hover{background:#ffffff22!important;transform:translateX(-6px)}
header{backdrop-filter:blur(10px);position:sticky;top:0;z-index:5}
.hero{background:linear-gradient(135deg,#2E7D5B,#7b4f2c)!important;color:#fff;border-radius:20px;box-shadow:0 12px 30px #2e7d5b55;animation:pIn .5s}
.cards>div{border-radius:18px;background:linear-gradient(145deg,#fff,#f6ede2)!important;box-shadow:0 6px 18px #0001;animation:pIn .5s both;transition:.25s}
.cards>div:hover{transform:translateY(-6px) rotate(-.4deg);box-shadow:0 16px 30px #0002}.cards b{background:linear-gradient(90deg,#2E7D5B,#7b4f2c);-webkit-background-clip:text;color:transparent}
.panel{border-radius:20px!important;box-shadow:0 8px 26px #0001;animation:pIn .5s both}
.pos{align-items:start}.cartpanel{position:sticky;top:76px;border-top:5px solid var(--g1)}
.grid{gap:14px!important}
.product{position:relative;border:0!important;border-radius:18px!important;background:linear-gradient(160deg,#fff,#f4eadf)!important;box-shadow:0 4px 14px #0001;overflow:hidden;animation:pIn .4s both;transition:transform .25s cubic-bezier(.2,.9,.3,1.4),box-shadow .25s}
.product:hover:not(.out){transform:translateY(-8px) scale(1.04)!important;box-shadow:0 18px 34px #2e7d5b44}
.product:hover img{transform:scale(1.12) rotate(2deg)}.product img{transition:.3s}
.product span{display:inline-block;background:#2E7D5B;color:#fff;border-radius:999px;padding:2px 12px;margin:4px 0;font-weight:700}
.product small{display:block;color:#8a7a6a}.product.low small{color:#c4873d;font-weight:700}
.product.out{filter:grayscale(1);opacity:.45}.product.pop{animation:pPop .35s}
.cartpanel .row{animation:pSlide .3s;border-radius:12px;padding:6px 8px;transition:.2s}.cartpanel .row:hover{background:#2E7D5B14}
.cartpanel .row button{width:26px;height:26px;border-radius:50%;border:0;background:#2E7D5B;color:#fff;cursor:pointer}
#total{font-size:1.5em;color:#2E7D5B}.btn.wide{background:linear-gradient(90deg,#2E7D5B,#3da578)!important;font-size:1.1em;padding:14px;border-radius:14px;box-shadow:0 8px 20px #2e7d5b66}
.search{border-radius:14px!important;transition:.2s}.search:focus{outline:0;box-shadow:0 0 0 4px #2e7d5b33}
@keyframes pIn{from{opacity:0;transform:translateY(14px)}}@keyframes pSlide{from{opacity:0;transform:translateX(-20px)}}
@keyframes pPop{50%{transform:scale(.92)}}
#pro-toast{position:fixed;top:18px;left:50%;transform:translate(-50%,-90px);background:#2b211b;color:#fff;padding:12px 22px;border-radius:14px;z-index:2147483001;transition:.35s;box-shadow:0 10px 30px #0005;direction:rtl}#pro-toast.s{transform:translate(-50%,0)}

html[data-th=night]{filter:invert(.9) hue-rotate(180deg)}html[data-th=night] img,html[data-th=night] video{filter:invert(1) hue-rotate(180deg)}
html[data-th=sepia]{filter:sepia(.4) saturate(1.1)}html[data-th=soft]{filter:brightness(.93) contrast(1.05)}
tbody tr,table tr{transition:background .15s,transform .15s}tbody tr:hover{background:#2E7D5B18!important;transform:scale(1.005)}
.card,[class*=card],[class*=product],[class*=tile],[class*=item]{transition:transform .2s,box-shadow .2s}
.card:hover,[class*=card]:hover,[class*=product]:hover,[class*=tile]:hover{transform:translateY(-5px) scale(1.02);box-shadow:0 12px 26px #0003;z-index:2}
button,.btn,a.btn{transition:transform .12s,filter .12s}button:hover,.btn:hover{filter:brightness(1.1);transform:translateY(-1px)}
#pro-root{position:fixed;right:16px;bottom:18px;z-index:2147482000;direction:rtl;font:14px Tahoma}
#pro-fab{width:48px;height:48px;border-radius:50%;border:0;background:#4A3628;color:#fff;font-size:22px;cursor:pointer;box-shadow:0 5px 14px #0004}
#pro-menu{display:none;position:absolute;right:0;bottom:58px;width:250px;background:#fff;color:#222;border-radius:14px;padding:12px;box-shadow:0 10px 30px #0004}
#pro-menu.o{display:block}#pro-menu button,#pro-menu a{display:block;width:100%;margin:4px 0;padding:8px;border:0;border-radius:8px;background:#EDE1D4;color:#222;text-align:right;cursor:pointer;text-decoration:none;box-sizing:border-box}
#pro-menu input{width:100%;box-sizing:border-box;padding:6px;direction:ltr;font-size:11px}@media print{#pro-root{display:none}}</style>
<div id="pro-root"><div id="pro-menu"><b>🎨 المظهر</b>
<button data-t="">☀ عادي</button><button data-t="soft">🌤 مريح للعين</button><button data-t="sepia">📜 دافئ</button><button data-t="night">🌙 ليلي</button>
<b>🔗 مشاركة الموقع</b><input id="pro-url" readonly placeholder="لا يوجد رابط حالياً"><button id="pro-copy">📋 نسخ الرابط</button><a id="pro-wa" target="_blank">🟢 إرسال واتساب</a>
<a href="/pro/settings">⚙ الفاتورة والمستخدمون</a></div><button id="pro-fab">✨</button></div>
<script>(function(){var d=document,r=d.documentElement,m=d.getElementById("pro-menu");
function T(t){if(t)r.setAttribute("data-th",t);else r.removeAttribute("data-th");try{localStorage.proTh=t||""}catch(e){}}
try{T(localStorage.proTh)}catch(e){}
m.querySelectorAll("[data-t]").forEach(function(b){b.onclick=function(){T(b.dataset.t)}});
d.getElementById("pro-fab").onclick=function(){m.classList.toggle("o");if(m.classList.contains("o"))fetch("/pro/share",{credentials:"same-origin"}).then(function(x){return x.json()}).then(function(j){
 var u=d.getElementById("pro-url");u.value=j.url||(/^(127\.|localhost|192\.168|10\.)/.test(location.hostname)?'':location.origin);if(!u.value)u.placeholder='الرابط العام غير جاهز بعد، انتظر قليلاً';d.getElementById("pro-wa").href="https://wa.me/?text="+encodeURIComponent("رابط مكتبة الأمل: "+u.value)})};
d.getElementById("pro-copy").onclick=function(){var u=d.getElementById("pro-url");u.select();navigator.clipboard?navigator.clipboard.writeText(u.value):d.execCommand("copy");this.textContent="✔ تم النسخ"};
var tb=d.createElement("div");tb.id="pro-toast";d.body.appendChild(tb);var tt;
window.alert=function(x){tb.textContent=x;tb.classList.add("s");clearTimeout(tt);tt=setTimeout(function(){tb.classList.remove("s")},3200)};
d.addEventListener("click",function(e){var b=e.target.closest&&e.target.closest(".product");if(b){b.classList.remove("pop");void b.offsetWidth;b.classList.add("pop")}});
new MutationObserver(function(){d.querySelectorAll(".product:not(.out):not(.low)").forEach(function(b){var m=/المخزون:\s*(\d+)/.exec(b.textContent);if(m&&+m[1]<=5)b.classList.add("low")})}).observe(d.body,{childList:true,subtree:true});

})();</script>"""
