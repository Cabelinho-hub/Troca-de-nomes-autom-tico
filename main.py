import discord
from discord.ext import commands
import os
from groq import Groq
from flask import Flask
from threading import Thread

# --- WEB SERVER (Mantém o bot vivo no Render/UptimeRobot) ---
app = Flask('')
@app.route('/')
def home(): return "Bot de Justiça Raze RP - Base de Dados Local Ativa!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

# --- CONFIGURAÇÕES ---
ID_CANAL_LOGS = 1417278749497364550
# Certifique-se de que a variável de ambiente GROQ_API_KEY está configurada no Render
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# --- FUNÇÃO DE LEITURA DO SEU ARQUIVO ---
def carregar_regras_locais():
    # O arquivo deve se chamar regras.txt e estar na mesma pasta do main.py
    caminho = "regras.txt" 
    try:
        if os.path.exists(caminho):
            with open(caminho, "r", encoding="utf-8") as f:
                # Lendo até 100k caracteres (cobre centenas de abas do Gitbook)
                return f.read()[:100000]
        else:
            return "ERRO: O arquivo regras.txt não foi encontrado na pasta do bot."
    except Exception as e:
        return f"Erro ao ler o arquivo de regras: {e}"

# --- BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.command()
async def julgar(ctx, *, denuncia: str = None):
    # Verifica se há texto ou se é uma resposta a outra mensagem
    if not denuncia and not ctx.message.reference:
        return await ctx.send("❌ **Uso correto:** `!julgar [relato]` ou responda a uma mensagem com `!julgar`.")

    msg_analise = await ctx.send("⚖️ **Consultando Base de Dados Interna...** Analisando regulamento completo.")
    
    try:
        # Carrega as regras do seu arquivo TXT instantaneamente
        regras_completas = carregar_regras_locais()
        
        situacao = denuncia
        # Se for resposta a alguém, anexa o texto da mensagem original
        if ctx.message.reference:
            ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            situacao = f"Relato: {denuncia or 'Análise de mensagem'}. Texto Original do Denunciado: {ref_msg.content}"

        # Chamada para a Groq (Modelo Llama 3.3 70B para raciocínio avançado)
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você é o Juiz Supremo e Auditor do Raze RP. Seu conhecimento é baseado estritamente nestas regras:\n\n"
                        f"{regras_completas}\n\n"
                        "DIRETRIZES:\n"
                        "1. Analise TUDO: Ilegal, Legal, Abordagens, Crimes, Punições, Metagaming, etc.\n"
                        "2. Se houver infração, nomeie o tópico da regra e explique o porquê.\n"
                        "3. Seja imparcial, técnico e direto no veredito.\n"
                        "4. Se a situação for complexa, divida em tópicos para facilitar a leitura da Staff."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Realize o julgamento desta situação: {situacao}",
                }
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.1, # Precisão máxima
        )

        veredito = chat_completion.choices[0].message.content
        canal_log = bot.get_channel(ID_CANAL_LOGS)

        # Função para enviar mensagens longas (limite do Discord)
        async def enviar_resultado(destino, texto):
            if len(texto) <= 4000:
                embed = discord.Embed(
                    title="⚖️ Relatório de Julgamento",
                    description=texto,
                    color=0x2b2d31
                )
                embed.set_footer(text=f"Analista Groq | Solicitado por: {ctx.author.name}")
                await destino.send(embed=embed)
            else:
                # Se o veredito for gigante, corta em partes de 1900 caracteres
                for i in range(0, len(texto), 1900):
                    await destino.send(f"⚠️ **PARTE {int(i/1900)+1}:**\n{texto[i:i+1900]}")

        # Envia o veredito para os canais
        if canal_log:
            await enviar_resultado(canal_log, veredito)
            await msg_analise.edit(content="✅ **Julgamento Concluído!** O relatório detalhado foi enviado para o canal de logs.")
        else:
            await msg_analise.delete()
            await enviar_resultado(ctx, veredito)

    except Exception as e:
        await msg_analise.edit(content=f"❌ **Erro no Sistema:** {str(e)[:500]}")

if __name__ == "__main__":
    keep_alive()
    # Certifique-se de que a variável de ambiente TOKEN está configurada no Render
    bot.run(os.environ.get("TOKEN"))
