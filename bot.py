"""
U-Gift Bot - To'liq professional bot
Telegram Mini App + Qulaypay to'lov + Fragment API
"""
import asyncio, logging, json, os, time, aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
)
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN        = os.getenv("BOT_TOKEN")
SUPER_ADMIN_ID   = int(os.getenv("ADMIN_ID", "0"))
TON_API_KEY      = os.getenv("TON_API_KEY", "")
FRAGMENT_COOKIES = os.getenv("FRAGMENT_COOKIES", "")
WEB_URL          = os.getenv("WEB_URL", "")
QULAYPAY_KEY     = os.getenv("QULAYPAY_API_KEY", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

# ═══════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════
DB = "database.json"

def db() -> dict:
    if os.path.exists(DB):
        with open(DB, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "users": {}, "orders": [], "admins": {}, "promo_codes": {},
        "settings": {
            "bot_active"        : True,
            "min_stars"         : 50,
            "referral_bonus"    : 5000,
            "required_channels" : [],
            "logs_channel"      : None,
            "support_link"      : "",
            "channel_link"      : "",
            "logo_file_id"      : None,
            "prices": {
                "star"  : 210,
                "pm3"   : 195000,
                "pm6"   : 370000,
                "pm12"  : 680000,
            },
            "promo_active": True,
        }
    }

def sdb(data):
    with open(DB, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_user(uid): return db()["users"].get(str(uid), {})

def set_user(uid, data):
    d = db()
    if str(uid) not in d["users"]: d["users"][str(uid)] = {}
    d["users"][str(uid)].update(data)
    sdb(d)

def is_admin(uid): return uid == SUPER_ADMIN_ID or str(uid) in db().get("admins", {})
def is_super(uid): return uid == SUPER_ADMIN_ID
def fmt(n): return f"{int(n):,}".replace(",", " ")

# ═══════════════════════════════════════
# STATES
# ═══════════════════════════════════════
class A(StatesGroup):
    broadcast    = State()
    channel      = State()
    logs         = State()
    support      = State()
    channel_link = State()
    admin_id     = State()
    ban_id       = State()
    ref_bonus    = State()
    promo_code   = State()
    promo_disc   = State()
    promo_limit  = State()
    promo_product= State()
    price_key    = State()
    logo         = State()
    min_stars    = State()

# ═══════════════════════════════════════
# YORDAMCHI
# ═══════════════════════════════════════
async def send_log(text):
    d = db(); ch = d["settings"].get("logs_channel")
    if ch:
        try: await bot.send_message(ch, text, parse_mode="HTML")
        except: pass

async def notify_admins(text, kb=None, photo=None):
    d = db(); admins = [SUPER_ADMIN_ID] + [int(a) for a in d.get("admins", {}).keys()]
    for aid in admins:
        try:
            if photo: await bot.send_photo(aid, photo, caption=text, reply_markup=kb, parse_mode="HTML")
            else: await bot.send_message(aid, text, reply_markup=kb, parse_mode="HTML")
        except: pass

async def check_sub(uid):
    d = db()
    for ch in d["settings"]["required_channels"]:
        try:
            m = await bot.get_chat_member(ch, uid)
            if m.status in ["left", "kicked"]: return False
        except: pass
    return True

def get_sub_kb(d):
    chs = d["settings"]["required_channels"]
    btns = [[InlineKeyboardButton(text=f"📢 {ch}", url=f"https://t.me/{ch.lstrip('@')}")] for ch in chs]
    btns.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

# ═══════════════════════════════════════
# MINI APP KB
# ═══════════════════════════════════════
def webapp_kb():
    if WEB_URL and WEB_URL.startswith("https://"):
        return ReplyKeyboardMarkup(keyboard=[[
            KeyboardButton(text="🛍 Marketga kirish", web_app=WebAppInfo(url=WEB_URL))
        ]], resize_keyboard=True)
    return ReplyKeyboardMarkup(keyboard=[[
        KeyboardButton(text="🛍 Marketga kirish")
    ]], resize_keyboard=True)

# ═══════════════════════════════════════
# START
# ═══════════════════════════════════════
@dp.message(Command("start"))
async def cmd_start(msg: types.Message, state: FSMContext):
    await state.clear()
    d = db(); uid = str(msg.from_user.id)

    if not d["settings"]["bot_active"] and not is_admin(msg.from_user.id):
        await msg.answer("🔧 Bot hozirda texnik ishlar uchun o'chirilgan."); return

    # Yangi foydalanuvchi
    if uid not in d["users"]:
        d["users"][uid] = {
            "lang": "uz", "balance": 0, "orders": [],
            "referrals": 0, "ref_earned": 0,
            "joined": datetime.now().isoformat(),
            "banned": False, "promo_used": [],
            "username": msg.from_user.username or "",
            "name": msg.from_user.full_name or "",
        }
        # Referral
        args = msg.text.split()
        if len(args) > 1 and args[1].startswith("ref_"):
            ref_id = args[1][4:]
            if ref_id in d["users"]:
                bonus = d["settings"]["referral_bonus"]
                d["users"][ref_id]["balance"] = d["users"][ref_id].get("balance", 0) + bonus
                d["users"][ref_id]["referrals"] = d["users"][ref_id].get("referrals", 0) + 1
                d["users"][ref_id]["ref_earned"] = d["users"][ref_id].get("ref_earned", 0) + bonus
                try: await bot.send_message(int(ref_id), f"🎉 Yangi referral! +{fmt(bonus)} so'm bonus!")
                except: pass
        sdb(d)
    else:
        # Username yangilash
        d["users"][uid]["username"] = msg.from_user.username or ""
        d["users"][uid]["name"] = msg.from_user.full_name or ""
        sdb(d)

    d = db()
    if d["users"][uid].get("banned"):
        await msg.answer("🚫 Siz botdan bloklangansiz."); return

    args = msg.text.split()
    if len(args) > 1 and args[1] == "admin" and is_admin(msg.from_user.id):
        await cmd_admin(msg, state); return

    # Obuna tekshirish
    if not await check_sub(msg.from_user.id):
        await msg.answer("📢 <b>Botdan foydalanish uchun kanallarga obuna bo'ling:</b>",
                        parse_mode="HTML", reply_markup=get_sub_kb(d)); return

    # Welcome xabar
    logo = d["settings"].get("logo_file_id")
    text = (
        f"👋 <b>Salom, {msg.from_user.first_name}!</b>\n\n"
        f"⭐ <b>U-Gift Market</b> ga xush kelibsiz!\n\n"
        f"Bu yerda Telegram Premium Gift va Stars sotib olishingiz mumkin.\n\n"
        f"👇 Quyidagi tugma orqali marketga kiring:"
    )
    if logo:
        await msg.answer_photo(logo, caption=text, parse_mode="HTML", reply_markup=webapp_kb())
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=webapp_kb())

@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(cb: types.CallbackQuery):
    if await check_sub(cb.from_user.id):
        await cb.message.delete()
        await cmd_start(cb.message, None)
    else:
        await cb.answer("❌ Hali obuna bo'lmadingiz!", show_alert=True)

# ═══════════════════════════════════════
# WEB APP DAN KELGAN MA'LUMOT
# ═══════════════════════════════════════
@dp.message(F.web_app_data)
async def on_webapp_data(msg: types.Message):
    try:
        data = json.loads(msg.web_app_data.data)
        action = data.get("action")
        uid    = str(msg.from_user.id)
        d      = db()

        if action == "buy_stars":
            stars    = int(data.get("stars", 50))
            username = data.get("username", "").strip().lstrip("@")
            price    = int(data.get("price", 0))
            bal      = d["users"].get(uid, {}).get("balance", 0)

            if bal < price:
                await msg.answer(
                    f"❌ <b>Balans yetarli emas!</b>\n\n"
                    f"Kerak: <b>{fmt(price)} so'm</b>\n"
                    f"Sizda: <b>{fmt(bal)} so'm</b>\n\n"
                    f"Hisobingizni to'ldiring!",
                    parse_mode="HTML"
                )
                return

            await process_order(msg, uid, "stars", username, None, stars, price, d)

        elif action == "buy_premium":
            months   = int(data.get("months", 3))
            username = data.get("username", "").strip().lstrip("@")
            price    = int(data.get("price", 0))
            bal      = d["users"].get(uid, {}).get("balance", 0)

            if bal < price:
                await msg.answer(
                    f"❌ <b>Balans yetarli emas!</b>\n\n"
                    f"Kerak: <b>{fmt(price)} so'm</b>\n"
                    f"Sizda: <b>{fmt(bal)} so'm</b>\n\n"
                    f"Hisobingizni to'ldiring!",
                    parse_mode="HTML"
                )
                return

            await process_order(msg, uid, "premium", username, months, None, price, d)

    except Exception as e:
        log.error(f"WebApp data error: {e}")
        await msg.answer("❌ Xato yuz berdi. Qayta urinib ko'ring.")

async def process_order(msg, uid, service, username, months, stars, price, d):
    proc = await msg.answer("⏳ <b>Buyurtma bajarilmoqda...</b>", parse_mode="HTML")

    d["users"][uid]["balance"] -= price
    svc_txt = f"⭐ Premium {months} oy" if service == "premium" else f"🌟 {fmt(stars)} Stars"

    order = {
        "id"        : len(d["orders"]) + 1,
        "user_id"   : uid,
        "service"   : service,
        "username"  : username,
        "months"    : months,
        "stars"     : stars,
        "price"     : price,
        "status"    : "processing",
        "created_at": datetime.now().isoformat(),
    }
    d["orders"].append(order)
    d["users"][uid].setdefault("orders", []).append(order["id"])
    sdb(d)

    success = await do_fragment(order)
    d = db()

    if success:
        for o in d["orders"]:
            if o["id"] == order["id"]: o["status"] = "completed"
        sdb(d)
        await proc.edit_text(
            f"🎉 <b>Muvaffaqiyatli yuborildi!</b>\n\n"
            f"<code>━━━━━━━━━━━━━━━━</code>\n"
            f"🛍 {svc_txt}\n"
            f"👤 @{username}\n"
            f"💰 {fmt(price)} so'm\n"
            f"<code>━━━━━━━━━━━━━━━━</code>\n\n"
            f"✨ Xarid uchun rahmat!",
            parse_mode="HTML"
        )
        await send_log(f"✅ #{order['id']} | {svc_txt} → @{username} | {fmt(price)} so'm | ID:{uid}")
    else:
        d["users"][uid]["balance"] += price
        for o in d["orders"]:
            if o["id"] == order["id"]: o["status"] = "failed"
        sdb(d)
        await proc.edit_text(
            "❌ <b>Xato yuz berdi!</b>\n\nBalans qaytarildi.\nAdmin bilan bog'laning.",
            parse_mode="HTML"
        )
        await send_log(f"❌ #{order['id']} | {svc_txt} → @{username} | XATO")

async def do_fragment(order):
    try:
        from FragmentAPI import SyncFragmentAPI
        api = SyncFragmentAPI(cookies=FRAGMENT_COOKIES, wallet_api_key=TON_API_KEY)
        if order["service"] == "premium":
            r = api.gift_premium(order["username"], order["months"])
        elif order["service"] == "stars":
            r = api.buy_stars(order["username"], order["stars"])
        else: return False
        return bool(r)
    except Exception as e:
        log.error(f"Fragment: {e}"); return False

# ═══════════════════════════════════════
# API ENDPOINTS (webapp uchun)
# ═══════════════════════════════════════
# Bu funksiyalar app.py orqali chaqiriladi

# ═══════════════════════════════════════
# ADMIN PANEL
# ═══════════════════════════════════════
def admin_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Statistika",       callback_data="adm_stats"),
         InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="adm_users")],
        [InlineKeyboardButton(text="💰 Narxlar",          callback_data="adm_prices"),
         InlineKeyboardButton(text="🎁 Promo kodlar",     callback_data="adm_promos")],
        [InlineKeyboardButton(text="📋 Buyurtmalar",      callback_data="adm_orders"),
         InlineKeyboardButton(text="📢 Xabar yuborish",   callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="🖼 Logo o'rnatish",   callback_data="adm_logo"),
         InlineKeyboardButton(text="⚙️ Sozlamalar",       callback_data="adm_settings")],
        [InlineKeyboardButton(text="👑 Adminlar",         callback_data="adm_admins"),
         InlineKeyboardButton(text="📢 Kanallar",         callback_data="adm_channels")],
        [InlineKeyboardButton(text=f"🤖 Bot {'O\'CH ❌' if db()['settings']['bot_active'] else 'YOQ ✅'}", callback_data="adm_toggle_bot")],
    ])

