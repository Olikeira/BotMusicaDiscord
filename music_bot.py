import discord
from discord.ext import commands
import yt_dlp
import os
from dotenv import load_dotenv

# --- Carrega as variáveis de ambiente do arquivo .env ---
load_dotenv()

# --- Configuração Inicial ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- Opções para o yt-dlp ---
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

# --- Evento de Inicialização ---
@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')

# --- Comando para Entrar no Canal de Voz ---
@bot.command(name='entrar', help='Faz o bot entrar no seu canal de voz.')
async def entrar(ctx):
    if not ctx.message.author.voice:
        await ctx.send(f'{ctx.message.author.name} não está conectado a um canal de voz.')
        return
    else:
        channel = ctx.message.author.voice.channel
    await channel.connect()

# --- Comando para Sair do Canal de Voz ---
@bot.command(name='sair', help='Faz o bot sair do canal de voz.')
async def sair(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client and voice_client.is_connected(): # Adicionada verificação se voice_client existe
        await voice_client.disconnect()
    else:
        await ctx.send("O bot não está conectado a um canal de voz.")

# --- Comando para Tocar Música ---
@bot.command(name='tocar', help='Toca uma música do YouTube.')
async def tocar(ctx, *, url):
    if not ctx.message.guild.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("Você precisa estar em um canal de voz para tocar música.")
            return

    voice_client = ctx.message.guild.voice_client
    if voice_client.is_playing():
        voice_client.stop()

    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        info = ydl.extract_info(url, download=False)
        audio_url = info['url']

    # CORREÇÃO AQUI: A função da biblioteca é .play()
    voice_client.play(discord.FFmpegPCMAudio(audio_url, **FFMPEG_OPTIONS))
    await ctx.send(f'**Tocando agora:** {info["title"]}')

# --- Comando para Pausar a Música ---
@bot.command(name='pause', help='Pausa a música que está tocando.')
async def pause(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.pause()
    else:
        await ctx.send("Não há música tocando no momento.")

# --- Comando para Retomar a Música ---
@bot.command(name='continuar', help='Retoma a música pausada.')
async def continuar(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client and voice_client.is_paused():
        # CORREÇÃO AQUI: A função da biblioteca é .resume()
        voice_client.resume()
    else:
        await ctx.send("A música não está pausada.")

# --- Comando para Parar a Música ---
@bot.command(name='parar', help='Para a música e limpa a fila.')
async def parar(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client and voice_client.is_playing():
        # CORREÇÃO AQUI: A função da biblioteca é .stop()
        voice_client.stop()
    else:
        await ctx.send("Não há música tocando no momento.")

bot.run('Token do seu bot')
