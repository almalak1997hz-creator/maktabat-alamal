from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_file, send_from_directory
from werkzeug.exceptions import RequestEntityTooLarge
import sqlite3, os, secrets, shutil
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

APP_NAME = "مكتبة الأمل"
CURRENCY = "ر.ع"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "maktabat_alamal.db")
LOGO_DIR = os.path.join(BASE_DIR, "static")
# نفس مجلد صور برنامج سطح المكتب حتى تظهر الصور في النسختين
UPLOAD_DIR = os.path.join(BASE_DIR, "product_images")
ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
SECRET_FILE = os.path.join(BASE_DIR, ".secret_key")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

app = Flask(__name__, static_folder="static", template_folder="templates")
if os.path.exists(SECRET_FILE):
    SECRET_KEY = open(SECRET_FILE, encoding="utf-8").read().strip()
else:
    SECRET_KEY = secrets.token_hex(32)
    with open(SECRET_FILE, "w", encoding="utf-8") as f:
        f.write(SECRET_KEY)
app.secret_key = SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=4 * 1024 * 1024,
)


def db():
    c = sqlite3.connect(DB_FILE, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def ensure_column(c, table, column, definition):
    cols = {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    c = db()
    c.execute("""CREATE TABLE IF NOT EXISTS products(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        barcode TEXT UNIQUE,
        price REAL NOT NULL DEFAULT 0,
        stock INTEGER NOT NULL DEFAULT 0,
        min_stock INTEGER NOT NULL DEFAULT 5,
        image TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS sales(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_date TEXT NOT NULL,
        total REAL NOT NULL,
        paid REAL NOT NULL,
        change_amount REAL NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS sale_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_id INTEGER,
        product_id INTEGER,
        product_name TEXT,
        quantity INTEGER,
        price REAL,
        subtotal REAL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    ensure_column(c, "products", "image", "TEXT")
    ensure_column(c, "users", "created_at", "TEXT")
    ensure_column(c, "sales", "pay_method", "TEXT DEFAULT 'cash'")
    ensure_column(c, "sales", "discount", "REAL DEFAULT 0")
    ensure_column(c, "sales", "user", "TEXT")
    ensure_column(c, "sale_items", "cost", "REAL")
    ensure_column(c, "products", "cost", "REAL DEFAULT 0")
    if not c.execute("SELECT id FROM users LIMIT 1").fetchone():
        c.execute(
            "INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)",
            ("admin", generate_password_hash("1234"), datetime.now().isoformat(timespec="seconds")),
        )
    c.commit(); c.close()


init_db()


def save_product_image(file_storage):
    """حفظ الصورة المرفوعة وإرجاع اسم الملف (أو None إذا لم تُرفع صورة)."""
    if not file_storage or not file_storage.filename:
        return None
    ext = os.path.splitext(secure_filename(file_storage.filename))[1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        raise ValueError("صيغة الصورة غير مدعومة (PNG, JPG, GIF, BMP, WEBP).")
    name = f"product_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{ext}"
    file_storage.save(os.path.join(UPLOAD_DIR, name))
    return name


def image_url(value):
    """رابط عرض الصورة من اسم الملف المخزن (يدعم المسارات القديمة)."""
    if not value:
        return ""
    name = os.path.basename(str(value).replace("\\", "/"))
    if not os.path.isfile(os.path.join(UPLOAD_DIR, name)):
        return ""
    return url_for("product_image", name=name)


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


@app.route("/product-image/<path:name>")
@login_required
def product_image(name):
    return send_from_directory(UPLOAD_DIR, os.path.basename(name), max_age=3600)


@app.errorhandler(RequestEntityTooLarge)
def too_large(e):
    flash("حجم الصورة كبير جدًا (الحد الأقصى 4 ميغابايت).", "danger")
    return redirect(url_for("products"))


@app.context_processor
def globals_():
    return {"APP_NAME": APP_NAME, "CURRENCY": CURRENCY, "image_url": image_url}


@app.route("/health")
def health():
    return jsonify(ok=True, app=APP_NAME, time=datetime.now().isoformat(timespec="seconds"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        c = db(); user = c.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone(); c.close()
        if user and check_password_hash(user["password_hash"], p):
            session.clear(); session["user_id"] = user["id"]; session["username"] = user["username"]
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("اسم المستخدم أو كلمة المرور غير صحيحة.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    c = db()
    data = {
        "products": c.execute("SELECT COUNT(*) n FROM products").fetchone()["n"],
        "stock": c.execute("SELECT COALESCE(SUM(stock),0) n FROM products").fetchone()["n"],
        "low": c.execute("SELECT COUNT(*) n FROM products WHERE stock<=min_stock").fetchone()["n"],
        "today": c.execute("SELECT COALESCE(SUM(total),0) n FROM sales WHERE date(sale_date)=date('now','localtime')").fetchone()["n"],
        "month": c.execute("SELECT COALESCE(SUM(total),0) n FROM sales WHERE strftime('%Y-%m',sale_date)=strftime('%Y-%m','now','localtime')").fetchone()["n"],
        "latest": c.execute("SELECT * FROM sales ORDER BY id DESC LIMIT 10").fetchall(),
    }
    c.close(); return render_template("dashboard.html", **data)


@app.route("/pos")
@login_required
def pos(): return render_template("pos.html")


@app.route("/api/products")
@login_required
def api_products():
    q = request.args.get("q", "").strip()
    c = db()
    rows = c.execute(
        "SELECT id,name,barcode,price,stock,min_stock,image FROM products "
        "WHERE name LIKE ? OR COALESCE(barcode,'') LIKE ? ORDER BY name LIMIT 200",
        (f"%{q}%", f"%{q}%"),
    ).fetchall(); c.close()
    out = []
    for x in rows:
        d = dict(x); d["image_url"] = image_url(d.get("image")); out.append(d)
    return jsonify(out)


@app.post("/api/sale")
@login_required
def api_sale():
    d = request.get_json(silent=True) or {}
    items = d.get("items", [])
    method = "transfer" if d.get("method") == "transfer" else "cash"
    try: discount = max(0.0, float(d.get("discount", 0) or 0))
    except Exception: discount = 0.0

    try: paid = float(d.get("paid", 0) or 0)
    except Exception: paid = 0
    if not items: return jsonify(ok=False, message="السلة فارغة."), 400
    c = db()
    try:
        checked = []; total = 0.0
        for x in items:
            pid, qty = int(x["id"]), int(x["quantity"])
            p = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            if not p: raise ValueError("المنتج غير موجود.")
            if qty < 1 or p["stock"] < qty: raise ValueError(f"المخزون غير كافٍ: {p['name']}")
            sub = float(p["price"]) * qty; total += sub; checked.append((p, qty, sub))
        discount = min(discount, total); total = round(total - discount, 3)
        if method == "transfer": paid = total
        if paid < total: raise ValueError("المبلغ المدفوع أقل من الإجمالي.")
        change = max(0.0, paid - total)
        cur = c.execute(
            "INSERT INTO sales(sale_date,total,paid,change_amount,pay_method,discount,user) VALUES(?,?,?,?,?,?,?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), total, paid, change, method, discount, session.get("username")),
        )
        sid = cur.lastrowid
        for p, q, sub in checked:
            c.execute("INSERT INTO sale_items(sale_id,product_id,product_name,quantity,price,subtotal,cost) VALUES(?,?,?,?,?,?,?)",
                      (sid, p["id"], p["name"], q, p["price"], sub, (p["cost"] if "cost" in p.keys() else None) or None))
            c.execute("UPDATE products SET stock=stock-? WHERE id=?", (q, p["id"]))
        c.commit()
        try:
            import pro_features; pro_features.save_invoice(sid)   # حفظ الفاتورة تلقائياً في مجلد invoices
        except Exception: pass
        return jsonify(ok=True, sale_id=sid, total=total, change=change)
    except Exception as e:
        c.rollback(); return jsonify(ok=False, message=str(e)), 400
    finally: c.close()


@app.route("/products", methods=["GET", "POST"])
@login_required
def products():
    if request.method == "POST":
        c = db()
        try:
            n = request.form.get("name", "").strip()
            b = request.form.get("barcode", "").strip() or None
            price = float(request.form.get("price", "0").replace(",", "."))
            stock = int(request.form.get("stock", "0"))
            mn = int(request.form.get("min_stock", "5"))
            if not n: raise ValueError("أدخل اسم المنتج.")
            if price < 0 or stock < 0 or mn < 0: raise ValueError("القيم لا يمكن أن تكون سالبة.")
            img = save_product_image(request.files.get("image")) or ""
            cur = c.execute("INSERT INTO products(name,barcode,price,stock,min_stock,image) VALUES(?,?,?,?,?,?)", (n,b,price,stock,mn,img))
            if request.form.get("cost") and _can_cost(): c.execute("UPDATE products SET cost=? WHERE id=?", (max(0.0, float(request.form["cost"].replace(",", "."))), cur.lastrowid))
            c.commit(); flash("تمت إضافة المنتج.", "success")
        except Exception as e: c.rollback(); flash(str(e), "danger")
        finally: c.close()
    c = db(); rows = c.execute("SELECT * FROM products ORDER BY id DESC").fetchall(); c.close()
    return render_template("products.html", products=rows)


@app.route("/products/<int:pid>/edit", methods=["GET", "POST"])
@login_required
def edit_product(pid):
    c = db(); p = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not p: c.close(); flash("المنتج غير موجود.", "danger"); return redirect(url_for("products"))
    if request.method == "POST":
        try:
            n = request.form.get("name", "").strip(); b = request.form.get("barcode", "").strip() or None
            price = float(request.form.get("price", "0").replace(",", ".")); stock = int(request.form.get("stock", "0")); mn = int(request.form.get("min_stock", "5"))
            if not n: raise ValueError("أدخل اسم المنتج.")
            img = p["image"] or ""
            new_img = save_product_image(request.files.get("image"))
            if new_img: img = new_img
            elif request.form.get("remove_image"): img = ""
            c.execute("UPDATE products SET name=?,barcode=?,price=?,stock=?,min_stock=?,image=? WHERE id=?", (n,b,price,stock,mn,img,pid))
            if request.form.get("cost") is not None and _can_cost(): c.execute("UPDATE products SET cost=? WHERE id=?", (max(0.0, float((request.form["cost"] or "0").replace(",", "."))), pid))
            c.commit(); flash("تم حفظ التعديلات.", "success")
            return redirect(url_for("products"))
        except Exception as e: c.rollback(); flash(str(e), "danger")
    c.close(); return render_template("product_edit.html", product=p)


@app.post("/products/<int:pid>/delete")
@login_required
def delete_product(pid):
    c=db(); c.execute("DELETE FROM products WHERE id=?", (pid,)); c.commit(); c.close(); flash("تم حذف المنتج.", "success"); return redirect(url_for("products"))


@app.route("/inventory")
@login_required
def inventory():
    c=db(); rows=c.execute("SELECT * FROM products ORDER BY stock ASC,name").fetchall(); c.close(); return render_template("inventory.html", products=rows)


@app.route("/count")
@login_required
def count_inventory():
    c=db(); rows=c.execute("SELECT * FROM products ORDER BY name").fetchall(); c.close(); return render_template("count.html", products=rows)


@app.post("/count/<int:pid>")
@login_required
def update_stock(pid):
    try: stock=int(request.form.get("stock", "0"));
    except Exception: stock=-1
    c=db()
    if stock < 0: flash("الكمية غير صحيحة.", "danger")
    else: c.execute("UPDATE products SET stock=? WHERE id=?", (stock,pid)); c.commit(); flash("تم تحديث الجرد.", "success")
    c.close(); return redirect(url_for("count_inventory"))


@app.route("/sales")
@login_required
def sales():
    c=db(); rows=c.execute("SELECT * FROM sales ORDER BY id DESC LIMIT 1000").fetchall(); c.close(); return render_template("sales.html", sales=rows)


def _delete_sales(c, sale_ids, restore_stock, reset_numbering=False):
    if not sale_ids:
        return 0
    marks = ",".join("?" * len(sale_ids))
    if restore_stock:
        rows = c.execute(
            f"SELECT product_id, SUM(quantity) q FROM sale_items WHERE sale_id IN ({marks}) GROUP BY product_id",
            sale_ids,
        ).fetchall()
        for r in rows:
            if r["product_id"] is not None:
                c.execute("UPDATE products SET stock=stock+? WHERE id=?", (r["q"] or 0, r["product_id"]))
    c.execute(f"DELETE FROM sale_items WHERE sale_id IN ({marks})", sale_ids)
    c.execute(f"DELETE FROM sales WHERE id IN ({marks})", sale_ids)
    if reset_numbering and c.execute("SELECT COUNT(*) n FROM sales").fetchone()["n"] == 0:
        c.execute("DELETE FROM sqlite_sequence WHERE name IN ('sales','sale_items')")
    return len(sale_ids)


@app.post("/sales/<int:sid>/delete")
@login_required
def delete_sale(sid):
    restore = request.form.get("restore", "1") == "1"
    c = db()
    try:
        n = _delete_sales(c, [sid], restore); c.commit()
        flash("تم حذف الفاتورة." if n else "الفاتورة غير موجودة.", "success")
    except Exception as e:
        c.rollback(); flash(f"تعذر الحذف: {e}", "danger")
    finally: c.close()
    return redirect(url_for("sales"))


@app.post("/sales/delete-all")
@login_required
def delete_all_sales():
    restore = request.form.get("restore", "1") == "1"
    c = db()
    try:
        ids = [r["id"] for r in c.execute("SELECT id FROM sales").fetchall()]
        n = _delete_sales(c, ids, restore, reset_numbering=True); c.commit()
        flash(f"تم حذف {n} فاتورة.", "success")
    except Exception as e:
        c.rollback(); flash(f"تعذر الحذف: {e}", "danger")
    finally: c.close()
    return redirect(url_for("sales"))


@app.route("/reports")
@login_required
def reports():
    c=db()
    today=c.execute("SELECT COALESCE(SUM(total),0)n FROM sales WHERE date(sale_date)=date('now','localtime')").fetchone()["n"]
    week=c.execute("SELECT COALESCE(SUM(total),0)n FROM sales WHERE strftime('%Y-%W',sale_date)=strftime('%Y-%W','now','localtime')").fetchone()["n"]
    month=c.execute("SELECT COALESCE(SUM(total),0)n FROM sales WHERE strftime('%Y-%m',sale_date)=strftime('%Y-%m','now','localtime')").fetchone()["n"]
    top=c.execute("SELECT product_name,SUM(quantity) quantity,SUM(subtotal) amount FROM sale_items GROUP BY product_id ORDER BY quantity DESC LIMIT 20").fetchall()
    c.close(); return render_template("reports.html",today=today,week=week,month=month,top=top)


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        old=request.form.get("old_password", ""); new=request.form.get("new_password", "")
        c=db(); u=c.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
        if not check_password_hash(u["password_hash"], old): flash("كلمة المرور الحالية غير صحيحة.", "danger")
        elif len(new)<6: flash("استخدم كلمة مرور من 6 أحرف على الأقل.", "danger")
        else: c.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new), u["id"])); c.commit(); flash("تم تغيير كلمة المرور.", "success")
        c.close()
    return render_template("settings.html")


@app.post("/backup")
@login_required
def backup():
    stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
    dest=os.path.join(BACKUP_DIR, f"maktabat_alamal_{stamp}.db")
    c=db()
    try:
        dst=sqlite3.connect(dest)
        c.backup(dst); dst.close(); flash("تم إنشاء نسخة احتياطية بنجاح.", "success")
    except Exception as e: flash(f"تعذر إنشاء النسخة الاحتياطية: {e}", "danger")
    finally: c.close()
    return redirect(url_for("settings"))


@app.route("/api/summary")
@login_required
def summary():
    c=db(); d={
        "products":c.execute("SELECT COUNT(*)n FROM products").fetchone()["n"],
        "stock":c.execute("SELECT COALESCE(SUM(stock),0)n FROM products").fetchone()["n"],
        "low":c.execute("SELECT COUNT(*)n FROM products WHERE stock<=min_stock").fetchone()["n"],
        "today":c.execute("SELECT COALESCE(SUM(total),0)n FROM sales WHERE date(sale_date)=date('now','localtime')").fetchone()["n"],
        "month":c.execute("SELECT COALESCE(SUM(total),0)n FROM sales WHERE strftime('%Y-%m',sale_date)=strftime('%Y-%m','now','localtime')").fetchone()["n"],
    }; c.close(); return jsonify(d)


# المساعد الذكي (صفحة الويب)
import ai_web
ai_web.register(app, db, CURRENCY)


import ai_products
ai_products.register(app, db, login_required)
import pro_features


def _can_cost():
    return pro_features.has_perm("costs")


pro_features.register(app, db, login_required, BASE_DIR, APP_NAME, CURRENCY)


if __name__ == "__main__":
    from waitress import serve
    print(f"{APP_NAME}: http://127.0.0.1:5000")
    serve(app, host="127.0.0.1", port=5000, threads=8)
