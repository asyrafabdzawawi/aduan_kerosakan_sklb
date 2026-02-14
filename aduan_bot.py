import pytz
import os
import json
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
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
# ADMIN LIST
# ==================================================
ADMIN_IDS = [
    522707506,
    3998287,
    5114021646,
    14518619,
    53256464,
    8214543588
]


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
# PAPAR MENU UTAMA
# ==================================================
async def papar_menu(update, context):

    user_id = update.effective_user.id

    reply_keyboard = [
        ["🛠️ Buat Aduan Kerosakan"],
        ["📋 Semak Status Aduan"]
    ]

    if user_id in ADMIN_IDS:
        reply_keyboard.append(["📊 Semak Rekod Aduan"])

    reply_markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "🤖 *Sistem Aduan Kerosakan SK Labu Besar*\n\n"
        "Sila pilih menu di bawah:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


# ==================================================
# START
# ==================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await papar_menu(update, context)


# ==================================================
# BUAT ADUAN
# ==================================================
async def buat_aduan_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [[InlineKeyboardButton(k, callback_data=f"kategori|{k}")] for k in KATEGORI_LIST]

    await update.message.reply_text(
        "🛠️ Pilih kategori kerosakan:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==================================================
# SEMAK STATUS
# ==================================================
async def semak_status_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data.clear()
    context.user_data["step"] = "semak_id"

    await update.message.reply_text(
        "📋 Sila masukkan ID Aduan anda\n\nContoh: A0023"
    )


# ==================================================
# ADMIN – SEMAK REKOD
# ==================================================
async def semak_rekod_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Anda tidak dibenarkan akses menu ini.")
        return

    sheet_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"

    keyboard = [
        [InlineKeyboardButton("📊 Buka Google Sheet", url=sheet_url)]
    ]

    await update.message.reply_text(
        "📊 *Rekod Aduan Kerosakan*\n\nKlik butang di bawah:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


# ==================================================
# CALLBACK FLOW
# ==================================================
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    key, value = query.data.split("|")

    if key == "kategori":
        context.user_data["kategori"] = value
        context.user_data["step"] = "lokasi"

        await query.edit_message_text(
            "📍 Sila taip lokasi kerosakan (contoh: Kelas 5 Amber, Makmal Komputer):"
        )


# ==================================================
# TEXT FLOW
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
        await update.message.reply_text(
            "📸 Sila hantar **1 gambar** kerosakan (wajib).",
            parse_mode="Markdown"
        )

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
                    f"📌 Status : *{row[11]}*",
                    parse_mode="Markdown"
                )
                break

        if not jumpa:
            await update.message.reply_text(
                "❌ ID Aduan tidak dijumpai.\nPastikan ID betul."
            )

        context.user_data.clear()


# ==================================================
# IMAGE HANDLER
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

        image_url = blob.generate_signed_url(
            version="v4",
            expiration=60*60*24*7,
            method="GET"
        )

        os.remove(filename)

        tz = pytz.timezone("Asia/Kuala_Lumpur")
        now = datetime.now(tz)

        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        tarikh = now.strftime("%d/%m/%Y")
        masa = now.strftime("%I:%M %p")

        records = sheet.get_all_values()
        total = len(records)

        id_aduan = f"A{str(total).zfill(4)}"

        insert_index = 2

        # Formula dinamik ikut row semasa
        image_formula = '=IMAGE(INDIRECT("K"&ROW()))'

        sheet.insert_row(
            [
                id_aduan,
                timestamp,
                tarikh,
                masa,
                user.full_name,
                user.id,
                context.user_data.get("kategori"),
                context.user_data.get("lokasi"),
                context.user_data.get("keterangan"),
                '=IMAGE(INDIRECT("K"&ROW()))',
                image_url,
                "Dalam proses"
            ],
            index=insert_index,
            value_input_option="USER_ENTERED"
        )


        context.user_data.clear()

        await update.message.reply_text(
            f"✅ Aduan berjaya direkod\n\n"
            f"🆔 ID Aduan : {id_aduan}\n"
            f"📅 Tarikh   : {tarikh}\n"
            f"⏰ Masa     : {masa}"
        )

    except Exception as e:
        print("SYSTEM ERROR:", e)
        await update.message.reply_text("⚠️ Ralat sistem berlaku.")


# ==================================================
# RUN BOT
# ==================================================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^🛠️ Buat Aduan Kerosakan$"), buat_aduan_text))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^📋 Semak Status Aduan$"), semak_status_text))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^📊 Semak Rekod Aduan$"), semak_rekod_admin))

    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.PHOTO, gambar))

    print("🤖 Bot Aduan Kerosakan sedang berjalan...")
    app.run_polling()


if __name__ == "__main__":
    main()
