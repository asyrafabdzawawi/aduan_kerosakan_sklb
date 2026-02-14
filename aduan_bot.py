import pytz
import os
import json
from io import BytesIO
from datetime import datetime
from urllib.parse import urlparse, unquote
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from PIL import Image as PILImage

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

import firebase_admin
from firebase_admin import credentials, storage

import gspread
from google.oauth2.service_account import Credentials

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4


# ==================================================
# CONFIG
# ==================================================
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
SHEET_ID = "1j9ZKSju8r-tcRitKKCAY-RGKH4jUeczgsVpecEJwgvI"
FIREBASE_BUCKET = "relief-31bc6.firebasestorage.app"


# ==================================================
# ADMIN
# ==================================================
ADMIN_IDS = [522707506,3998287,5114021646,14518619,53256464,8214543588]


# ==================================================
# FIREBASE
# ==================================================
firebase_creds = credentials.Certificate(
    json.loads(os.environ["FIREBASE_SERVICE_ACCOUNT_JSON"])
)

firebase_admin.initialize_app(firebase_creds, {
    "storageBucket": FIREBASE_BUCKET
})

bucket = storage.bucket()


# ==================================================
# GOOGLE SHEET
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
# MENU
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await papar_menu(update, context)


# ==================================================
# BUAT ADUAN
# ==================================================
async def buat_aduan_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = [[InlineKeyboardButton(k, callback_data=f"kategori|{k}")]
                for k in KATEGORI_LIST]

    await update.message.reply_text(
        "🛠️ Pilih kategori kerosakan:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def kategori_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    kategori = query.data.split("|")[1]
    context.user_data["kategori"] = kategori
    context.user_data["step"] = "lokasi"

    await query.message.reply_text(
        f"📍 Kategori dipilih: {kategori}\n\nSila masukkan lokasi kerosakan:"
    )


# ==================================================
# SEMAK REKOD
# ==================================================
async def semak_rekod(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Tidak dibenarkan.")
        return

    records = sheet.get_all_values()

    if len(records) <= 1:
        await update.message.reply_text("Tiada rekod aduan.")
        return

    text = "📊 *Rekod Aduan Terkini*\n\n"

    for row in records[1:6]:
        text += (
            f"🆔 {row[0]}\n"
            f"📅 {row[2]} | 🛠️ {row[6]}\n"
            f"📌 {row[11]}\n\n"
        )

    await update.message.reply_text(text, parse_mode="Markdown")


# ==================================================
# SEMAK STATUS
# ==================================================
async def semak_status_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["step"] = "semak_id"

    await update.message.reply_text("📋 Sila masukkan ID Aduan anda\n\nContoh: A0023")


# ==================================================
# PILIH BULAN PDF
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

    if step == "lokasi":
        context.user_data["lokasi"] = update.message.text
        context.user_data["step"] = "keterangan"
        await update.message.reply_text("📝 Sila terangkan masalah / kerosakan:")

    elif step == "keterangan":
        context.user_data["keterangan"] = update.message.text
        context.user_data["step"] = "gambar"
        await update.message.reply_text("📸 Sila hantar 1 gambar kerosakan (wajib).")

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
# JANA PDF (2 COLUMN VERSION)
# ==================================================
async def jana_laporan_pdf(update, bulan_pilih):

    records = sheet.get_all_values()
    data_bulan = []

    for row in records[1:]:
        try:
            tarikh_obj = datetime.strptime(row[2].strip(), "%d/%m/%Y")
            bulan_format = tarikh_obj.strftime("%m/%Y")
            if bulan_format == bulan_pilih:
                data_bulan.append(row)
        except:
            continue

    filename_pdf = f"Laporan_{bulan_pilih.replace('/','_')}.pdf"

    doc = SimpleDocTemplate(filename_pdf, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("<b>LAPORAN ADUAN KEROSAKAN SK LABU BESAR</b>", styles["Title"]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Bulan: {bulan_pilih}", styles["Normal"]))
    elements.append(Paragraph(f"Jumlah Aduan: {len(data_bulan)}", styles["Normal"]))
    elements.append(Spacer(1, 20))

    for row in data_bulan:

        text_content = []
        text_content.append(Paragraph("<b>MAKLUMAT ADUAN</b>", styles["Heading3"]))
        text_content.append(Spacer(1, 6))
        text_content.append(Paragraph(f"ID Aduan : {row[0]}", styles["Normal"]))
        text_content.append(Paragraph(f"Tarikh   : {row[2]}", styles["Normal"]))
        text_content.append(Paragraph(f"Kategori : {row[6]}", styles["Normal"]))
        text_content.append(Paragraph(f"Lokasi   : {row[7]}", styles["Normal"]))
        text_content.append(Paragraph(f"Keterangan : {row[8]}", styles["Normal"]))

        img_element = Paragraph("Tiada gambar", styles["Normal"])

        try:
            image_url = row[10]
            parsed = urlparse(image_url)
            clean_path = unquote(parsed.path).lstrip("/")
            clean_path = clean_path.replace("relief-31bc6.firebasestorage.app/", "")
            blob = bucket.blob(clean_path)
            image_bytes = blob.download_as_bytes()

            pil_img = PILImage.open(BytesIO(image_bytes))
            img_width, img_height = pil_img.size

            max_width = 3 * inch
            max_height = 4 * inch

            ratio = min(max_width / img_width, max_height / img_height)
            new_width = img_width * ratio
            new_height = img_height * ratio

            img_element = Image(BytesIO(image_bytes), width=new_width, height=new_height)
            img_element.hAlign = 'LEFT'

        except:
            pass

        table_data = [[text_content, img_element]]

        table = Table(table_data, colWidths=[3.8 * inch, 2.2 * inch])

        table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))

        elements.append(table)
        elements.append(Spacer(1, 20))

    doc.build(
        elements,
        onFirstPage=add_footer,
        onLaterPages=add_footer
    )

    await update.message.reply_document(document=open(filename_pdf, "rb"))
    os.remove(filename_pdf)

# ==================================================
# GAMBAR
# ==================================================
async def gambar(update: Update, context: ContextTypes.DEFAULT_TYPE):

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
            id_aduan, timestamp, tarikh, masa,
            user.full_name, user.id,
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

# ==================================================
# RUN BOT
# ==================================================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(MessageHandler(filters.Regex("^🛠️ Buat Aduan Kerosakan$"), buat_aduan_text))
    app.add_handler(MessageHandler(filters.Regex("^📋 Semak Status Aduan$"), semak_status_text))
    app.add_handler(MessageHandler(filters.Regex("^📊 Semak Rekod Aduan$"), semak_rekod))
    app.add_handler(MessageHandler(filters.Regex("^📄 Laporan Bulanan PDF$"), pilih_bulan_laporan))

    app.add_handler(CallbackQueryHandler(kategori_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.PHOTO, gambar))

    print("🤖 Bot Aduan Kerosakan sedang berjalan...", flush=True)
    app.run_polling()



if __name__ == "__main__":
    main()
