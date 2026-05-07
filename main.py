import discord
from discord.ext import commands
import os
import psycopg2
from psycopg2 import pool
from flask import Flask
from threading import Thread
from waitress import serve
import re

# --- 1. CONFIGURAÇÕES E VARIÁVEIS (No topo do arquivo) ---
TOKEN = os.getenv('DISCORD_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')

def get_env_int(name):
    value = os.getenv(name, '').strip()
    return int(value) if value.isdigit() else 0

BOT_ALVO_ID = get_env_int('BOT_ALVO_ID')
CANAL_CODIGOS_ID = get_env_int('CANAL_CODIGOS_ID')
CANAL_PAINEL_ID = get_env_int('CANAL_PAINEL_ID')      # <-- ESSA LINHA É A QUE FALTA
CANAL_LOG_RANK_ID = get_env_int('CANAL_LOG_RANK_ID') # Verifique se esta também existe
CANAL_LOG_SUCESSO_ID = get_env_int('CANAL_LOG_SUCESSO_ID')
CANAL_LOG_ERRO_ID = get_env_int('CANAL_LOG_ERRO_ID')

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
    # ELE SÓ PODE IGNORAR SE FOR ELE MESMO
    if message.author == bot.user:
        return

    # Verifique se essa condição está correta (use print para debugar)
     if message.author.id == int(BOT_ALVO_ID) and message.channel.id == int(CANAL_CODIGOS_ID):
        full_text = ""
    # 2. Coleta todo o texto (da mensagem e de embeds)
    full_text = message.content
    if message.embeds:
        for embed in message.embeds:
            if embed.description: full_text += f" {embed.description}"
            if embed.fields:
                for field in embed.fields: full_text += f" {field.value}"

    # 3. Busca todos os IDs mencionados no formato <@123...> ou <@!123...>
    all_mentions = re.findall(r'<@!?(\d+)>', full_text)

    if len(all_mentions) >= 2:
        quem_usou = all_mentions[0]
        quem_ganhou = all_mentions[-1]
        
        # Tenta pegar o código (palavras com letras e números)
        codigo_match = re.search(r'\b([A-Z0-9]{4,})\b', full_text)
        codigo_texto = codigo_match.group(1) if codigo_match else "S/C"

        # 4. Salva no Banco e MENCIONA no log
        try:
            novo_total = update_pontos(quem_ganhou) # Sua função de DB
            
            canal_log = bot.get_channel(CANAL_LOG_SUCESSO_ID)
            if canal_log:
                # O USO DE f"<@{id}>" garante a menção mesmo que o bot não conheça o usuário
                await canal_log.send(
                    f"✅ **Ponto Registrado!**\n"
                    f"👤 **Usou:** <@{quem_usou}>\n"
                    f"🏆 **Ganhou:** <@{quem_ganhou}>\n"
                    f"🔑 **Código:** `{codigo_texto}`\n"
                    f"📊 **Total de <@{quem_ganhou}>:** {novo_total} pontos"
                )
        except Exception as e:
            print(f"Erro ao processar: {e}")
    else:
        # Log de erro caso ele não ache as 2 pessoas
        canal_erro = bot.get_channel(CANAL_LOG_ERRO_ID)
        if canal_erro:
            await canal_erro.send(f"⚠️ Identifiquei uma mensagem, mas não encontrei as menções necessárias.\n**Texto lido:** {full_text[:100]}...")
            
@bot.command()
@commands.has_permissions(administrator=True)
async def setup_painel(ctx): # Adicionado 'async' aqui
    canal_painel = bot.get_channel(CANAL_PAINEL_ID) or await bot.fetch_channel(CANAL_PAINEL_ID)
    if canal_painel:
        view = RankingView()
        embed = discord.Embed(
            title="🏆 Painel de Rankings",
            description="Clique nos botões abaixo para visualizar as classificações atualizadas.",
            color=discord.Color.blue()
        )
        await canal_painel.send(embed=embed, view=view)
        await ctx.send("✅ Painel enviado com sucesso!")
    else:
        await ctx.send("❌ Não consegui encontrar o canal. Verifique o ID.") 
        
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
