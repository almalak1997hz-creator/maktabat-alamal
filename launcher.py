import os, sys, subprocess, time, urllib.request, re, webbrowser, shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent
PYTHON = sys.executable
REQ = BASE / "requirements.txt"
CLOUDFLARED = BASE / "cloudflared.exe"
URL_FILE = BASE / "رابط_مكتبة_الأمل.txt"


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=BASE, **kw)


def ensure_packages():
    try:
        import flask, waitress  # noqa
        return True
    except Exception:
        print("تثبيت مكونات مكتبة الأمل لأول مرة...")
        p = run([PYTHON, "-m", "pip", "install", "-r", str(REQ)])
        return p.returncode == 0


def wait_server():
    for _ in range(60):
        try:
            with urllib.request.urlopen("http://127.0.0.1:5000/health", timeout=1) as r:
                if r.status == 200: return True
        except Exception: pass
        time.sleep(0.5)
    return False


def port_busy():
    import socket
    s = socket.socket(); s.settimeout(0.5)
    r = s.connect_ex(("127.0.0.1", 5000)); s.close()
    return r == 0


def publish_when_ready(url):
    """لا نعرض الرابط العام إلا بعد أن يصبح الـDNS جاهزاً (يتأخر ثوانٍ بعد إنشائه)."""
    import socket, threading
    def work():
        host = url.split("//")[1]
        for _ in range(90):
            try:
                socket.gethostbyname(host)
                urllib.request.urlopen(url + "/health", timeout=5)
                print("\n✔ الرابط يعمل الآن:", url)
                import urllib.parse
                webbrowser.open("https://wa.me/96892826608?text=" + urllib.parse.quote("رابط مكتبة الأمل اليوم: " + url))
                return
            except Exception:
                time.sleep(2)
        print("\n⚠ لم أستطع التأكد من الرابط تلقائياً، لكنه محفوظ وقد يعمل بعد قليل.")
    threading.Thread(target=work, daemon=True).start()


def main():
    try: URL_FILE.unlink()
    except Exception: pass
    if port_busy():
        print("⚠ المنفذ 5000 مشغول بنسخة قديمة من البرنامج، لذلك لن تظهر التحديثات.")
        print("أغلق نافذة البرنامج القديمة (أو نفّذ: taskkill /F /IM python.exe) ثم أعد التشغيل.")
        input("اضغط Enter للإغلاق..."); return 1
    if not ensure_packages():
        print("تعذر تثبيت المكونات. شغّل install.bat ثم حاول مرة أخرى.")
        input("اضغط Enter للإغلاق...")
        return 1
    app_proc = subprocess.Popen([PYTHON, "app.py"], cwd=BASE, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    if not wait_server():
        print("تعذر تشغيل خادم مكتبة الأمل.")
        app_proc.terminate(); input("اضغط Enter للإغلاق..."); return 1
    webbrowser.open("http://127.0.0.1:5000")
    if not CLOUDFLARED.exists():
        print("تم تشغيل المكتبة محليًا.")
        print("للدخول من الهاتف: ضع cloudflared.exe داخل مجلد البرنامج ثم أعد التشغيل.")
        print("الرابط المحلي: http://127.0.0.1:5000")
        try: app_proc.wait()
        except KeyboardInterrupt: pass
        return 0
    print("جاري تشغيل الاتصال الآمن... انتظر ظهور رابط trycloudflare.com")
    tunnel = subprocess.Popen([str(CLOUDFLARED), "tunnel", "--url", "http://127.0.0.1:5000"], cwd=BASE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    found = None
    try:
        for line in tunnel.stdout:
            print(line, end="")
            m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
            if m and not found:
                found = m.group(0)
                URL_FILE.write_text(found, encoding="utf-8")
                print("\nرابط مكتبة الأمل:", found)
                publish_when_ready(found)
    except KeyboardInterrupt:
        pass
    finally:
        for p in (tunnel, app_proc):
            try: p.terminate()
            except Exception: pass
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
