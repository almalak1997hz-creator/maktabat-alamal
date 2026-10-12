import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
import os
import random
import shutil
from datetime import datetime

from PIL import Image, ImageTk


# ============================================================
# إعدادات البرنامج
# ============================================================

APP_NAME = "مكتبة الأمل"
CURRENCY = "ر.ع"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "maktabat_alamal.db")
PRODUCT_IMAGES_DIR = os.path.join(BASE_DIR, "product_images")
BARCODES_DIR = os.path.join(BASE_DIR, "barcodes")
os.makedirs(PRODUCT_IMAGES_DIR, exist_ok=True)
os.makedirs(BARCODES_DIR, exist_ok=True)


# ============================================================
# قاعدة البيانات المحلية
# ============================================================

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    barcode TEXT UNIQUE,
    price REAL NOT NULL DEFAULT 0,
    stock INTEGER NOT NULL DEFAULT 0,
    min_stock INTEGER NOT NULL DEFAULT 5,
    image TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_date TEXT NOT NULL,
    total REAL NOT NULL,
    paid REAL NOT NULL,
    change_amount REAL NOT NULL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS sale_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER,
    product_id INTEGER,
    product_name TEXT,
    quantity INTEGER,
    price REAL,
    subtotal REAL
)
""")


conn.commit()


def ensure_all_product_barcodes():
    cursor.execute("SELECT id, barcode FROM products")
    rows = cursor.fetchall()
    changed = False

    for product_id, barcode in rows:
        if not barcode:
            while True:
                new_barcode = str(random.randint(10000000, 99999999))
                cursor.execute(
                    "SELECT 1 FROM products WHERE barcode=? LIMIT 1",
                    (new_barcode,)
                )
                if not cursor.fetchone():
                    break
            cursor.execute(
                "UPDATE products SET barcode=? WHERE id=?",
                (new_barcode, product_id)
            )
            changed = True

    if changed:
        conn.commit()


ensure_all_product_barcodes()


# ============================================================
# الألوان
# ============================================================

BG = "#F4F6F8"
WHITE = "#FFFFFF"
DARK = "#263238"
PRIMARY = "#1565C0"
PRIMARY_DARK = "#0D47A1"
GREEN = "#2E7D32"
RED = "#C62828"
ORANGE = "#EF6C00"
GRAY = "#607D8B"



# ============================================================
# إنشاء باركود مرئي قابل للمسح والطباعة - Code 128
# ============================================================

def code128_b_values(data):
    """تحويل نص ASCII إلى قيم Code 128-B."""
    if not data:
        raise ValueError("الباركود فارغ")
    for ch in data:
        if ord(ch) < 32 or ord(ch) > 126:
            raise ValueError("Code 128-B يدعم أحرف ASCII فقط.")
    values = [104]  # Start B
    values.extend(ord(ch) - 32 for ch in data)
    checksum = values[0]
    for position, value in enumerate(values[1:], start=1):
        checksum += value * position
    values.append(checksum % 103)
    values.append(106)  # Stop
    return values


def create_barcode_image(barcode, product_name="", price=None, output_path=None):
    """إنشاء PNG لباركود Code 128 بحجم مناسب للطباعة والمسح."""
    from PIL import Image, ImageDraw, ImageFont

    patterns = [
        "212222","222122","222221","121223","121322","131222","122213","122312","132212","221213",
        "221312","231212","112232","122132","122231","113222","123122","123221","223211","221132",
        "221231","213212","223112","312131","311222","321122","321221","312212","322112","322211",
        "212123","212321","232121","111323","131123","131321","112313","132113","132311","211313",
        "231113","231311","112133","112331","132131","113123","113321","133121","313121","211331",
        "231131","213113","213311","213131","311123","311321","331121","312113","312311","332111",
        "314111","221411","431111","111224","111422","121124","121421","141122","141221","112214",
        "112412","122114","122411","142112","142211","241211","221114","413111","241112","134111",
        "111242","121142","121241","114212","124112","124211","411212","421112","421211","212141",
        "214121","412121","111143","111341","131141","114113","114311","411113","411311","113141",
        "114131","311141","411131","211412","211214","211232","2331112"
    ]

    width, height = 945, 470
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    try:
        title_font = ImageFont.truetype("arial.ttf", 36)
        number_font = ImageFont.truetype("arialbd.ttf", 34)
        small_font = ImageFont.truetype("arial.ttf", 24)
    except Exception:
        title_font = ImageFont.load_default()
        number_font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    title = product_name or "مكتبة الأمل"
    bbox = draw.textbbox((0, 0), title, font=title_font)
    draw.text(((width - (bbox[2] - bbox[0])) / 2, 18), title,
              fill="black", font=title_font)

    module = 4
    x, y, bar_height = 55, 95, 245

    for value in code128_b_values(str(barcode)):
        black = True
        for digit in patterns[value]:
            w = int(digit) * module
            if black:
                draw.rectangle([x, y, x + w - 1, y + bar_height], fill="black")
            x += w
            black = not black

    number_text = str(barcode)
    bbox = draw.textbbox((0, 0), number_text, font=number_font)
    draw.text(((width - (bbox[2] - bbox[0])) / 2, 360),
              number_text, fill="black", font=number_font)

    if price is not None:
        price_text = f"السعر: {price:.3f} ر.ع"
        bbox = draw.textbbox((0, 0), price_text, font=small_font)
        draw.text(((width - (bbox[2] - bbox[0])) / 2, 420),
                  price_text, fill="black", font=small_font)

    if output_path is None:
        output_path = os.path.join(BARCODES_DIR, f"{barcode}.png")

    image.save(output_path, "PNG", dpi=(300, 300))
    return output_path


# ============================================================
# البرنامج الرئيسي
# ============================================================

class LibraryPOS:

    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1250x750")
        self.root.minsize(1100, 650)
        self.root.configure(bg=BG)

        self.cart = []
        self.selected_image = ""
        self.product_image_preview = None
        self._product_image_photo = None
        self.product_images_cache = {}

        self.setup_style()
        self.create_header()
        self.create_main_area()

        self.show_pos()


    # ========================================================
    # Style
    # ========================================================

    def setup_style(self):

        style = ttk.Style()

        try:
            style.theme_use("clam")
        except:
            pass

        style.configure(
            "Treeview",
            background=WHITE,
            foreground=DARK,
            rowheight=34,
            fieldbackground=WHITE,
            font=("Arial", 11)
        )

        style.configure(
            "Treeview.Heading",
            background=PRIMARY,
            foreground=WHITE,
            font=("Arial", 11, "bold")
        )

        style.map(
            "Treeview",
            background=[("selected", "#BBDEFB")],
            foreground=[("selected", DARK)]
        )

        style.configure(
            "TButton",
            font=("Arial", 10, "bold"),
            padding=8
        )

        style.configure(
            "TEntry",
            font=("Arial", 11)
        )


    # ========================================================
    # Header
    # ========================================================

    def create_header(self):

        header = tk.Frame(
            self.root,
            bg=PRIMARY,
            height=75
        )

        header.pack(fill="x")
        header.pack_propagate(False)

        title = tk.Label(
            header,
            text="مكتبة الأمل",
            bg=PRIMARY,
            fg=WHITE,
            font=("Arial", 26, "bold")
        )

        title.pack(side="right", padx=30)

        subtitle = tk.Label(
            header,
            text="الملده",
            bg=PRIMARY,
            fg="#E3F2FD",
            font=("Arial", 11)
        )

        subtitle.pack(side="right", padx=5)


    # ========================================================
    # Main Area
    # ========================================================

    def create_main_area(self):

        container = tk.Frame(
            self.root,
            bg=BG
        )

        container.pack(fill="both", expand=True)

        # القائمة الجانبية
        self.sidebar = tk.Frame(
            container,
            bg=DARK,
            width=210
        )

        self.sidebar.pack(
            side="right",
            fill="y"
        )

        self.sidebar.pack_propagate(False)

        buttons = [
            ("🛒 الكاشير", self.show_pos),
            ("📦 المنتجات", self.show_products),
            ("📊 المخزون", self.show_inventory),
            ("📋 الجرد", self.show_inventory_count),
            ("💰 المبيعات", self.show_sales),
            ("📈 التقارير", self.show_reports),
        ]

        for text, command in buttons:

            btn = tk.Button(
                self.sidebar,
                text=text,
                command=command,
                bg=DARK,
                fg=WHITE,
                activebackground=PRIMARY,
                activeforeground=WHITE,
                relief="flat",
                bd=0,
                font=("Arial", 12, "bold"),
                anchor="e",
                padx=20,
                pady=15,
                cursor="hand2"
            )

            btn.pack(fill="x", pady=2)


        # مساحة المحتوى
        self.content = tk.Frame(
            container,
            bg=BG
        )

        self.content.pack(
            side="left",
            fill="both",
            expand=True
        )


    # ========================================================
    # تنظيف الصفحة
    # ========================================================

    def clear_content(self):

        for widget in self.content.winfo_children():
            widget.destroy()


    # ========================================================
    # صفحة الكاشير
    # ========================================================

    def show_pos(self):

        self.clear_content()

        title = tk.Label(
            self.content,
            text="نقطة البيع - الكاشير",
            bg=BG,
            fg=DARK,
            font=("Arial", 20, "bold")
        )

        title.pack(
            anchor="e",
            padx=25,
            pady=20
        )

        top = tk.Frame(
            self.content,
            bg=BG
        )

        top.pack(
            fill="x",
            padx=25
        )

        tk.Label(
            top,
            text="بحث عن المنتج:",
            bg=BG,
            font=("Arial", 11, "bold")
        ).pack(side="right", padx=5)

        self.search_entry = ttk.Entry(
            top,
            width=35
        )

        self.search_entry.pack(
            side="right",
            padx=5
        )

        self.search_entry.bind(
            "<KeyRelease>",
            lambda e: self.load_pos_products()
        )

        ttk.Button(
            top,
            text="إضافة بالباركود",
            command=self.add_by_barcode
        ).pack(
            side="right",
            padx=5
        )

        main = tk.Frame(
            self.content,
            bg=BG
        )

        main.pack(
            fill="both",
            expand=True,
            padx=25,
            pady=15
        )


        # المنتجات
        products_frame = tk.LabelFrame(
            main,
            text="المنتجات",
            bg=WHITE,
            font=("Arial", 12, "bold")
        )

        products_frame.pack(
            side="right",
            fill="both",
            expand=True,
            padx=(0, 10)
        )

        columns = (
            "id",
            "name",
            "barcode",
            "price",
            "stock"
        )

        self.pos_tree = ttk.Treeview(
            products_frame,
            columns=columns,
            show="headings"
        )

        headings = {
            "id": "رقم",
            "name": "اسم المنتج",
            "barcode": "الباركود",
            "price": "السعر",
            "stock": "المخزون"
        }

        for col in columns:

            self.pos_tree.heading(
                col,
                text=headings[col]
            )

        self.pos_tree.column("id", width=50)
        self.pos_tree.column("name", width=180)
        self.pos_tree.column("barcode", width=120)
        self.pos_tree.column("price", width=100)
        self.pos_tree.column("stock", width=80)

        self.pos_tree.pack(
            fill="both",
            expand=True,
            padx=5,
            pady=5
        )

        self.pos_tree.bind(
            "<Double-1>",
            lambda e: self.add_selected_product()
        )


        ttk.Button(
            products_frame,
            text="إضافة للسلة",
            command=self.add_selected_product
        ).pack(
            pady=8
        )


        # السلة
        cart_frame = tk.LabelFrame(
            main,
            text="سلة المشتريات",
            bg=WHITE,
            font=("Arial", 12, "bold"),
            width=400
        )

        cart_frame.pack(
            side="left",
            fill="both",
            padx=(10, 0)
        )

        cart_columns = (
            "name",
            "quantity",
            "price",
            "subtotal"
        )

        self.cart_tree = ttk.Treeview(
            cart_frame,
            columns=cart_columns,
            show="headings",
            height=12
        )

        cart_headings = {
            "name": "المنتج",
            "quantity": "الكمية",
            "price": "السعر",
            "subtotal": "الإجمالي"
        }

        for col in cart_columns:
            self.cart_tree.heading(
                col,
                text=cart_headings[col]
            )

        self.cart_tree.column("name", width=150)
        self.cart_tree.column("quantity", width=60)
        self.cart_tree.column("price", width=80)
        self.cart_tree.column("subtotal", width=90)

        self.cart_tree.pack(
            fill="both",
            expand=True,
            padx=5,
            pady=5
        )


        buttons = tk.Frame(
            cart_frame,
            bg=WHITE
        )

        buttons.pack(
            fill="x",
            pady=5
        )

        ttk.Button(
            buttons,
            text="حذف",
            command=self.remove_cart_item
        ).pack(
            side="right",
            padx=5
        )

        ttk.Button(
            buttons,
            text="تفريغ السلة",
            command=self.clear_cart
        ).pack(
            side="right",
            padx=5
        )


        self.total_label = tk.Label(
            cart_frame,
            text="الإجمالي: 0.000 ر.ع",
            bg=WHITE,
            fg=PRIMARY_DARK,
            font=("Arial", 18, "bold")
        )

        self.total_label.pack(
            pady=10
        )


        tk.Label(
            cart_frame,
            text="المبلغ المدفوع",
            bg=WHITE,
            font=("Arial", 11, "bold")
        ).pack()

        self.paid_entry = ttk.Entry(
            cart_frame,
            justify="center",
            font=("Arial", 14)
        )

        self.paid_entry.pack(
            padx=30,
            pady=5,
            fill="x"
        )


        self.change_label = tk.Label(
            cart_frame,
            text="الباقي: 0.000 ر.ع",
            bg=WHITE,
            fg=GREEN,
            font=("Arial", 14, "bold")
        )

        self.change_label.pack(
            pady=5
        )


        ttk.Button(
            cart_frame,
            text="إتمام البيع",
            command=self.complete_sale
        ).pack(
            fill="x",
            padx=20,
            pady=10
        )

        self.load_pos_products()


    # ========================================================
    # تحميل المنتجات للكاشير
    # ========================================================

    def load_pos_products(self):

        for item in self.pos_tree.get_children():
            self.pos_tree.delete(item)

        search = ""

        if hasattr(self, "search_entry"):
            search = self.search_entry.get().strip()

        if search:

            cursor.execute("""
                SELECT id, name, barcode, price, stock
                FROM products
                WHERE name LIKE ?
                OR barcode LIKE ?
                ORDER BY name
            """, (f"%{search}%", f"%{search}%"))

        else:

            cursor.execute("""
                SELECT id, name, barcode, price, stock
                FROM products
                ORDER BY name
            """)

        rows = cursor.fetchall()

        for row in rows:

            self.pos_tree.insert(
                "",
                "end",
                values=(
                    row[0],
                    row[1],
                    row[2] or "",
                    f"{row[3]:.3f}",
                    row[4]
                )
            )


    # ========================================================
    # إضافة منتج للسلة
    # ========================================================

    def add_selected_product(self):

        selected = self.pos_tree.selection()

        if not selected:
            messagebox.showwarning(
                "تنبيه",
                "اختر منتجًا أولاً."
            )
            return

        item = self.pos_tree.item(selected[0])

        product_id = item["values"][0]

        cursor.execute(
            "SELECT id, name, price, stock FROM products WHERE id=?",
            (product_id,)
        )

        product = cursor.fetchone()

        if not product:
            return

        pid, name, price, stock = product

        if stock <= 0:
            messagebox.showwarning(
                "المخزون",
                "هذا المنتج غير متوفر في المخزون."
            )
            return

        for cart_item in self.cart:

            if cart_item["id"] == pid:

                if cart_item["quantity"] + 1 > stock:

                    messagebox.showwarning(
                        "المخزون",
                        "الكمية المطلوبة أكبر من المخزون."
                    )

                    return

                cart_item["quantity"] += 1
                self.refresh_cart()
                return

        self.cart.append({
            "id": pid,
            "name": name,
            "price": price,
            "quantity": 1,
            "stock": stock
        })

        self.refresh_cart()


    # ========================================================
    # إضافة بالباركود
    # ========================================================

    def add_by_barcode(self):

        barcode = self.search_entry.get().strip()

        if not barcode:
            return

        cursor.execute("""
            SELECT id, name, price, stock
            FROM products
            WHERE barcode=?
        """, (barcode,))

        product = cursor.fetchone()

        if not product:

            messagebox.showwarning(
                "الباركود",
                "لم يتم العثور على المنتج."
            )

            return

        pid, name, price, stock = product

        if stock <= 0:

            messagebox.showwarning(
                "المخزون",
                "المنتج غير متوفر."
            )

            return

        for item in self.cart:

            if item["id"] == pid:

                if item["quantity"] < stock:
                    item["quantity"] += 1

                self.refresh_cart()
                return

        self.cart.append({
            "id": pid,
            "name": name,
            "price": price,
            "quantity": 1,
            "stock": stock
        })

        self.refresh_cart()


    # ========================================================
    # تحديث السلة
    # ========================================================

    def refresh_cart(self):

        for item in self.cart_tree.get_children():
            self.cart_tree.delete(item)

        total = 0

        for item in self.cart:

            subtotal = (
                item["price"] *
                item["quantity"]
            )

            total += subtotal

            self.cart_tree.insert(
                "",
                "end",
                iid=str(item["id"]),
                values=(
                    item["name"],
                    item["quantity"],
                    f"{item['price']:.3f}",
                    f"{subtotal:.3f}"
                )
            )

        self.total_label.config(
            text=f"الإجمالي: {total:.3f} {CURRENCY}"
        )

        self.calculate_change()


    # ========================================================
    # حساب الباقي
    # ========================================================

    def calculate_change(self, event=None):

        total = sum(
            item["price"] * item["quantity"]
            for item in self.cart
        )

        try:
            paid = float(
                self.paid_entry.get()
                .replace(",", ".")
            )
        except:
            paid = 0

        change = paid - total

        if change >= 0:

            self.change_label.config(
                text=f"الباقي: {change:.3f} {CURRENCY}",
                fg=GREEN
            )

        else:

            self.change_label.config(
                text=f"المتبقي: {abs(change):.3f} {CURRENCY}",
                fg=RED
            )


    # ========================================================
    # حذف من السلة
    # ========================================================

    def remove_cart_item(self):

        selected = self.cart_tree.selection()

        if not selected:
            return

        product_id = int(selected[0])

        self.cart = [
            item for item in self.cart
            if item["id"] != product_id
        ]

        self.refresh_cart()


    # ========================================================
    # تفريغ السلة
    # ========================================================

    def clear_cart(self):

        self.cart.clear()

        self.refresh_cart()


    # ========================================================
    # إتمام البيع
    # ========================================================

    def complete_sale(self):

        if not self.cart:

            messagebox.showwarning(
                "الفاتورة",
                "السلة فارغة."
            )

            return

        total = sum(
            item["price"] * item["quantity"]
            for item in self.cart
        )

        try:

            paid = float(
                self.paid_entry.get()
                .replace(",", ".")
            )

        except:

            messagebox.showwarning(
                "المبلغ",
                "أدخل المبلغ المدفوع بشكل صحيح."
            )

            return

        if paid < total:

            messagebox.showwarning(
                "المبلغ",
                "المبلغ المدفوع أقل من إجمالي الفاتورة."
            )

            return

        change = paid - total

        date = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        cursor.execute("""
            INSERT INTO sales
            (sale_date, total, paid, change_amount)
            VALUES (?, ?, ?, ?)
        """, (
            date,
            total,
            paid,
            change
        ))

        sale_id = cursor.lastrowid

        for item in self.cart:

            subtotal = (
                item["price"] *
                item["quantity"]
            )

            cursor.execute("""
                INSERT INTO sale_items
                (
                    sale_id,
                    product_id,
                    product_name,
                    quantity,
                    price,
                    subtotal
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                sale_id,
                item["id"],
                item["name"],
                item["quantity"],
                item["price"],
                subtotal
            ))

            cursor.execute("""
                UPDATE products
                SET stock = stock - ?
                WHERE id=?
            """, (
                item["quantity"],
                item["id"]
            ))

        conn.commit()

        messagebox.showinfo(
            "تم البيع",
            f"تم تسجيل الفاتورة بنجاح.\n\n"
            f"الإجمالي: {total:.3f} {CURRENCY}\n"
            f"المدفوع: {paid:.3f} {CURRENCY}\n"
            f"الباقي: {change:.3f} {CURRENCY}"
        )

        self.cart.clear()
        self.paid_entry.delete(0, "end")
        self.refresh_cart()
        self.load_pos_products()


    # ========================================================
    # صفحة المنتجات
    # ========================================================

    def show_products(self):

        self.clear_content()

        title = tk.Label(
            self.content,
            text="إدارة المنتجات",
            bg=BG,
            fg=DARK,
            font=("Arial", 20, "bold")
        )

        title.pack(
            anchor="e",
            padx=25,
            pady=20
        )


        form = tk.Frame(
            self.content,
            bg=WHITE,
            padx=20,
            pady=20
        )

        form.pack(
            fill="x",
            padx=25
        )


        self.product_name = self.make_field(
            form,
            "اسم المنتج"
        )

        self.product_barcode = self.make_field(
            form,
            "الباركود"
        )

        self.product_price = self.make_field(
            form,
            "السعر (ر.ع)"
        )

        self.product_stock = self.make_field(
            form,
            "الكمية"
        )

        self.product_min_stock = self.make_field(
            form,
            "حد التنبيه"
        )


        self.selected_image = ""

        image_box = tk.Frame(form, bg=WHITE, width=110, height=95)
        image_box.pack(side="right", padx=8)
        image_box.pack_propagate(False)

        self.product_image_preview = tk.Label(
            image_box,
            text="لا توجد صورة",
            bg="#F3EEE8",
            fg=GRAY,
            font=("Arial", 9, "bold")
        )
        self.product_image_preview.pack(fill="both", expand=True)

        ttk.Button(
            form,
            text="🖼 اختيار صورة",
            command=self.choose_image
        ).pack(
            side="right",
            padx=5
        )

        ttk.Button(
            form,
            text="🔢 توليد باركود",
            command=self.generate_and_show_barcode
        ).pack(
            side="right",
            padx=5
        )

        ttk.Button(
            form,
            text="➕ إضافة المنتج",
            command=self.add_product
        ).pack(
            side="right",
            padx=5
        )


        ttk.Button(
            form,
            text="حذف المنتج",
            command=self.delete_product
        ).pack(
            side="right",
            padx=5
        )

        ttk.Button(
            form,
            text="🖨 باركود / طباعة",
            command=self.print_selected_barcode
        ).pack(
            side="right",
            padx=5
        )


        table_frame = tk.Frame(
            self.content,
            bg=BG
        )

        table_frame.pack(
            fill="both",
            expand=True,
            padx=25,
            pady=15
        )


        columns = (
            "id",
            "name",
            "barcode",
            "price",
            "stock",
            "min_stock",
            "image"
        )

        self.products_tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings"
        )

        names = {
            "id": "الرقم",
            "name": "اسم المنتج",
            "barcode": "الباركود",
            "price": "السعر",
            "stock": "المخزون",
            "min_stock": "حد التنبيه",
            "image": "الصورة"
        }

        for col in columns:

            self.products_tree.heading(
                col,
                text=names[col]
            )

        self.products_tree.column("id", width=60)
        self.products_tree.column("name", width=220)
        self.products_tree.column("barcode", width=140)
        self.products_tree.column("price", width=100)
        self.products_tree.column("stock", width=100)
        self.products_tree.column("min_stock", width=100)
        self.products_tree.column("image", width=200)

        self.products_tree.pack(
            fill="both",
            expand=True
        )

        self.products_tree.bind(
            "<Double-1>",
            self.edit_product_dialog
        )

        self.load_products()


    # ========================================================
    # إنشاء خانة
    # ========================================================

    def make_field(self, parent, label):

        frame = tk.Frame(
            parent,
            bg=WHITE
        )

        frame.pack(
            side="right",
            padx=7
        )

        tk.Label(
            frame,
            text=label,
            bg=WHITE,
            font=("Arial", 10, "bold")
        ).pack()

        entry = ttk.Entry(
            frame,
            width=16,
            justify="right"
        )

        entry.pack(
            pady=5
        )

        return entry


    # ========================================================
    # اختيار صورة
    # ========================================================

    def choose_image(self):

        file = filedialog.askopenfilename(
            title="اختر صورة المنتج",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.gif *.webp"),
                ("All files", "*.*")
            ]
        )

        if not file:
            return

        self.selected_image = file
        self.show_product_image_preview(file)

    def show_product_image_preview(self, file_path):

        if not self.product_image_preview or not os.path.exists(file_path):
            return

        try:
            image = Image.open(file_path).convert("RGB")
            image.thumbnail((90, 75), Image.LANCZOS)
            self._product_image_photo = ImageTk.PhotoImage(image)
            self.product_image_preview.config(
                image=self._product_image_photo,
                text=""
            )
        except Exception:
            self.product_image_preview.config(
                image="",
                text="تعذر عرض الصورة"
            )

    def generate_barcode(self):

        # باركود رقمي بسيط من 8 أرقام، ويضمن عدم تكراره في قاعدة البيانات.
        while True:
            barcode = str(random.randint(10000000, 99999999))
            cursor.execute(
                "SELECT 1 FROM products WHERE barcode=? LIMIT 1",
                (barcode,)
            )
            if not cursor.fetchone():
                return barcode

    def generate_and_show_barcode(self):

        barcode = self.generate_barcode()
        self.product_barcode.delete(0, "end")
        self.product_barcode.insert(0, barcode)
        self.product_barcode.focus_set()


    # ========================================================
    # باركود المنتج: إنشاء / عرض / طباعة
    # ========================================================

    def get_product_barcode_path(self, product_id, barcode, name="", price=None):
        path = os.path.join(BARCODES_DIR, f"{barcode}.png")
        try:
            if not os.path.exists(path):
                create_barcode_image(
                    barcode,
                    product_name=name,
                    price=price,
                    output_path=path
                )
        except Exception as e:
            messagebox.showerror("الباركود", f"تعذر إنشاء صورة الباركود:\n{e}")
            return None
        return path

    def show_barcode_dialog(self, product_id):
        cursor.execute("""
            SELECT name, barcode, price
            FROM products
            WHERE id=?
        """, (product_id,))
        product = cursor.fetchone()

        if not product:
            messagebox.showwarning("الباركود", "لم يتم العثور على المنتج.")
            return

        name, barcode, price = product

        if not barcode:
            barcode = self.generate_barcode()
            cursor.execute(
                "UPDATE products SET barcode=? WHERE id=?",
                (barcode, product_id)
            )
            conn.commit()

        path = self.get_product_barcode_path(
            product_id, barcode, name, price
        )
        if not path:
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(f"باركود: {name}")
        dialog.geometry("720x500")
        dialog.configure(bg=WHITE)

        tk.Label(
            dialog,
            text="باركود المنتج",
            bg=WHITE,
            fg=DARK,
            font=("Arial", 18, "bold")
        ).pack(pady=(15, 5))

        tk.Label(
            dialog,
            text=f"{name}\nالرقم: {barcode}",
            bg=WHITE,
            fg=GRAY,
            font=("Arial", 11, "bold"),
            justify="center"
        ).pack(pady=5)

        try:
            img = Image.open(path).convert("RGB")
            img.thumbnail((650, 320), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            label = tk.Label(dialog, image=photo, bg=WHITE)
            label.image = photo
            label.pack(pady=10)
        except Exception as e:
            tk.Label(
                dialog,
                text=f"تعذر عرض الباركود:\n{e}",
                bg=WHITE,
                fg=RED
            ).pack(pady=20)

        buttons = tk.Frame(dialog, bg=WHITE)
        buttons.pack(pady=10)

        def print_barcode():
            try:
                if os.name != "nt":
                    raise RuntimeError("الطباعة المباشرة مفعلة هنا لويندوز.")
                os.startfile(os.path.abspath(path), "print")
            except Exception as e:
                messagebox.showerror(
                    "الطباعة",
                    "تعذر إرسال الباركود للطابعة تلقائيًا.\n"
                    "يمكنك اختيار «فتح الصورة» ثم طباعتها يدويًا.\n\n"
                    f"{e}"
                )

        def open_barcode():
            try:
                os.startfile(os.path.abspath(path))
            except Exception as e:
                messagebox.showerror("فتح الصورة", str(e))

        ttk.Button(
            buttons,
            text="🖨 طباعة الباركود",
            command=print_barcode
        ).pack(side="right", padx=6)

        ttk.Button(
            buttons,
            text="🖼 فتح الصورة",
            command=open_barcode
        ).pack(side="right", padx=6)

        ttk.Button(
            buttons,
            text="إغلاق",
            command=dialog.destroy
        ).pack(side="right", padx=6)

    def print_selected_barcode(self):
        selected = self.products_tree.selection()
        if not selected:
            messagebox.showwarning(
                "الباركود",
                "اختر المنتج أولاً ثم اضغط «باركود / طباعة»."
            )
            return

        item = self.products_tree.item(selected[0])
        self.show_barcode_dialog(item["values"][0])


    # ========================================================
    # إضافة منتج
    # ========================================================

    def add_product(self):

        name = self.product_name.get().strip()
        barcode = self.product_barcode.get().strip() or self.generate_barcode()

        # الصورة اختيارية، لكن البرنامج ينبه المستخدم إذا لم يضفها.
        if not self.selected_image:
            add_without_image = messagebox.askyesno(
                "صورة المنتج",
                "لم تختر صورة لهذا المنتج. هل تريد إضافته بدون صورة؟"
            )
            if not add_without_image:
                return

        try:
            price = float(
                self.product_price.get()
                .replace(",", ".")
            )

            stock = int(
                self.product_stock.get()
            )

            min_stock = int(
                self.product_min_stock.get()
                or 5
            )

        except:

            messagebox.showerror(
                "خطأ",
                "تأكد من إدخال السعر والكميات بشكل صحيح."
            )

            return


        if not name:

            messagebox.showwarning(
                "المنتج",
                "أدخل اسم المنتج."
            )

            return


        try:

            stored_image = ""
            if self.selected_image and os.path.exists(self.selected_image):
                extension = os.path.splitext(self.selected_image)[1].lower() or ".jpg"
                safe_name = f"product_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{extension}"
                destination = os.path.join(PRODUCT_IMAGES_DIR, safe_name)
                shutil.copy2(self.selected_image, destination)
                stored_image = os.path.relpath(destination, BASE_DIR)

            cursor.execute("""
                INSERT INTO products
                (
                    name,
                    barcode,
                    price,
                    stock,
                    min_stock,
                    image
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                name,
                barcode or None,
                price,
                stock,
                min_stock,
                stored_image
            ))

            conn.commit()

            create_barcode_image(
                barcode,
                product_name=name,
                price=price,
                output_path=os.path.join(BARCODES_DIR, f"{barcode}.png")
            )

        except sqlite3.IntegrityError:

            messagebox.showerror(
                "خطأ",
                "هذا الباركود موجود مسبقًا."
            )

            return


        messagebox.showinfo(
            "تم",
            f"تمت إضافة المنتج بنجاح.\n\n"
            f"الباركود: {barcode}\n"
            "تم إنشاء باركود مرئي قابل للمسح والطباعة."
        )

        self.product_name.delete(0, "end")
        self.product_barcode.delete(0, "end")
        self.product_price.delete(0, "end")
        self.product_stock.delete(0, "end")
        self.product_min_stock.delete(0, "end")

        self.selected_image = ""
        self._product_image_photo = None
        if self.product_image_preview:
            self.product_image_preview.config(image="", text="لا توجد صورة")

        self.load_products()


    # ========================================================
    # تحميل المنتجات
    # ========================================================

    def load_products(self):

        if not hasattr(self, "products_tree"):
            return

        for item in self.products_tree.get_children():
            self.products_tree.delete(item)

        cursor.execute("""
            SELECT
                id,
                name,
                barcode,
                price,
                stock,
                min_stock,
                image
            FROM products
            ORDER BY id DESC
        """)

        for row in cursor.fetchall():

            if row[2]:
                try:
                    self.get_product_barcode_path(
                        row[0], row[2], row[1], row[3]
                    )
                except Exception:
                    pass

            self.products_tree.insert(
                "",
                "end",
                values=(
                    row[0],
                    row[1],
                    row[2] or "",
                    f"{row[3]:.3f}",
                    row[4],
                    row[5],
                    "✓ موجودة"
                    if row[6] and os.path.exists(
                        os.path.join(BASE_DIR, row[6])
                    )
                    else "—"
                )
            )


    # ========================================================
    # حذف منتج
    # ========================================================

    def delete_product(self):

        selected = self.products_tree.selection()

        if not selected:
            messagebox.showwarning(
                "حذف",
                "اختر المنتج أولاً."
            )

            return

        item = self.products_tree.item(
            selected[0]
        )

        product_id = item["values"][0]

        confirm = messagebox.askyesno(
            "تأكيد",
            "هل تريد حذف المنتج؟"
        )

        if not confirm:
            return

        cursor.execute(
            "DELETE FROM products WHERE id=?",
            (product_id,)
        )

        conn.commit()

        self.load_products()


    # ========================================================
    # تعديل المنتج
    # ========================================================

    def edit_product_dialog(self, event=None):

        selected = self.products_tree.selection()

        if not selected:
            return

        item = self.products_tree.item(
            selected[0]
        )

        product_id = item["values"][0]

        cursor.execute("""
            SELECT
                name,
                barcode,
                price,
                stock,
                min_stock,
                image
            FROM products
            WHERE id=?
        """, (product_id,))

        product = cursor.fetchone()

        if not product:
            return


        dialog = tk.Toplevel(
            self.root
        )

        dialog.title("تعديل المنتج")
        dialog.geometry("420x400")
        dialog.configure(bg=WHITE)

        entries = {}

        labels = [
            ("اسم المنتج", product[0]),
            ("الباركود", product[1] or ""),
            ("السعر", product[2]),
            ("المخزون", product[3]),
            ("حد التنبيه", product[4])
        ]

        edit_image = {"path": product[5] or ""}

        def choose_edit_image():
            file = filedialog.askopenfilename(
                title="اختر صورة المنتج",
                filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.webp")]
            )
            if file:
                edit_image["path"] = file
                image_label.config(text=os.path.basename(file))



        for label, value in labels:

            frame = tk.Frame(
                dialog,
                bg=WHITE
            )

            frame.pack(
                fill="x",
                padx=30,
                pady=8
            )

            tk.Label(
                frame,
                text=label,
                bg=WHITE,
                font=("Arial", 10, "bold")
            ).pack(
                side="right"
            )

            entry = ttk.Entry(
                frame,
                justify="right"
            )

            entry.insert(
                0,
                str(value)
            )

            entry.pack(
                side="left",
                fill="x",
                expand=True,
                padx=10
            )

            entries[label] = entry


        image_frame = tk.Frame(dialog, bg=WHITE)
        image_frame.pack(fill="x", padx=30, pady=8)

        tk.Label(
            image_frame,
            text="صورة المنتج",
            bg=WHITE,
            font=("Arial", 10, "bold")
        ).pack(side="right")

        image_label = tk.Label(
            image_frame,
            text=(os.path.basename(product[5]) if product[5] else "لا توجد صورة"),
            bg=WHITE,
            fg=GRAY
        )
        image_label.pack(side="left", padx=10)

        ttk.Button(
            image_frame,
            text="اختيار صورة",
            command=choose_edit_image
        ).pack(side="left")


        def save():

            try:

                name = entries["اسم المنتج"].get()
                barcode = entries["الباركود"].get()
                price = float(
                    entries["السعر"].get()
                )
                stock = int(
                    entries["المخزون"].get()
                )
                min_stock = int(
                    entries["حد التنبيه"].get()
                )

                cursor.execute("""
                    UPDATE products
                    SET
                        name=?,
                        barcode=?,
                        price=?,
                        stock=?,
                        min_stock=?,
                        image=?
                    WHERE id=?
                """, (
                    name,
                    barcode or None,
                    price,
                    stock,
                    min_stock,
                    edit_image["path"],
                    product_id
                ))

                conn.commit()

                if barcode:
                    create_barcode_image(
                        barcode,
                        product_name=name,
                        price=price,
                        output_path=os.path.join(
                            BARCODES_DIR, f"{barcode}.png"
                        )
                    )

                dialog.destroy()
                self.load_products()

            except Exception as e:

                messagebox.showerror(
                    "خطأ",
                    f"تعذر حفظ التعديل:\n{e}"
                )


        ttk.Button(
            dialog,
            text="حفظ التعديلات",
            command=save
        ).pack(
            pady=20
        )


    # ========================================================
    # صفحة المخزون
    # ========================================================

    def show_inventory(self):

        self.clear_content()

        tk.Label(
            self.content,
            text="إدارة المخزون",
            bg=BG,
            fg=DARK,
            font=("Arial", 20, "bold")
        ).pack(
            anchor="e",
            padx=25,
            pady=20
        )


        cards = tk.Frame(
            self.content,
            bg=BG
        )

        cards.pack(
            fill="x",
            padx=25
        )


        cursor.execute(
            "SELECT COUNT(*) FROM products"
        )

        products_count = cursor.fetchone()[0]


        cursor.execute(
            "SELECT COALESCE(SUM(stock),0) FROM products"
        )

        total_stock = cursor.fetchone()[0]


        cursor.execute("""
            SELECT COUNT(*)
            FROM products
            WHERE stock <= min_stock
        """)

        low_stock = cursor.fetchone()[0]


        self.stat_card(
            cards,
            "عدد المنتجات",
            products_count,
            PRIMARY
        )

        self.stat_card(
            cards,
            "إجمالي الكمية",
            total_stock,
            GREEN
        )

        self.stat_card(
            cards,
            "مخزون منخفض",
            low_stock,
            RED
        )


        table = ttk.Treeview(
            self.content,
            columns=(
                "name",
                "barcode",
                "price",
                "stock",
                "min_stock",
                "status"
            ),
            show="headings"
        )

        heads = {
            "name": "المنتج",
            "barcode": "الباركود",
            "price": "السعر",
            "stock": "الكمية",
            "min_stock": "الحد الأدنى",
            "status": "الحالة"
        }

        for col in heads:

            table.heading(
                col,
                text=heads[col]
            )

        table.column("name", width=230)
        table.column("barcode", width=150)
        table.column("price", width=100)
        table.column("stock", width=100)
        table.column("min_stock", width=100)
        table.column("status", width=120)

        table.pack(
            fill="both",
            expand=True,
            padx=25,
            pady=20
        )


        cursor.execute("""
            SELECT
                name,
                barcode,
                price,
                stock,
                min_stock
            FROM products
            ORDER BY stock ASC
        """)

        for row in cursor.fetchall():

            status = (
                "⚠ منخفض"
                if row[3] <= row[4]
                else "✓ جيد"
            )

            table.insert(
                "",
                "end",
                values=(
                    row[0],
                    row[1] or "",
                    f"{row[2]:.3f}",
                    row[3],
                    row[4],
                    status
                )
            )


    # ========================================================
    # بطاقة إحصائية
    # ========================================================

    def stat_card(
        self,
        parent,
        title,
        value,
        color
    ):

        frame = tk.Frame(
            parent,
            bg=WHITE,
            width=220,
            height=100
        )

        frame.pack(
            side="right",
            padx=8,
            fill="x",
            expand=True
        )

        frame.pack_propagate(False)

        tk.Label(
            frame,
            text=title,
            bg=WHITE,
            fg=GRAY,
            font=("Arial", 11, "bold")
        ).pack(
            pady=(15, 5)
        )

        tk.Label(
            frame,
            text=str(value),
            bg=WHITE,
            fg=color,
            font=("Arial", 22, "bold")
        ).pack()


    # ========================================================
    # صفحة الجرد
    # ========================================================

    def show_inventory_count(self):

        self.clear_content()

        tk.Label(
            self.content,
            text="الجرد",
            bg=BG,
            fg=DARK,
            font=("Arial", 20, "bold")
        ).pack(
            anchor="e",
            padx=25,
            pady=20
        )


        info = tk.Frame(
            self.content,
            bg=WHITE
        )

        info.pack(
            fill="x",
            padx=25
        )


        today = datetime.now()

        day = today.strftime(
            "%Y-%m-%d"
        )

        week = today.strftime(
            "الأسبوع %U"
        )

        month = today.strftime(
            "%Y-%m"
        )


        self.stat_card(
            info,
            "الجرد اليومي",
            day,
            PRIMARY
        )

        self.stat_card(
            info,
            "الجرد الأسبوعي",
            week,
            GREEN
        )

        self.stat_card(
            info,
            "الجرد الشهري",
            month,
            ORANGE
        )


        table = ttk.Treeview(
            self.content,
            columns=(
                "name",
                "stock"
            ),
            show="headings"
        )

        table.heading(
            "name",
            text="المنتج"
        )

        table.heading(
            "stock",
            text="الكمية الحالية"
        )

        table.column(
            "name",
            width=400
        )

        table.column(
            "stock",
            width=150
        )

        table.pack(
            fill="both",
            expand=True,
            padx=25,
            pady=20
        )


        cursor.execute("""
            SELECT name, stock
            FROM products
            ORDER BY name
        """)

        for row in cursor.fetchall():

            table.insert(
                "",
                "end",
                values=row
            )


    # ========================================================
    # صفحة المبيعات
    # ========================================================

    def show_sales(self):

        self.clear_content()

        tk.Label(
            self.content,
            text="سجل المبيعات",
            bg=BG,
            fg=DARK,
            font=("Arial", 20, "bold")
        ).pack(
            anchor="e",
            padx=25,
            pady=20
        )


        table = ttk.Treeview(
            self.content,
            columns=(
                "id",
                "date",
                "total",
                "paid",
                "change"
            ),
            show="headings"
        )


        heads = {
            "id": "رقم الفاتورة",
            "date": "التاريخ",
            "total": "الإجمالي",
            "paid": "المدفوع",
            "change": "الباقي"
        }

        for col in heads:

            table.heading(
                col,
                text=heads[col]
            )

        table.column("id", width=100)
        table.column("date", width=180)
        table.column("total", width=120)
        table.column("paid", width=120)
        table.column("change", width=120)

        table.pack(
            fill="both",
            expand=True,
            padx=25,
            pady=10
        )


        cursor.execute("""
            SELECT
                id,
                sale_date,
                total,
                paid,
                change_amount
            FROM sales
            ORDER BY id DESC
        """)

        for row in cursor.fetchall():

            table.insert(
                "",
                "end",
                values=(
                    row[0],
                    row[1],
                    f"{row[2]:.3f} {CURRENCY}",
                    f"{row[3]:.3f} {CURRENCY}",
                    f"{row[4]:.3f} {CURRENCY}"
                )
            )


    # ========================================================
    # صفحة التقارير
    # ========================================================

    def show_reports(self):

        self.clear_content()

        tk.Label(
            self.content,
            text="التقارير والإحصائيات",
            bg=BG,
            fg=DARK,
            font=("Arial", 20, "bold")
        ).pack(
            anchor="e",
            padx=25,
            pady=20
        )


        cursor.execute("""
            SELECT
                COALESCE(SUM(total),0)
            FROM sales
            WHERE date(sale_date)=date('now','localtime')
        """)

        today_sales = cursor.fetchone()[0]


        cursor.execute("""
            SELECT
                COALESCE(SUM(total),0)
            FROM sales
            WHERE strftime('%Y-%W', sale_date)
                  =
                  strftime('%Y-%W','now','localtime')
        """)

        week_sales = cursor.fetchone()[0]


        cursor.execute("""
            SELECT
                COALESCE(SUM(total),0)
            FROM sales
            WHERE strftime('%Y-%m', sale_date)
                  =
                  strftime('%Y-%m','now','localtime')
        """)

        month_sales = cursor.fetchone()[0]


        frame = tk.Frame(
            self.content,
            bg=BG
        )

        frame.pack(
            fill="x",
            padx=25
        )


        self.report_card(
            frame,
            "مبيعات اليوم",
            today_sales,
            PRIMARY
        )

        self.report_card(
            frame,
            "مبيعات الأسبوع",
            week_sales,
            GREEN
        )

        self.report_card(
            frame,
            "مبيعات الشهر",
            month_sales,
            ORANGE
        )


        tk.Label(
            self.content,
            text="أكثر المنتجات مبيعًا",
            bg=BG,
            fg=DARK,
            font=("Arial", 16, "bold")
        ).pack(
            anchor="e",
            padx=25,
            pady=20
        )


        table = ttk.Treeview(
            self.content,
            columns=(
                "product",
                "quantity",
                "amount"
            ),
            show="headings"
        )

        table.heading(
            "product",
            text="المنتج"
        )

        table.heading(
            "quantity",
            text="الكمية المباعة"
        )

        table.heading(
            "amount",
            text="قيمة المبيعات"
        )

        table.column(
            "product",
            width=300
        )

        table.column(
            "quantity",
            width=150
        )

        table.column(
            "amount",
            width=150
        )

        table.pack(
            fill="both",
            expand=True,
            padx=25,
            pady=10
        )


        cursor.execute("""
            SELECT
                product_name,
                SUM(quantity),
                SUM(subtotal)
            FROM sale_items
            GROUP BY product_id
            ORDER BY SUM(quantity) DESC
            LIMIT 20
        """)

        for row in cursor.fetchall():

            table.insert(
                "",
                "end",
                values=(
                    row[0],
                    row[1],
                    f"{row[2]:.3f} {CURRENCY}"
                )
            )


    # ========================================================
    # بطاقة التقرير
    # ========================================================

    def report_card(
        self,
        parent,
        title,
        value,
        color
    ):

        frame = tk.Frame(
            parent,
            bg=WHITE,
            height=130
        )

        frame.pack(
            side="right",
            fill="x",
            expand=True,
            padx=8
        )

        frame.pack_propagate(False)

        tk.Label(
            frame,
            text=title,
            bg=WHITE,
            fg=GRAY,
            font=("Arial", 12, "bold")
        ).pack(
            pady=(20, 8)
        )

        tk.Label(
            frame,
            text=f"{value:.3f} {CURRENCY}",
            bg=WHITE,
            fg=color,
            font=("Arial", 22, "bold")
        ).pack()


    # ========================================================
    # تشغيل
    # ========================================================


if __name__ == "__main__":

    root = tk.Tk()

    app = LibraryPOS(root)

    root.mainloop()
