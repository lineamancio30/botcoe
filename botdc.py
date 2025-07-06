import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput, Select
import datetime
import sqlite3
import json

# Configuração inicial do SQLite
def init_db():
    conn = sqlite3.connect('relatorios.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS relatorios (
            message_id INTEGER PRIMARY KEY,
            oficiais TEXT,
            acao TEXT,
            comando TEXT,
            status TEXT,
            criador INTEGER
        )
    ''')
    conn.commit()
    conn.close()

init_db()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Configuração de canais (substitua pelos IDs reais)
CANAL_CRIAR_RELATORIO = 1356719115842359448
CANAL_RELATORIO_CRIADO = 1356719213384831047

class PersistentView(View):
    def __init__(self):
        super().__init__(timeout=None)

class ConfirmButton(Button):
    def __init__(self):
        super().__init__(
            label="✅ Confirmar Participação", 
            style=discord.ButtonStyle.green, 
            custom_id="confirm_button"
        )
    
    async def callback(self, interaction: discord.Interaction):
        conn = sqlite3.connect('relatorios.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM relatorios WHERE message_id = ?', (interaction.message.id,))
        relatorio = cursor.fetchone()
        
        if not relatorio:
            await interaction.response.send_message("❌ Relatório não encontrado!", ephemeral=True, delete_after=30)
            conn.close()
            return
        
        oficiais = json.loads(relatorio[1]) if relatorio[1] else []
        user_mention = interaction.user.mention
        
        if user_mention in oficiais:
            oficiais.remove(user_mention)
            response_message = "❌ Participação removida!"
            self.style = discord.ButtonStyle.green
            self.label = "✅ Confirmar Participação"
        else:
            oficiais.append(user_mention)
            response_message = "✅ Participação confirmada!"
            self.style = discord.ButtonStyle.red
            self.label = "❌ Remover Confirmação"
        
        cursor.execute('''
            UPDATE relatorios 
            SET oficiais = ? 
            WHERE message_id = ?
        ''', (json.dumps(oficiais), interaction.message.id))
        conn.commit()
        conn.close()
        
        embed = interaction.message.embeds[0]
        embed.set_field_at(
            2, 
            name="Oficiais", 
            value="\n".join(oficiais) or "Nenhum confirmado", 
            inline=True
        )
        
        view = PersistentView()
        view.add_item(ConfirmButton())
        view.add_item(StatusSelect())
        
        await interaction.message.edit(embed=embed, view=view)
        await interaction.response.send_message(
            response_message,
            ephemeral=True,
            delete_after=30
        )

class StatusSelect(Select):
    def __init__(self):
        super().__init__(
            placeholder="Atualizar Status...", 
            options=[
                discord.SelectOption(label="✅ Vitória", value="Vitória"),
                discord.SelectOption(label="❌ Derrota", value="Derrota"),
                discord.SelectOption(label="🔄 Em Andamento", value="Em Andamento")
            ],
            custom_id="status_select"
        )
    
    async def callback(self, interaction: discord.Interaction):
        conn = sqlite3.connect('relatorios.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM relatorios WHERE message_id = ?', (interaction.message.id,))
        relatorio = cursor.fetchone()
        
        if not relatorio:
            await interaction.response.send_message("❌ Relatório não encontrado!", ephemeral=True, delete_after=30)
            conn.close()
            return
        
        if interaction.user.id != relatorio[5]:  # Índice 5 = criador
            await interaction.response.send_message(
                "❌ Apenas o criador do relatório pode atualizar o status!", 
                ephemeral=True,
                delete_after=30
            )
            conn.close()
            return
        
        cursor.execute('''
            UPDATE relatorios 
            SET status = ? 
            WHERE message_id = ?
        ''', (self.values[0], interaction.message.id))
        conn.commit()
        conn.close()
        
        embed = interaction.message.embeds[0]
        embed.set_field_at(1, name="Status", value=self.values[0], inline=True)
        
        await interaction.message.edit(embed=embed)
        await interaction.response.send_message(
            f"✅ Status atualizado para: **{self.values[0]}**", 
            ephemeral=True,
            delete_after=30
        )

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f'Sincronizados {len(synced)} comandos')
        print(f'Bot {bot.user} online!')
    except Exception as e:
        print(f'Erro ao sincronizar comandos: {e}')

@bot.tree.command(name="relatorio", description="Cria um novo relatório")
async def criar_relatorio(interaction: discord.Interaction):
    if interaction.channel_id != CANAL_CRIAR_RELATORIO:
        return await interaction.response.send_message(
            "❌ Use no canal correto!",
            ephemeral=True,
            delete_after=30
        )

    class RelatorioModal(Modal, title="Criar Relatório"):
        acao = TextInput(label="Nome da Ação", placeholder="Ex: Fleeca (Praia)")
        comando = TextInput(label="Comando da Ação", placeholder="Ex: [3°SGT] Lari Butterfly")

        async def on_submit(self, interaction: discord.Interaction):
            embed = discord.Embed(
                title=f"📋 {self.acao.value}",
                color=0x3498db,
                timestamp=datetime.datetime.now()
            )
            embed.add_field(name="Comando da Ação", value=self.comando.value, inline=False)
            embed.add_field(name="Status", value="🔄 Em Andamento", inline=True)
            embed.add_field(name="Oficiais", value="Nenhum confirmado", inline=True)
            embed.set_footer(text=f"Criado por {interaction.user.display_name}")

            view = PersistentView()
            view.add_item(ConfirmButton())
            view.add_item(StatusSelect())

            channel = bot.get_channel(CANAL_RELATORIO_CRIADO)
            msg = await channel.send(embed=embed, view=view)

            conn = sqlite3.connect('relatorios.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO relatorios 
                (message_id, oficiais, acao, comando, status, criador)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                msg.id,
                json.dumps([]),
                self.acao.value,
                self.comando.value,
                "Em Andamento",
                interaction.user.id
            ))
            conn.commit()
            conn.close()

            await interaction.response.send_message(
                "✅ Relatório criado com sucesso!",
                ephemeral=True,
                delete_after=30
            )

    await interaction.response.send_modal(RelatorioModal())

bot.run("MTM1NjY0MDU0NTcyMzc4MTM3MA.GDHRsf._jLKx-w-g9EqoK4tIqnOI4vDslJBmH4N5YZdBg")