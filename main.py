import discord
from discord.ext import commands
import os
import psycopg2
from psycopg2 import pool
from flask import Flask
from threading import Thread
from waitress import serve
import re

# --- 1. CONFIGURAÇÕES E BANCO (PostgreSQL) ---
TOKEN = os.getenv('DISCORD_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
BOT_ALVO_ID = int(os.getenv('BOT_ALVO_ID', 0))
CANAL_LOGS_ID = int(os.getenv('CANAL_LOGS_ID', 0)) 

# Pool de conexões para garantir performance e estabilidade no banco
db_pool = psycopg2.pool.SimpleConnectionPool(1, 10, DATABASE_URL, sslmode='require')

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
app = Flask('')

def init_db():
    """Inicializa o banco de dados criando a tabela, se não existir."""
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute('''CREATE TABLE IF NOT EXISTS logs_uso (
                id SERIAL PRIMARY KEY,
                quem_usou_id TEXT,
                codigo TEXT,
                criador_id TEXT,
                data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            conn.commit()
    finally:
        db_pool.putconn(conn)

def registrar_uso(user_id, codigo, criador_id):
    """Insere o registro no banco de dados."""
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO logs_uso (quem_usou_id, codigo, criador_id) VALUES (%s, %s, %s)", 
                       (str(user_id), codigo, str(criador_id)))
            conn.commit()
            return True
    except Exception as e:
        print(f"Erro ao salvar: {e}")
        return False
    finally:
        db_pool.putconn(conn)

def get_ranking(dias=None):
    """Retorna o ranking com base no período (dias)."""
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            query = "SELECT criador_id, COUNT(*) FROM logs_uso "
            if dias: query += f"WHERE data >= CURRENT_DATE - INTERVAL '{dias} days' "
            query += "GROUP BY criador_id ORDER BY COUNT(*) DESC LIMIT 10"
            cur.execute(query)
            return cur.fetchall()
    finally:
        db_pool.putconn(conn)

# --- 2. LÓGICA DE IDENTIFICAÇÃO (Logs) ---
@bot.event
async def on_message(message):
    if message.author.id == BOT_ALVO_ID:
        content = message.content
        if message.embeds:
            for e in message.embeds: content += f" {e.description or ''}"
        
        # Regex para achar menções (@user) e códigos alfanuméricos
        mentions = re.findall(r'<@!?(\d+)>', content)
        codigos = re.findall(r'\b[A-Z0-9]{5,}\b', content)

        if len(mentions) >= 2 and codigos:
            if registrar_uso(mentions[0], codigos[0], mentions[-1]):
                log_ch = bot.get_channel(CANAL_LOGS_ID)
                if log_ch: await log_ch.send(f"✅ <@{mentions[0]}> usou `{codigos[0]}` (<@{mentions[-1]}>).")
    await bot.process_commands(message)

# --- 3. PAINEL E RANKING INTERATIVO ---
class RankingView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    
    async def enviar_ranking(self, interaction, titulo, dias):
        dados = get_ranking(dias)
        msg = f"🏆 **{titulo}**\n\n"
        if dados:
            for i, (uid, qtd) in enumerate(dados):
                msg += f"{i+1}º | <@{uid}> - {qtd} pts\n"
        else:
            msg += "Nenhum dado encontrado no período."
        await interaction.response.send_message(msg, ephemeral=False)

    @discord.ui.button(label="Semanal", style=discord.ButtonStyle.primary, custom_id="r1")
    async def sem(self, i: discord.Interaction, b: discord.ui.Button): await self.enviar_ranking(i, "Rank Semanal", 7)
    @discord.ui.button(label="Quinzenal", style=discord.ButtonStyle.success, custom_id="r2")
    async def qui(self, i: discord.Interaction, b: discord.ui.Button): await self.enviar_ranking(i, "Rank Quinzenal", 15)
    @discord.ui.button(label="Mensal", style=discord.ButtonStyle.danger, custom_id="r3")
    async def men(self, i: discord.Interaction, b: discord.ui.Button): await self.enviar_ranking(i, "Rank Mensal", 30)

@bot.command()
@commands.has_permissions(administrator=True)
async def painel(ctx):
    await ctx.send("📊 **Painel de Rankings**", view=RankingView())

# --- 4. EXECUÇÃO ---
@app.route('/')
def home(): return "Bot Online"

@bot.event
async def on_ready():
    init_db()
    bot.add_view(RankingView()) # Persistir botões
    print(f"Bot logado como {bot.user}")

if __name__ == "__main__":
    Thread(target=lambda: serve(app, host='0.0.0.0', port=10000), daemon=True).start()
    bot.run(TOKEN)
