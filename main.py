import discord
from discord.ext import commands
import google.generativeai as genai
import os
from flask import Flask
from threading import Thread

# --- 1. CONFIGURAÇÃO DO SITE (KEEP ALIVE PARA RENDER) ---
app = Flask('')

@app.route('/')
def health_check():
    return "Bot online!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- 2. CONFIGURAÇÃO DE VARIÁVEIS E IA ---
# Pegando das Environment Variables do Render
TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_KEY")

# IDs fixos dos seus canais (conforme você passou)
LOG_CANAL_ID = 1417278749497364550
ERRO_CANAL_ID = 1417278742052601939

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# --- 3. CONFIGURAÇÃO DO BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Função para enviar logs nos canais específicos
async def enviar_log(mensagem, tipo="info"):
    canal_id = LOG_CANAL_ID if tipo == "info" else ERRO_CANAL_ID
    canal = bot.get_channel(canal_id)
    if canal:
        cor = discord.Color.green() if tipo == "info" else discord.Color.red()
        embed = discord.Embed(title=f"Log: {tipo.upper()}", description=mensagem, color=cor)
        await canal.send(embed=embed)

@bot.event
async def on_ready():
    print(f"✅ Bot online como {bot.user}")
    await enviar_log(f"Bot iniciado com sucesso e conectado como {bot.user}", "info")

@bot.command()
async def ajuda(ctx):
    # Se responder a uma mensagem, analisa ela. Se não, analisa a própria mensagem !ajuda
    target_msg = ctx.message.reference.resolved if ctx.message.reference else ctx.message
    
    async with ctx.typing():
        try:
            prompt = (
                "Você é um especialista em suporte técnico. "
                "Analise o texto e/ou imagem abaixo e forneça uma solução detalhada, "
                "do básico ao avançado. Use blocos de código se necessário."
            )
            content = [prompt, target_msg.content]
            
            if target_msg.attachments:
                for att in target_msg.attachments:
                    img_data = await att.read()
                    content.append({'mime_type': 'image/jpeg', 'data': img_data})

            response = model.generate_content(content)
            
            embed = discord.Embed(
                title="🛠️ Suporte Técnico RAZE", 
                description=response.text[:4000], 
                color=discord.Color.blue()
            )
            await ctx.reply(embed=embed)
            await enviar_log(f"Comando !ajuda usado por {ctx.author}", "info")

        except Exception as e:
            await enviar_log(f"Erro no !ajuda: {str(e)}", "erro")
            await ctx.send("❌ Tive um problema técnico. O erro foi reportado aos logs.")

# --- 4. EXECUÇÃO ---
if __name__ == "__main__":
    # Inicia o Flask em segundo plano
    t = Thread(target=run_flask)
    t.start()
    
    # Inicia o Bot
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Erro: DISCORD_TOKEN não encontrado nas variáveis de ambiente.")
