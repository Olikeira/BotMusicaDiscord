import discord
from discord.ext import commands
import yt_dlp
import asyncio
import logging
from functools import partial

# --- Configuração de Logging ---
logging.basicConfig(level=logging.INFO)

# --- Configuração Inicial ---
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- Configurações de Audio ---
YDL_OPTIONS = {
    'format': 'bestaudio[ext=webm]/bestaudio/best',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'extract_flat': False,
    'cachedir': False,
    'geo_bypass': True,
    'prefer_ffmpeg': True
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -rw_timeout 20000000',
    'options': '-vn -threads 1'
}

ytdl = yt_dlp.YoutubeDL(YDL_OPTIONS)

# --- Dados globais ---
guilds_data = {}

class YTDLSource(discord.PCMVolumeTransformer):
    """Classe para source de áudio do YouTube"""
    
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        
    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        """Cria source da URL"""
        loop = loop or asyncio.get_event_loop()
        
        try:
            partial_ytdl = partial(ytdl.extract_info, url, download=not stream)
            data = await loop.run_in_executor(None, partial_ytdl)
            
            if 'entries' in data:
                data = data['entries'][0]
            
            filename = data['url'] if stream else ytdl.prepare_filename(data)
            ffmpeg_source = discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS)
            return cls(ffmpeg_source, data=data)
            
        except Exception as e:
            print(f"[ERRO] Erro ao criar source: {e}")
            return None

