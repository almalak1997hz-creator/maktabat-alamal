"""المساعد الذكي لنسخة الويب (Flask).

التركيب في app.py (قبل if __name__ == "__main__":):
    import ai_web
    ai_web.register(app, db, CURRENCY)

يضيف مسارات /api/ai/* ويحقن زر المساعد العائم تلقائياً في كل صفحة HTML بعد تسجيل الدخول،
دون الحاجة لتعديل أي قالب (template).
"""
import collections
import threading
import time

from flask import jsonify, request, session

import ai_engine
from ai_engine import text as _text

_llm_slots = threading.BoundedSemaphore(2)          # أقصى طلبين متزامنين للنموذج
_hits = collections.defaultdict(collections.deque)  # تحديد المعدل لكل مستخدم

_SKIP_PREFIX = ("/static", "/api/", "/product-image", "/login", "/logout", "/health", "/backup")
_SKIP_WORDS = ("print", "invoice", "receipt", "فاتورة")


def register(app, db, currency="ر.ع"):

    def guard():
        """تسجيل الدخول + ترويسة مخصصة (تمنع الطلبات من مواقع أخرى) + حد 40 طلباً/دقيقة."""
        uid = session.get("user_id")
        if not uid:
            return jsonify(error="انتهت الجلسة، سجّل الدخول من جديد."), 401
        if request.headers.get("X-Requested-With") != "XMLHttpRequest":
            return jsonify(error="طلب غير مسموح."), 403
        dq, now = _hits[uid], time.time()
        while dq and now - dq[0] > 60:
            dq.popleft()
        if len(dq) >= 40:
            return jsonify(error="طلبات كثيرة، انتظر قليلاً."), 429
        dq.append(now)
        return None

    def reply_json(r):
        return jsonify(blocks=r.blocks, changed=bool(r.changed))

    @app.get("/api/ai/welcome")
    def ai_welcome():
        bad = guard()
        if bad:
            return bad
        c = db()
        try:
            return jsonify(blocks=ai_engine.Engine(c, currency).welcome(), changed=False)
        finally:
            c.close()

    @app.post("/api/ai/chat")
    def ai_chat():
        bad = guard()
        if bad:
            return bad
        msg = str((request.get_json(silent=True) or {}).get("text") or "").strip()
        if not msg or len(msg) > 400:
            return jsonify(blocks=[_text("اكتب سؤالاً قصيراً (حتى 400 حرف).")], changed=False)
        c = db()
        try:
            eng = ai_engine.Engine(c, currency)
            reply = eng.respond(msg)
            if reply.task:
                if not _llm_slots.acquire(timeout=60):
                    return jsonify(blocks=[_text("النموذج مشغول الآن، أعد المحاولة بعد قليل.")], changed=False)
                try:
                    reply = eng.resolve(reply)
                finally:
                    _llm_slots.release()
            return reply_json(reply)
        except Exception:
            app.logger.exception("ai_chat failed")
            return jsonify(blocks=[_text("حدث خطأ غير متوقع.")], changed=False)
        finally:
            c.close()

    @app.post("/api/ai/exec")
    def ai_exec():
        bad = guard()
        if bad:
            return bad
        op = (request.get_json(silent=True) or {}).get("op")
        if not isinstance(op, dict):
            return jsonify(blocks=[_text("⚠ طلب غير صالح.")], changed=False)
        c = db()
        try:
            return reply_json(ai_engine.Engine(c, currency).execute(op))
        finally:
            c.close()

    @app.after_request
    def inject_widget(resp):
        try:
            if (resp.status_code != 200 or resp.mimetype != "text/html" or resp.direct_passthrough
                    or not session.get("user_id")):
                return resp
            path = request.path
            if path.startswith(_SKIP_PREFIX) or any(w in path.lower() for w in _SKIP_WORDS):
                return resp
            html = resp.get_data(as_text=True)
            if "aiw-root" in html:
                return resp
            i = html.lower().rfind("</body>")
            html = html + WIDGET if i < 0 else html[:i] + WIDGET + html[i:]
            resp.set_data(html)
        except Exception:
            app.logger.exception("ai widget injection failed")
        return resp