async def adm_text():
    d = db(); s = d["settings"]
    total = len(d["users"]); orders = len(d["orders"])
    done  = len([o for o in d["orders"] if o["status"] == "completed"])
    rev   = sum(o["price"] for o in d["orders"] if o["status"] == "completed")
    today = datetime.now().date().isoformat()
    t_rev = sum(o["price"] for o in d["orders"] if o["status"] == "completed" and o["created_at"][:10] == today)
    p     = s["prices"]
    return (
        f"👨‍💼 <b>Admin Panel — U-Gift</b>\n\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"<b>💰 Narxlar:</b>\n"
        f"⭐ 1 Stars = <b>{fmt(p['star'])} so'm</b>\n"
        f"👑 Premium 3oy = <b>{fmt(p['pm3'])} so'm</b>\n"
        f"👑 Premium 6oy = <b>{fmt(p['pm6'])} so'm</b>\n"
        f"💎 Premium 12oy = <b>{fmt(p['pm12'])} so'm</b>\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"👥 Foydalanuvchilar: <b>{total}</b>\n"
        f"📋 Jami: <b>{orders}</b> | ✅ <b>{done}</b>\n"
        f"<code>━━━━━━━━━━━━━━━━</code>\n"
        f"📅 Bugun: <b>{fmt(t_rev)} so'm</b>\n"
        f"💰 Jami: <b>{fmt(rev)} so'm</b>"
    )

