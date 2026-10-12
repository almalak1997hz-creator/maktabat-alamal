"""نافذة المساعد الذكي لبرنامج مكتبة الأمل (Tkinter).

الاستخدام من main.py:
    import ai_assistant
    ai_assistant.open_assistant(self.root, conn, on_change=..., theme={...}, currency=CURRENCY, export_dir=BASE_DIR)
"""
import csv
import os
import queue
import re
import threading
import tkinter as tk
from datetime import date, timedelta
from tkinter import ttk, messagebox, filedialog

import ai_core as core
import ai_engine

F = "Segoe UI"

_DEFAULT_THEME = {
    "BG": "#EDE1D4", "WHITE": "#FFFCF8", "DARK": "#2B211B", "PRIMARY": "#9A7654",
    "PRIMARY_DARK": "#4A3628", "GREEN": "#2E7D5B", "RED": "#C34F48",
    "ORANGE": "#C4873D", "GRAY": "#74685E", "LIGHT": "#E2D3C3",
    "BORDER": "#D5C4B2", "HOVER": "#B18B67",
}

_instance = None


def open_assistant(root, conn, on_change=None, theme=None, currency="ر.ع", export_dir=None):
    """يفتح نافذة المساعد (نافذة واحدة فقط؛ إن كانت مفتوحة يُحضرها للأمام)."""
    global _instance
    if _instance is not None:
        try:
            if _instance.win.winfo_exists():
                _instance.win.deiconify()
                _instance.win.lift()
                _instance.entry.focus_set()
                return _instance
        except tk.TclError:
            pass
    _instance = Assistant(root, conn, on_change, theme, currency, export_dir)
    return _instance


