import discord
from discord.ext import commands
import google.generativeai as genai
from groq import Groq
import os
import requests
from bs4 import BeautifulSoup
import asyncio
from flask import Flask
from threading import Thread
import yt_dlp
import uuid

# --- SERVIDOR WEB ---
app = Flask('')
@app.route('/')
def home(): return "Bot Híbrido Online!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run); t.daemon = True; t.start()

# --- CONFIGURAÇÃO DAS IAs ---
# Gemini para Visão (Vídeo)
genai.configure(api_key=os.environ.get("GEMINI_KEY"))
model_gemini = genai.GenerativeModel(
    model_name='gemini-1.5-flash',
    generation_config={"request_options": {"api_version": "v1"}}
    
# Groq para Lógica e Regras (Texto)
client_groq = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# --- FUNÇÕES ---
def baixar_video(url):
    unique_id = str(uuid.uuid4())[:8]
    filename = f'temp_{unique_id}.mp4'
    ydl_opts = {
        'format': 'mp4/best',
        'outtmpl': filename,
        'max_filesize': 30*1024*1024, # Limite de 30MB
        'quiet': True,
        'no_warnings': True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # Verifica se o arquivo realmente existe no servidor após o download
        if os.path.exists(filename):
            return filename
        else:
            print(f"Erro: Arquivo {filename} não foi criado.")
            return None
    except Exception as e:
        print(f"Erro no yt-dlp: {e}")
        return None

async def extrair_regras():
    url = "https://gitbook.io"
    try:
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, lambda: requests.get(url, timeout=10))
        soup = BeautifulSoup(res.text, 'html.parser')
        return soup.get_text()[:15000]
    except: return "Regras padrão de RP: Proibido VDM e RDM."

# --- BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command()
async def julgar(ctx):
    path = None
    url = None
    myfile = None

    # Detectar vídeo
    if ctx.message.attachments:
        attachment = ctx.message.attachments[0]
        path = f"temp_{uuid.uuid4().hex}_{attachment.filename}"
        await attachment.save(path)
    elif "http" in ctx.message.content:
        url = [p for p in ctx.message.content.split() if "http" in p][0]

    if url and not path:
        msg_wait = await ctx.send("📥 Baixando vídeo para o tribunal...")
        path = baixar_video(url)
        await msg_wait.delete()

    if not path:
        return await ctx.send("❌ Não encontrei vídeo/link para analisar.")

    msg_status = await ctx.send("⚖️ **Iniciando Julgamento Híbrido...**\n1. Gemini analisando imagens...\n2. Groq revisando o regulamento...")

    try:
        # FASE 1: GEMINI (ASSISTE O VÍDEO)
        myfile = genai.upload_file(path)
        while myfile.state.name == "PROCESSING":
            await asyncio.sleep(3)
            myfile = genai.get_file(myfile.name)

        video_analysis = model_gemini.generate_content(["Descreva detalhadamente as ações dos jogadores neste clipe de GTA RP.", myfile])
        descricao_video = video_analysis.text

        # FASE 2: GROQ (APLICA AS REGRAS)
        regras = await extrair_regras()
        
        chat_completion = client_groq.chat.completions.create(
            messages=[
                {"role": "system", "content": f"Você é o Juiz Final do Raze RP. Regras: {regras}"},
                {"role": "user", "content": f"Com base nesta descrição visual do vídeo: {descricao_video}, houve infração? Dê um veredito curto e cite a regra."}
            ],
            model="llama-3.3-70b-versatile",
        )
        veredito_final = chat_completion.choices.message.content

        # RESULTADO
        canal_log = bot.get_channel(1417278749497364550)
        formato = (
            f"⚖️ **JULGAMENTO HÍBRIDO (GEMINI + GROQ)**\n"
            f"**Solicitante:** {ctx.author.mention}\n"
            f"**👁️ Análise Visual (Gemini):** {descricao_video[:400]}...\n\n"
            f"**🔨 Veredito Final (Groq/Llama):**\n{veredito_final}"
        )

        if canal_log:
            await canal_log.send(formato)
            await msg_status.edit(content="✅ Julgamento concluído! Verifique as logs.")
        else:
            await msg_status.edit(content=formato)

    except Exception as e:
        await msg_status.edit(content=f"❌ Erro no processamento: {e}")
    finally:
        if path and os.path.exists(path): os.remove(path)
        if myfile: 
            try: genai.delete_file(myfile.name)
            except: pass

keep_alive()
bot.run(os.environ.get("TOKEN"))
