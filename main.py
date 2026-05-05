import discord
from discord.ext import commands
import os
import psycopg2
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot Online!"

def run_flask():
    # O Render usa a porta 10000 por padrão ou a variável PORT
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()
# --- CONFIGURAÇÕES VIA VARIÁVEIS DE AMBIENTE (RENDER) ---
TOKEN = os.getenv('DISCORD_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL') # URL do Postgres do Render
BOT_ALVO_ID = int(os.getenv('1465393972569706609', 0))
CANAL_CODIGOS_ID = int(os.getenv('1424602887991988384', 0))
CANAL_LOG_1_ID = int(os.getenv('1485786544366424217', 0))
CANAL_LOG_2_ID = int(os.getenv('1498147503453769738', 0))

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- FUNÇÕES DO BANCO DE DATA (POSTGRESQL) ---
def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS ranking 
                   (user_id TEXT PRIMARY KEY, quantidade INTEGER DEFAULT 0)''')
    conn.commit()
    cur.close()
    conn.close()

def update_pontos(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO ranking (user_id, quantidade) VALUES (%s, 1)
        ON CONFLICT (user_id) DO UPDATE SET quantidade = ranking.quantidade + 1
        RETURNING quantidade;
    """, (user_id,))
    total = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return total

# --- EVENTOS ---
@bot.event
async def on_ready():
    init_db()
    print(f'Bot {bot.user} online e Banco de Dados conectado!')

@bot.event
async def on_message(message):
    # Ignora mensagens do próprio bot
    if message.author == bot.user:
        return

    # Lógica de leitura: canal específico + bot alvo
    if message.channel.id == CANAL_CODIGOS_ID and message.author.id == BOT_ALVO_ID:
        if message.mentions:
            ultima_pessoa = message.mentions[-1]
            novo_total = update_pontos(str(ultima_pessoa.id))
            
            texto_log = f"{novo_total} pessoa(s) usou o código de {ultima_pessoa.mention}"
            
            # Envio para os dois canais de logs
            for canal_id in [CANAL_LOG_1_ID, CANAL_LOG_2_ID]:
                canal = bot.get_channel(canal_id)
                if canal:
                    await canal.send(texto_log)

    await bot.process_commands(message)

# --- COMANDOS ---
@bot.command()
async def ver(ctx, user: discord.Member):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT quantidade FROM ranking WHERE user_id = %s", (str(user.id),))
    res = cur.fetchone()
    cur.close()
    conn.close()
    
    pontos = res[0] if res else 0
    await ctx.send(f"A pessoa {user.mention} possui {pontos} pontos registrados.")

@bot.command()
async def apagar(ctx, user: discord.Member):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM ranking WHERE user_id = %s", (str(user.id),))
    conn.commit()
    cur.close()
    conn.close()
    await ctx.send(f"Registros de {user.mention} deletados.")

bot.run(TOKEN)