@dp.message(Command("admin"))
async def cmd_admin(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id): return
    await state.clear()
    await msg.answer(await adm_text(), parse_mode="HTML", reply_markup=admin_main_kb())

@dp.callback_query(F.data == "adm_main")
async def cb_adm_main(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    if state: await state.clear()
    try: await cb.message.edit_text(await adm_text(), parse_mode="HTML", reply_markup=admin_main_kb())
    except: await cb.message.answer(await adm_text(), parse_mode="HTML", reply_markup=admin_main_kb())

def back_kb(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")]])

# STATISTIKA
@dp.callback_query(F.data == "adm_stats")
async def cb_stats(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return
    d = db(); today = datetime.now().date().isoformat()
    t_ord = [o for o in d["orders"] if o["created_at"][:10] == today]
    t_rev = sum(o["price"] for o in t_ord if o["status"] == "completed")
    total_rev = sum(o["price"] for o in d["orders"] if o["status"] == "completed")
    await cb.message.edit_text(
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{len(d['users'])}</b>\n"
        f"📋 Jami: <b>{len(d['orders'])}</b>\n"
        f"✅ Bajarilgan: <b>{len([o for o in d['orders'] if o['status']=='completed'])}</b>\n"
        f"❌ Xato: <b>{len([o for o in d['orders'] if o['status']=='failed'])}</b>\n\n"
        f"📅 Bugun: <b>{len(t_ord)}</b> ta buyurtma\n"
        f"💰 Bugungi daromad: <b>{fmt(t_rev)} so'm</b>\n"
        f"💰 Jami daromad: <b>{fmt(total_rev)} so'm</b>",
        parse_mode="HTML", reply_markup=back_kb()
    )

# FOYDALANUVCHILAR
@dp.callback_query(F.data == "adm_users")
async def cb_users(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return
    d = db()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Bloklash",       callback_data="adm_ban"),
         InlineKeyboardButton(text="✅ Ochish",          callback_data="adm_unban")],
        [InlineKeyboardButton(text="💰 Balans berish",  callback_data="adm_give_bal")],
        [InlineKeyboardButton(text="🔙 Orqaga",         callback_data="adm_main")],
    ])
    await cb.message.edit_text(
        f"👥 <b>Foydalanuvchilar</b>\n\n"
        f"Jami: <b>{len(d['users'])}</b>\n"
        f"Banlangan: <b>{len([u for u in d['users'].values() if u.get('banned')])}</b>",
        parse_mode="HTML", reply_markup=kb
    )

@dp.callback_query(F.data.in_({"adm_ban","adm_unban","adm_give_bal"}))
async def cb_ban(cb: types.CallbackQuery, state: FSMContext):
    labels = {"adm_ban":"bloklash","adm_unban":"ochish","adm_give_bal":"balans berish"}
    await cb.message.edit_text(f"👤 Foydalanuvchi ID ({labels[cb.data]}):")
    await state.update_data(ban_action=cb.data); await state.set_state(A.ban_id)

@dp.message(A.ban_id)
async def enter_ban(msg: types.Message, state: FSMContext):
    try:
        parts = msg.text.strip().split()
        uid   = str(int(parts[0]))
        data  = await state.get_data(); d = db()
        action = data.get("ban_action")
        if uid not in d["users"]:
            await msg.answer("❌ Foydalanuvchi topilmadi!"); await state.clear(); return
        if action == "adm_ban":
            d["users"][uid]["banned"] = True; sdb(d)
            await msg.answer(f"🚫 Bloklandi: <code>{uid}</code>", parse_mode="HTML")
        elif action == "adm_unban":
            d["users"][uid]["banned"] = False; sdb(d)
            await msg.answer(f"✅ Ochildi: <code>{uid}</code>", parse_mode="HTML")
        elif action == "adm_give_bal":
            if len(parts) < 2:
                await msg.answer("❌ Format: ID SUMMA\nMasalan: 123456 50000"); return
            amount = int(parts[1])
            d["users"][uid]["balance"] = d["users"][uid].get("balance", 0) + amount; sdb(d)
            await bot.send_message(int(uid), f"✅ Hisobingizga <b>+{fmt(amount)} so'm</b> qo'shildi!", parse_mode="HTML")
            await msg.answer(f"✅ {fmt(amount)} so'm berildi: <code>{uid}</code>", parse_mode="HTML")
        await state.clear(); await cmd_admin(msg, state)
    except: await msg.answer("❌ Noto'g'ri format!")

# NARXLAR
@dp.callback_query(F.data == "adm_prices")
async def cb_prices(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); p = d["settings"]["prices"]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⭐ 1 Stars: {fmt(p['star'])} so'm",     callback_data="adm_p_star")],
        [InlineKeyboardButton(text=f"👑 Premium 3oy: {fmt(p['pm3'])} so'm",  callback_data="adm_p_pm3")],
        [InlineKeyboardButton(text=f"👑 Premium 6oy: {fmt(p['pm6'])} so'm",  callback_data="adm_p_pm6")],
        [InlineKeyboardButton(text=f"💎 Premium 12oy: {fmt(p['pm12'])} so'm",callback_data="adm_p_pm12")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")],
    ])
    await cb.message.edit_text(
        "💰 <b>Narxlarni yangilash</b>\n\n<i>So'mda kiriting</i>",
        parse_mode="HTML", reply_markup=kb
    )

