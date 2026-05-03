import discord
from discord.ext import commands
import os
from flask import Flask
from threading import Thread
import datetime
import sqlite3
import re
import pytz
from discord.ui import Button, View

# --- BANCO DE DADOS ---
conn = sqlite3.connect('metricas_raze.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS registros (
        user_id TEXT, 
        username TEXT, 
        codigo_usado TEXT, 
        data_hora DATETIME
    )
''')
conn.commit()

# --- CONFIGURAÇÃO WEB ---
app = Flask(__name__)
@app.route('/')
def home(): return "Bot Online!"

def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- IDs ---
CANAL_LOG_STAFF_ID = 1435826826827268178
CANAL_LOG_PLAYER_ID = 1472005008063991969
LINK_TICKET = "https://discord.com/channels/1325138278298550272/1411159343390396477"
CANAL_ENTRADA = 1465403347694522490  # Onde as msgs chegam
LOG_SUCESSO = 1417278744258937005
LOG_ERRO = 1417278747031109662
CARGOS_IGNORADOS = [1411158281409400832]
fuso_br = pytz.timezone('America/Sao_Paulo')
ID_CATEGORIA_DENUNCIA = 1457468204543901908  # Substitua pelo ID da categoria de denúncias
LINK_REGRAS = "https://razerp.gitbook.io/raze-roleplay/punicoes"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- CLASSE DO BOTÃO PARA O ANÚNCIO ---
class AnuncioView(discord.ui.View):
    def __init__(self, label, url):
        super().__init__(timeout=None)
        # Cria o botão de link
        self.add_item(discord.ui.Button(label=label, url=url, style=discord.ButtonStyle.link))
        
# --- FORMULÁRIOS DE MÉTRICAS ---
class FormularioBuscaID(discord.ui.Modal, title="Consultar Histórico"):
    id_input = discord.ui.TextInput(label="ID do Usuário", placeholder="Cole o ID aqui...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = self.id_input.value
        cursor.execute("SELECT codigo_usado, data_hora FROM registros WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
        
        if not rows:
            return await interaction.response.send_message(f"❌ Nenhum registro para o ID `{user_id}`.", ephemeral=True)

        resposta = f"🔍 **Resultados para <@{user_id}>:**\n"
        for i, row in enumerate(rows, 1):
            try:
                data_dt = datetime.datetime.fromisoformat(str(row[1]))
                data_f = data_dt.strftime("%d/%m/%Y %H:%M")
            except:
                data_f = str(row[1])[:16]
            resposta += f"**{i}.** Código: `{row[0]}` — {data_f}\n"
        
        await interaction.response.send_message(resposta, ephemeral=True)

class FormularioLimparID(discord.ui.Modal, title="Limpar Histórico de ID"):
    id_input = discord.ui.TextInput(label="ID do Usuário para Deletar", placeholder="ID aqui...", required=True)
    confirmacao = discord.ui.TextInput(label="Confirmação", placeholder="Digite 'DELETAR' para confirmar", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        if self.confirmacao.value.upper() != "DELETAR":
            return await interaction.response.send_message("❌ Operação cancelada. Você não digitou 'DELETAR'.", ephemeral=True)
        
        user_id = self.id_input.value
        cursor.execute("DELETE FROM registros WHERE user_id = ?", (user_id,))
        conn.commit()
        await interaction.response.send_message(f"✅ Todos os registros do ID `{user_id}` foram removidos com sucesso.", ephemeral=True)
# --- CÓDIGO DE PUNIÇÃO (MANTIDO) ---

class RevogacaoView(discord.ui.View):
    def __init__(self, punido_id):
        super().__init__(timeout=None)
        self.punido_id = punido_id

    @discord.ui.button(label="Solicitar Revisão", style=discord.ButtonStyle.secondary, custom_id="revogar_btn", emoji="⚖️")
    async def revogar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        if interaction.user.id != self.punido_id:
            return await interaction.followup.send("❌ Apenas o usuário punido pode interagir aqui!", ephemeral=True)
        
        try:
            embed_dm = discord.Embed(
                title="⚖️ Revisão de Punição",
                description=f"Olá! Você solicitou a revisão da sua punição no **Raze RP**.\n\nPara prosseguir, abra um ticket em nosso suporte:\n{LINK_TICKET}",
                color=0xf1c40f
            )
            await interaction.user.send(embed=embed_dm)
            await interaction.followup.send("✅ Instruções enviadas no seu privado!", ephemeral=True)
            
            canal_staff = bot.get_channel(CANAL_LOG_STAFF_ID)
            if canal_staff:
                await canal_staff.send(f"🔔 **SOLICITAÇÃO DE REVISÃO:** {interaction.user.mention} (ID: {interaction.user.id}) clicou no botão de revisão.")
        except:
            await interaction.followup.send("❌ Sua DM está fechada! Não consegui enviar as instruções.", ephemeral=True)

class FormularioPunicao(discord.ui.Modal, title="📝 Registrar Punição - Raze RP"):
    usuario_id = discord.ui.TextInput(label="ID do Usuário Punido", placeholder="Ex: 1020", min_length=1, max_length=20)
    motivo = discord.ui.TextInput(label="Motivo da Punição", style=discord.TextStyle.paragraph, placeholder="Descreva o ocorrido...", required=True)
    tempo_adv = discord.ui.TextInput(label="Nível da Advertência", placeholder="Ex: ADV 1, ADV 2...", required=True)
    tempo_ban = discord.ui.TextInput(label="Usuário Banido?", placeholder="SIM ou NÃO", min_length=2, max_length=3)
    amarrado = discord.ui.TextInput(label="Tempo Amarrado (Minutos)", default="0")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            punido = await bot.fetch_user(int(self.usuario_id.value))
            agora = datetime.datetime.now(fuso_br).strftime("%d/%m/%Y %H:%M")

            # --- EMBED PÚBLICA (MAIS BONITA) ---
            embed_pub = discord.Embed(title="⚠️ REGISTRO DE PUNIÇÃO", color=0x2b2d31)
            embed_pub.set_thumbnail(url=punido.display_avatar.url)
            
            embed_pub.description = f"O cidadão {punido.mention} foi punido por violar as diretrizes da cidade."
            
            embed_pub.add_field(name="👤 Infrator", value=f"{punido.name} (`{punido.id}`)", inline=True)
            embed_pub.add_field(name="👮 Responsável", value=f"{interaction.user.mention}", inline=True)
            embed_pub.add_field(name="🚫 Punição", value=f"**{self.tempo_adv.value}**", inline=True)
            
            embed_pub.add_field(name="🔗 Banimento", value=self.tempo_ban.value.upper(), inline=True)
            embed_pub.add_field(name="⏳ Amarrado", value=f"{self.amarrado.value} min", inline=True)
            embed_pub.add_field(name="📅 Data", value=agora, inline=True)
            
            embed_pub.add_field(name="📝 Motivo Detalhado", value=f"```\n{self.motivo.value}\n```", inline=False)
            
            embed_pub.set_footer(text="Raze RP • Sistema de Punições", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)

            canal_player = bot.get_channel(CANAL_LOG_PLAYER_ID)
            if canal_player:
                await canal_player.send(embed=embed_pub, view=RevogacaoView(punido.id))

            # --- EMBED STAFF (LOG INTERNO) ---
            embed_staff = discord.Embed(title="🚨 LOG DE STAFF - PUNIÇÃO", color=0xFF1493)
            embed_staff.add_field(name="Informações", value=f"**Infrator:** {punido.mention}\n**Staff:** {interaction.user.mention}\n**Tipo:** {self.tempo_adv.value}", inline=False)
            embed_staff.add_field(name="Motivo", value=self.motivo.value)
            
            canal_staff = bot.get_channel(CANAL_LOG_STAFF_ID)
            if canal_staff:
                await canal_staff.send(embed=embed_staff)

            await interaction.followup.send(f"✅ Punição de {punido.name} registrada com sucesso!", ephemeral=True)

        except ValueError:
            await interaction.followup.send("❌ O ID do usuário deve conter apenas números!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Erro ao registrar: {str(e)}", ephemeral=True)

@bot.event
async def on_message(message):
    # 1. Ignora mensagens do próprio bot
    if message.author.id == bot.user.id:
        return
        
    # 2. Verifica se a mensagem veio do canal de entrada correto
    if message.channel.id == CANAL_ENTRADA:
        # Tenta separar o ID (primeira parte) do resto (novo nome)
        partes = message.content.split(' ', 1)
        
        if len(partes) < 2:
            return # Mensagem não está no formato "ID Nome"

        try:
            user_id = int(partes[0])
            novo_nome_raw = partes[1]
            novo_nome = f"#{novo_nome_raw}"
            
            guild = message.guild
            member = guild.get_member(user_id)

            # 3. Se o usuário estiver no servidor
            if member:
                # Verifica a Whitelist de cargos (Cargos Ignorados)
                tem_cargo_protegido = any(role.id in CARGOS_IGNORADOS for role in member.roles)

                if tem_cargo_protegido:
                    canal_erro = bot.get_channel(LOG_ERRO)
                    if canal_erro:
                        await canal_erro.send(f"🛡️ **Protegido:** {member.mention} possui um cargo da lista de ignorados.")
                    return

                try:
                    # Altera o apelido
                    await member.edit(nick=novo_nome)
                    canal_sucesso = bot.get_channel(LOG_SUCESSO)
                    if canal_sucesso:
                        await canal_sucesso.send(f"✅ **Sucesso:** {member.mention} renomeado para `{novo_nome}`.")
                
                except discord.Forbidden:
                    canal_erro = bot.get_channel(LOG_ERRO)
                    if canal_erro:
                        await canal_erro.send(f"❌ **Erro de Permissão:** O cargo do bot precisa estar ACIMA do cargo de {member.mention}.")
            
            # 4. Se o usuário NÃO estiver no servidor
            else:
                canal_erro = bot.get_channel(LOG_ERRO)
                if canal_erro:
                    await canal_erro.send(f"⚠️ **Não encontrado:** O ID `{user_id}` não está no servidor.")

        except ValueError:
            # Isso acontece se a primeira parte da mensagem não for um número (ID)
            pass

    # 5. IMPORTANTE: Permite que os outros comandos (!comando) continuem funcionando
    await bot.process_commands(message)
    
@bot.command()
@commands.has_permissions(administrator=True)
async def anuncio(ctx, *, conteudo: str):
    """Formato: !anuncio link_botao mensagem link_imagem"""
    
    await ctx.message.delete()
    
    partes = conteudo.split() # Divide por espaços

    if len(partes) < 3:
        return await ctx.send("❌ Use o formato: `!anuncio link_botao mensagem link_imagem`", delete_after=5)

    link_botao = partes[0]      # Pega o primeiro
    imagem_url = partes[-1]     # Pega o último
    
    # Junta tudo que sobrou no meio para formar a mensagem
    mensagem = " ".join(partes[1:-1])

    embed = discord.Embed(description=mensagem, color=0xFF1493)
    embed.set_image(url=imagem_url)
    embed.set_footer(text="Raze RP - O momento é agora. 🔥")

    view = AnuncioView(label="Entrar no Discord", url=link_botao)

    await ctx.send(embed=embed, view=view)

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_punicao(ctx):
    view = discord.ui.View(timeout=None)
    btn = discord.ui.Button(label="Abrir Registro", style=discord.ButtonStyle.danger)
    async def callback(interaction): await interaction.response.send_modal(FormularioPunicao())
    btn.callback = callback
    view.add_item(btn)
    await ctx.send("🛡️ **Painel de Punições - Raze RP**", view=view)

@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user}')


@bot.event
async def on_guild_channel_create(channel):
    ID_CATEGORIA_DENUNCIA = 123456789012345678  # <--- TROQUE PELO ID DA SUA CATEGORIA
    LINK_REGRAS = "https://linkdasregras.com"    # <--- TROQUE PELO SEU LINK
    
    if channel.category_id == ID_CATEGORIA_DENUNCIA:
        embed = discord.Embed(
            title="🚨 FORMULÁRIO DE DENÚNCIA",
            description=(
                "Olá! Para sua denúncia ser analisada, responda com:\n\n",
                "👤 **Seu Nome e ID:**\n",
                "📅 **Data e Hora:**\n",
                "🆔 **ID do Denunciado:**\n",
                "🎬 **Provas (YouTube ou Medal):**\n",
                "📝 **Motivo Detalhado:**\n\n",
                "⚠️ *Denúncias são resolvidas entre 24h a 48h.*",
            ),
            color=discord.Color.red()
        )
        
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Ver Regras", url=LINK_REGRAS))

        await channel.send(embed=embed, view=view)
        
if __name__ == "__main__":
    Thread(target=run_server).start()
    token = os.environ.get("TOKEN")
    if token: bot.run(token)
