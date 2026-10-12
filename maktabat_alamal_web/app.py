from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import sqlite3, os, secrets
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

APP_NAME = "مكتبة الأمل"
CURRENCY = "ر.ع"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "maktabat_alamal.db")
SECRET_FILE = os.path.join(BASE_DIR, ".secret_key")
app = Flask(__name__)
if os.path.exists(SECRET_FILE):
    SECRET_KEY = open(SECRET_FILE, encoding='utf-8').read().strip()
else:
    SECRET_KEY = secrets.token_hex(32)
    with open(SECRET_FILE, 'w', encoding='utf-8') as f: f.write(SECRET_KEY)
app.secret_key = SECRET_KEY
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

def db():
    c=sqlite3.connect(DB_FILE, timeout=20); c.row_factory=sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL'); return c

def init_db():
    c=db()
    c.execute('''CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,barcode TEXT UNIQUE,price REAL NOT NULL DEFAULT 0,stock INTEGER NOT NULL DEFAULT 0,min_stock INTEGER NOT NULL DEFAULT 5,image TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sales(id INTEGER PRIMARY KEY AUTOINCREMENT,sale_date TEXT NOT NULL,total REAL NOT NULL,paid REAL NOT NULL,change_amount REAL NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sale_items(id INTEGER PRIMARY KEY AUTOINCREMENT,sale_id INTEGER,product_id INTEGER,product_name TEXT,quantity INTEGER,price REAL,subtotal REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,created_at TEXT NOT NULL)''')
    if not c.execute('SELECT id FROM users LIMIT 1').fetchone():
        c.execute('INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)',('admin',generate_password_hash('1234'),datetime.now().isoformat(timespec='seconds')))
    c.commit(); c.close()

def login_required(fn):
    @wraps(fn)
    def w(*a,**k): return fn(*a,**k) if session.get('user_id') else redirect(url_for('login',next=request.path))
    return w

@app.context_processor
def globals_(): return {'APP_NAME':APP_NAME,'CURRENCY':CURRENCY}

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        u=request.form.get('username','').strip(); p=request.form.get('password',''); c=db(); user=c.execute('SELECT * FROM users WHERE username=?',(u,)).fetchone(); c.close()
        if user and check_password_hash(user['password_hash'],p): session.clear(); session['user_id']=user['id']; session['username']=user['username']; return redirect(request.args.get('next') or '/')
        flash('اسم المستخدم أو كلمة المرور غير صحيحة.','danger')
    return render_template('login.html')
@app.route('/logout')
def logout(): session.clear(); return redirect('/login')

@app.route('/')
@login_required
def dashboard():
    c=db(); data={
      'products':c.execute('SELECT COUNT(*) n FROM products').fetchone()['n'],
      'stock':c.execute('SELECT COALESCE(SUM(stock),0) n FROM products').fetchone()['n'],
      'low':c.execute('SELECT COUNT(*) n FROM products WHERE stock<=min_stock').fetchone()['n'],
      'today':c.execute("SELECT COALESCE(SUM(total),0) n FROM sales WHERE date(sale_date)=date('now','localtime')").fetchone()['n'],
      'month':c.execute("SELECT COALESCE(SUM(total),0) n FROM sales WHERE strftime('%Y-%m',sale_date)=strftime('%Y-%m','now','localtime')").fetchone()['n'],
      'latest':c.execute('SELECT * FROM sales ORDER BY id DESC LIMIT 10').fetchall()}; c.close()
    return render_template('dashboard.html',**data)

@app.route('/pos')
@login_required
def pos(): return render_template('pos.html')
@app.route('/api/products')
@login_required
def api_products():
    q=request.args.get('q','').strip(); c=db(); rows=c.execute('SELECT id,name,barcode,price,stock,min_stock FROM products WHERE name LIKE ? OR barcode LIKE ? ORDER BY name',(f'%{q}%',f'%{q}%')).fetchall(); c.close(); return jsonify([dict(x) for x in rows])
@app.post('/api/sale')
@login_required
def api_sale():
    d=request.get_json(force=True); items=d.get('items',[]); paid=float(d.get('paid',0) or 0)
    if not items:return jsonify(ok=False,message='السلة فارغة.'),400
    c=db()
    try:
        checked=[]; total=0
        for x in items:
            pid=int(x['id']); qty=int(x['quantity']); p=c.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
            if not p: raise ValueError('المنتج غير موجود.')
            if qty<1 or p['stock']<qty: raise ValueError(f"المخزون غير كافٍ: {p['name']}")
            sub=p['price']*qty; total+=sub; checked.append((p,qty,sub))
        if paid<total: raise ValueError('المبلغ المدفوع أقل من الإجمالي.')
        change=paid-total; cur=c.execute('INSERT INTO sales(sale_date,total,paid,change_amount) VALUES(?,?,?,?)',(datetime.now().strftime('%Y-%m-%d %H:%M:%S'),total,paid,change)); sid=cur.lastrowid
        for p,q,sub in checked:
            c.execute('INSERT INTO sale_items(sale_id,product_id,product_name,quantity,price,subtotal) VALUES(?,?,?,?,?,?)',(sid,p['id'],p['name'],q,p['price'],sub)); c.execute('UPDATE products SET stock=stock-? WHERE id=?',(q,p['id']))
        c.commit(); return jsonify(ok=True,sale_id=sid,total=total,change=change)
    except Exception as e: c.rollback(); return jsonify(ok=False,message=str(e)),400
    finally:c.close()

