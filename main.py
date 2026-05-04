import discord
from discord.ext import commands
import os
import requests
from bs4 import BeautifulSoup
import asyncio
from flask import Flask
from threading import Thread
from groq import Groq

# --- WEB SERVER ---
app = Flask('')
@app.route('/')
def home(): return "Bot Groq Online!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

# --- CONFIGURAÇÕES ---
ID_CANAL_LOGS = 1417278749497364550
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# --- FUNÇÃO DE REGRAS ---
async def extrair_regras():
    base_url = "https://gitbook.io"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, lambda: requests.get(base_url, headers=headers, timeout=10))
        soup = BeautifulSoup(res.text, 'html.parser')
        
        links = set()
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith('/raze-roleplay/'):
                links.add("https://gitbook.io" + href)
        
        texto_completo = ""
        for link in list(links)[:5]: # Lendo as 5 principais abas
            r = await loop.run_in_executor(None, lambda: requests.get(link, headers=headers))
            s = BeautifulSoup(r.text, 'html.parser')
            texto_completo += s.get_text()
        return texto_completo[:15000]
    except:
        return "Regras não disponíveis."

# --- BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command()
async def julgar(ctx, *, denuncia: str = None):
    # Se não houver texto, mas houver imagem, o Groq Vision poderia ser usado (requer código extra)
    if not denuncia and not ctx.message.reference:
        return await ctx.send("❌ Descreva a situação ou responda a uma mensagem para eu julgar.")

    msg_analise = await ctx.send("⚖️ Consultando o regulamento do Raze RP via Groq...")
    
    try:
        regras = await extrair_regras()
        situacao = denuncia
        
        # Se estiver respondendo a alguém, pega o texto da pessoa
        if ctx.message.reference:
            ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            situacao = f"Contexto da denúncia: {denuncia or ''}. Mensagem original: {ref_msg.content}"

        # Chamada para a Groq (Llama 3)
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": f"Você é um Administrador sênior do Raze RP. Use estas regras: {regras}",
                },
                {
                    "role": "user",
                    "content": f"Julgue a seguinte situação e diga se houve VDM, RDM ou outra infração: {situacao}",
                }
            ],
            model="llama-3.3-70b-versatile",
        )

        veredito = chat_completion.choices[0].message.content
        
        canal_log = bot.get_channel(ID_CANAL_LOGS)
        if canal_log:
            await canal_log.send(f"⚠️ **JULGAMENTO GROQ**\nSolicitado por: {ctx.author.mention}\n\n{veredito}")
            await msg_analise.edit(content="✅ Julgamento concluído! Veja o canal de logs.")
        else:
            await msg_analise.edit(content=f"⚖️ **Veredito:**\n{veredito}")

    except Exception as e:
        await msg_analise.edit(content=f"❌ Erro na Groq: {e}")

if __name__ == "__main__":
    keep_alive()
    bot.run(os.environ.get("TOKEN"))
