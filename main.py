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
import uuid

# --- WEB SERVER PARA MANTER VIVO ---
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
# Recomendo colocar GEMINI_KEY no Environment Variables do Render também!
GEMINI_KEY = os.environ.get("GEMINI_KEY", "AIzaSy...") 
ID_CANAL_LOGS = 1417278749497364550

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# --- FUNÇÕES DE SUPORTE ---

def baixar_video_link(url):
    unique_id = str(uuid.uuid4())[:8]
    filename = f'temp_video_{unique_id}.mp4'
    ydl_opts = {
        'format': 'mp4/best',
        'outtmpl': filename,
        'max_filesize': 40 * 1024 * 1024, # 40MB
        'quiet': True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return filename
    except Exception as e:
        print(f"Erro no download: {e}")
        return None

def extrair_regras_completo():
    base_url = "https://razerp.gitbook.io/raze-roleplay"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
        res = requests.get(base_url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        links = set()
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith('/raze-roleplay/'):
                links.add("https://razerp.gitbook.io" + href)
        
        regras_finais = ""
        # Limitado a 10 páginas para performance no Render
        for link in list(links)[:10]: 
            r = requests.get(link, headers=headers)
            s = BeautifulSoup(r.text, 'html.parser')
            
            titulo = s.find('h1').get_text() if s.find('h1') else "Regra"
            texto = " ".join([p.get_text() for p in s.find_all(['p', 'li'])])
            regras_finais += f"\n--- {titulo} ---\n{texto}\n"
            time.sleep(0.5)

        return regras_finais[:30000]
    except Exception as e:
        return f"Erro ao extrair regras: {e}"

# --- BOT DISCORD ---

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'✅ Bot {bot.user} conectado e pronto para julgar!')

@bot.command()
async def julgar(ctx):
    url = None
    path = None

    # Verifica se é resposta, link no texto ou anexo
    if ctx.message.reference:
        ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        if "http" in ref_msg.content:
            url = [p for p in ref_msg.content.split() if "http" in p][0]
        elif ref_msg.attachments:
            attachment = ref_msg.attachments[0]
            path = f"temp_{attachment.filename}"
            await attachment.save(path)

    elif "http" in ctx.message.content:
        url = [p for p in ctx.message.content.split() if "http" in p][0]
    
    elif ctx.message.attachments:
        attachment = ctx.message.attachments[0]
        path = f"temp_{attachment.filename}"
        await attachment.save(path)

    if url and not path:
        msg_wait = await ctx.send("📥 Baixando vídeo da URL...")
        path = baixar_video_link(url)
        await msg_wait.delete()

    if path:
        msg_analise = await ctx.send("⚖️ Analisando evidências contra o regulamento...")
        try:
            # Upload para o Gemini
            myfile = genai.upload_file(path)
            
            # Aguarda o processamento do vídeo no Google (importante para vídeos longos)
            while myfile.state.name == "PROCESSING":
                time.sleep(2)
                myfile = genai.get_file(myfile.name)

            regras = extrair_regras_completo()
            
            prompt = (
                f"Você é um moderador de Roleplay experiente. "
                f"Analise o vídeo anexado com base nestas regras: \n{regras}\n\n"
                "O jogador cometeu alguma infração? Se sim, qual? Cite o nome da regra e dê um veredito direto."
            )
            
            response = model.generate_content([prompt, myfile])
            
            canal_log = bot.get_channel(ID_CANAL_LOGS)
            veredito_texto = f"⚠️ **NOVO JULGAMENTO**\n**Réu/Solicitado por:** {ctx.author.mention}\n\n**Veredito da IA:**\n{response.text}"
            
            if canal_log:
                await canal_log.send(veredito_texto)
                await msg_analise.edit(content="✅ Julgamento concluído! Verifique o canal de logs.")
            else:
                await msg_analise.edit(content=veredito_texto)
                
        except Exception as e:
            await msg_analise.edit(content=f"❌ Erro durante a análise: {e}")
        finally:
            # Garante que o arquivo seja deletado
            if path and os.path.exists(path):
                os.remove(path)
                try:
                    genai.delete_file(myfile.name) # Limpa no Google Cloud também
                except: pass
    else:
        await ctx.send("❌ Nenhum vídeo encontrado. Envie um arquivo, um link ou responda a um vídeo com !julgar.")

# --- INICIALIZAÇÃO ---

if __name__ == "__main__":
    keep_alive()
    token_sistema = os.environ.get("TOKEN") 
    
    if not token_sistema:
        print("ERRO: Variável 'TOKEN' não configurada no Render!")
    else:
        bot.run(token_sistema)
