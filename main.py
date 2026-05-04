import discord
from discord.ext import commands
import google.generativeai as genai
import os
import requests
from bs4 import BeautifulSoup
import time
from flask import Flask
from threading import Thread
import yt_dlp

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

def baixar_video_link(url):
    ydl_opts = {
        'format': 'mp4/best',  # Garante que venha em MP4
        'outtmpl': './temp_video.mp4',
        'max_filesize': 40 * 1024 * 1024, # Limite de 40MB para não travar o Render
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return './temp_video.mp4'
    except:
        return None
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
    # 1. Tentar achar o link ou arquivo
    url = None
    path = None

    # Se você respondeu a uma mensagem
    if ctx.message.reference:
        ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        # Verifica se na mensagem respondida tem um link
        if "http" in ref_msg.content:
            palavras = ref_msg.content.split()
            for p in palavras:
                if "http" in p:
                    url = p
                    break
        # Se não tem link, vê se tem anexo
        elif ref_msg.attachments:
            attachment = ref_msg.attachments[0]
            path = f"./temp_{attachment.filename}"
            await attachment.save(path)

    # Se você mandou o link direto no comando: !julgar http...
    elif "http" in ctx.message.content:
        palavras = ctx.message.content.split()
        for p in palavras:
            if "http" in p:
                url = p
                break
    
    # Se tem anexo direto no comando
    elif ctx.message.attachments:
        attachment = ctx.message.attachments[0]
        path = f"./temp_{attachment.filename}"
        await attachment.save(path)

    # 2. Se achou link, baixa o vídeo
    if url:
        msg_wait = await ctx.send("📥 Baixando vídeo do link...")
        path = baixar_video_link(url)
        await msg_wait.delete()

    # 3. Enviar para a IA
    if path:
        msg_analise = await ctx.send("⚖️ Analisando contra as regras do Raze RP...")
        try:
            myfile = genai.upload_file(path)
            regras = extrair_regras_completo()
            
            prompt = f"Analise este vídeo com base nestas regras: {regras}. O jogador cometeu infração? Dê o veredito."
            response = model.generate_content([prompt, myfile])
            
            # Enviar para o CANAL DE LOGS
            canal_log = bot.get_channel(ID_CANAL_LOGS)
            if canal_log:
                await canal_log.send(f"⚠️ **NOVO JULGAMENTO**\nSolicitado por: {ctx.author.mention}\n\n**Veredito:**\n{response.text}")
            
            await msg_analise.edit(content="✅ Julgamento finalizado! Confira o canal de logs.")
        except Exception as e:
            await msg_analise.edit(content=f"❌ Erro na IA: {e}")
        finally:
            if os.path.exists(path):
                os.remove(path)
    else:
        await ctx.send("❌ Não encontrei vídeo ou link para analisar. Tente anexar o arquivo ou responder a um link!")

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