@dp.callback_query(F.data.in_({"adm_p_star","adm_p_pm3","adm_p_pm6","adm_p_pm12"}))
async def cb_set_price(cb: types.CallbackQuery, state: FSMContext):
    if not is_super(cb.from_user.id): return
    labels = {"adm_p_star":"1 Stars","adm_p_pm3":"Premium 3 oy","adm_p_pm6":"Premium 6 oy","adm_p_pm12":"Premium 12 oy"}
    key    = cb.data.replace("adm_p_","")
    await cb.message.edit_text(f"💰 <b>{labels[cb.data]}</b> narxini so'mda kiriting:", parse_mode="HTML")
    await state.update_data(price_key=key); await state.set_state(A.price_key)

@dp.message(A.price_key)
async def enter_price(msg: types.Message, state: FSMContext):
    try:
        v = int(msg.text.replace(" ","").replace(",",""))
        if v <= 0: await msg.answer("❌ 0 dan katta bo'lishi kerak!"); return
        data = await state.get_data(); key = data["price_key"]
        d = db(); d["settings"]["prices"][key] = v; sdb(d)
        await msg.answer(f"✅ Narx yangilandi: <b>{fmt(v)} so'm</b>", parse_mode="HTML")
        await state.clear(); await cmd_admin(msg, state)
    except: await msg.answer("❌ Faqat raqam kiriting!")