WIDGET = r"""
<style>
.aiw-root,.aiw-root *{box-sizing:border-box;font-family:"Segoe UI",Tahoma,Arial,sans-serif}
.aiw-root{direction:rtl;position:fixed;z-index:2147483000;left:18px;bottom:18px}
.aiw-fab{width:58px;height:58px;border-radius:50%;border:0;background:#2E7D5B;color:#fff;font-size:28px;cursor:pointer;
  box-shadow:0 6px 18px rgba(0,0,0,.3);display:flex;align-items:center;justify-content:center;padding:0}
.aiw-fab:hover{background:#256a4c}
.aiw-panel{display:none;position:absolute;left:0;bottom:70px;width:min(440px,calc(100vw - 24px));
  height:min(690px,calc(100vh - 110px));background:#EDE1D4;border-radius:16px;overflow:hidden;
  box-shadow:0 12px 40px rgba(0,0,0,.35);flex-direction:column;color:#2B211B}
.aiw-panel.open{display:flex}
.aiw-head{background:#4A3628;color:#fff;padding:12px 14px;display:flex;align-items:center;gap:8px;border-bottom:3px solid #9A7654}
.aiw-head .t{flex:1}.aiw-head b{font-size:16px;display:block}.aiw-head small{font-size:11px;color:#EADFD3}
.aiw-ib{background:rgba(255,255,255,.14);color:#fff;border:0;border-radius:8px;padding:6px 10px;cursor:pointer;font-size:13px}
.aiw-ib:hover{background:rgba(255,255,255,.28)}
.aiw-chips{display:flex;gap:6px;overflow-x:auto;padding:8px 10px;white-space:nowrap;flex:none}
.aiw-chip{background:#E2D3C3;color:#2B211B;border:0;border-radius:999px;padding:6px 12px;cursor:pointer;font-size:12.5px;flex:none}
.aiw-chip:hover{background:#D5C4B2}
.aiw-msgs{flex:1;overflow-y:auto;padding:8px 10px;display:flex;flex-direction:column;gap:8px}
.aiw-b{max-width:92%;padding:9px 13px;border-radius:14px;font-size:14px;line-height:1.6;white-space:pre-wrap;word-wrap:break-word}
.aiw-b.bot{background:#FFFCF8;border:1px solid #D5C4B2;align-self:flex-start;border-top-right-radius:4px}
.aiw-b.user{background:#9A7654;color:#fff;align-self:flex-end;border-top-left-radius:4px}
.aiw-card{background:#FFFCF8;border:1px solid #D5C4B2;border-radius:12px;padding:10px;align-self:stretch}
.aiw-note{font-size:12px;color:#74685E;padding:0 4px;white-space:pre-wrap}
.aiw-stats{display:flex;flex-wrap:wrap;gap:6px}
.aiw-tile{flex:1 1 90px;border:1px solid #D5C4B2;border-radius:10px;padding:8px;text-align:center;background:#FFFCF8}
.aiw-tile b{display:block;font-size:16px;color:#4A3628}.aiw-tile span{font-size:11px;color:#74685E}
.aiw-tile.good b{color:#2E7D5B}.aiw-tile.bad b{color:#C34F48}.aiw-tile.warn b{color:#C4873D}
.aiw-bar{display:grid;grid-template-columns:105px 1fr;gap:6px;align-items:center;margin:5px 0;font-size:12.5px}
.aiw-bar .l{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.aiw-track{background:#F1E8DD;border-radius:6px;height:20px;position:relative;overflow:hidden}
.aiw-fill{background:#9A7654;height:100%;border-radius:6px}.aiw-bar:first-child .aiw-fill{background:#2E7D5B}
.aiw-track em{position:absolute;inset:0;display:flex;align-items:center;padding:0 8px;font-style:normal;font-size:11.5px;font-weight:600;color:#2B211B}
.aiw-tw{overflow-x:auto;max-height:300px;overflow-y:auto;border:1px solid #D5C4B2;border-radius:8px}
.aiw-tw table{border-collapse:collapse;width:100%;font-size:12.5px;background:#FFFCF8}
.aiw-tw th{background:#4A3628;color:#fff;padding:6px 8px;position:sticky;top:0;white-space:nowrap}
.aiw-tw td{padding:5px 8px;border-top:1px solid #EFE4D6;text-align:center}.aiw-tw td:first-child{text-align:right}
.aiw-tw tr.odd td{background:#FAF3EA}.aiw-tw tr.bad td{color:#C34F48}.aiw-tw tr.warn td{color:#C4873D}
.aiw-title{font-weight:700;font-size:14px;margin-bottom:8px}
.aiw-fields{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}
.aiw-fields label{font-size:11.5px;color:#74685E;display:block}
.aiw-fields input{border:1px solid #D5C4B2;border-radius:8px;padding:7px 9px;font-size:14px;width:100%;direction:rtl;background:#fff}
.aiw-btns{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.aiw-btn{border:0;border-radius:8px;padding:8px 14px;cursor:pointer;font-size:13px;font-weight:700;background:#9A7654;color:#fff}
.aiw-btn.green{background:#2E7D5B}.aiw-btn.ghost{background:#E2D3C3;color:#2B211B}.aiw-btn:disabled{opacity:.5;cursor:default}
.aiw-warn{color:#C4873D;font-size:12.5px;margin-top:6px}
.aiw-done{color:#2E7D5B;font-weight:700;font-size:14px}.aiw-done.no{color:#74685E}
.aiw-in{display:flex;gap:6px;padding:8px 10px 10px;background:#EDE1D4;flex:none}
.aiw-in input{flex:1;border:1px solid #D5C4B2;border-radius:10px;padding:10px 12px;font-size:14px;direction:rtl;background:#FFFCF8;min-width:0}
.aiw-in button{border:0;border-radius:10px;background:#9A7654;color:#fff;padding:0 16px;font-weight:700;cursor:pointer;font-size:14px}
.aiw-in button:disabled{opacity:.5}
@media (max-width:520px){.aiw-root{left:10px;bottom:10px}.aiw-panel{bottom:66px}}
@media print{.aiw-root{display:none!important}}
</style>
<div class="aiw-root" id="aiwRoot">
  <div class="aiw-panel" id="aiwPanel" role="dialog" aria-label="المساعد الذكي">
    <div class="aiw-head">
      <div class="t"><b>🤖 مساعد مكتبة الأمل</b><small>يعمل محلياً • بياناتك لا تغادر جهازك</small></div>
      <button class="aiw-ib" id="aiwClear" title="مسح المحادثة">🗑</button>
      <button class="aiw-ib" id="aiwClose" title="إغلاق">✖</button>
    </div>
    <div class="aiw-chips" id="aiwChips"></div>
    <div class="aiw-msgs" id="aiwMsgs"></div>
    <div class="aiw-in"><input id="aiwInput" type="text" maxlength="400" placeholder="اكتب طلبك بالعربية..." autocomplete="off"><button id="aiwSend">إرسال</button></div>
  </div>
  <button class="aiw-fab" id="aiwFab" title="المساعد الذكي">🤖</button>
</div>
<script>
(function(){
  var CHIPS=[["📈 الأكثر مبيعاً","أكثر المنتجات مبيعا هذا الشهر"],["💰 مبيعات اليوم","مبيعات اليوم"],["📦 جرد الشهر","جرد هذا الشهر"],
    ["⚠ الناقصة","المنتجات الناقصة"],["🛒 ماذا أطلب؟","ماذا اطلب من المورد"],["🐢 الراكدة","المنتجات الراكدة"],["📊 حلل مبيعاتي","حلل مبيعاتي"],
    ["🏷 باركود للمنتجات","ضيف باركود لكل المنتجات"],["↩ تراجع","تراجع"],["❓ مساعدة","ماذا تستطيع"]];
  var $=function(id){return document.getElementById(id)};
  var panel=$("aiwPanel"),msgs=$("aiwMsgs"),input=$("aiwInput"),sendBtn=$("aiwSend"),busy=false,hist=[];
  try{hist=JSON.parse(sessionStorage.getItem("aiwHist")||"[]")}catch(e){hist=[]}
  function save(){try{sessionStorage.setItem("aiwHist",JSON.stringify(hist.slice(-40)))}catch(e){}}
  function el(tag,cls,txt){var e=document.createElement(tag);if(cls)e.className=cls;if(txt!=null)e.textContent=txt;return e}
  function down(){setTimeout(function(){msgs.scrollTop=msgs.scrollHeight},30)}
  function bubble(t,who){var b=el("div","aiw-b "+who,t);msgs.appendChild(b);down();return b}
  function card(){var c=el("div","aiw-card");msgs.appendChild(c);down();return c}
  function api(url,body){
    var o={method:body?"POST":"GET",credentials:"same-origin",headers:{"X-Requested-With":"XMLHttpRequest"}};
    if(body){o.headers["Content-Type"]="application/json";o.body=JSON.stringify(body)}
    return fetch(url,o).then(function(r){
      var ct=r.headers.get("content-type")||"";
      if(ct.indexOf("json")<0)throw new Error("انتهت الجلسة، حدّث الصفحة وسجّل الدخول.");
      return r.json().then(function(j){if(j.error)throw new Error(j.error);return j})});
  }
  function csv(title,cols,rows){
    var q=function(v){return '"'+String(v==null?"":v).replace(/"/g,'""')+'"'};
    var s="\ufeff"+[cols].concat(rows).map(function(r){return r.map(q).join(",")}).join("\r\n");
    var a=document.createElement("a");a.href=URL.createObjectURL(new Blob([s],{type:"text/csv;charset=utf-8"}));
    a.download=(title||"report")+".csv";document.body.appendChild(a);a.click();setTimeout(function(){URL.revokeObjectURL(a.href);a.remove()},500);
  }
  function table(b,parent){
    var w=el("div","aiw-tw"),t=el("table"),h=el("tr");
    b.columns.forEach(function(c){h.appendChild(el("th",null,c))});t.appendChild(el("thead")).appendChild(h);
    var tb=el("tbody");
    b.rows.forEach(function(r,i){var tr=el("tr",(b.tags&&b.tags[i])||(i%2?"odd":""));r.forEach(function(v){tr.appendChild(el("td",null,v))});tb.appendChild(tr)});
    t.appendChild(tb);w.appendChild(t);parent.appendChild(w);
  }
  function btnFor(x,parent){
    var b=el("button","aiw-btn ghost",x.label);b.type="button";
    b.onclick=function(){
      if(x.send)send(x.send);
      else if(x.fill){input.value=x.fill;input.focus()}
      else if(x.export)csv(x.export.title,x.export.columns,x.export.rows)};
    parent.appendChild(b);
  }
  function render(blocks){
    blocks.forEach(function(b){
      if(b.type==="text")bubble(b.text,"bot");
      else if(b.type==="note"){var n=el("div","aiw-note",b.text);msgs.appendChild(n)}
      else if(b.type==="stats"){var c=card(),s=el("div","aiw-stats");
        b.tiles.forEach(function(t){var d=el("div","aiw-tile "+(t.tone||""));d.appendChild(el("b",null,t.value));d.appendChild(el("span",null,t.label));s.appendChild(d)});
        c.appendChild(s)}
      else if(b.type==="bars"){var c2=card(),peak=Math.max.apply(null,b.items.map(function(i){return i.value}))||1;
        b.items.forEach(function(i){var r=el("div","aiw-bar");r.appendChild(el("div","l",i.label));
          var tr=el("div","aiw-track"),f=el("div","aiw-fill");f.style.width=Math.max(3,i.value/peak*100)+"%";tr.appendChild(f);tr.appendChild(el("em",null,i.text));r.appendChild(tr);c2.appendChild(r)})}
      else if(b.type==="table"){var c3=card();table(b,c3)}
      else if(b.type==="actions"){var c4=card(),bt=el("div","aiw-btns");b.buttons.forEach(function(x){btnFor(x,bt)});c4.appendChild(bt)}
      else if(b.type==="op")renderOp(b);
    });
  }
  function renderOp(b){
    var c=card();c.appendChild(el("div","aiw-title",b.title));
    if(b.table)table(b.table,c);
    var inputs={};
    if(b.fields&&b.fields.length){var f=el("div","aiw-fields");
      b.fields.forEach(function(x){var w=el("div");w.style.flex=(x.width>15?"2 1 160px":"1 1 80px");w.appendChild(el("label",null,x.label));
        var i=el("input");i.value=x.value;i.inputMode="decimal";if(x.key==="name")i.inputMode="text";inputs[x.key]=i;w.appendChild(i);f.appendChild(w)});c.appendChild(f)}
    if(b.note)c.appendChild(el("div","aiw-warn",b.note));
    var bar=el("div","aiw-btns");c.appendChild(bar);
    function finish(txt,ok){c.innerHTML="";c.appendChild(el("div","aiw-done"+(ok?"":" no"),txt))}
    b.buttons.forEach(function(x){
      var bt=el("button","aiw-btn "+(x.tone==="green"?"green":x.tone==="ghost"?"ghost":""),x.label);bt.type="button";
      bt.onclick=function(){
        var op=Object.assign({},x.op);Object.keys(inputs).forEach(function(k){op[k]=inputs[k].value});
        bar.querySelectorAll("button").forEach(function(z){z.disabled=true});
        api("/api/ai/exec",{op:op}).then(function(r){
          var first=r.blocks.filter(function(z){return z.type==="text"})[0];
          finish(first?first.text:"تم.",!!r.changed);
          var rest=r.blocks.filter(function(z){return z!==first});if(rest.length)render(rest);
          hist.push({who:"bot",blocks:first?[first].concat(rest):rest});save();
          if(r.changed)refreshHint();
        }).catch(function(e){finish("⚠ "+e.message,false)});
      };bar.appendChild(bt)});
    var cancel=el("button","aiw-btn ghost","✖ إلغاء");cancel.type="button";cancel.onclick=function(){finish("تم الإلغاء.",false)};bar.appendChild(cancel);
  }
  function refreshHint(){
    var c=card(),b=el("button","aiw-btn ghost","🔄 تحديث الصفحة لرؤية التغيير");b.type="button";b.onclick=function(){location.reload()};c.appendChild(b);
  }
  function send(text){
    text=(text||"").trim();if(!text||busy)return;
    busy=true;sendBtn.disabled=true;input.value="";bubble(text,"user");hist.push({who:"user",text:text});
    var w=bubble("جارٍ التفكير ...","bot");
    api("/api/ai/chat",{text:text}).then(function(r){
      w.remove();render(r.blocks);
      hist.push({who:"bot",blocks:r.blocks.filter(function(z){return z.type!=="op"})});save();
      if(r.changed)refreshHint();
    }).catch(function(e){w.remove();bubble("⚠ "+e.message,"bot")}).then(function(){busy=false;sendBtn.disabled=false;input.focus()});
  }
  function replay(){
    msgs.innerHTML="";
    if(!hist.length){api("/api/ai/welcome").then(function(r){render(r.blocks);hist.push({who:"bot",blocks:r.blocks});save()}).catch(function(e){bubble("مرحباً 👋 أنا مساعدك الذكي.","bot")});return}
    hist.forEach(function(h){if(h.who==="user")bubble(h.text,"user");else render(h.blocks)});
  }
  var chips=$("aiwChips");
  CHIPS.forEach(function(c){var b=el("button","aiw-chip",c[0]);b.type="button";b.onclick=function(){send(c[1])};chips.appendChild(b)});
  var shown=false;
  function toggle(open){
    var o=open==null?!panel.classList.contains("open"):open;panel.classList.toggle("open",o);
    try{sessionStorage.setItem("aiwOpen",o?"1":"0")}catch(e){}
    if(o){if(!shown){shown=true;replay()}input.focus();down()}
  }
  $("aiwFab").onclick=function(){toggle()};$("aiwClose").onclick=function(){toggle(false)};
  $("aiwClear").onclick=function(){hist=[];save();replay()};
  sendBtn.onclick=function(){send(input.value)};
  input.addEventListener("keydown",function(e){if(e.key==="Enter"&&!e.isComposing){e.preventDefault();send(input.value)}});
  try{if(sessionStorage.getItem("aiwOpen")==="1")toggle(true)}catch(e){}
})();
</script>
"""
