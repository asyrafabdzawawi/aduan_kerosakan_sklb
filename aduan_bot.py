import pytz
import os
import json
from io import BytesIO
from datetime import datetime
from urllib.parse import urlparse, unquote

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

import firebase_admin
from firebase_admin import credentials, storage

import gspread
from google.oauth2.service_account import Credentials

# PDF IMPORT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4


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

firebase_admin.initialize_app(firebase_creds, {
    "storageBucket": FIREBASE_BUCKET
})

bucket = storage.bucket()


# ==================================================
# GOOGLE SHEET INIT
# ==================================================
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

sheet_creds = Credentials.from_service_account_info(
    json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]),
    scopes=SCOPES
)

gc = gspread.authorize(sheet_creds)
sheet = gc.open_by_key(SHEET_ID).sheet1


# ==================================================
# DATA
# ==================================================
KATEGORI_LIST = ["Elektrik", "ICT", "Paip", "Perabot", "Bangunan", "Lain-lain"]


# ==================================================
# PAPAR MENU
# ==================================================
async def papar_menu(update, context):

    user_id = update.effective_user.id

    reply_keyboard = [
        ["🛠️ Buat Aduan Kerosakan"],
        ["📋 Semak Status Aduan"]
    ]

    if user_id in ADMIN_IDS:
        reply_keyboard.append(["📊 Semak Rekod Aduan"])
        reply_keyboard.append(["📄 Laporan Bulanan PDF"])

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
# SEMAK STATUS
# ==================================================
async def semak_status_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["step"] = "semak_id"
    await update.message.reply_text("📋 Sila masukkan ID Aduan anda\n\nContoh: A0023")


# ==================================================
# PILIH BULAN LAPORAN
# ==================================================
async def pilih_bulan_laporan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Tidak dibenarkan.")
        return

    context.user_data["step"] = "pilih_bulan"

    await update.message.reply_text(
        "📅 Masukkan bulan laporan dalam format:\n\nMM/YYYY\nContoh: 02/2026"
    )


# ==================================================
# TEXT FLOW
# ==================================================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    step = context.user_data.get("step")

    if step == "semak_id":
        id_cari = update.message.text.strip().upper()
        records = sheet.get_all_values()

        for row in records[1:]:
            if row[0] == id_cari:
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

        context.user_data.clear()

    elif step == "pilih_bulan":
        bulan_pilih = update.message.text.strip()
        await jana_laporan_pdf(update, bulan_pilih)
        context.user_data.clear()


# ==================================================
# JANA PDF (VERSI FINAL STABIL)
# ==================================================
async def jana_laporan_pdf(update, bulan_pilih):

    records = sheet.get_all_values()
    data_bulan = [row for row in records[1:] if bulan_pilih in row[2]]

    filename_pdf = f"Laporan_{bulan_pilih.replace('/','_')}.pdf"
    doc = SimpleDocTemplate(filename_pdf, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("<b>LAPORAN ADUAN KEROSAKAN</b>", styles["Title"]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Bulan: {bulan_pilih}", styles["Normal"]))
    elements.append(Paragraph(f"Jumlah Aduan: {len(data_bulan)}", styles["Normal"]))
    elements.append(Spacer(1, 20))

    for row in data_bulan:

        elements.append(Paragraph("<b>MAKLUMAT ADUAN</b>", styles["Heading3"]))
        elements.append(Spacer(1, 6))
        elements.append(Paragraph(f"ID Aduan : {row[0]}", styles["Normal"]))
        elements.append(Paragraph(f"Tarikh   : {row[2]}", styles["Normal"]))
        elements.append(Paragraph(f"Kategori : {row[6]}", styles["Normal"]))
        elements.append(Paragraph(f"Lokasi   : {row[7]}", styles["Normal"]))
        elements.append(Paragraph(f"Keterangan : {row[8]}", styles["Normal"]))
        elements.append(Spacer(1, 8))

        try:
            image_url = row[10]

            parsed = urlparse(image_url)
            clean_path = unquote(parsed.path).lstrip("/")
            clean_path = clean_path.replace("relief-31bc6.firebasestorage.app/", "")

            blob = bucket.blob(clean_path)
            image_bytes = blob.download_as_bytes()

            image_stream = BytesIO(image_bytes)
            img = Image(image_stream, width=180, height=120)
            elements.append(img)

        except Exception as e:
            print("ERROR GAMBAR:", e)
            elements.append(
                Paragraph("Gambar tidak dapat dipaparkan.", styles["Normal"])
            )

        elements.append(Spacer(1, 15))
        elements.append(Paragraph("--------------------------------------------------", styles["Normal"]))
        elements.append(Spacer(1, 20))

    doc.build(elements)

    await update.message.reply_document(document=open(filename_pdf, "rb"))
    os.remove(filename_pdf)


# ==================================================
# RUN BOT
# ==================================================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^📋 Semak Status Aduan$"), semak_status_text))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^📄 Laporan Bulanan PDF$"), pilih_bulan_laporan))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("🤖 Bot Aduan Kerosakan sedang berjalan...")
    app.run_polling()


if __name__ == "__main__":
    main()
