import discord
from discord.ext import commands
import google.generativeai as genai
import os
import requests
from bs4 import BeautifulSoup
import time

# --- CONFIGURAÇÕES ---
DISCORD_TOKEN = 'SEU_TOKEN_AQUI'
GEMINI_KEY = 'AIzaSyBmIuFCFu2XITTr_JI7cCMXBxcDNotu3Yg'
URL_REGRAS = 'https://razerp.gitbook.io/raze-roleplay' # O bot vai ler aqui

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

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Verificar se há anexos (imagem ou vídeo)
    if message.attachments:
        attachment = message.attachments[0]
        
        if any(attachment.filename.lower().endswith(ext) for ext in ['png', 'jpg', 'jpeg', 'mp4', 'mov']):
            msg_analise = await message.channel.send("👀 Analisando mídia contra as regras...")
            
            # Download temporário
            path = f"./temp_{attachment.filename}"
            await attachment.save(path)

            try:
                # 1. Carregar arquivo no Google AI
                myfile = genai.upload_file(path)
                regras = extrair_regras()
                
                # 2. Pedir julgamento à IA
                prompt = f"Baseado nestas regras: {regras}. Analise este arquivo e diga se ele viola algo. Responda de forma curta: 'APROVADO' ou 'VIOLAÇÃO: [motivo]'."
                response = model.generate_content([prompt, myfile])
                
                await msg_analise.edit(content=f"⚖️ **Veredito:** {response.text}")

            except Exception as e:
                await msg_analise.edit(content=f"❌ Erro na análise: {e}")
            finally:
                if os.path.exists(path):
                    os.remove(path)

    await bot.process_commands(message)

bot.run(DISCORD_TOKEN)
