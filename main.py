import discord
from discord.ext import commands
import google.generativeai as genai
import os
import logging
from flask import Flask
from threading import Thread
import os

app = Flask('')

@app.route('/')
def health_check():
    return "Bot está online!", 200

def run():
    # O Render exige que usemos a porta que ele fornece na variável PORT
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# Inicia o servidor Flask em uma thread separada
Thread(target=run).start()

# Inicia o Bot do Discord
try:
    bot.run(TOKEN)
except Exception as e:
    print(f"Erro ao iniciar o bot: {e}")
    
def keep_alive():
    t = Thread(target=run)
    t.start()
# 1. Configuração de Variáveis de Ambiente (Render)
TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_KEY")
LOG_CANAL_ID = int(os.getenv("1417278749497364550", 0))
ERRO_CANAL_ID = int(os.getenv("1417278742052601939", 0))

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Função auxiliar para mandar logs nos canais do Discord
async def enviar_log(mensagem, tipo="info"):
    canal_id = LOG_CANAL_ID if tipo == "info" else ERRO_CANAL_ID
    canal = bot.get_channel(canal_id)
    if canal:
        cor = discord.Color.green() if tipo == "info" else discord.Color.red()
        embed = discord.Embed(title=f"Log de Sistema: {tipo.upper()}", description=mensagem, color=cor)
        await canal.send(embed=embed)

@bot.event
async def on_ready():
    print(f"Bot online como {bot.user}")
    await enviar_log(f"Bot iniciado com sucesso e conectado como {bot.user}", "info")

@bot.command()
async def ajuda(ctx):
    target_msg = ctx.message.reference.resolved if ctx.message.reference else ctx.message
    
    async with ctx.typing():
        try:
            # Lógica da IA (simplificada para o exemplo)
            content = ["Analise detalhadamente:", target_msg.content]
            
            if target_msg.attachments:
                for att in target_msg.attachments:
                    img_data = await att.read()
                    content.append({'mime_type': 'image/jpeg', 'data': img_data})

            response = model.generate_content(content)
            
            # Embed de Resposta
            embed = discord.Embed(title="🛠️ Suporte Técnico IA", description=response.text[:4000], color=discord.Color.blue())
            await ctx.reply(embed=embed)
            
            # Log de Sucesso no Canal de Logs
            await enviar_log(f"Comando !ajuda usado por {ctx.author} no canal {ctx.channel}", "info")

        except Exception as e:
            # Log de Erro no Canal de Erros
            await enviar_log(f"Erro ao processar !ajuda para {ctx.author}: {str(e)}", "erro")
            await ctx.send("❌ Tive um problema técnico. O erro foi reportado aos logs.")

bot.run(TOKEN)