class Assistant:
    def __init__(self, root, conn, on_change=None, theme=None, currency="ر.ع", export_dir=None):
        self.root = root
        self.conn = conn
        self.on_change = on_change
        self.T = {**_DEFAULT_THEME, **(theme or {})}
        self.currency = currency
        self.export_dir = export_dir or os.getcwd()
        self.busy = False
        self.engine = ai_engine.Engine(conn, currency)

        T = self.T
        self.win = tk.Toplevel(root)
        self.win.title("المساعد الذكي")
        self.win.configure(bg=T["BG"])
        self.win.minsize(700, 560)
        self.win.transient(root)
        try:
            w, h = 920, 760
            x = root.winfo_rootx() + max((root.winfo_width() - w) // 2, 0)
            y = root.winfo_rooty() + max((root.winfo_height() - h) // 2, 0)
            self.win.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            self.win.geometry("920x760")
        self.win.protocol("WM_DELETE_WINDOW", self.close)

        self._style()
        self._build_header()
        self._build_chips()
        self._build_chat()
        self._build_input()
        self.welcome()

    # ------------------------------------------------------------------
    # بناء الواجهة
    # ------------------------------------------------------------------
    def _style(self):
        T = self.T
        s = ttk.Style()
        s.configure("AI.Treeview", rowheight=28, font=(F, 10), background=T["WHITE"],
                    fieldbackground=T["WHITE"], foreground=T["DARK"], borderwidth=0)
        s.configure("AI.Treeview.Heading", font=(F, 10, "bold"),
                    background=T["PRIMARY_DARK"], foreground=T["WHITE"])
        s.map("AI.Treeview", background=[("selected", T["HOVER"])], foreground=[("selected", T["WHITE"])])

    def btn(self, parent, text, cmd, kind="primary"):
        T = self.T
        colors = {
            "primary": (T["PRIMARY"], T["WHITE"], T["HOVER"]),
            "green": (T["GREEN"], T["WHITE"], "#256a4c"),
            "danger": (T["RED"], T["WHITE"], "#a8403a"),
            "ghost": (T["LIGHT"], T["DARK"], T["BORDER"]),
        }
        bg, fg, ab = colors[kind]
        return tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, activebackground=ab,
                         activeforeground=fg, relief="flat", bd=0, padx=14, pady=6,
                         cursor="hand2", font=(F, 10, "bold"))

    def _build_header(self):
        T = self.T
        hdr = tk.Frame(self.win, bg=T["PRIMARY_DARK"], height=72)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        box = tk.Frame(hdr, bg=T["PRIMARY_DARK"])
        box.pack(side="right", padx=20)
        tk.Label(box, text="🤖  مساعد مكتبة الأمل", font=(F, 17, "bold"),
                 bg=T["PRIMARY_DARK"], fg=T["WHITE"]).pack(anchor="e", pady=(10, 0))
        tk.Label(box, text="يعمل محلياً على جهازك • بياناتك لا تغادر الحاسوب", font=(F, 9),
                 bg=T["PRIMARY_DARK"], fg="#EADFD3").pack(anchor="e")
        self.btn(hdr, "🗑  مسح المحادثة", self.clear_chat, "primary").pack(side="left", padx=16)
        tk.Frame(self.win, bg=T["PRIMARY"], height=3).pack(fill="x")

    def _build_chips(self):
        T = self.T
        chips = [
            ("📈 الأكثر مبيعاً هذا الشهر", "أكثر المنتجات مبيعا هذا الشهر"),
            ("💰 مبيعات اليوم", "مبيعات اليوم"),
            ("📅 مبيعات الأسبوع", "مبيعات هذا الاسبوع"),
            ("📦 جرد هذا الشهر", "جرد هذا الشهر"),
            ("⚠ المنتجات الناقصة", "المنتجات الناقصة"),
            ("🛒 ماذا أطلب؟", "ماذا اطلب من المورد"),
            ("🐢 المنتجات الراكدة", "المنتجات الراكدة"),
            ("📊 حلل مبيعاتي", "حلل مبيعاتي"),
            ("🏷 باركود للمنتجات", "ضيف باركود لكل المنتجات"),
            ("↩ تراجع عن آخر تعديل", "تراجع"),
            ("❓ ماذا تستطيع؟", "ماذا تستطيع"),
        ]
        wrap = tk.Frame(self.win, bg=T["BG"])
        wrap.pack(fill="x", padx=14, pady=(10, 0))
        for i in range(0, len(chips), 4):
            row = tk.Frame(wrap, bg=T["BG"])
            row.pack(fill="x", pady=2)
            for label, q in chips[i:i + 4]:
                self.btn(row, label, lambda q=q: self.submit(q), "ghost").pack(side="right", padx=3)
        self.btn(wrap, "➕ إضافة منتج", self.prefill_add, "primary").pack(side="left", padx=3, pady=2)

    def _build_chat(self):
        T = self.T
        wrap = tk.Frame(self.win, bg=T["BG"])
        wrap.pack(fill="both", expand=True, padx=14, pady=(8, 4))
        self.canvas = tk.Canvas(wrap, bg=T["BG"], highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="left", fill="y")
        self.canvas.pack(side="right", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=T["BG"])
        self.inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.inner_id, width=e.width))
        self.win.bind("<MouseWheel>", self.on_wheel)

    def _build_input(self):
        T = self.T
        bar = tk.Frame(self.win, bg=T["WHITE"], highlightthickness=1, highlightbackground=T["BORDER"])
        bar.pack(fill="x", padx=14, pady=(4, 14))
        self.send_btn = self.btn(bar, "إرسال  ➤", self.submit, "primary")
        self.send_btn.pack(side="left", padx=8, pady=8)
        self.entry = tk.Entry(bar, font=(F, 12), justify="right", relief="flat", bg=T["WHITE"],
                              fg=T["DARK"], insertbackground=T["DARK"])
        self.entry.pack(side="right", fill="x", expand=True, padx=10, pady=10, ipady=4)
        self.entry.bind("<Return>", lambda e: self.submit())
        self.entry.focus_set()

    def on_wheel(self, e):
        if isinstance(e.widget, ttk.Treeview):
            return
        self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")

    def close(self):
        global _instance
        _instance = None
        self.win.destroy()

    # ------------------------------------------------------------------
    # عناصر المحادثة
    # ------------------------------------------------------------------
    def scroll_bottom(self):
        self.win.after(90, lambda: self.canvas.yview_moveto(1.0))

    def bubble(self, text, who="bot"):
        T = self.T
        row = tk.Frame(self.inner, bg=T["BG"])
        row.pack(fill="x", pady=4, padx=4)
        if who == "user":
            box = tk.Frame(row, bg=T["PRIMARY"])
            box.pack(side="right")
            tk.Label(box, text=text, bg=T["PRIMARY"], fg=T["WHITE"], justify="right", anchor="e",
                     wraplength=560, font=(F, 11), padx=14, pady=9).pack()
        else:
            tk.Label(row, text="🤖", bg=T["BG"], font=(F, 15)).pack(side="left", anchor="n", padx=(0, 6))
            box = tk.Frame(row, bg=T["WHITE"], highlightthickness=1, highlightbackground=T["BORDER"])
            box.pack(side="left")
            tk.Label(box, text=text, bg=T["WHITE"], fg=T["DARK"], justify="right", anchor="e",
                     wraplength=600, font=(F, 11), padx=14, pady=9).pack()
        self.scroll_bottom()
        return row

    def card(self):
        """بطاقة بيضاء بعرض المحادثة؛ تعيد الإطار الداخلي لإضافة المحتوى."""
        T = self.T
        row = tk.Frame(self.inner, bg=T["BG"])
        row.pack(fill="x", pady=3, padx=(40, 4))
        box = tk.Frame(row, bg=T["WHITE"], highlightthickness=1, highlightbackground=T["BORDER"])
        box.pack(fill="x")
        body = tk.Frame(box, bg=T["WHITE"])
        body.pack(fill="x", padx=12, pady=10)
        self.scroll_bottom()
        return body

    def stats(self, tiles):
        T = self.T
        body = self.card()
        for label, value, color in tiles:
            tile = tk.Frame(body, bg=T["WHITE"], highlightthickness=1, highlightbackground=T["BORDER"])
            tile.pack(side="right", expand=True, fill="x", padx=4)
            tk.Label(tile, text=value, bg=T["WHITE"], fg=color or T["PRIMARY_DARK"],
                     font=(F, 15, "bold")).pack(pady=(8, 0))
            tk.Label(tile, text=label, bg=T["WHITE"], fg=T["GRAY"], font=(F, 9)).pack(pady=(0, 8))
        return body

    def bars(self, items):
        """مخطط أعمدة أفقي: items = [(الاسم، القيمة، النص)]."""
        T = self.T
        body = self.card()
        cv = tk.Canvas(body, bg=T["WHITE"], highlightthickness=0, height=len(items) * 30 + 8)
        cv.pack(fill="x")
        peak = max((v for _, v, _ in items), default=0) or 1

        def short(s, n=26):
            return s if len(s) <= n else s[:n - 1] + "…"

        def draw(W):
            cv.delete("all")
            x0 = W - 215
            maxlen = max(40, x0 - 170)
            for i, (label, val, txt) in enumerate(items):
                y = 6 + i * 30
                cv.create_text(W - 8, y + 12, text=short(label), anchor="e", font=(F, 10), fill=T["DARK"])
                ln = max(3, int(maxlen * val / peak))
                cv.create_rectangle(x0 - ln, y + 3, x0, y + 21,
                                    fill=T["GREEN"] if i == 0 else T["PRIMARY"], outline="")
                cv.create_text(x0 - ln - 6, y + 12, text=txt, anchor="e",
                               font=(F, 9, "bold"), fill=T["PRIMARY_DARK"])

        cv.bind("<Configure>", lambda e: draw(e.width))
        return body

    def table(self, columns, rows, tags=None, height=10, widths=None, body=None):
        T = self.T
        body = body or self.card()
        box = tk.Frame(body, bg=T["WHITE"])
        box.pack(fill="x")
        ids = [f"c{i}" for i in range(len(columns))]
        h = max(1, min(len(rows), height))
        tree = ttk.Treeview(box, columns=ids, show="headings", style="AI.Treeview", height=h,
                            displaycolumns=list(reversed(ids)), selectmode="browse")
        for i, name in enumerate(columns):
            tree.heading(ids[i], text=name)
            w = widths[i] if widths else (230 if i == 0 else 110)
            tree.column(ids[i], width=w, anchor="e" if i == 0 else "center", stretch=True)
        tree.tag_configure("odd", background="#FAF3EA")
        tree.tag_configure("bad", foreground=T["RED"])
        tree.tag_configure("warn", foreground=T["ORANGE"])
        tree.tag_configure("good", foreground=T["GREEN"])
        for n, r in enumerate(rows):
            tag = tags[n] if tags and n < len(tags) else ""
            row_tags = (tag,) if tag else (("odd",) if n % 2 else ())
            tree.insert("", "end", values=list(r), tags=row_tags)
        if len(rows) > height:
            vs = ttk.Scrollbar(box, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=vs.set)
            vs.pack(side="left", fill="y")
        tree.pack(side="right", fill="x", expand=True)
        return body

    def actions(self, body, buttons):
        row = tk.Frame(body, bg=self.T["WHITE"])
        row.pack(fill="x", pady=(8, 0))
        for text, cmd, kind in buttons:
            self.btn(row, text, cmd, kind).pack(side="right", padx=4)

    def money(self, v):
        return f"{v:,.3f} {self.currency}"

    def note(self, body, text, color=None):
        tk.Label(body, text=text, bg=self.T["WHITE"], fg=color or self.T["GRAY"], font=(F, 9),
                 justify="right", anchor="e", wraplength=760).pack(anchor="e", pady=(6, 0))

    # ------------------------------------------------------------------
    # تصدير
    # ------------------------------------------------------------------
    def export_csv(self, title, columns, rows):
        safe = re.sub(r"[^\w\-]+", "_", title).strip("_") or "تقرير"
        path = filedialog.asksaveasfilename(
            parent=self.win, defaultextension=".csv", initialdir=self.export_dir,
            initialfile=f"{safe}.csv", filetypes=[("ملف Excel (CSV)", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(columns)
                w.writerows(rows)
        except OSError as e:
            messagebox.showerror("خطأ", f"تعذّر حفظ الملف:\n{e}", parent=self.win)
            return
        self.bubble(f"✔ تم حفظ الملف:\n{path}")
        try:
            os.startfile(path)  # ويندوز: يفتحه في Excel
        except Exception:
            pass

    # ------------------------------------------------------------------
    # عرض كتل المحرّك
    # ------------------------------------------------------------------
    def render(self, blocks):
        T = self.T
        tone = {"good": T["GREEN"], "bad": T["RED"], "warn": T["ORANGE"], None: None}
        for b in blocks:
            t = b.get("type")
            if t == "text":
                self.bubble(b["text"])
            elif t == "note":
                row = tk.Frame(self.inner, bg=T["BG"])
                row.pack(fill="x", padx=(40, 4))
                tk.Label(row, text=b["text"], bg=T["BG"], fg=T["GRAY"], font=(F, 9), justify="right",
                         anchor="e", wraplength=760).pack(anchor="w")
            elif t == "stats":
                self.stats([(x["label"], x["value"], tone.get(x.get("tone"))) for x in b["tiles"]])
            elif t == "bars":
                self.bars([(x["label"], x["value"], x["text"]) for x in b["items"]])
            elif t == "table":
                self.table(b["columns"], b["rows"], b.get("tags"), widths=b.get("widths"))
            elif t == "actions":
                body = self.card()
                self.actions(body, [(x["label"], self.button_command(x), "ghost") for x in b["buttons"]])
            elif t == "op":
                self.render_op(b)

    def button_command(self, x):
        if "send" in x:
            return lambda q=x["send"]: self.submit(q)
        if "fill" in x:
            return lambda q=x["fill"]: self.prefill(q)
        if "export" in x:
            ex = x["export"]
            return lambda: self.export_csv(ex["title"], ex["columns"], ex["rows"])
        return lambda: None

    def render_op(self, b):
        T = self.T
        body = self.card()
        tk.Label(body, text=b["title"], bg=T["WHITE"], fg=T["DARK"], font=(F, 11, "bold"),
                 justify="right", anchor="e", wraplength=760).pack(anchor="e", pady=(0, 8))
        if b.get("table"):
            tb = b["table"]
            self.table(tb["columns"], tb["rows"], tb.get("tags"), widths=tb.get("widths"), body=body)
        entries = {}
        if b.get("fields"):
            row = tk.Frame(body, bg=T["WHITE"])
            row.pack(anchor="e", pady=(4, 0))
            for f in b["fields"]:
                entries[f["key"]] = self.entry_field(row, f["label"], f["value"], f.get("width", 12))
        if b.get("note"):
            tk.Label(body, text=b["note"], bg=T["WHITE"], fg=T["ORANGE"], font=(F, 10), justify="right",
                     anchor="e", wraplength=760).pack(anchor="e", pady=(6, 0))
        bar = tk.Frame(body, bg=T["WHITE"])
        bar.pack(fill="x", pady=(10, 0))

        def run(op):
            payload = {**op, **{k: e.get() for k, e in entries.items()}}
            reply = self.engine.execute(payload)
            first = next((x for x in reply.blocks if x["type"] == "text"), None)
            ok = reply.changed
            self.finish_card(body, first["text"] if first else "تم.", ok=ok, notify=reply.changed)
            self.render([x for x in reply.blocks if x is not first])

        for btn in b["buttons"]:
            self.btn(bar, btn["label"], lambda op=btn["op"]: run(op), btn.get("tone", "primary")).pack(side="right", padx=4)
        self.btn(bar, "✖ إلغاء", lambda: self.finish_card(body, "تم الإلغاء.", ok=False), "ghost").pack(side="right", padx=4)

    def entry_field(self, parent, label, value, width):
        T = self.T
        f = tk.Frame(parent, bg=T["WHITE"])
        f.pack(side="right", padx=6)
        tk.Label(f, text=label, bg=T["WHITE"], fg=T["GRAY"], font=(F, 9)).pack(anchor="e")
        e = tk.Entry(f, width=width, justify="right", font=(F, 11), relief="solid", bd=1)
        e.pack(ipady=3)
        e.insert(0, str(value))
        return e

    def finish_card(self, body, msg, ok=True, notify=False):
        for w in body.winfo_children():
            w.destroy()
        tk.Label(body, text=msg, bg=self.T["WHITE"], fg=self.T["GREEN"] if ok else self.T["GRAY"],
                 font=(F, 11, "bold"), justify="right", anchor="e", wraplength=760).pack(anchor="e")
        if notify and self.on_change:
            try:
                self.on_change()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # التدفق العام
    # ------------------------------------------------------------------
    def welcome(self):
        try:
            self.render(self.engine.welcome())
        except Exception:
            self.bubble("مرحباً 👋 أنا مساعدك الذكي في مكتبة الأمل.")

    def clear_chat(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self.welcome()

    def prefill(self, text):
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        self.entry.focus_set()
        self.entry.icursor("end")

    def prefill_add(self):
        self.prefill("أضف منتج ")

    def submit(self, text=None):
        if self.busy:
            return
        text = (text if isinstance(text, str) else self.entry.get()).strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self.bubble(text, "user")
        try:
            self.step(self.engine.respond(text))
        except Exception as e:
            self.bubble(f"حدث خطأ غير متوقع: {e}")

    def step(self, reply):
        if reply.blocks:
            self.render(reply.blocks)
        if reply.changed and self.on_change:
            try:
                self.on_change()
            except Exception:
                pass
        if reply.task:
            self.run_task(*reply.task)

    def run_task(self, work, then):
        """ينفّذ عملاً بطيئاً (النموذج) في خيط منفصل حتى لا تتجمد النافذة."""
        self.busy = True
        self.send_btn.config(state="disabled")
        wait = self.bubble("جارٍ التفكير ...")
        q = queue.Queue()

        def run():
            try:
                q.put(("ok", work()))
            except core.AIConnectionError:
                q.put(("conn", None))
            except ValueError as e:
                q.put(("val", str(e)))
            except Exception as e:
                q.put(("err", str(e)))

        threading.Thread(target=run, daemon=True).start()

        def poll():
            try:
                kind, val = q.get_nowait()
            except queue.Empty:
                try:
                    if self.win.winfo_exists():
                        self.win.after(120, poll)
                except tk.TclError:
                    pass
                return
            try:
                if not self.win.winfo_exists():
                    return
            except tk.TclError:
                return
            self.busy = False
            self.send_btn.config(state="normal")
            wait.destroy()
            try:
                if kind == "ok":
                    self.step(then(val))
                elif kind == "conn":
                    self.render(ai_engine.Engine.conn_error())
                elif kind == "val":
                    self.bubble(val)
                else:
                    self.bubble(f"خطأ غير متوقع: {val}")
            except Exception as e:
                self.bubble(f"حدث خطأ غير متوقع: {e}")

        poll()