class MusicPlayer:
    """Player de música para cada servidor"""
    
    def __init__(self, ctx):
        self.ctx = ctx
        self.bot = ctx.bot
        self.guild_id = ctx.guild.id
        self.queue = asyncio.Queue()
        self.current = None
        self.volume = 0.5
        self.player_task = None
        self.is_playing = False
        
    async def add_song(self, url, title=None):
        """Adiciona música à fila"""
        song_data = {'url': url, 'title': title or url}
        await self.queue.put(song_data)
        
    async def connect_safe(self, channel, max_retries=3):
        """Conecta com retry"""
        for attempt in range(max_retries):
            try:
                print(f"[CONEXAO] Tentativa {attempt + 1}...")
                
                # Desconecta se já conectado
                if self.ctx.voice_client and self.ctx.voice_client.is_connected():
                    await self.ctx.voice_client.disconnect(force=True)
                    await asyncio.sleep(1)
                
                voice_client = await channel.connect(timeout=15.0, reconnect=True)
                print(f"[CONEXAO] Conectado!")
                return voice_client
                
            except Exception as e:
                print(f"[CONEXAO] Erro tentativa {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(3)
                    
        return None
        
    async def start_player(self):
        """Inicia o player"""
        if self.player_task and not self.player_task.done():
            return
            
        self.player_task = self.bot.loop.create_task(self._player_loop())
        
    async def stop_player(self):
        """Para o player"""
        if self.player_task:
            self.player_task.cancel()
            
        voice_client = self.ctx.voice_client
        if voice_client:
            voice_client.stop()
            
    async def _player_loop(self):
        """Loop principal do player"""
        await self.bot.wait_until_ready()
        
        while True:
            try:
                # Espera música na fila
                try:
                    song = await asyncio.wait_for(self.queue.get(), timeout=300.0)
                except asyncio.TimeoutError:
                    await self.ctx.send("[TIMEOUT] Desconectando por inatividade...")
                    break
                
                # Conecta se necessário
                voice_client = self.ctx.voice_client
                if not voice_client or not voice_client.is_connected():
                    voice_client = await self.connect_safe(self.ctx.author.voice.channel)
                    if not voice_client:
                        await self.ctx.send("[ERRO] Falha ao conectar!")
                        continue
                
                # Carrega e toca música
                await self.ctx.send(f"[CARREGANDO] {song['title']}")
                
                try:
                    source = await YTDLSource.from_url(song['url'], loop=self.bot.loop, stream=True)
                    if not source:
                        await self.ctx.send(f"[ERRO] Falha ao carregar: {song['title']}")
                        continue
                        
                    source.volume = self.volume
                    self.current = song
                    self.is_playing = True
                    
                    voice_client.play(source, after=lambda e: print(f'Player error: {e}') if e else None)
                    
                    duration_str = ""
                    if source.duration:
                        mins, secs = divmod(source.duration, 60)
                        duration_str = f" [{int(mins):02d}:{int(secs):02d}]"
                        
                    await self.ctx.send(f"[TOCANDO] {source.title}{duration_str}")
                    
                    # Espera terminar
                    while voice_client.is_playing() or voice_client.is_paused():
                        if not voice_client.is_connected():
                            print("[ERRO] Conexao perdida")
                            break
                        await asyncio.sleep(1)
                        
                except Exception as e:
                    await self.ctx.send(f"[ERRO] Erro ao tocar: {song['title']}")
                    print(f"Erro no player: {e}")
                    
                finally:
                    self.current = None
                    self.is_playing = False
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Erro crítico: {e}")
                await asyncio.sleep(2)
                
        # Desconecta ao sair
        voice_client = self.ctx.voice_client
        if voice_client and voice_client.is_connected():
            await voice_client.disconnect()

def get_player(ctx):
    """Obtém player do servidor"""
    guild_id = ctx.guild.id
    if guild_id not in guilds_data:
        guilds_data[guild_id] = {'player': MusicPlayer(ctx)}
    return guilds_data[guild_id]['player']

# --- Eventos ---
@bot.event
async def on_ready():
    print(f'[BOT] {bot.user} esta online!')

@bot.event
async def on_voice_state_update(member, before, after):
    """Auto-desconexão quando fica sozinho"""
    if member.bot:
        return
        
    if before.channel and before.channel.guild.voice_client:
        voice_client = before.channel.guild.voice_client
        
        if voice_client.channel == before.channel:
            remaining = [m for m in before.channel.members if not m.bot]
            
            if len(remaining) == 0:
                await asyncio.sleep(10)
                if len([m for m in before.channel.members if not m.bot]) == 0:
                    guild_id = before.channel.guild.id
                    if guild_id in guilds_data:
                        await guilds_data[guild_id]['player'].stop_player()
                    await voice_client.disconnect()

# --- Comandos ---
@bot.command(name='entrar', help='Bot entra no canal de voz')
async def entrar(ctx):
    """Bot entra no canal"""
    if not ctx.author.voice:
        return await ctx.send("[ERRO] Voce nao esta em um canal de voz!")
    
    channel = ctx.author.voice.channel
    player = get_player(ctx)
    
    voice_client = await player.connect_safe(channel)
    if voice_client:
        await ctx.send(f"[CONECTADO] Entrei no canal {channel.name}")
    else:
        await ctx.send("[ERRO] Nao consegui conectar!")

@bot.command(name='sair', help='Bot sai do canal de voz')
async def sair(ctx):
    """Bot sai do canal"""
    guild_id = ctx.guild.id
    
    if guild_id in guilds_data:
        await guilds_data[guild_id]['player'].stop_player()
        
    voice_client = ctx.voice_client
    if voice_client:
        await voice_client.disconnect()
        await ctx.send("[SAINDO] Desconectado!")
    else:
        await ctx.send("[ERRO] Nao estou conectado!")

@bot.command(name='tocar', aliases=['play', 'p'], help='Toca uma música')
async def tocar(ctx, *, pesquisa: str):
    """Toca música do YouTube"""
    if not ctx.author.voice:
        return await ctx.send("[ERRO] Voce precisa estar em um canal de voz!")
    
    player = get_player(ctx)
    
    # Conecta se necessário
    if not ctx.voice_client:
        voice_client = await player.connect_safe(ctx.author.voice.channel)
        if not voice_client:
            return await ctx.send("[ERRO] Nao consegui conectar!")
    
    await ctx.send("[BUSCANDO] Procurando musica...")
    
    try:
        # Busca música
        loop = asyncio.get_event_loop()
        partial_ytdl = partial(ytdl.extract_info, pesquisa, download=False)
        data = await loop.run_in_executor(None, partial_ytdl)
        
        if 'entries' in data:
            data = data['entries'][0]
            
        # Adiciona à fila
        await player.add_song(data['webpage_url'], data['title'])
        
        duration_str = ""
        if data.get('duration'):
            mins, secs = divmod(data['duration'], 60)
            duration_str = f" [{int(mins):02d}:{int(secs):02d}]"
            
        await ctx.send(f"[ADICIONADO] {data['title']}{duration_str}")
        
        # Inicia player
        await player.start_player()
        
    except Exception as e:
        await ctx.send(f"[ERRO] Erro ao buscar: {str(e)}")

@bot.command(name='pause', help='Pausa a música')
async def pause(ctx):
    """Pausa música"""
    voice_client = ctx.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await ctx.send("[PAUSADO] Musica pausada!")
    else:
        await ctx.send("[ERRO] Nada tocando!")

@bot.command(name='continuar', aliases=['resume'], help='Retoma música pausada')
async def continuar(ctx):
    """Retoma música"""
    voice_client = ctx.voice_client
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await ctx.send("[RETOMADO] Musica retomada!")
    else:
        await ctx.send("[ERRO] Musica nao pausada!")

@bot.command(name='parar', aliases=['stop'], help='Para a música')
async def parar(ctx):
    """Para música"""
    guild_id = ctx.guild.id
    
    if guild_id in guilds_data:
        await guilds_data[guild_id]['player'].stop_player()
        
    voice_client = ctx.voice_client
    if voice_client:
        voice_client.stop()
        await ctx.send("[PARADO] Musica parada!")
    else:
        await ctx.send("[ERRO] Nada tocando!")

@bot.command(name='pular', aliases=['skip', 's'], help='Pula música atual')
async def pular(ctx):
    """Pula música"""
    voice_client = ctx.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await ctx.send("[PULADO] Musica pulada!")
    else:
        await ctx.send("[ERRO] Nada tocando!")

@bot.command(name='volume', aliases=['vol'], help='Ajusta volume (0-100)')
async def volume(ctx, vol: int = None):
    """Controla volume"""
    voice_client = ctx.voice_client
    
    if not voice_client or not voice_client.source:
        return await ctx.send("[ERRO] Nada tocando!")
    
    if vol is None:
        current_vol = int(voice_client.source.volume * 100)
        return await ctx.send(f"[VOLUME] Volume atual: {current_vol}%")
    
    if not 0 <= vol <= 100:
        return await ctx.send("[ERRO] Volume deve ser 0-100!")
    
    voice_client.source.volume = vol / 100
    guild_id = ctx.guild.id
    if guild_id in guilds_data:
        guilds_data[guild_id]['player'].volume = vol / 100
        
    await ctx.send(f"[VOLUME] Volume: {vol}%")

@bot.command(name='tocando', aliases=['np'], help='Mostra música atual')
async def tocando(ctx):
    """Mostra música atual"""
    guild_id = ctx.guild.id
    
    if guild_id not in guilds_data:
        return await ctx.send("[ERRO] Nada tocando!")
    
    player = guilds_data[guild_id]['player']
    
    if not player.current:
        return await ctx.send("[ERRO] Nada tocando!")
    
    embed = discord.Embed(
        title="[TOCANDO AGORA]",
        description=player.current['title'],
        color=0x00ff00
    )
    
    await ctx.send(embed=embed)

bot.run('TOKEN_DO_SEU_BOT')
