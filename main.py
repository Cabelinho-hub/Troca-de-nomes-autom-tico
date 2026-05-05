import discord
from discord.ext import commands
import os
import requests
from bs4 import BeautifulSoup
import asyncio
from flask import Flask
from threading import Thread
from groq import Groq
import time

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

# Sistema de Cache para as regras não travarem o bot
cache_regras = {"texto": "", "ultima_atualizacao": 0}

# --- FUNÇÃO DE REGRAS COM CACHE E LEITURA AMPLIADA ---
async def extrair_regras():
    agora = time.time()
    # Se já leu as regras nos últimos 60 minutos, usa o que está na memória
    if cache_regras["texto"] and (agora - cache_regras["ultima_atualizacao"] < 3600):
        return cache_regras["texto"]

    base_url = "https://gitbook.io" 
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, lambda: requests.get(base_url, headers=headers, timeout=15))
        soup = BeautifulSoup(res.text, 'html.parser')
        
        links = set()
        for a in soup.find_all('a', href=True):
            href = a['href']
            if "/raze-roleplay/" in href:
                full_url = href if href.startswith('http') else "https://razerp.gitbook.io" + href
                links.add(full_url)
        
        texto_completo = ""
        # Lendo as 20 principais abas para cobertura total
        for link in list(links)[:20]: 
            try:
                r = await loop.run_in_executor(None, lambda: requests.get(link, headers=headers, timeout=10))
                s = BeautifulSoup(r.text, 'html.parser')
                body_content = s.find('main') or s.find('body')
                if body_content:
                    for trash in body_content(["script", "style", "nav", "footer"]):
                        trash.decompose()
                    texto_completo += f"\n--- SEÇÃO: {link.split('/')[-1].upper()} ---\n"
                    texto_completo += body_content.get_text(separator=' ', strip=True) + "\n"
            except:
                continue

        # Salva no cache
        cache_regras["texto"] = texto_completo[:40000]
        cache_regras["ultima_atualizacao"] = agora
        return cache_regras["texto"]
    except Exception as e:
        print(f"Erro ao extrair regras: {e}")
        return cache_regras["texto"] or "Regras não disponíveis."

# --- BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command()
async def julgar(ctx, *, denuncia: str = None):
    if not denuncia and not ctx.message.reference:
        return await ctx.send("❌ Descreva a situação ou responda a uma mensagem para eu julgar.")

    msg_analise = await ctx.send("⚖️ Consultando o regulamento e gerando veredito detalhado...")
    
    try:
        regras = await extrair_regras()
        situacao = denuncia
        
        if ctx.message.reference:
            ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            situacao = f"Contexto da denúncia: {denuncia or ''}. Mensagem original: {ref_msg.content}"

        # Chamada para a Groq
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você é o Auditor Supremo do Raze RP. Analise denúncias de forma técnica.\n"
                        f"BASE DE REGRAS: {regras}\n\n"
                        "INSTRUÇÕES:\n"
                        "1. Analise TODAS as infrações (Meta, Power, Amor à vida, Ilegal, etc).\n"
                        "2. Cite o nome da regra e o motivo técnico.\n"
                        "3. Seja imparcial e direto."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Julgue a situação perante as regras: {situacao}",
                }
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.1,
        )

        veredito = chat_completion.choices[0].message.content
        canal_log = bot.get_channel(ID_CANAL_LOGS)

        # Função interna para enviar o texto sem estourar o limite de 2000 caracteres
        async def enviar_resultado(destino, texto):
            if len(texto) <= 4000:
                embed = discord.Embed(title="⚖️ Relatório de Julgamento", description=texto, color=0x2b2d31)
                embed.set_footer(text=f"Solicitado por: {ctx.author.name}")
                await destino.send(embed=embed)
            else:
                for i in range(0, len(texto), 1900):
                    await destino.send(f"⚠️ **Parte {int(i/1900)+1}**\n{texto[i:i+1900]}")

        # Envio final
        if canal_log:
            await enviar_resultado(canal_log, veredito)
            await msg_analise.edit(content="✅ **Julgamento concluído!** Veja o canal de logs.")
        else:
            await msg_analise.delete()
            await enviar_resultado(ctx, veredito)

    except Exception as e:
        await msg_analise.edit(content=f"❌ Erro no processamento: {str(e)[:1000]}")

if __name__ == "__main__":
    keep_alive()
    bot.run(os.environ.get("TOKEN"))
