import discord
from discord.ext import commands
import google.generativeai as genai
import os
import requests
from bs4 import BeautifulSoup
import time
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot Online!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start() 
# --- CONFIGURAÇÕES ---
DISCORD_TOKEN = 'SEU_TOKEN_AQUI'
GEMINI_KEY = 'AIzaSyBmIuFCFu2XITTr_JI7cCMXBxcDNotu3Yg'
URL_REGRAS = 'https://razerp.gitbook.io/raze-roleplay' # O bot vai ler aqui
ID_CANAL_LOGS = 1417278749497364550
# Configurar IA
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash') # Versão rápida e grátis

# Configurar Bot Discord
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def extrair_regras_completo():
    """Varre todas as páginas do GitBook do Raze RP"""
    base_url = "https://razerp.gitbook.io/raze-roleplay"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        # 1. Pega a página principal para achar os links das outras abas
        res = requests.get(base_url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Procura por links que apontam para sub-páginas do GitBook
        links = set()
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith('/raze-roleplay/'):
                links.add("https://razerp.gitbook.io" + href)
        
        print(f"📚 Encontradas {len(links)} páginas de regras. Lendo conteúdo...")

        regras_finais = ""
        # 2. Visita cada link e extrai o texto
        for link in list(links)[:15]: # Limite de 15 páginas para não travar
            r = requests.get(link, headers=headers)
            s = BeautifulSoup(r.text, 'html.parser')
            
            # Pega o título da página e o texto dos parágrafos
            titulo = s.find('h1').text if s.find('h1') else "Sem Título"
            texto = " ".join([p.text for p in s.find_all(['p', 'li'])])
            regras_finais += f"\n--- SEÇÃO: {titulo} ---\n{texto}\n"
            time.sleep(1) # Pausa leve para não ser bloqueado

        return regras_finais[:30000] # O Gemini Flash aguenta muito texto
    except Exception as e:
        return f"Erro ao ler site: {e}"
        
@bot.event
async def on_ready():
    print(f'Bot {bot.user} online e julgando!')

@bot.command()
async def julgar(ctx):
    """Comando !julgar: analise o anexo da mensagem ou a mensagem acima"""
    
    # Verifica se o usuário mandou um anexo junto com o comando !julgar
    attachment = None
    if ctx.message.attachments:
        attachment = ctx.message.attachments[0]
    # Se não mandou anexo, verifica se o comando foi uma resposta a outra mensagem com anexo
    elif ctx.message.reference:
        ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        if ref_msg.attachments:
            attachment = ref_msg.attachments[0]

    if not attachment:
        return await ctx.send("❌ Você precisa enviar uma imagem/vídeo com o comando ou responder a um vídeo!")

    if any(attachment.filename.lower().endswith(ext) for ext in ['png', 'jpg', 'jpeg', 'mp4', 'mov']):
        # Canal de Logs
        canal_log = bot.get_channel(ID_CANAL_LOGS)
        
        msg_status = await ctx.send("⚖️ Enviando para o tribunal da IA...")
        path = f"./temp_{attachment.filename}"
        await attachment.save(path)

        try:
            myfile = genai.upload_file(path)
            regras = extrair_regras_completo() # Sua função que lê o GitBook
            
            prompt = f"Analise esta mídia conforme as regras: {regras}. Diga se há infração."
            response = model.generate_content([prompt, myfile])

            # Manda a resposta detalhada no canal de LOGS
            embed = discord.Embed(title="⚖️ Novo Julgamento de Denúncia", color=discord.Color.red())
            embed.add_field(name="Autor do Comando", value=ctx.author.mention)
            embed.add_field(name="Veredito", value=response.text)
            embed.set_footer(text="IA Moderadora Raze RP")
            
            if canal_log:
                await canal_log.send(embed=embed)
            
            # Responde no canal atual de forma resumida
            await msg_status.edit(content=f"✅ Julgamento concluído! Detalhes enviados no canal de logs.")

        except Exception as e:
            await msg_status.edit(content=f"❌ Erro: {e}")
        finally:
            if os.path.exists(path):
                os.remove(path)

if __name__ == "__main__":
    keep_alive()
    # Esta linha pega o valor que você salvou no Render
    token_sistema = os.environ.get("TOKEN") 
    
    if token_sistema is None:
        print("ERRO: A variável 'TOKEN' não foi encontrada no Render!")
    else:
        bot.run(token_sistema)