# PROMO KODLAR
@dp.callback_query(F.data == "adm_promos")
async def cb_promos(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); promos = d.get("promo_codes", {})
    pt = ""
    for k, v in promos.items():
        prod = {"all":"Hammasi","stars":"Stars","pm3":"Premium 3oy","pm6":"Premium 6oy","pm12":"Premium 12oy"}.get(v.get("product","all"),"?")
        pt += f"• <code>{k}</code> — {v['discount']}% | {prod} | {v.get('used',0)}/{v.get('limit','∞')}\n"
    if not pt: pt = "Promo kodlar yo'q"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yaratish",  callback_data="adm_new_promo"),
         InlineKeyboardButton(text="🗑 Tozalash",  callback_data="adm_clear_promos")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="adm_main")],
    ])
    await cb.message.edit_text(f"🎁 <b>Promo kodlar:</b>\n\n{pt}", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "adm_new_promo")
async def new_promo(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("🎁 Promo kod nomini kiriting:\n\n<i>Masalan: SALE20</i>", parse_mode="HTML")
    await state.set_state(A.promo_code)

@dp.message(A.promo_code)
async def enter_promo_code(msg: types.Message, state: FSMContext):
    await state.update_data(promo_code=msg.text.strip().upper())
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Hammasi",    callback_data="pp_all")],
        [InlineKeyboardButton(text="🌟 Stars",      callback_data="pp_stars")],
        [InlineKeyboardButton(text="👑 Premium 3oy",callback_data="pp_pm3")],
        [InlineKeyboardButton(text="👑 Premium 6oy",callback_data="pp_pm6")],
        [InlineKeyboardButton(text="💎 Premium 12oy",callback_data="pp_pm12")],
    ])
    await msg.answer("🛍 Qaysi mahsulot uchun?", reply_markup=kb)
    await state.set_state(A.promo_product)

