import discord
from discord.ext import commands
import os
import psycopg2
from flask import Flask
from threading import Thread
from waitress import serve

# --- 1. CONFIGURAÇÕES E VARIÁVEIS ---
TOKEN = os.getenv('DISCORD_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')

def get_env_int(name):
    value = os.getenv(name, '').strip()
    return int(value) if value.isdigit() else 0

BOT_ALVO_ID = get_env_int('BOT_ALVO_ID')
CANAL_CODIGOS_ID = get_env_int('CANAL_CODIGOS_ID')
CANAL_LOG_1_ID = get_env_int('CANAL_LOG_1_ID')
CANAL_LOG_2_ID = get_env_int('CANAL_LOG_2_ID')

# --- 2. INICIALIZAÇÃO DO BOT E FLASK ---
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
app = Flask('')

@app.route('/')
def home():
    return "Bot Online!"

# --- 3. FUNÇÃO DO BANCO DE DADOS (DEFINIÇÃO) ---
def init_db():
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        cur = conn.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS ranking 
                       (user_id TEXT PRIMARY KEY, quantidade INTEGER DEFAULT 0)''')
        conn.commit()
        cur.close()
        conn.close()
        print("Banco de dados conectado e pronto!")
    except Exception as e:
        print(f"Erro no Banco de Dados: {e}")

def update_pontos(user_id):
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
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

# --- 4. EVENTOS E COMANDOS ---
@bot.event
async def on_ready():
    print(f'Logado como {bot.user}')

@bot.event
async def on_message(message):
    if message.author.id == BOT_ALVO_ID and message.channel.id == CANAL_CODIGOS_ID:
        if message.mentions:
            ultima_pessoa = message.mentions[-1]
            novo_total = update_pontos(str(ultima_pessoa.id))
            texto = f"{novo_total} pessoa(s) usou o código de {ultima_pessoa.mention}"
            for cid in [CANAL_LOG_1_ID, CANAL_LOG_2_ID]:
                canal = bot.get_channel(cid)
                if canal: await canal.send(texto)
    await bot.process_commands(message)

@bot.command()
async def ver(ctx, user: discord.Member):
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    cur = conn.cursor()
    cur.execute("SELECT quantidade FROM ranking WHERE user_id = %s", (str(user.id),))
    res = cur.fetchone()
    cur.close()
    conn.close()
    pontos = res[0] if res else 0
    await ctx.send(f"{user.mention} tem {pontos} pontos.")

# --- 5. INICIALIZAÇÃO ---
def run_flask():
    serve(app, host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

if __name__ == "__main__":
    init_db() # Agora ela existe e pode ser chamada!
    Thread(target=run_flask, daemon=True).start()
    bot.run(TOKEN)
