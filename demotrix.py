import os
import json
import time
import random
import html
from datetime import datetime

import telebot
from telebot import types

# =========================
# CONFIG
# =========================
TOKEN_B = "8510996448:AAHwKgbOz-TjDhf2w1gmwKzBG8bwk1QeIwU"  # вставь новый токен после /revoke
ADMINS = {"1015953944", "8498982238"}  # user_id строками

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
PATH_CONFIG  = os.path.join(DATA_DIR, "config.json")
PATH_REVIEWS = os.path.join(DATA_DIR, "reviews.json")
PATH_ORDERS  = os.path.join(DATA_DIR, "orders.json")

FLOOD_DELAY = 0.35
_last_action = {}

bot = telebot.TeleBot(TOKEN_B, parse_mode="HTML")

# =========================
# UI SCREEN (одно сообщение, которое редактируем)
# =========================
LAST_UI_MSG = {}      # chat_id -> message_id "экрана"

# Reply-keyboard carrier (чтобы меню снизу НЕ пропадало)
MENU_CARRIER = {}     # chat_id -> message_id
MENU_TEXT = "Меню (кнопки снизу):"

# =========================
# HELPERS
# =========================
def antiflood(user_id: int):
    t = time.time()
    last = _last_action.get(user_id, 0)
    if (t - last) < FLOOD_DELAY:
        time.sleep(FLOOD_DELAY - (t - last))
    _last_action[user_id] = time.time()

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

def esc(s: str) -> str:
    return html.escape(s or "")

