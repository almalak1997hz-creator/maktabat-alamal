"""إضافة منتج بجملة عربية باستخدام نموذج Ollama محلي.

الاستخدام في app.py (قبل السطر if __name__ == "__main__"):
    import ai_products
    ai_products.register(app, db, login_required)
"""
import json
import re

from ai_core import _chat
from flask import jsonify, request

MODEL = "qwen2.5:3b"   # غيّره إلى qwen2.5:7b إن سمح جهازك

SYSTEM = """أنت مساعد لإدخال المنتجات في نظام مبيعات مكتبة.
استخرج من جملة المستخدم بيانات المنتج، وأعد JSON فقط بهذه الحقول:
{"name": اسم المنتج كما ذكره المستخدم, "quantity": عدد صحيح, "price": سعر القطعة الواحدة}
لا تشرح ولا تحسب شيئاً. وإن لم تجد قيمة فاجعلها null.

أمثلة:
الجملة: عندي قلم أزرق 50 قطعة بسعر 2 ريال
الناتج: {"name": "قلم أزرق", "quantity": 50, "price": 2}
الجملة: منتج آلة حاسبة تتوفر منه 10 قطع بسعر 1 ريال عماني
الناتج: {"name": "آلة حاسبة", "quantity": 10, "price": 1}
"""

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789..")


def _clean_text(text):
    return re.sub(r"\s+", " ", (text or "").translate(_AR_DIGITS)).strip()


def parse_product(text):
    """يستخرج name/quantity/price من الجملة، ويتحقق منها بنفسه."""
    r = _chat(
        format="json",
        options={"temperature": 0},
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": text},
        ],
    )
    data = json.loads(r["message"]["content"])

    name = str(data.get("name") or "").strip()
    quantity = int(float(data.get("quantity")))
    price = float(data.get("price"))
    if not name or len(name) > 100:
        raise ValueError("لم أفهم اسم المنتج.")
    if not (0 < quantity <= 1_000_000):
        raise ValueError("لم أفهم الكمية.")
    if not (0 <= price <= 1_000_000):
        raise ValueError("لم أفهم السعر.")
    return {"name": name, "quantity": quantity, "price": round(price, 3)}


def register(app, db, login_required):

    @app.post("/api/ai/parse-product")
    @login_required
    def ai_parse_product():
        text = _clean_text((request.get_json(silent=True) or {}).get("text"))
        if not text or len(text) > 300:
            return jsonify(error="اكتب جملة قصيرة تصف المنتج."), 400
        try:
            product = parse_product(text)
        except (ValueError, TypeError, json.JSONDecodeError):
            return jsonify(error="لم أستطع فهم الجملة. اكتبها بصيغة: منتج X كمية N بسعر P."), 422
        except Exception:
            return jsonify(error="تعذّر الاتصال بـ Ollama. تأكد أنه يعمل وأن النموذج محمّل."), 503

        # هل المنتج موجود مسبقاً بنفس الاسم؟
        c = db()
        try:
            row = c.execute("SELECT id, stock FROM products WHERE name=?", (product["name"],)).fetchone()
        finally:
            c.close()
        product["existing"] = {"id": row["id"], "stock": row["stock"]} if row else None
        return jsonify(product)

    @app.post("/api/ai/add-product")
    @login_required
    def ai_add_product():
        d = request.get_json(silent=True) or {}
        try:
            name = str(d.get("name", "")).strip()
            quantity = int(d.get("quantity"))
            price = float(d.get("price"))
            if not name or len(name) > 100 or not (0 < quantity <= 1_000_000) or not (0 <= price <= 1_000_000):
                raise ValueError
        except (ValueError, TypeError):
            return jsonify(error="بيانات غير صالحة."), 400

        c = db()
        try:
            if d.get("mode") == "add_stock":
                cur = c.execute("UPDATE products SET stock = stock + ? WHERE id=?", (quantity, int(d.get("existing_id") or 0)))
                if cur.rowcount != 1:
                    raise ValueError("المنتج غير موجود.")
                msg = "تمت زيادة المخزون."
            else:
                c.execute(
                    "INSERT INTO products(name,barcode,price,stock,min_stock,image) VALUES(?,?,?,?,?,?)",
                    (name, None, price, quantity, 5, ""),
                )
                msg = "تمت إضافة المنتج."
            c.commit()
        except ValueError as e:
            c.rollback()
            return jsonify(error=str(e)), 400
        except Exception:
            c.rollback()
            return jsonify(error="تعذّر الحفظ."), 500
        finally:
            c.close()
        return jsonify(ok=True, message=msg)
