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

# PDF IMPORT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import TableStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart


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
# PILIH BULAN UNTUK LAPORAN
# ==================================================
async def pilih_bulan_laporan(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Tidak dibenarkan.")
        return

    context.user_data["step"] = "pilih_bulan"

    await update.message.reply_text(
        "📅 Masukkan bulan laporan dalam format:\n\nMM/YYYY\n\nContoh: 02/2026"
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
        await update.message.reply_text("📸 Sila hantar **1 gambar** kerosakan (wajib).", parse_mode="Markdown")

    elif step == "semak_id":
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
# JANA PDF LAPORAN
# ==================================================
async def jana_laporan_pdf(update, bulan_pilih):

    records = sheet.get_all_values()
    data_bulan = []

    for row in records[1:]:
        if bulan_pilih in row[2]:
            data_bulan.append(row)

    jumlah = len(data_bulan)

    kategori_count = {}
    for row in data_bulan:
        kategori = row[6]
        kategori_count[kategori] = kategori_count.get(kategori, 0) + 1

    filename = f"Laporan_{bulan_pilih.replace('/','_')}.pdf"
    doc = SimpleDocTemplate(filename, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("<b>LAPORAN ADUAN KEROSAKAN</b>", styles["Title"]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Bulan: {bulan_pilih}", styles["Normal"]))
    elements.append(Paragraph(f"Jumlah Aduan: {jumlah}", styles["Normal"]))
    elements.append(Spacer(1, 20))

    # Carta
    drawing = Drawing(400, 200)
    chart = VerticalBarChart()
    chart.x = 50
    chart.y = 50
    chart.height = 125
    chart.width = 300
    chart.data = [list(kategori_count.values())]
    chart.categoryAxis.categoryNames = list(kategori_count.keys())
    drawing.add(chart)
    elements.append(drawing)
    elements.append(Spacer(1, 20))

    # Senarai Aduan
    table_data = [["ID", "Tarikh", "Kategori", "Lokasi", "Status"]]
    for row in data_bulan:
        table_data.append([row[0], row[2], row[6], row[7], row[11]])

    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("GRID", (0,0), (-1,-1), 1, colors.grey),
        ("FONTSIZE", (0,0), (-1,-1), 8)
    ]))

    elements.append(table)
    doc.build(elements)

    await update.message.reply_document(document=open(filename, "rb"))
    os.remove(filename)


# ==================================================
# IMAGE HANDLER (KEKAL ASAL)
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

        tz = pytz.timezone("Asia/Kuala_Lumpur")
        now = datetime.now(tz)

        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        tarikh = now.strftime("%d/%m/%Y")
        masa = now.strftime("%I:%M %p")

        records = sheet.get_all_values()
        total = len(records)
        id_aduan = f"A{str(total).zfill(4)}"

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
            index=2,
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
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^📄 Laporan Bulanan PDF$"), pilih_bulan_laporan))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.PHOTO, gambar))

    print("🤖 Bot Aduan Kerosakan sedang berjalan...")
    app.run_polling()


if __name__ == "__main__":
    main()