@dp.callback_query(F.data.startswith("pp_"))
async def cb_promo_product(cb: types.CallbackQuery, state: FSMContext):
    product = cb.data[3:]
    await state.update_data(promo_product=product)
    await cb.message.edit_text("📈 Chegirma foizi (1-90):")
    await state.set_state(A.promo_disc)

@dp.message(A.promo_disc)
async def enter_promo_disc(msg: types.Message, state: FSMContext):
    try:
        v = int(msg.text)
        if v < 1 or v > 90: await msg.answer("❌ 1-90 orasida!"); return
        await state.update_data(promo_disc=v)
        await msg.answer("🔢 Necha kishi uchun? (0 = cheksiz):")
        await state.set_state(A.promo_limit)
    except: await msg.answer("❌ Faqat raqam!")

@dp.message(A.promo_limit)
async def enter_promo_limit(msg: types.Message, state: FSMContext):
    try:
        limit = int(msg.text); data = await state.get_data(); d = db()
        code  = data["promo_code"]
        prods = {"all":"Hammasi","stars":"Stars","pm3":"Premium 3oy","pm6":"Premium 6oy","pm12":"Premium 12oy"}
        d["promo_codes"][code] = {
            "discount": data["promo_disc"],
            "product" : data.get("promo_product","all"),
            "limit"   : limit if limit > 0 else None,
            "used"    : 0,
            "created_at": datetime.now().isoformat()
        }
        sdb(d)
        await msg.answer(
            f"✅ <b>Promo kod yaratildi!</b>\n\n"
            f"🎁 <code>{code}</code>\n"
            f"📉 Chegirma: <b>{data['promo_disc']}%</b>\n"
            f"🛍 Mahsulot: <b>{prods.get(data.get('promo_product','all'))}</b>\n"
            f"🔢 Limit: <b>{limit if limit > 0 else 'Cheksiz'}</b>",
            parse_mode="HTML"
        )
        await state.clear(); await cmd_admin(msg, state)
    except: await msg.answer("❌ Faqat raqam!")

@dp.callback_query(F.data == "adm_clear_promos")
async def clear_promos(cb: types.CallbackQuery):
    d = db(); d["promo_codes"] = {}; sdb(d)
    await cb.answer("✅ Tozalandi!"); await cb_promos(cb)

# BUYURTMALAR
@dp.callback_query(F.data == "adm_orders")
async def cb_orders(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return
    d = db(); orders = d["orders"][-8:]
    if not orders: await cb.answer("Buyurtmalar yo'q!", show_alert=True); return
    st = {"completed":"✅","failed":"❌","processing":"⏳"}
    text = "📋 <b>So'nggi buyurtmalar:</b>\n<code>━━━━━━━━━━━━━━━━</code>\n\n"
    for o in reversed(orders):
        svc = {"premium":f"P{o.get('months',3)}oy","stars":f"{fmt(o.get('stars',0))}⭐"}.get(o["service"],o["service"])
        text += f"{st.get(o['status'],'❓')} <b>#{o['id']}</b> @{o.get('username','?')} — {svc} — {fmt(o['price'])} so'm\n"
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=back_kb())

