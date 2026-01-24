import pytz
import os
import json
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

import firebase_admin
from firebase_admin import credentials, storage

import gspread
from google.oauth2.service_account import Credentials


# ==================================================
# CONFIG
# ==================================================
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
SHEET_ID = "1j9ZKSju8r-tcRitKKCAY-RGKH4jUeczgsVpecEJwgvI"
FIREBASE_BUCKET = "relief-31bc6.firebasestorage.app"


# ==================================================
# FIREBASE INIT
# ==================================================
firebase_creds = credentials.Certificate(
    json.loads(os.environ["FIREBASE_SERVICE_ACCOUNT_JSON"])
)
firebase_admin.initialize_app(firebase_creds, {"storageBucket": FIREBASE_BUCKET})
bucket = storage.bucket()


# ==================================================
# GOOGLE SHEET INIT
# ==================================================
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
sheet_creds = Credentials.from_service_account_info(
    json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]), scopes=SCOPES
)
gc = gspread.authorize(sheet_creds)
sheet = gc.open_by_key(SHEET_ID).sheet1


# ==================================================
# DATA
# ==================================================
KATEGORI_LIST = ["Elektrik", "ICT", "Paip", "Perabot", "Bangunan", "Lain-lain"]


# ==================================================
# PAPAR MENU UTAMA (INLINE)
# ==================================================
async def papar_menu(update, context):
    keyboard = [
        [InlineKeyboardButton("🛠️ Buat Aduan Kerosakan", callback_data="menu|aduan")],
        [InlineKeyboardButton("📋 Semak Status Aduan", callback_data="menu|status")]
    ]

    reply_keyboard = [[KeyboardButton("🏠 Menu Utama")]]
    reply_markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "🤖 *Sistem Aduan Kerosakan SK Labu Besar*\n\n"
        "Sila pilih menu di bawah:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


# ==================================================
# /start
# ==================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await papar_menu(update, context)


# ==================================================
# MENU UTAMA (BUTANG BAWAH TYPING)
# ==================================================
async def menu_utama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await papar_menu(update, context)


# ==================================================
# MULAKAN ADUAN
# ==================================================
async def buat_aduan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(k, callback_data=f"kategori|{k}")] for k in KATEGORI_LIST]

    await update.callback_query.edit_message_text(
        "🛠️ Pilih kategori kerosakan:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==================================================
# MULA SEMAK STATUS
# ==================================================
async def semak_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["step"] = "semak_id"

    await update.callback_query.edit_message_text(
        "📋 Sila masukkan ID Aduan anda\n\nContoh: A0023"
    )


# ==================================================
# CALLBACK FLOW
# ==================================================
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    key, *rest = query.data.split("|")
    value = rest[0] if rest else None

    # ---- MENU UTAMA INLINE ----
    if key == "menu":
        if value == "aduan":
            await buat_aduan(update, context)
        elif value == "status":
            await semak_status(update, context)

    # ---- FLOW ADUAN ASAL ----
    elif key == "kategori":
        context.user_data["kategori"] = value
        await query.edit_message_text(
            "📍 Sila taip lokasi kerosakan (contoh: Kelas 5 Amanah, Makmal Komputer):"
        )
        context.user_data["step"] = "lokasi"


# ==================================================
# TEXT HANDLER (LOKASI, KETERANGAN & SEMAK STATUS)
# ==================================================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step")

    # ---------- FLOW ADUAN (ASAL - TAK DIUBAH) ----------
    if step == "lokasi":
        context.user_data["lokasi"] = update.message.text
        context.user_data["step"] = "keterangan"

        await update.message.reply_text("📝 Sila terangkan masalah / kerosakan:")

    elif step == "keterangan":
        context.user_data["keterangan"] = update.message.text
        context.user_data["step"] = "gambar"

        await update.message.reply_text(
            "📸 Sila hantar **1 gambar** kerosakan (wajib).",
            parse_mode="Markdown"
        )

    # ---------- FLOW SEMAK STATUS ----------
    elif step == "semak_id":
        id_cari = update.message.text.strip().upper()

        records = sheet.get_all_values()
        jumpa = False

        for row in records[1:]:
            if row[0] == id_cari:
                jumpa = True

                await update.message.reply_text(
                    f"📋 *Status Aduan*\n\n"
                    f"🆔 ID Aduan : {row[0]}\n"
                    f"📅 Tarikh  : {row[2]}\n"
                    f"⏰ Masa    : {row[3]}\n"
                    f"🛠️ Kategori: {row[6]}\n"
                    f"📍 Lokasi : {row[7]}\n"
                    f"📌 Status : *{row[10]}*",
                    parse_mode="Markdown"
                )
                break

        if not jumpa:
            await update.message.reply_text(
                "❌ ID Aduan tidak dijumpai.\n\nPastikan ID betul, contoh: A0023"
            )

        context.user_data.clear()


# ==================================================
# IMAGE HANDLER (WAJIB GAMBAR)
# ==================================================
async def gambar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if context.user_data.get("step") != "gambar":
            return

        user = update.effective_user
        photo = update.message.photo[-1]
        file = await photo.get_file()

        filename = f"{user.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        await file.download_to_drive(filename)

        blob = bucket.blob(f"aduan/{filename}")
        blob.upload_from_filename(filename, content_type="image/jpeg")

        image_url = blob.generate_signed_url(version="v4", expiration=60*60*24*7, method="GET")
        os.remove(filename)

        # TIMESTAMP (MALAYSIA)
        tz = pytz.timezone("Asia/Kuala_Lumpur")
        now = datetime.now(tz)

        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        tarikh = now.strftime("%d/%m/%Y")
        masa = now.strftime("%I:%M %p")

        # AUTO ID ADUAN
        total = len(sheet.get_all_values())
        id_aduan = f"A{str(total).zfill(4)}"

        # SIMPAN KE GOOGLE SHEET
        last_row = total + 1
        sheet.update(f"A{last_row}:K{last_row}", [[
            id_aduan,
            timestamp,
            tarikh,
            masa,
            user.full_name,
            user.id,
            context.user_data.get("kategori"),
            context.user_data.get("lokasi"),
            context.user_data.get("keterangan"),
            image_url,
            "Menunggu tindakan pentadbir."
        ]])

        context.user_data.clear()

        await update.message.reply_text(
            f"✅ Aduan berjaya direkod\n\n"
            f"🆔 ID Aduan : {id_aduan}\n"
            f"📅 Tarikh   : {tarikh}\n"
            f"⏰ Masa     : {masa}\n\n"
            f"Terima kasih atas makluman anda 🙏"
        )

    except Exception as e:
        print("SYSTEM ERROR:", e)
        await update.message.reply_text(
            "⚠️ Aduan diterima tetapi berlaku ralat sistem.\nSila maklumkan pentadbir."
        )


# ==================================================
# RUN BOT
# ==================================================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^🏠 Menu Utama$"), menu_utama))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.PHOTO, gambar))

    print("🤖 Bot Aduan Kerosakan sedang berjalan...")
    app.run_polling()


if __name__ == "__main__":
    main()