@app.route('/products',methods=['GET','POST'])
@login_required
def products():
    c=db()
    if request.method=='POST':
        try:
            n=request.form.get('name','').strip(); b=request.form.get('barcode','').strip() or None; price=float(request.form.get('price','0').replace(',','.')); stock=int(request.form.get('stock','0')); mn=int(request.form.get('min_stock','5'))
            if not n: raise ValueError('أدخل اسم المنتج.')
            c.execute('INSERT INTO products(name,barcode,price,stock,min_stock,image) VALUES(?,?,?,?,?,?)',(n,b,price,stock,mn,'')); c.commit(); flash('تمت إضافة المنتج.','success')
        except Exception as e: flash(str(e),'danger')
    rows=c.execute('SELECT * FROM products ORDER BY id DESC').fetchall(); c.close(); return render_template('products.html',products=rows)
@app.post('/products/<int:pid>/delete')
@login_required
def delete_product(pid):
    c=db(); c.execute('DELETE FROM products WHERE id=?',(pid,)); c.commit(); c.close(); return redirect('/products')
@app.route('/inventory')
@login_required
def inventory():
    c=db(); rows=c.execute('SELECT * FROM products ORDER BY stock ASC,name').fetchall(); c.close(); return render_template('inventory.html',products=rows)
@app.route('/sales')
@login_required
def sales():
    c=db(); rows=c.execute('SELECT * FROM sales ORDER BY id DESC').fetchall(); c.close(); return render_template('sales.html',sales=rows)
@app.route('/reports')
@login_required
def reports():
    c=db(); today=c.execute("SELECT COALESCE(SUM(total),0)n FROM sales WHERE date(sale_date)=date('now','localtime')").fetchone()['n']; week=c.execute("SELECT COALESCE(SUM(total),0)n FROM sales WHERE strftime('%Y-%W',sale_date)=strftime('%Y-%W','now','localtime')").fetchone()['n']; month=c.execute("SELECT COALESCE(SUM(total),0)n FROM sales WHERE strftime('%Y-%m',sale_date)=strftime('%Y-%m','now','localtime')").fetchone()['n']; top=c.execute('SELECT product_name,SUM(quantity) quantity,SUM(subtotal) amount FROM sale_items GROUP BY product_id ORDER BY quantity DESC LIMIT 20').fetchall(); c.close(); return render_template('reports.html',today=today,week=week,month=month,top=top)
@app.route('/settings',methods=['GET','POST'])
@login_required
def settings():
    if request.method=='POST':
        old=request.form.get('old_password',''); new=request.form.get('new_password',''); c=db(); u=c.execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone()
        if not check_password_hash(u['password_hash'],old): flash('كلمة المرور الحالية غير صحيحة.','danger')
        elif len(new)<6: flash('استخدم كلمة مرور من 6 أحرف على الأقل.','danger')
        else: c.execute('UPDATE users SET password_hash=? WHERE id=?',(generate_password_hash(new),u['id'])); c.commit(); flash('تم تغيير كلمة المرور.','success')
        c.close()
    return render_template('settings.html')
@app.route('/api/summary')
@login_required
def summary():
    c=db(); d={'products':c.execute('SELECT COUNT(*)n FROM products').fetchone()['n'],'stock':c.execute('SELECT COALESCE(SUM(stock),0)n FROM products').fetchone()['n'],'low':c.execute('SELECT COUNT(*)n FROM products WHERE stock<=min_stock').fetchone()['n'],'today':c.execute("SELECT COALESCE(SUM(total),0)n FROM sales WHERE date(sale_date)=date('now','localtime')").fetchone()['n'],'month':c.execute("SELECT COALESCE(SUM(total),0)n FROM sales WHERE strftime('%Y-%m',sale_date)=strftime('%Y-%m','now','localtime')").fetchone()['n']}; c.close(); return jsonify(d)

if __name__=='__main__':
    init_db(); print('\nمكتبة الأمل: http://127.0.0.1:5000\n'); app.run(host='0.0.0.0',port=5000,debug=False)