# BROADCAST
@dp.callback_query(F.data == "adm_broadcast")
async def cb_broadcast(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return
    await cb.message.edit_text("📢 <b>Xabar yozing:</b>", parse_mode="HTML")
    await state.set_state(A.broadcast)

@dp.message(A.broadcast)
async def enter_broadcast(msg: types.Message, state: FSMContext):
    d = db(); sent = failed = 0
    prog = await msg.answer(f"⏳ 0/{len(d['users'])}")
    for i, uid in enumerate(d["users"]):
        try: await bot.send_message(int(uid), f"📢 <b>Xabar:</b>\n\n{msg.text}", parse_mode="HTML"); sent += 1
        except: failed += 1
        if i % 20 == 0:
            try: await prog.edit_text(f"⏳ {i}/{len(d['users'])}")
            except: pass
        await asyncio.sleep(0.05)
    await prog.edit_text(f"✅ Yuborildi! ✅{sent} ❌{failed}")
    await state.clear(); await cmd_admin(msg, state)

# LOGO
@dp.callback_query(F.data == "adm_logo")
async def cb_logo(cb: types.CallbackQuery, state: FSMContext):
    if not is_super(cb.from_user.id): return
    await cb.message.edit_text("🖼 Logo rasmini yuboring:\n\n<i>512×512 px tavsiya etiladi</i>", parse_mode="HTML")
    await state.set_state(A.logo)

@dp.message(A.logo)
async def enter_logo(msg: types.Message, state: FSMContext):
    if not msg.photo:
        await msg.answer("❌ Rasm yuboring!"); return
    file_id = msg.photo[-1].file_id
    d = db(); d["settings"]["logo_file_id"] = file_id; sdb(d)
    await msg.answer("✅ Logo saqlandi!")
    await state.clear(); await cmd_admin(msg, state)

# SOZLAMALAR
@dp.callback_query(F.data == "adm_settings")
async def cb_settings(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); s = d["settings"]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⭐ Min Stars: {s['min_stars']}",    callback_data="adm_set_minstars")],
        [InlineKeyboardButton(text=f"👥 Referral bonus: {fmt(s['referral_bonus'])} so'm", callback_data="adm_set_refbonus")],
        [InlineKeyboardButton(text="📢 Support linki",                   callback_data="adm_set_support")],
        [InlineKeyboardButton(text="📣 Kanal linki",                     callback_data="adm_set_chanlink")],
        [InlineKeyboardButton(text="🔙 Orqaga",                          callback_data="adm_main")],
    ])
    await cb.message.edit_text("⚙️ <b>Sozlamalar</b>", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data.in_({"adm_set_minstars","adm_set_refbonus","adm_set_support","adm_set_chanlink"}))
async def cb_set_settings(cb: types.CallbackQuery, state: FSMContext):
    labels = {
        "adm_set_minstars" : ("Min Stars (minimum 50):", A.min_stars),
        "adm_set_refbonus" : ("Referral bonus (so'mda):", A.ref_bonus),
        "adm_set_support"  : ("Support linki (https://t.me/...):", A.support),
        "adm_set_chanlink" : ("Kanal linki (https://t.me/...):", A.channel_link),
    }
    lbl, st = labels[cb.data]
    await cb.message.edit_text(lbl)
    await state.update_data(settings_action=cb.data)
    await state.set_state(st)

@dp.message(A.min_stars)
async def enter_min_stars(msg: types.Message, state: FSMContext):
    try:
        v = int(msg.text)
        if v < 50: await msg.answer("❌ Min 50!"); return
        d = db(); d["settings"]["min_stars"] = v; sdb(d)
        await msg.answer(f"✅ Min Stars: <b>{v}</b>", parse_mode="HTML")
        await state.clear(); await cmd_admin(msg, state)
    except: await msg.answer("❌ Faqat raqam!")

@dp.message(A.ref_bonus)
async def enter_ref_bonus(msg: types.Message, state: FSMContext):
    try:
        v = int(msg.text.replace(" ",""))
        d = db(); d["settings"]["referral_bonus"] = v; sdb(d)
        await msg.answer(f"✅ Referral bonus: <b>{fmt(v)} so'm</b>", parse_mode="HTML")
        await state.clear(); await cmd_admin(msg, state)
    except: await msg.answer("❌ Faqat raqam!")

@dp.message(A.support)
async def enter_support(msg: types.Message, state: FSMContext):
    d = db(); d["settings"]["support_link"] = msg.text.strip(); sdb(d)
    await msg.answer(f"✅ Support: {msg.text.strip()}")
    await state.clear(); await cmd_admin(msg, state)

@dp.message(A.channel_link)
async def enter_chanlink(msg: types.Message, state: FSMContext):
    d = db(); d["settings"]["channel_link"] = msg.text.strip(); sdb(d)
    await msg.answer(f"✅ Kanal linki: {msg.text.strip()}")
    await state.clear(); await cmd_admin(msg, state)

