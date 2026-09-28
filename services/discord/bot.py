import os

import discord
import wavelink

TOKEN = os.environ.get("DISCORD_TOKEN", "").strip()
HEALTH_URL = os.environ.get("HEALTH_URL", "http://server-dashboard:8000/health")
LAVALINK_URL = os.environ.get("LAVALINK_URL", "http://server-lavalink:2333")
LAVALINK_PASSWORD = os.environ.get("LAVALINK_PASSWORD", "").strip()

if not TOKEN:
    raise SystemExit("DISCORD_TOKEN is empty. Set it in .env before enabling the discord profile.")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)


async def connect_lavalink() -> None:
    if not LAVALINK_PASSWORD:
        print("LAVALINK_PASSWORD is empty. Music commands will fail until it is set.")
        return
    node = wavelink.Node(uri=LAVALINK_URL, password=LAVALINK_PASSWORD)
    await wavelink.Pool.connect(nodes=[node], client=client)


def player_for(interaction: discord.Interaction) -> wavelink.Player | None:
    voice = interaction.guild.voice_client if interaction.guild else None
    return voice if isinstance(voice, wavelink.Player) else None


@tree.command(name="server", description="Check whether the server health endpoint is online")
async def server_status(interaction: discord.Interaction) -> None:
    import urllib.request

    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=5) as response:
            body = response.read().decode()
    except Exception:
        await interaction.response.send_message("The server health check did not respond.")
        return
    if '"online"' in body.replace(" ", ""):
        await interaction.response.send_message("The server is online.")
        return
    await interaction.response.send_message("The server health check did not report online.")


@tree.command(name="play", description="Play a SoundCloud link or a direct audio URL")
async def play(interaction: discord.Interaction, url: str) -> None:
    member = interaction.user
    channel = getattr(getattr(member, "voice", None), "channel", None)
    if channel is None or interaction.guild is None:
        await interaction.response.send_message("Join a voice channel first.")
        return
    await interaction.response.defer()
    player = player_for(interaction)
    if player is None:
        player = await channel.connect(cls=wavelink.Player)
    tracks = await wavelink.Playable.search(url)
    if isinstance(tracks, wavelink.Playlist):
        chosen = tracks.tracks
    else:
        chosen = list(tracks or [])
    if not chosen:
        await interaction.followup.send("No playable audio was found. YouTube is turned off. Use SoundCloud or a direct audio URL.")
        return
    track = chosen[0]
    if player.playing:
        await player.queue.put(track)
        await interaction.followup.send(f"Queued {track.title}")
        return
    await player.play(track)
    await interaction.followup.send(f"Playing {track.title}")


@tree.command(name="skip", description="Skip the current track")
async def skip(interaction: discord.Interaction) -> None:
    player = player_for(interaction)
    if player is None or not player.playing:
        await interaction.response.send_message("Nothing is playing.")
        return
    await player.skip()
    await interaction.response.send_message("Skipped.")


@tree.command(name="stop", description="Stop playback and leave the voice channel")
async def stop(interaction: discord.Interaction) -> None:
    player = player_for(interaction)
    if player is None:
        await interaction.response.send_message("The bot is not in a voice channel.")
        return
    await player.disconnect()
    await interaction.response.send_message("Stopped.")


@tree.command(name="queue", description="Show the upcoming tracks")
async def queue(interaction: discord.Interaction) -> None:
    player = player_for(interaction)
    if player is None or (not player.playing and player.queue.is_empty):
        await interaction.response.send_message("The queue is empty.")
        return
    lines = []
    if player.current:
        lines.append(f"Now: {player.current.title}")
    for index, track in enumerate(player.queue, start=1):
        lines.append(f"{index}. {track.title}")
        if index == 10:
            break
    await interaction.response.send_message("\n".join(lines))


@client.event
async def on_ready() -> None:
    try:
        await connect_lavalink()
    except Exception as exc:
        print(f"Lavalink did not connect: {exc}")
    await tree.sync()
    print(f"discord bot connected as {client.user}")


client.run(TOKEN)
