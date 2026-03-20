"""
U-Gift Flask Server
- Qulaypay webhook
- WebApp API endpoints
"""
import json, os, hmac, hashlib, asyncio
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv
import aiohttp

load_dotenv()

app = Flask(__name__, static_folder="webapp")

DB              = "database.json"
QULAYPAY_KEY    = os.getenv("QULAYPAY_API_KEY", "")
QULAYPAY_SECRET = os.getenv("QULAYPAY_SECRET", "")
BOT_TOKEN       = os.getenv("BOT_TOKEN", "")
SUPER_ADMIN_ID  = int(os.getenv("ADMIN_ID", "0"))

def db():
    if os.path.exists(DB):
        with open(DB, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"users":{}, "orders":[], "admins":{}, "promo_codes":{},
            "settings":{"prices":{"star":210,"pm3":195000,"pm6":370000,"pm12":680000},
                        "referral_bonus":5000,"min_stars":50,"required_channels":[],
                        "logs_channel":None,"support_link":"","channel_link":"",
                        "logo_file_id":None,"bot_active":True,"promo_active":True}}

def sdb(data):
    with open(DB, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def fmt(n): return f"{int(n):,}".replace(",", " ")

def is_admin(uid):
    d = db()
    return int(uid) == SUPER_ADMIN_ID or str(uid) in d.get("admins", {})

async def send_tg(chat_id, text):
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
            )
    except: pass