# KANALLAR
@dp.callback_query(F.data == "adm_channels")
async def cb_channels(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); chs = d["settings"]["required_channels"]; logs = d["settings"].get("logs_channel","Yo'q")
    ct = "\n".join([f"• {c}" for c in chs]) if chs else "Kanallar yo'q"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Kanal qo'shish",  callback_data="adm_add_ch")],
        [InlineKeyboardButton(text="📝 Logs kanali",     callback_data="adm_set_logs")],
        [InlineKeyboardButton(text="🗑 Tozalash",         callback_data="adm_clear_ch")],
        [InlineKeyboardButton(text="🔙 Orqaga",          callback_data="adm_main")],
    ])
    await cb.message.edit_text(f"📢 <b>Kanallar:</b>\n{ct}\n\n📝 <b>Logs:</b> {logs}", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "adm_add_ch")
async def add_ch(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("📢 Kanal username (@channel):")
    await state.set_state(A.channel)

@dp.message(A.channel)
async def enter_channel(msg: types.Message, state: FSMContext):
    d = db(); d["settings"]["required_channels"].append(msg.text.strip()); sdb(d)
    await msg.answer(f"✅ Kanal: {msg.text.strip()}")
    await state.clear(); await cmd_admin(msg, state)

@dp.callback_query(F.data == "adm_clear_ch")
async def clear_ch(cb: types.CallbackQuery):
    d = db(); d["settings"]["required_channels"] = []; sdb(d)
    await cb.answer("✅ Tozalandi!"); await cb_channels(cb)

@dp.callback_query(F.data == "adm_set_logs")
async def set_logs(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("📝 Logs kanal (@logs):")
    await state.set_state(A.logs)

@dp.message(A.logs)
async def enter_logs(msg: types.Message, state: FSMContext):
    d = db(); d["settings"]["logs_channel"] = msg.text.strip(); sdb(d)
    await msg.answer(f"✅ Logs: {msg.text.strip()}")
    await state.clear(); await cmd_admin(msg, state)

# ADMINLAR
@dp.callback_query(F.data == "adm_admins")
async def cb_admins(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); admins = d.get("admins", {})
    at = "\n".join([f"• <code>{a}</code>" for a in admins]) if admins else "Adminlar yo'q"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Qo'shish", callback_data="adm_add_admin"),
         InlineKeyboardButton(text="➖ O'chirish",callback_data="adm_del_admin")],
        [InlineKeyboardButton(text="🔙 Orqaga",  callback_data="adm_main")],
    ])
    await cb.message.edit_text(f"👑 <b>Adminlar:</b>\n\n{at}", parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data.in_({"adm_add_admin","adm_del_admin"}))
async def manage_admin(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text(f"👑 Admin ID ({'qo\'shish' if cb.data=='adm_add_admin' else 'o\'chirish'}):")
    await state.update_data(admin_action=cb.data); await state.set_state(A.admin_id)

@dp.message(A.admin_id)
async def enter_admin(msg: types.Message, state: FSMContext):
    try:
        aid = int(msg.text.strip())
        if aid == SUPER_ADMIN_ID: await msg.answer("❌ Asosiy adminni o'zgartirish mumkin emas!"); await state.clear(); return
        data = await state.get_data(); d = db()
        if data.get("admin_action") == "adm_add_admin":
            d["admins"][str(aid)] = {"added": datetime.now().isoformat()}; sdb(d)
            await msg.answer(f"✅ Admin: <code>{aid}</code>", parse_mode="HTML")
        else:
            if str(aid) in d["admins"]: del d["admins"][str(aid)]; sdb(d); await msg.answer(f"✅ O'chirildi: {aid}")
            else: await msg.answer("❌ Admin topilmadi!")
        await state.clear(); await cmd_admin(msg, state)
    except: await msg.answer("❌ Noto'g'ri ID!")

@dp.callback_query(F.data == "adm_toggle_bot")
async def toggle_bot(cb: types.CallbackQuery):
    if not is_super(cb.from_user.id): return
    d = db(); d["settings"]["bot_active"] = not d["settings"]["bot_active"]; sdb(d)
    await cb.answer(f"Bot {'YOQILDI ✅' if d['settings']['bot_active'] else 'O\'CHIRILDI ❌'}", show_alert=True)
    await cb_adm_main(cb, None)

# ═══════════════════════════════════════
# MAIN
# ═══════════════════════════════════════
async def main():
    log.info("🚀 U-Gift Bot ishga tushmoqda...")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
