import os
import aiohttp

WEBHOOK_URL = os.getenv("LOG_WEBHOOK_URL")


async def send_log(embed: dict):
    async with aiohttp.ClientSession() as session:
        await session.post(WEBHOOK_URL, json={"embeds": [embed]})


async def log_command(ctx, command_name):
    display_name = ctx.author.display_name
    username = str(ctx.author)

    is_dm = ctx.guild is None

    server_name = None
    guild_id = None

    if not is_dm:
        server_name = ctx.guild.name
        guild_id = str(ctx.guild.id)

    embed = {
        "title": f"/{command_name}",
        "color": 0x5865F2,
        "fields": [
            {
                "name": "User",
                "value": f"{display_name} ({username})",
                "inline": False
            },
            {
                "name": "Location",
                "value": "DM" if is_dm else f"{server_name} ({guild_id})",
                "inline": False
            }
        ]
    }

    await send_log(embed)

async def log_interaction(interaction: discord.Interaction, command_name: str):
    display_name = interaction.user.display_name
    username = str(interaction.user)

    is_dm = interaction.guild is None

    server_name = None
    guild_id = None

    if not is_dm:
        server_name = interaction.guild.name
        guild_id = str(interaction.guild.id)

    embed = {
        "title": f"/{command_name}",
        "color": 0x5865F2,
        "fields": [
            {
                "name": "User",
                "value": f"{display_name} ({username})",
                "inline": False
            },
            {
                "name": "Location",
                "value": "DM" if is_dm else f"{server_name} ({guild_id})",
                "inline": False
            }
        ]
    }

    await send_log(embed)