# ═══════════════════════════════════════
# WEBAPP STATIC FILES
# ═══════════════════════════════════════
@app.route("/")
def index():
    return send_from_directory("webapp", "index.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("webapp", path)

# ═══════════════════════════════════════
# API — WEBAPP UCHUN
# ═══════════════════════════════════════
@app.route("/api/settings")
def api_settings():
    """WebApp uchun sozlamalar va narxlar"""
    d   = db()
    uid = request.args.get("uid", "0")
    u   = d["users"].get(str(uid), {})
    s   = d["settings"]
    return jsonify({
        "prices"        : s["prices"],
        "min_stars"     : s["min_stars"],
        "support_link"  : s.get("support_link", ""),
        "channel_link"  : s.get("channel_link", ""),
        "referral_bonus": s.get("referral_bonus", 5000),
        "balance"       : u.get("balance", 0),
        "referrals"     : u.get("referrals", 0),
        "ref_earned"    : u.get("ref_earned", 0),
        "username"      : u.get("username", ""),
        "name"          : u.get("name", ""),
        "orders_count"  : len(u.get("orders", [])),
        "promo_active"  : s.get("promo_active", True),
    })

@app.route("/api/promo/check", methods=["POST"])
def api_promo_check():
    """Promo kodni tekshirish"""
    data    = request.json
    code    = data.get("code", "").upper().strip()
    uid     = str(data.get("uid", "0"))
    product = data.get("product", "all")
    d       = db()
    promos  = d.get("promo_codes", {})

    if code not in promos:
        return jsonify({"success": False, "error": "Noto'g'ri promo kod"})

    promo = promos[code]

    # Mahsulot tekshirish
    if promo.get("product", "all") not in ("all", product):
        return jsonify({"success": False, "error": "Bu promo kod bu mahsulot uchun emas"})

    # Limit tekshirish
    if promo.get("limit") and promo.get("used", 0) >= promo["limit"]:
        return jsonify({"success": False, "error": "Promo kodning limiti tugagan"})

    # Foydalanuvchi ishlatganmi
    if code in d["users"].get(uid, {}).get("promo_used", []):
        return jsonify({"success": False, "error": "Siz bu promo kodni allaqachon ishlatgansiz"})

    return jsonify({"success": True, "discount": promo["discount"]})

@app.route("/api/topup/create", methods=["POST"])
def api_topup_create():
    """Qulaypay to'lov yaratish"""
    data   = request.json
    uid    = str(data.get("uid", "0"))
    amount = int(data.get("amount", 0))

    if amount < 5000:
        return jsonify({"success": False, "error": "Minimum 5 000 so'm"})

    import requests as req
    try:
        r = req.post(
            "https://api.qulaypay.uz/transaction/create",
            headers={
                "Authorization": f"Bearer {QULAYPAY_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "access_token": QULAYPAY_KEY,
                "amount"      : amount,
                "comment"     : f"U-Gift balans | ID:{uid}",
                "redirect_url": "https://t.me/u_gift_bot",
            },
            timeout=10
        )
        res = r.json()
        if res.get("status") == "success":
            txn = res["transaction"]
            # Kutilayotgan to'lov saqlaymiz
            d = db()
            if "pending_topups" not in d: d["pending_topups"] = {}
            d["pending_topups"][txn["id"]] = {"uid": uid, "amount": amount, "created_at": datetime.now().isoformat()}
            sdb(d)
            return jsonify({"success": True, "payment_url": txn["payment_url"], "txn_id": txn["id"]})
        else:
            return jsonify({"success": False, "error": res.get("message", "Xato")})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/history")
def api_history():
    """Foydalanuvchi tarixi"""
    uid    = request.args.get("uid", "0")
    d      = db()
    orders = [o for o in d["orders"] if o["user_id"] == str(uid)][-20:]
    return jsonify({"orders": list(reversed(orders))})

@app.route("/api/top10")
def api_top10():
    """Top 10 foydalanuvchi"""
    period = request.args.get("period", "daily")
    d      = db()
    today  = datetime.now().date().isoformat()

    top = {}
    for o in d["orders"]:
        if o["status"] != "completed": continue
        if period == "daily" and o["created_at"][:10] != today: continue
        elif period == "weekly":
            from datetime import timedelta
            week_ago = (datetime.now() - timedelta(days=7)).date().isoformat()
            if o["created_at"][:10] < week_ago: continue
        elif period == "monthly":
            if o["created_at"][:7] != today[:7]: continue

        uid = o["user_id"]
        stars = o.get("stars", 0) or 0
        if uid not in top: top[uid] = {"stars": 0, "orders": 0}
        top[uid]["stars"]  += stars
        top[uid]["orders"] += 1

    result = []
    for uid, stats in sorted(top.items(), key=lambda x: x[1]["stars"], reverse=True)[:10]:
        u = d["users"].get(uid, {})
        result.append({
            "uid"    : uid,
            "name"   : u.get("name", "Foydalanuvchi"),
            "stars"  : stats["stars"],
            "orders" : stats["orders"],
        })

    return jsonify({"top": result})

@app.route("/api/referral")
def api_referral():
    """Referral ma'lumotlari"""
    uid    = request.args.get("uid", "0")
    d      = db()
    u      = d["users"].get(str(uid), {})
    import requests as req
    try:
        me  = req.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe", timeout=5).json()
        username = me["result"]["username"]
        link = f"https://t.me/{username}?start=ref_{uid}"
    except:
        link = ""
    return jsonify({
        "link"       : link,
        "referrals"  : u.get("referrals", 0),
        "ref_earned" : u.get("ref_earned", 0),
        "bonus"      : d["settings"].get("referral_bonus", 5000),
    })

# ═══════════════════════════════════════
# QULAYPAY WEBHOOK
# ═══════════════════════════════════════
@app.route("/webhook/qulaypay", methods=["POST"])
def qulaypay_webhook():
    data = request.json
    print(f"Qulaypay webhook: {data}")

    if not data: return jsonify({"status": "error"}), 400

    txn_id = data.get("transaction", {}).get("id") or data.get("id")
    status = data.get("transaction", {}).get("status") or data.get("status")
    amount = data.get("transaction", {}).get("amount") or data.get("amount")

    if status != "paid":
        return jsonify({"status": "ok"})

    d = db()
    pending = d.get("pending_topups", {})

    if txn_id not in pending:
        return jsonify({"status": "ok"})

    topup = pending[txn_id]
    uid   = topup["uid"]
    amt   = int(topup.get("amount", amount or 0))

    if uid in d["users"]:
        d["users"][uid]["balance"] = d["users"][uid].get("balance", 0) + amt
        del d["pending_topups"][txn_id]
        sdb(d)

        # Botdan xabar yuborish
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(send_tg(
            int(uid),
            f"✅ <b>Balansingiz to'ldirildi!</b>\n\n"
            f"➕ <b>+{fmt(amt)} so'm</b>\n"
            f"💰 Joriy balans: <b>{fmt(d['users'][uid]['balance'])} so'm</b>"
        ))
        loop.close()

    return jsonify({"status": "ok"})

# ═══════════════════════════════════════
# ADMIN API
# ═══════════════════════════════════════
@app.route("/api/admin/stats")
def api_admin_stats():
    uid = request.args.get("uid", "0")
    if not is_admin(uid): return jsonify({"error": "Unauthorized"}), 401
    d = db(); today = datetime.now().date().isoformat()
    t_rev = sum(o["price"] for o in d["orders"] if o["status"]=="completed" and o["created_at"][:10]==today)
    total_rev = sum(o["price"] for o in d["orders"] if o["status"]=="completed")
    return jsonify({
        "users"        : len(d["users"]),
        "orders"       : len(d["orders"]),
        "completed"    : len([o for o in d["orders"] if o["status"]=="completed"]),
        "today_revenue": t_rev,
        "total_revenue": total_rev,
        "prices"       : d["settings"]["prices"],
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
