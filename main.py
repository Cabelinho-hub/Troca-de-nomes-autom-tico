import discord
from discord.ext import commands
import asyncio

# 1. CONFIGURAÇÕES (Preencha com os IDs do seu servidor)
TOKEN = "SEU_TOKEN_AQUI"
CANAL_ENTRADA = 1465403347694522490       # Canal onde as pessoas digitam "ID Nome"
LOG_SUCESSO = 1417278744258937005          # Canal onde o bot avisa que deu certo
LOG_ERRO = 1417278747031109662             # Canal onde o bot avisa falhas
CARGOS_IGNORADOS = [1411158281409400832]    # IDs de cargos que o bot NÃO pode renomear

# 2. INICIALIZAÇÃO (Intents são obrigatórios para ler mensagens e membros)
intents = discord.Intents.default()
intents.message_content = True  # Para ler o que foi digitado
intents.members = True          # Para encontrar e renomear os membros
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot de Nomes online como {bot.user}")

# 3. O SEU EVENTO (O código que você mandou)
@bot.event
async def on_message(message):
    if message.author.id == bot.user.id:
        return
        
    if message.channel.id == CANAL_ENTRADA:
        partes = message.content.split(' ', 1)
        if len(partes) < 2:
            return

        try:
            user_id = int(partes[0])
            novo_nome = f"#{partes[1]}"
            
            guild = message.guild
            member = guild.get_member(user_id)

            if member:
                # Verifica cargos protegidos
                if any(role.id in CARGOS_IGNORADOS for role in member.roles):
                    canal_erro = bot.get_channel(LOG_ERRO)
                    if canal_erro:
                        await canal_erro.send(f"🛡️ **Protegido:** {member.mention} possui cargo ignorado.")
                    return

                try:
                    await member.edit(nick=novo_nome)
                    canal_sucesso = bot.get_channel(LOG_SUCESSO)
                    if canal_sucesso:
                        await canal_sucesso.send(f"✅ **Sucesso:** {member.mention} renomeado.")
                except discord.Forbidden:
                    canal_erro = bot.get_channel(LOG_ERRO)
                    if canal_erro:
                        await canal_erro.send(f"❌ **Erro:** Cargo do bot está abaixo do usuário.")
            else:
                canal_erro = bot.get_channel(LOG_ERRO)
                if canal_erro:
                    await canal_erro.send(f"⚠️ **Não encontrado:** ID `{user_id}` fora do server.")
        except ValueError:
            pass

    await bot.process_commands(message)

# 4. RODAR O BOT
bot.run(TOKEN)
