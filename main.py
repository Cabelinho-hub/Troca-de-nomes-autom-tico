import discord
from discord.ext import commands
from discord import app_commands
import os
import psycopg2
from psycopg2 import pool
import re
from flask import Flask
from threading import Thread
from waitress import serve
from datetime import datetime, timedelta

# --- 1. CONFIGURAÇÕES E VARIÁVEIS ---
TOKEN = os.getenv('DISCORD_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')

def get_env_int(name):
    value = os.getenv(name, '').strip()
    return int(value) if value.isdigit() else 0

BOT_ALVO_ID = get_env_int('BOT_ALVO_ID')
CANAL_CODIGOS_ID = get_env_int('CANAL_CODIGOS_ID')
CANAL_PAINEL_ID = get_env_int('CANAL_PAINEL_ID')
CANAL_LOG_RANK_ID = get_env_int('CANAL_LOG_RANK_ID')
CANAL_LOG_SUCESSO_ID = get_env_int('CANAL_LOG_SUCESSO_ID')
CANAL_LOG_ERRO_ID = get_env_int('CANAL_LOG_ERRO_ID')

# --- 2. BANCO DE DADOS (POOL DE CONEXÕES) ---
try:
    db_pool = psycopg2.pool.SimpleConnectionPool(1, 10, DATABASE_URL, sslmode='require')
    conn = db_pool.getconn()
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS logs_pontos 
                   (id SERIAL PRIMARY KEY, quem_usou TEXT, quem_ganhou TEXT, 
                    codigo TEXT, data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    cur.close()
    db_pool.putconn(conn)
    print("✅ Banco de dados e tabelas prontos!")
except Exception as e:
    print(f"❌ Erro ao iniciar Banco de Dados: {e}")

def registrar_ponto(quem_usou, quem_ganhou, codigo):
    conn = db_pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO logs_pontos (quem_usou, quem_ganhou, codigo) VALUES (%s, %s, %s)", 
                    (str(quem_usou), str(quem_ganhou), str(codigo)))
        cur.execute("SELECT COUNT(*) FROM logs_pontos WHERE quem_ganhou = %s", (str(quem_ganhou),))
        total = cur.fetchone()[0]
        conn.commit()
        return total
    finally:
        cur.close()
        db_pool.putconn(conn)

def get_ranking(periodo_dias=None):
    conn = db_pool.getconn()
    try:
        cur = conn.cursor()
        query = "SELECT quem_ganhou, COUNT(*) as total FROM logs_pontos "
        if periodo_dias:
            data_limite = datetime.now() - timedelta(days=periodo_dias)
            query += f"WHERE data_registro >= '{data_limite.strftime('%Y-%m-%d %H:%M:%S')}' "
        query += "GROUP BY quem_ganhou ORDER BY total DESC LIMIT 10"
        cur.execute(query)
        return cur.fetchall()
    finally:
        cur.close()
        db_pool.putconn(conn)

# --- 3. INTERFACE DO BOT (BOTÕES) ---
class RankingView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def mostrar_rank(self, interaction, dias, titulo):
        await interaction.response.defer(ephemeral=True)
        dados = get_ranking(dias)
        canal_rank = bot.get_channel(CANAL_LOG_RANK_ID) or await bot.fetch_channel(CANAL_LOG_RANK_ID)
        
        if not dados:
            msg = f"📭 O ranking {titulo} ainda está vazio."
        else:
            msg = f"🏆 **RANKING {titulo.upper()}** 🏆\n\n"
            for i, (user_id, qtd) in enumerate(dados, 1):
                medalha = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"**{i}º**"
                msg += f"{medalha} <@{user_id}> — `{qtd} pontos`\n"
        
        await canal_rank.send(msg)
        await interaction.followup.send("✅ Ranking enviado no canal de logs!", ephemeral=True)

    @discord.ui.button(label="Semanal", style=discord.ButtonStyle.green)
    async def rank_semanal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.mostrar_rank(interaction, 7, "Semanal")

    @discord.ui.button(label="Quinzenal", style=discord.ButtonStyle.blurple)
    async def rank_quinzenal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.mostrar_rank(interaction, 15, "Quinzenal")

    @discord.ui.button(label="Mensal", style=discord.ButtonStyle.red)
    async def rank_mensal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.mostrar_rank(interaction, 30, "Mensal")

# --- 4. EVENTOS E COMANDOS ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'🤖 Bot logado como {bot.user.name}')
    # Envia o painel automaticamente
    canal = bot.get_channel(CANAL_PAINEL_ID) or await bot.fetch_channel(CANAL_PAINEL_ID)
    if canal:
        await canal.purge(limit=5, check=lambda m: m.author == bot.user)
        view = RankingView()
        embed = discord.Embed(title="🏆 Central de Rankings", description="Clique abaixo para ver as estatísticas.", color=0xFFD700)
        await canal.send(embed=embed, view=view)

@bot.event
async def on_message(message):
    if message.author.id == bot.user.id:
        return

    # LOGICA DE CAPTURA DO BOT ALVO
    if message.author.id == BOT_ALVO_ID and message.channel.id == CANAL_CODIGOS_ID:
        full_text = message.content
        if message.embeds:
            for em in message.embeds:
                full_text += f" {em.title} {em.description}"
                for f in em.fields: full_text += f" {f.value}"
        
        mentions = re.findall(r'<@!?(\d+)>', full_text)
        if len(mentions) >= 2:
            usou, ganhou = mentions[0], mentions[-1]
            cod_match = re.search(r'\b([A-Z0-9]{4,})\b', full_text)
            codigo = cod_match.group(1) if cod_match else "S/C"
            
            total = registrar_ponto(usou, ganhou, codigo)
            
            log_sucesso = bot.get_channel(CANAL_LOG_SUCESSO_ID) or await bot.fetch_channel(CANAL_LOG_SUCESSO_ID)
            if log_sucesso:
                await log_sucesso.send(f"✅ <@{usou}> usou o código de <@{ganhou}>! (Total: {total})")
        else:
            log_erro = bot.get_channel(CANAL_LOG_ERRO_ID) or await bot.fetch_channel(CANAL_LOG_ERRO_ID)
            if log_erro:
                await log_erro.send(f"⚠️ Erro ao identificar IDs na mensagem: {full_text[:100]}")

    await bot.process_commands(message)

# --- 5. FLASK (KEEP ALIVE) ---
app = Flask('')
@app.route('/')
def home(): return "Bot Online!"

def run(): serve(app, host='0.0.0.0', port=10000)

if __name__ == "__main__":
    Thread(target=run).start()
    bot.run(TOKEN)