def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def ensure_list_schema(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("reviews", "orders", "items", "data"):
            if isinstance(data.get(k), list):
                return data[k]
    return []

def is_admin(user_id: int) -> bool:
    return str(user_id) in ADMINS

def safe_delete(chat_id: int, message_id: int):
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass

def delete_user_message(message):
    # удаляем входящее сообщение пользователя (чистим чат)
    safe_delete(message.chat.id, message.message_id)

def parse_chat_target(val):
    """
    Возвращает int для -100... или строку для @username
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    if s.lstrip("-").isdigit():
        try:
            return int(s)
        except Exception:
            return s
    return s

# =========================
# CONFIG STORAGE
# =========================
def get_config():
    default = {
        "shop_link": "https://t.me/tr1xaelshopbot",     # просто показываем текстом
        "support_link": "https://t.me/tr1xADMIN",       # менеджер
        "help_text": (
            "• По заказам — напишите менеджеру.\n"
            "• Индивидуальный заказ — через «📦 Инд. заказ».\n"
            "• Возврат/обмен — опишите проблему и приложите фото."
        ),
        # куда слать отзывы (chat_id -100... или @channel)
        "reviews_forward_chat": "-1003572348203",
        "reviews_forward_template": "⭐ <b>Отзыв</b>\nОт: {who}\nДата: {date}\n\n{text}",
    }
    cfg = load_json(PATH_CONFIG, default)
    for k, v in default.items():
        cfg.setdefault(k, v)
    save_json(PATH_CONFIG, cfg)
    return cfg

def set_config_key(key, value):
    cfg = get_config()
    cfg[key] = value
    save_json(PATH_CONFIG, cfg)

# =========================
# UI: Reply keyboard (постоянно)
# =========================
def kb_reply_main(user_id: int):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    # порядок: инд заказ -> отзыв -> помощь
    kb.row("📦 Инд. заказ", "📝 Отзыв")
    kb.row("🆘 Помощь")
    if is_admin(user_id):
        kb.row("👑 Админка")
    return kb

def ensure_reply_menu(chat_id: int, user_id: int):
    """
    Держим отдельное сообщение, которое "несёт" ReplyKeyboard.
    Его не удаляем — иначе меню снизу пропадёт.
    """
    if chat_id in MENU_CARRIER:
        return
    msg = bot.send_message(chat_id, MENU_TEXT, reply_markup=kb_reply_main(user_id))
    MENU_CARRIER[chat_id] = msg.message_id

# =========================
# UI: Inline keyboards
# =========================
def kb_inline_main(user_id: int):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📦 Инд. заказ", callback_data="go_order"))
    kb.add(types.InlineKeyboardButton("📝 Отзыв", callback_data="go_review"))
    kb.add(types.InlineKeyboardButton("🆘 Помощь", callback_data="go_help"))
    if is_admin(user_id):
        kb.add(types.InlineKeyboardButton("👑 Админка", callback_data="go_admin"))
    return kb

def kb_back_main():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🏠 Меню", callback_data="back_main"))
    return kb

def kb_cancel():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="order_cancel"))
    return kb

def kb_size():
    kb = types.InlineKeyboardMarkup(row_width=4)
    kb.add(
        types.InlineKeyboardButton("XS", callback_data="size:XS"),
        types.InlineKeyboardButton("S",  callback_data="size:S"),
        types.InlineKeyboardButton("M",  callback_data="size:M"),
        types.InlineKeyboardButton("L",  callback_data="size:L"),
        types.InlineKeyboardButton("XL", callback_data="size:XL"),
        types.InlineKeyboardButton("XXL", callback_data="size:XXL"),
        types.InlineKeyboardButton("30", callback_data="size:30"),
        types.InlineKeyboardButton("32", callback_data="size:32"),
        types.InlineKeyboardButton("34", callback_data="size:34"),
        types.InlineKeyboardButton("36", callback_data="size:36"),
    )
    kb.add(types.InlineKeyboardButton("✍️ Ввести вручную", callback_data="size:manual"))
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="order_cancel"))
    return kb

def kb_color():
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("⚫ Чёрный", callback_data="color:черный"),
        types.InlineKeyboardButton("⚪ Белый", callback_data="color:белый"),
        types.InlineKeyboardButton("🩶 Серый", callback_data="color:серый"),
        types.InlineKeyboardButton("🔴 Красный", callback_data="color:красный"),
        types.InlineKeyboardButton("🔵 Синий", callback_data="color:синий"),
        types.InlineKeyboardButton("🟢 Зелёный", callback_data="color:зелёный"),
        types.InlineKeyboardButton("🟤 Беж/Корич", callback_data="color:беж/корич"),
    )
    kb.add(types.InlineKeyboardButton("✍️ Другой цвет (вручную)", callback_data="color:manual"))
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="order_cancel"))
    return kb

def kb_qty():
    kb = types.InlineKeyboardMarkup(row_width=4)
    kb.add(
        types.InlineKeyboardButton("1", callback_data="qty:1"),
        types.InlineKeyboardButton("2", callback_data="qty:2"),
        types.InlineKeyboardButton("3", callback_data="qty:3"),
        types.InlineKeyboardButton("4", callback_data="qty:4"),
    )
    kb.add(types.InlineKeyboardButton("✍️ Ввести вручную", callback_data="qty:manual"))
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="order_cancel"))
    return kb

def kb_contact(user):
    uname = f"@{user.username}" if user.username else None
    kb = types.InlineKeyboardMarkup()
    if uname:
        kb.add(types.InlineKeyboardButton(f"✅ Использовать {uname}", callback_data="contact:use_username"))
    kb.add(types.InlineKeyboardButton("✍️ Ввести другой контакт", callback_data="contact:manual"))
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="order_cancel"))
    return kb

def kb_photo():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⏭ Пропустить фото", callback_data="photo:skip"))
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="order_cancel"))
    return kb

def kb_confirm():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Подтвердить", callback_data="order_confirm"))
    kb.add(types.InlineKeyboardButton("✏️ Заполнить заново", callback_data="go_order"))
    kb.add(types.InlineKeyboardButton("❌ Отмена", callback_data="order_cancel"))
    return kb

# ----- Admin UI -----
def kb_admin():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🧾 Новые заказы", callback_data="admin_new"))
    kb.add(types.InlineKeyboardButton("🔎 Найти по ID", callback_data="admin_find"))
    kb.add(types.InlineKeyboardButton("📥 Скачать orders.json", callback_data="admin_export_orders"))
    kb.add(types.InlineKeyboardButton("📥 Скачать reviews.json", callback_data="admin_export_reviews"))
    kb.add(types.InlineKeyboardButton("⚙️ Настройки", callback_data="admin_settings"))
    kb.add(types.InlineKeyboardButton("🏠 Меню", callback_data="back_main"))
    return kb

def kb_admin_settings():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✏️ Контакт менеджера", callback_data="admin_set_support"))
    kb.add(types.InlineKeyboardButton("✏️ Текст помощи", callback_data="admin_set_helptext"))
    kb.add(types.InlineKeyboardButton("✏️ Ссылка на магазин", callback_data="admin_set_shop"))
    kb.add(types.InlineKeyboardButton("✏️ Канал отзывов", callback_data="admin_set_reviews_channel"))
    kb.add(types.InlineKeyboardButton("👑 В админку", callback_data="go_admin"))
    return kb

def kb_admin_order_actions(order_id: str):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🟡 В работу", callback_data=f"st:{order_id}:in_progress"),
        types.InlineKeyboardButton("✅ Готово", callback_data=f"st:{order_id}:done"),
        types.InlineKeyboardButton("⛔ Отменить", callback_data=f"st:{order_id}:cancelled"),
    )
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="go_admin"))
    return kb

# =========================
# UI SHOW (всегда один экран)
# =========================
def ui_show(chat_id: int, text: str, reply_markup=None, edit_message_id=None, disable_preview=True):
    """
    1) Пытаемся отредактировать прошлый экран
    2) Если не получилось — удаляем прошлый экран и шлём новый
    """
    mid = edit_message_id or LAST_UI_MSG.get(chat_id)
    if mid:
        try:
            bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=mid,
                reply_markup=reply_markup,
                parse_mode="HTML",
                disable_web_page_preview=disable_preview
            )
            LAST_UI_MSG[chat_id] = mid
            return mid
        except Exception:
            # если редактирование не вышло — удалим прошлый экран, чтобы не плодить мусор
            safe_delete(chat_id, mid)

    msg = bot.send_message(
        chat_id,
        text,
        reply_markup=reply_markup,
        disable_web_page_preview=disable_preview
    )
    LAST_UI_MSG[chat_id] = msg.message_id
    return msg.message_id

# =========================
# STATE (simple FSM)
# =========================
STATE = {}  # user_id -> {"mode": str, "data": dict}

def set_state(uid: int, mode: str, data=None):
    STATE[uid] = {"mode": mode, "data": data or {}}

def get_state(uid: int):
    return STATE.get(uid, {"mode": None, "data": {}})

def clear_state(uid: int):
    STATE.pop(uid, None)

# =========================
# REVIEWS: save + forward
# =========================
def forward_review_to_channel(entry: dict):
    cfg = get_config()
    target_raw = cfg.get("reviews_forward_chat")
    target = parse_chat_target(target_raw)
    if not target:
        return

    if entry.get("username"):
        who = f"@{esc(entry['username'])}"
    else:
        who = f"<a href='tg://user?id={entry.get('user_id')}'>пользователь</a>"

    template = cfg.get("reviews_forward_template") or "⭐ <b>Отзыв</b>\nОт: {who}\nДата: {date}\n\n{text}"
    date = esc(entry.get("ts") or now_iso())

    try:
        if entry.get("type") == "photo":
            cap = esc(entry.get("caption") or "—")
            out = template.format(who=who, date=date, text=cap)[:1000]
            bot.send_photo(target, entry["file_id"], caption=out, parse_mode="HTML")
        else:
            txt = esc(entry.get("text") or "—")
            out = template.format(who=who, date=date, text=txt)
            bot.send_message(target, out, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        # пишем админам точную ошибку
        for admin_id in ADMINS:
            try:
                bot.send_message(int(admin_id), f"❌ Ошибка отправки отзыва в {esc(str(target_raw))}\n<code>{esc(str(e))}</code>")
            except Exception:
                pass

# =========================
# SECTIONS
# =========================
def send_home(chat_id: int, user_id: int, edit_id=None):
    ensure_reply_menu(chat_id, user_id)
    cfg = get_config()
    ui_show(
        chat_id,
        "<b>Сервис-бот магазина</b>\n"
        "Выберите раздел:\n\n"
        f"Магазин (ссылка): {esc(cfg['shop_link'])}\n"
        f"Менеджер: {esc(cfg['support_link'])}",
        reply_markup=kb_inline_main(user_id),
        edit_message_id=edit_id,
        disable_preview=True
    )

def section_help(chat_id: int, user_id: int, edit_id=None):
    ensure_reply_menu(chat_id, user_id)
    cfg = get_config()
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("👤 Написать менеджеру", url=cfg["support_link"]))
    kb.add(types.InlineKeyboardButton("🏠 Меню", callback_data="back_main"))
    ui_show(
        chat_id,
        "<b>🆘 Помощь</b>\n\n"
        f"{esc(cfg['help_text'])}\n\n"
        f"<b>Контакт:</b> {esc(cfg['support_link'])}",
        reply_markup=kb,
        edit_message_id=edit_id,
        disable_preview=True
    )

def section_review(chat_id: int, user_id: int, edit_id=None):
    ensure_reply_menu(chat_id, user_id)
    set_state(user_id, "review_wait", {})
    ui_show(
        chat_id,
        "<b>📝 Отзыв</b>\n"
        "Отправьте отзыв одним сообщением.\n"
        "Можно <b>текст</b> или <b>фото с подписью</b>.\n\n"
        "Отмена: кнопка ниже.",
        reply_markup=kb_cancel(),
        edit_message_id=edit_id,
        disable_preview=True
    )

def section_admin(chat_id: int, user_id: int, edit_id=None):
    ensure_reply_menu(chat_id, user_id)
    if not is_admin(user_id):
        return ui_show(chat_id, "Доступ запрещён.", reply_markup=kb_back_main(), edit_message_id=edit_id)
    ui_show(chat_id, "<b>👑 Админка</b>", reply_markup=kb_admin(), edit_message_id=edit_id)

# =========================
# ORDER WIZARD
# =========================
def make_order_id(user_id: int) -> str:
    return f"{int(time.time())}{random.randint(100,999)}_{user_id}"

def start_order(chat_id: int, user, edit_id=None):
    ensure_reply_menu(chat_id, user.id)
    order_id = make_order_id(user.id)
    data = {
        "order_id": order_id,
        "status": "new",
        "ts": now_iso(),
        "user_id": user.id,
        "username": user.username,
        "model": "",
        "brand": "",
        "size": "",
        "color": "",
        "qty": "",
        "budget": "",
        "city": "",
        "contact": "",
        "note": "",
        "photo_file_id": None
    }
    set_state(user.id, "order_model", data)
    ui_show(
        chat_id,
        "<b>📦 Индивидуальный заказ</b>\n\n"
        "Шаг 1/9: Напишите <b>модель / название вещи</b>.\n"
        "Пример: <i>Худи Oversize / карго / футболка</i>",
        reply_markup=kb_cancel(),
        edit_message_id=edit_id,
        disable_preview=True
    )

def status_label(s: str) -> str:
    return {
        "new": "🆕 NEW",
        "in_progress": "🟡 IN PROGRESS",
        "done": "✅ DONE",
        "cancelled": "⛔ CANCELLED",
    }.get(s, s)

def order_preview(user, d: dict) -> str:
    uname = f"@{user.username}" if user.username else "(без username)"
    return (
        "<b>✅ Проверьте заявку</b>\n\n"
        f"<b>ID:</b> <code>{esc(d.get('order_id'))}</code>\n"
        f"<b>Статус:</b> {status_label(d.get('status'))}\n"
        f"<b>Пользователь:</b> {esc(uname)}\n\n"
        f"<b>Модель:</b> {esc(d.get('model'))}\n"
        f"<b>Бренд:</b> {esc(d.get('brand'))}\n"
        f"<b>Размер:</b> {esc(d.get('size'))}\n"
        f"<b>Цвет:</b> {esc(d.get('color'))}\n"
        f"<b>Кол-во:</b> {esc(d.get('qty'))}\n"
        f"<b>Бюджет:</b> {esc(d.get('budget'))}\n"
        f"<b>Город/доставка:</b> {esc(d.get('city'))}\n"
        f"<b>Контакт:</b> {esc(d.get('contact'))}\n"
        f"<b>Комментарий:</b> {esc(d.get('note') or '—')}\n"
        f"<b>Фото:</b> {'есть' if d.get('photo_file_id') else 'нет'}\n"
    )

def persist_order(d: dict):
    orders = ensure_list_schema(load_json(PATH_ORDERS, []))
    orders.append(d)
    save_json(PATH_ORDERS, orders)

def find_order(order_id: str):
    orders = ensure_list_schema(load_json(PATH_ORDERS, []))
    for i, o in enumerate(orders):
        if o.get("order_id") == order_id:
            return i, o, orders
    return None, None, orders

def update_order_status(order_id: str, new_status: str):
    idx, o, orders = find_order(order_id)
    if o is None:
        return False, None
    o["status"] = new_status
    o["status_updated_ts"] = now_iso()
    orders[idx] = o
    save_json(PATH_ORDERS, orders)
    return True, o

# =========================
# COMMANDS
# =========================
@bot.message_handler(commands=["start", "menu"])
def cmd_start(message):
    antiflood(message.from_user.id)
    delete_user_message(message)
    send_home(message.chat.id, message.from_user.id)

@bot.message_handler(commands=["admin"])
def cmd_admin(message):
    antiflood(message.from_user.id)
    delete_user_message(message)
    section_admin(message.chat.id, message.from_user.id)

# =========================
# CALLBACKS
# =========================
@bot.callback_query_handler(func=lambda c: True)
def callbacks(call):
    antiflood(call.from_user.id)
    uid = call.from_user.id
    chat_id = call.message.chat.id
    data = call.data

    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    # NAV
    if data == "back_main":
        clear_state(uid)
        return send_home(chat_id, uid, edit_id=call.message.message_id)

    if data == "go_help":
        return section_help(chat_id, uid, edit_id=call.message.message_id)

    if data == "go_review":
        return section_review(chat_id, uid, edit_id=call.message.message_id)

    if data == "go_order":
        return start_order(chat_id, call.from_user, edit_id=call.message.message_id)

    if data == "go_admin":
        return section_admin(chat_id, uid, edit_id=call.message.message_id)

    # CANCEL
    if data == "order_cancel":
        clear_state(uid)
        return ui_show(chat_id, "Ок, отменено.", reply_markup=kb_back_main(), edit_message_id=call.message.message_id)

    # ORDER QUICK CHOICES
    if data.startswith("size:"):
        st = get_state(uid)
        if st["mode"] != "order_size":
            return
        choice = data.split(":", 1)[1]
        if choice == "manual":
            st["data"]["size"] = ""
            set_state(uid, "order_size_manual", st["data"])
            return ui_show(chat_id, "Введите размер вручную (пример: S / M / 30/32 / 44):",
                           reply_markup=kb_cancel(), edit_message_id=call.message.message_id)
        st["data"]["size"] = choice
        set_state(uid, "order_color", st["data"])
        return ui_show(chat_id, "Шаг 4/9: Выберите <b>цвет</b>:", reply_markup=kb_color(),
                       edit_message_id=call.message.message_id)

    if data.startswith("color:"):
        st = get_state(uid)
        if st["mode"] != "order_color":
            return
        choice = data.split(":", 1)[1]
        if choice == "manual":
            st["data"]["color"] = ""
            set_state(uid, "order_color_manual", st["data"])
            return ui_show(chat_id, "Введите цвет вручную:", reply_markup=kb_cancel(),
                           edit_message_id=call.message.message_id)
        st["data"]["color"] = choice
        set_state(uid, "order_qty", st["data"])
        return ui_show(chat_id, "Шаг 5/9: Выберите <b>количество</b>:", reply_markup=kb_qty(),
                       edit_message_id=call.message.message_id)

    if data.startswith("qty:"):
        st = get_state(uid)
        if st["mode"] != "order_qty":
            return
        choice = data.split(":", 1)[1]
        if choice == "manual":
            st["data"]["qty"] = ""
            set_state(uid, "order_qty_manual", st["data"])
            return ui_show(chat_id, "Введите количество вручную (пример: 1):", reply_markup=kb_cancel(),
                           edit_message_id=call.message.message_id)
        st["data"]["qty"] = choice
        set_state(uid, "order_budget", st["data"])
        return ui_show(chat_id, "Шаг 6/9: Укажите <b>бюджет</b> (пример: 1200 MDL / $60):",
                       reply_markup=kb_cancel(), edit_message_id=call.message.message_id)

    if data.startswith("contact:"):
        st = get_state(uid)
        if st["mode"] != "order_contact":
            return
        action = data.split(":", 1)[1]
        if action == "use_username":
            uname = f"@{call.from_user.username}" if call.from_user.username else ""
            st["data"]["contact"] = uname
            set_state(uid, "order_note", st["data"])
            return ui_show(chat_id, "Шаг 9/9: Комментарий (необязательно). Напишите детали или отправьте «-».",
                           reply_markup=kb_cancel(), edit_message_id=call.message.message_id)
        if action == "manual":
            st["data"]["contact"] = ""
            set_state(uid, "order_contact_manual", st["data"])
            return ui_show(chat_id, "Введите контакт (пример: @username или номер телефона):",
                           reply_markup=kb_cancel(), edit_message_id=call.message.message_id)

    if data == "photo:skip":
        st = get_state(uid)
        if st["mode"] != "order_photo":
            return
        set_state(uid, "order_confirm", st["data"])
        return ui_show(chat_id, order_preview(call.from_user, st["data"]), reply_markup=kb_confirm(),
                       edit_message_id=call.message.message_id)

    if data == "order_confirm":
        st = get_state(uid)
        if st["mode"] != "order_confirm":
            return
        persist_order(st["data"])

        ui_show(chat_id, "✅ Заявка отправлена. Менеджер свяжется с вами.", reply_markup=kb_back_main(),
                edit_message_id=call.message.message_id)

        admin_text = "<b>📦 Новый индивидуальный заказ</b>\n\n" + order_preview(call.from_user, st["data"])
        for admin_id in ADMINS:
            try:
                if st["data"].get("photo_file_id"):
                    bot.send_photo(int(admin_id), st["data"]["photo_file_id"], caption=admin_text)
                else:
                    bot.send_message(int(admin_id), admin_text)
            except Exception:
                pass

        clear_state(uid)
        return

    # ADMIN
    if data == "admin_new":
        if not is_admin(uid):
            return
        orders = ensure_list_schema(load_json(PATH_ORDERS, []))
        new_orders = [o for o in orders if o.get("status") == "new"]
        if not new_orders:
            return bot.send_message(chat_id, "Новых заказов нет.", reply_markup=kb_admin())
        for o in new_orders[-10:]:
            full = (
                f"<b>{status_label(o.get('status'))}</b>\n"
                f"<b>ID:</b> <code>{esc(o.get('order_id'))}</code>\n"
                f"<b>Пользователь:</b> @{esc(o.get('username') or '—')}\n"
                f"<b>Модель:</b> {esc(o.get('model'))}\n"
                f"<b>Бренд:</b> {esc(o.get('brand'))}\n"
                f"<b>Размер:</b> {esc(o.get('size'))}\n"
                f"<b>Цвет:</b> {esc(o.get('color'))}\n"
                f"<b>Кол-во:</b> {esc(o.get('qty'))}\n"
                f"<b>Бюджет:</b> {esc(o.get('budget'))}\n"
                f"<b>Город:</b> {esc(o.get('city'))}\n"
                f"<b>Контакт:</b> {esc(o.get('contact'))}\n"
                f"<b>Комментарий:</b> {esc(o.get('note') or '—')}\n"
                f"<b>Фото:</b> {'есть' if o.get('photo_file_id') else 'нет'}\n"
                f"<b>Время:</b> {esc(o.get('ts'))}"
            )
            if o.get("photo_file_id"):
                bot.send_photo(chat_id, o["photo_file_id"], caption=full, reply_markup=kb_admin_order_actions(o["order_id"]))
            else:
                bot.send_message(chat_id, full, reply_markup=kb_admin_order_actions(o["order_id"]))
        return

    if data == "admin_find":
        if not is_admin(uid):
            return
        set_state(uid, "admin_find_wait", {})
        bot.send_message(chat_id, "Введите ID заказа:", reply_markup=kb_admin())
        return

    if data == "admin_export_orders":
        if not is_admin(uid):
            return
        orders = ensure_list_schema(load_json(PATH_ORDERS, []))
        save_json(PATH_ORDERS, orders)
        with open(PATH_ORDERS, "rb") as f:
            bot.send_document(chat_id, f, caption="orders.json")
        return

    if data == "admin_export_reviews":
        if not is_admin(uid):
            return
        reviews = ensure_list_schema(load_json(PATH_REVIEWS, []))
        save_json(PATH_REVIEWS, reviews)
        with open(PATH_REVIEWS, "rb") as f:
            bot.send_document(chat_id, f, caption="reviews.json")
        return

    if data == "admin_settings":
        if not is_admin(uid):
            return
        cfg = get_config()
        bot.send_message(
            chat_id,
            "<b>⚙️ Настройки</b>\n\n"
            f"<b>Магазин:</b> {esc(cfg['shop_link'])}\n"
            f"<b>Контакт:</b> {esc(cfg['support_link'])}\n"
            f"<b>Канал отзывов:</b> {esc(str(cfg.get('reviews_forward_chat','')))}\n\n"
            f"<b>Текст помощи:</b>\n{esc(cfg['help_text'])}",
            reply_markup=kb_admin_settings(),
            disable_web_page_preview=True
        )
        return

    if data == "admin_set_support":
        if not is_admin(uid):
            return
        set_state(uid, "admin_wait_support", {})
        bot.send_message(chat_id, "Отправьте новую ссылку/контакт менеджера (пример: https://t.me/username).")
        return

    if data == "admin_set_helptext":
        if not is_admin(uid):
            return
        set_state(uid, "admin_wait_helptext", {})
        bot.send_message(chat_id, "Отправьте новый текст для «Помощь».")
        return

    if data == "admin_set_shop":
        if not is_admin(uid):
            return
        set_state(uid, "admin_wait_shop", {})
        bot.send_message(chat_id, "Отправьте новую ссылку на магазин (пример: https://t.me/tr1xaelshopbot).")
        return

    if data == "admin_set_reviews_channel":
        if not is_admin(uid):
            return
        set_state(uid, "admin_wait_reviews_channel", {})
        bot.send_message(chat_id, "Отправьте канал для отзывов: @username или -1003572348203\nБот должен быть админом и иметь право постить.")
        return

    if data.startswith("st:"):
        if not is_admin(uid):
            return
        _, order_id, new_status = data.split(":", 2)
        ok, order = update_order_status(order_id, new_status)
        if not ok:
            return bot.send_message(chat_id, "Заказ не найден.", reply_markup=kb_admin())

        bot.send_message(chat_id, f"Статус обновлён: <code>{esc(order_id)}</code> → <b>{status_label(new_status)}</b>",
                         reply_markup=kb_admin(), parse_mode="HTML")

        try:
            bot.send_message(
                int(order["user_id"]),
                f"Статус вашей заявки <code>{esc(order_id)}</code> изменён: <b>{status_label(new_status)}</b>\n"
                f"Если нужно — нажмите «🆘 Помощь».",
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception:
            pass
        return

# =========================
# TEXT ROUTER
# =========================
@bot.message_handler(content_types=["text"])
def text_router(message):
    antiflood(message.from_user.id)
    uid = message.from_user.id
    chat_id = message.chat.id
    text = (message.text or "").strip()

    # чистим сообщения пользователя
    delete_user_message(message)

    st = get_state(uid)
    mode = st["mode"]
    d = st["data"]

    # ADMIN INPUTS
    if mode == "admin_wait_support":
        if not is_admin(uid):
            clear_state(uid); return
        set_config_key("support_link", text)
        clear_state(uid)
        return bot.send_message(chat_id, "Готово. Контакт обновлён.", reply_markup=kb_admin())

    if mode == "admin_wait_helptext":
        if not is_admin(uid):
            clear_state(uid); return
        set_config_key("help_text", text)
        clear_state(uid)
        return bot.send_message(chat_id, "Готово. Текст помощи обновлён.", reply_markup=kb_admin())

    if mode == "admin_wait_shop":
        if not is_admin(uid):
            clear_state(uid); return
        set_config_key("shop_link", text)
        clear_state(uid)
        return bot.send_message(chat_id, "Готово. Ссылка на магазин обновлена.", reply_markup=kb_admin())

    if mode == "admin_wait_reviews_channel":
        if not is_admin(uid):
            clear_state(uid); return
        set_config_key("reviews_forward_chat", text.strip())
        clear_state(uid)
        return bot.send_message(chat_id, f"Готово. Канал отзывов: {text.strip()}", reply_markup=kb_admin())

    if mode == "admin_find_wait":
        if not is_admin(uid):
            clear_state(uid); return
        order_id = text
        idx, o, _ = find_order(order_id)
        if o is None:
            return bot.send_message(chat_id, "Не найдено. Проверь ID.", reply_markup=kb_admin())
        full = (
            f"<b>{status_label(o.get('status'))}</b>\n"
            f"<b>ID:</b> <code>{esc(o.get('order_id'))}</code>\n"
            f"<b>Пользователь:</b> @{esc(o.get('username') or '—')}\n"
            f"<b>Модель:</b> {esc(o.get('model'))}\n"
            f"<b>Бренд:</b> {esc(o.get('brand'))}\n"
            f"<b>Размер:</b> {esc(o.get('size'))}\n"
            f"<b>Цвет:</b> {esc(o.get('color'))}\n"
            f"<b>Кол-во:</b> {esc(o.get('qty'))}\n"
            f"<b>Бюджет:</b> {esc(o.get('budget'))}\n"
            f"<b>Город:</b> {esc(o.get('city'))}\n"
            f"<b>Контакт:</b> {esc(o.get('contact'))}\n"
            f"<b>Комментарий:</b> {esc(o.get('note') or '—')}\n"
            f"<b>Фото:</b> {'есть' if o.get('photo_file_id') else 'нет'}\n"
            f"<b>Время:</b> {esc(o.get('ts'))}"
        )
        clear_state(uid)
        if o.get("photo_file_id"):
            bot.send_photo(chat_id, o["photo_file_id"], caption=full, reply_markup=kb_admin_order_actions(o["order_id"]))
        else:
            bot.send_message(chat_id, full, reply_markup=kb_admin_order_actions(o["order_id"]))
        return

    # REVIEW TEXT
    if mode == "review_wait":
        reviews = ensure_list_schema(load_json(PATH_REVIEWS, []))
        entry = {
            "ts": now_iso(),
            "type": "text",
            "user_id": uid,
            "username": message.from_user.username,
            "text": text
        }
        reviews.append(entry)
        save_json(PATH_REVIEWS, reviews)

        # автопост в канал
        forward_review_to_channel(entry)

        clear_state(uid)
        ui_show(chat_id, "✅ Спасибо! Отзыв сохранён.", reply_markup=kb_back_main())
        return

    # ORDER WIZARD TEXT STEPS
    if mode == "order_model":
        d["model"] = text
        set_state(uid, "order_brand", d)
        ui_show(chat_id, "Шаг 2/9: Укажите <b>бренд</b> (пример: Nike / Stussy / Corteiz):",
                reply_markup=kb_cancel())
        return

    if mode == "order_brand":
        d["brand"] = text
        set_state(uid, "order_size", d)
        ui_show(chat_id, "Шаг 3/9: Выберите <b>размер</b>:", reply_markup=kb_size())
        return

    if mode == "order_size_manual":
        d["size"] = text
        set_state(uid, "order_color", d)
        ui_show(chat_id, "Шаг 4/9: Выберите <b>цвет</b>:", reply_markup=kb_color())
        return

    if mode == "order_color_manual":
        d["color"] = text
        set_state(uid, "order_qty", d)
        ui_show(chat_id, "Шаг 5/9: Выберите <b>количество</b>:", reply_markup=kb_qty())
        return

    if mode == "order_qty_manual":
        d["qty"] = text
        set_state(uid, "order_budget", d)
        ui_show(chat_id, "Шаг 6/9: Укажите <b>бюджет</b> (пример: 1200 MDL / $60):", reply_markup=kb_cancel())
        return

    if mode == "order_budget":
        d["budget"] = text
        set_state(uid, "order_city", d)
        ui_show(chat_id, "Шаг 7/9: <b>Город/доставка</b> (пример: Кишинёв / самовывоз):", reply_markup=kb_cancel())
        return

    if mode == "order_city":
        d["city"] = text
        set_state(uid, "order_contact", d)
        ui_show(chat_id, "Шаг 8/9: <b>Контакт</b>. Выберите вариант:", reply_markup=kb_contact(message.from_user))
        return

    if mode == "order_contact_manual":
        d["contact"] = text
        set_state(uid, "order_note", d)
        ui_show(chat_id, "Шаг 9/9: Комментарий (необязательно). Напишите детали или отправьте «-».", reply_markup=kb_cancel())
        return

    if mode == "order_note":
        d["note"] = "" if text == "-" else text
        set_state(uid, "order_photo", d)
        ui_show(chat_id, "Фото (по желанию): отправьте фото/скрин модели, или нажмите «Пропустить фото».", reply_markup=kb_photo())
        return

    # REPLY MENU BUTTONS
    if text == "🆘 Помощь":
        return section_help(chat_id, uid)
    if text == "📝 Отзыв":
        return section_review(chat_id, uid)
    if text == "📦 Инд. заказ":
        return start_order(chat_id, message.from_user)
    if text == "👑 Админка":
        return section_admin(chat_id, uid)

    return send_home(chat_id, uid)

# =========================
# PHOTO HANDLER (review + order photo step)
# =========================
@bot.message_handler(content_types=["photo"])
def photo_router(message):
    antiflood(message.from_user.id)
    uid = message.from_user.id
    chat_id = message.chat.id
    caption = (message.caption or "").strip()
    file_id = message.photo[-1].file_id

    delete_user_message(message)

    st = get_state(uid)
    mode = st["mode"]
    d = st["data"]

    if mode == "review_wait":
        reviews = ensure_list_schema(load_json(PATH_REVIEWS, []))
        entry = {
            "ts": now_iso(),
            "type": "photo",
            "user_id": uid,
            "username": message.from_user.username,
            "file_id": file_id,
            "caption": caption
        }
        reviews.append(entry)
        save_json(PATH_REVIEWS, reviews)

        forward_review_to_channel(entry)

        clear_state(uid)
        ui_show(chat_id, "✅ Спасибо! Отзыв (фото) сохранён.", reply_markup=kb_back_main())
        return

    if mode == "order_photo":
        d["photo_file_id"] = file_id
        set_state(uid, "order_confirm", d)
        ui_show(chat_id, order_preview(message.from_user, d), reply_markup=kb_confirm())
        return

    ui_show(chat_id, "Чтобы прикрепить фото к заявке — зайдите в «📦 Инд. заказ».", reply_markup=kb_back_main())

# =========================
# START POLLING
# =========================
bot.remove_webhook()
time.sleep(1)
print("BOT:", bot.get_me().username)
bot.infinity_polling(skip_pending=True)
