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

    # 1. Verifica IDs do Bot Alvo e do Canal
    if message.author.id == int(BOT_ALVO_ID) and message.channel.id == int(CANAL_CODIGOS_ID):
        
        # 2. Captura TUDO, inclusive de Webhooks e Interações
        full_text = ""
        
        # Se houver texto normal
        if message.content:
            full_text += f" {message.content} "
            
        # FORÇA a leitura de cada pedaço do Embed (Título, Descrição, Campos, Rodapé)
        if message.embeds:
            for e in message.embeds:
                embed_data = [e.title, e.description, e.footer.text, e.author.name]
                if e.fields:
                    for f in e.fields:
                        embed_data.extend([f.name, f.value])
                # Filtra apenas o que não é vazio e junta
                full_text += " ".join([str(p) for p in embed_data if p]) + " "

        # 3. Se ainda assim estiver vazio, tenta ler os componentes (botões/menus)
        if not full_text.strip():
            full_text = " ".join([str(comp) for comp in message.components])

        # 4. BUSCA POR IDs (Qualquer número de 17 a 20 dígitos)
        # O segredo é buscar o número puro, já que o texto da menção não está vindo
        ids_encontrados = re.findall(r'(\d{17,20})', full_text)

        # 5. BUSCA PELO CÓDIGO (Palavra grande em maiúsculo)
        cod_match = re.search(r'\b(RAZE[A-Z0-9]+)\b', full_text, re.IGNORECASE)
        codigo = cod_match.group(1) if cod_match else "N/A"

        if len(ids_encontrados) >= 2:
            usou = ids_encontrados[0]
            ganhou = ids_encontrados[-1]

            total = registrar_ponto(usou, ganhou, codigo)
            
            canal_sucesso = bot.get_channel(CANAL_LOG_SUCESSO_ID) or await bot.fetch_channel(CANAL_LOG_SUCESSO_ID)
            if canal_sucesso:
                await canal_sucesso.send(
                    f"✅ **Ponto Registrado!**\n"
                    f"👤 **Usou:** <@{usou}>\n"
                    f"🎬 **Streamer:** <@{ganhou}>\n"
                    f"🔑 **Código:** `{codigo}`\n"
                    f"📈 **Total:** `{total}` pontos"
                )
        else:
            # Esse log agora vai mostrar se o problema é que o texto REALMENTE não existe
            log_erro = bot.get_channel(CANAL_LOG_ERRO_ID) or await bot.fetch_channel(CANAL_LOG_ERRO_ID)
            if log_erro:
                await log_erro.send(f"⚠️ IDs não encontrados. Tamanho do texto lido: `{len(full_text)}` caracteres.")

    await bot.process_commands(message)

@bot.command()
async def testar(ctx):
    await ctx.send(f"Status da Intent: {bot.intents.message_content}")
    
# --- 5. FLASK (KEEP ALIVE) ---
app = Flask('')
@app.route('/')
def home(): return "Bot Online!"

def run(): serve(app, host='0.0.0.0', port=10000)

if __name__ == "__main__":
    Thread(target=run).start()
    bot.run(TOKEN)
