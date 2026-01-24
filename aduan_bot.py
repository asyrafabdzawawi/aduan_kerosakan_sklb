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
SHEET_ID = "PASTE_SHEET_ID_ADUAN_DI_SINI"
FIREBASE_BUCKET = "relief-31bc6.firebasestorage.app"   # guna bucket sama


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
# /start
# ==================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    reply_keyboard = [[KeyboardButton("🛠️ Buat Aduan Kerosakan")]]
    reply_markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True, one_time_keyboard=False)

    await update.message.reply_text(
        "🤖 *Sistem Aduan Kerosakan Sekolah*\n\nTekan butang di bawah untuk membuat aduan.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


# ==================================================
# MULAKAN ADUAN
# ==================================================
async def buat_aduan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(k, callback_data=f"kategori|{k}")] for k in KATEGORI_LIST]

    await update.message.reply_text(
        "🛠️ Pilih kategori kerosakan:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==================================================
# CALLBACK FLOW
# ==================================================
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    key, *rest = query.data.split("|")
    value = rest[0] if rest else None

    if key == "kategori":
        context.user_data["kategori"] = value
        await query.edit_message_text("📍 Sila taip lokasi kerosakan (contoh: Kelas 5 Amanah, Makmal Komputer):")

        context.user_data["step"] = "lokasi"

# ==================================================
# TEXT HANDLER (LOKASI & KETERANGAN)
# ==================================================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step")

    if step == "lokasi":
        context.user_data["lokasi"] = update.message.text
        context.user_data["step"] = "keterangan"

        await update.message.reply_text("📝 Sila terangkan masalah / kerosakan:")

    elif step == "keterangan":
        context.user_data["keterangan"] = update.message.text
        context.user_data["step"] = "gambar"

        await update.message.reply_text("📸 Sila hantar **1 gambar** kerosakan (wajib).", parse_mode="Markdown")


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

        # TIMESTAMP
        now = datetime.now()
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
            "Baru"
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
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^🛠️ Buat Aduan Kerosakan$"), buat_aduan))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.PHOTO, gambar))

    print("🤖 Bot Aduan Kerosakan sedang berjalan...")
    app.run_polling()


if __name__ == "__main__":
    main()
