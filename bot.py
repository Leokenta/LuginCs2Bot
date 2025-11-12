import os
import sqlite3
import random
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ChatMemberHandler,
)
import nest_asyncio
from dotenv import load_dotenv

# --- VERIFICAÇÃO DE ADMIN ---
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Se o ID estiver na lista de admins do .env, já passa
    if user.id in ADMIN_IDS:
        return True

    # Caso contrário, verifica se é admin real do grupo
    try:
        chat = update.effective_chat
        member = await chat.get_member(user.id)
        if member.status in ["administrator", "creator"]:
            return True
    except Exception:
        pass

    return False
# --- CONFIGURAÇÃO ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))
DB_PATH = os.getenv("DB_PATH", "./sorteio.db")

# --- LOGGING ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# --- BANCO DE DADOS ---
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS sorteio (
    premio TEXT,
    status TEXT,
    participantes TEXT
)
""")
conn.commit()

def get_sorteio():
    cursor.execute("SELECT premio, status, participantes FROM sorteio")
    row = cursor.fetchone()
    if not row:
        cursor.execute(
            "INSERT INTO sorteio (premio, status, participantes) VALUES (?, ?, ?)",
            ("Nenhum definido", "inativo", ""),
        )
        conn.commit()
        return {"premio": "Nenhum definido", "status": "inativo", "participantes": []}
    premio, status, participantes = row
    participantes = participantes.split(",") if participantes else []
    return {"premio": premio, "status": status, "participantes": participantes}

def update_sorteio(premio=None, status=None, participantes=None):
    sorteio = get_sorteio()
    premio = premio if premio is not None else sorteio["premio"]
    status = status if status is not None else sorteio["status"]
    participantes = ",".join(participantes) if participantes is not None else ",".join(sorteio["participantes"])
    cursor.execute(
        "UPDATE sorteio SET premio=?, status=?, participantes=?",
        (premio, status, participantes)
    )
    conn.commit()

# --- HELP ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.delete()
    except:
        pass

    if not await is_admin(update, context):
        return

    text = (
        "📘 <b>Comandos disponíveis (Somente Administradores)</b>\n\n"
        "🆘 <b>/help</b> — Mostra esta lista de comandos e suas funções.\n"
        "📊 <b>/status</b> — Exibe o status atual do sorteio, incluindo número de participantes.\n"
        "🎁 <b>/setpremio &lt;nome do prêmio&gt;</b> — Inicia um novo sorteio com o prêmio informado.\n"
        "⏹️ <b>/parar</b> — Encerra o sorteio atual, impedindo novas participações.\n"
        "🎯 <b>/sorteiar</b> — Sorteia aleatoriamente um vencedor entre os participantes.\n"
        "🔁 <b>/proximoganhador</b> — Realiza um novo sorteio entre os mesmos participantes, "
        "caso o vencedor anterior não tenha respondido dentro do prazo.\n\n"
        "💡 <i>Os membros do grupo só conseguem ver e participar dos sorteios, "
        "mas não conseguem usar comandos administrativos.</i>"
    )

    await update.effective_chat.send_message(text, parse_mode="HTML")

# --- STATUS ---
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.delete()
    except:
        pass

    if not await is_admin(update, context):
        return

    sorteio = get_sorteio()
    participantes = len(sorteio["participantes"])
    text = (
        f"🎮 Sorteio {'ativo' if sorteio['status']=='ativo' else 'inativo'}\n"
        f"🏆 Prêmio: {sorteio['premio']}\n"
        f"👥 Participantes: {participantes}"
    )
    await update.effective_chat.send_message(text)

# --- SETPREMIO ---
async def setpremio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.delete()
    except:
        pass

    if not await is_admin(update, context):
        return

    if not context.args:
        await update.effective_chat.send_message("Uso: /setpremio <nome do prêmio>")
        return

    premio = " ".join(context.args)
    update_sorteio(premio=premio, status="ativo", participantes=[])
    await send_sorteio_message(update)

# --- PARAR ---
async def parar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.delete()
    except:
        pass

    if not await is_admin(update, context):
        return

    update_sorteio(status="inativo")
    await update.effective_chat.send_message("Sorteio encerrado.")

# --- SORTEIAR ---
async def sortear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.delete()
    except:
        pass

    if not await is_admin(update, context):
        return

    sorteio = get_sorteio()
    participantes = sorteio["participantes"]

    if not participantes:
        await update.effective_chat.send_message("❌ Não há participantes para sortear.")
        return

    vencedor_id = random.choice(participantes)
    total = len(participantes)

    text = (
        f"🏆 <b>Resultado do Sorteio!</b>\n\n"
        f"🎁 Prêmio: <b>{sorteio['premio']}</b>\n"
        f"👑 Vencedor: @{vencedor_id}\n"
        f"👥 Participantes: <b>{total}</b>\n\n"
        f"⏰ @{vencedor_id}, você tem <b>24 horas</b> para responder.\n"
        f"Caso contrário, o sorteio será realizado novamente! 🔁"
    )

    update_sorteio(status="inativo", participantes=participantes)
    await update.effective_chat.send_message(text, parse_mode="HTML")

# --- PROXIMO GANHADOR ---
async def proximoganhador_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.delete()
    except:
        pass

    if not await is_admin(update, context):
        return

    sorteio = get_sorteio()
    participantes = sorteio["participantes"]

    if not participantes:
        await update.effective_chat.send_message("❌ Não há participantes para sortear novamente.")
        return

    vencedor_id = random.choice(participantes)
    total = len(participantes)

    text = (
        f"🔁 <b>Novo Sorteio Realizado!</b>\n\n"
        f"🎁 Prêmio: <b>{sorteio['premio']}</b>\n"
        f"👑 Novo vencedor: @{vencedor_id}\n"
        f"👥 Participantes: <b>{total}</b>\n\n"
        f"⏰ @{vencedor_id}, você tem <b>24 horas</b> para responder.\n"
        f"Caso contrário, o sorteio será realizado novamente! 🔁"
    )

    update_sorteio(status="inativo", participantes=participantes)
    await update.effective_chat.send_message(text, parse_mode="HTML")

# --- PARTICIPAR ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sorteio = get_sorteio()
    if sorteio["status"] != "ativo":
        return

    user = query.from_user
    user_str = user.username if user.username else str(user.id)
    if user_str not in sorteio["participantes"]:
        sorteio["participantes"].append(user_str)
        update_sorteio(participantes=sorteio["participantes"])
        await update_sorteio_message(context)

# --- MENSAGEM DO SORTEIO ---
sorteio_message_id = None
sorteio_chat_id = None

async def send_sorteio_message(update: Update):
    global sorteio_message_id, sorteio_chat_id
    sorteio = get_sorteio()
    participantes = len(sorteio["participantes"])
    text = (
        f"🎉 <b>SORTEIO INICIADO!</b> 🎉\n\n"
        f"🏆 <b>Prêmio:</b> <code>{sorteio['premio']}</code>\n"
        f"👥 <b>Participantes:</b> <code>{participantes}</code>\n\n"
        f"🔹 Clique no botão abaixo para participar!\n"
        f"⏳ Enquanto o sorteio estiver ativo, você pode entrar a qualquer momento."
    )

    keyboard = [
        [
            InlineKeyboardButton("🎟️ Participar do Sorteio", callback_data="participar"),
        ]
    ]

    msg = await update.effective_chat.send_message(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    sorteio_message_id = msg.message_id
    sorteio_chat_id = msg.chat_id

async def update_sorteio_message(context: ContextTypes.DEFAULT_TYPE):
    global sorteio_message_id, sorteio_chat_id
    if sorteio_message_id and sorteio_chat_id:
        sorteio = get_sorteio()
        participantes = len(sorteio["participantes"])
        text = (
            f"🎮 <b>SORTEIO ATIVO!</b>\n\n"
            f"🏆 <b>Prêmio:</b> <code>{sorteio['premio']}</code>\n"
            f"👥 <b>Participantes:</b> <code>{participantes}</code>\n\n"
            f"🔹 Clique em <b>“🎟️ Participar do Sorteio”</b> para entrar!"
        )
        keyboard = [
            [
                InlineKeyboardButton("🎟️ Participar do Sorteio", callback_data="participar"),
            ]
        ]
        try:
            await context.bot.edit_message_text(
                chat_id=sorteio_chat_id,
                message_id=sorteio_message_id,
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
        except:
            pass

# --- QUANDO ALGUÉM ENTRA NO GRUPO ---
async def member_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.chat_member.chat
    try:
        await context.bot.set_chat_permissions(
            chat_id=chat.id,
            permissions=ChatPermissions(can_send_messages=True)
        )
        await context.bot.set_chat_history_visibility(chat_id=chat.id, visibility="visible")
    except Exception as e:
        logging.warning(f"Erro ao ajustar visibilidade: {e}")

# --- INICIAR BOT ---
def main():
    nest_asyncio.apply()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("setpremio", setpremio_command))
    app.add_handler(CommandHandler("parar", parar_command))
    app.add_handler(CommandHandler("sorteiar", sortear_command))
    app.add_handler(CommandHandler("proximoganhador", proximoganhador_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(ChatMemberHandler(member_join, ChatMemberHandler.CHAT_MEMBER))

    app.run_polling()

if __name__ == "__main__":
    main()
