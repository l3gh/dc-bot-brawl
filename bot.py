#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║           Brawl Stars Discord Bot  —  bot.py             ║
╚══════════════════════════════════════════════════════════╝    
"""

import asyncio
import re
import io
import os
import sqlite3
from datetime import datetime, timedelta, timezone

import aiohttp
import discord
import matplotlib
matplotlib.use("Agg")  # non-interactive backend — must be before other mpl imports
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from logger import log_command
from logger import log_interaction

load_dotenv()

DISCORD_TOKEN: str        = os.getenv("DISCORD_TOKEN", "")
BS_API_KEY:    str        = os.getenv("BS_API_KEY", "")
GUILD_ID:      int | None = int(gid) if (gid := os.getenv("GUILD_ID")) else None

BS_BASE = "https://api.brawlstars.com/v1"
BS_BLUE = 0x1565C0
BS_GOLD = 0xF4B400
BS_RED  = 0xD32F2F

# ══════════════════════════════════════════════════════════
#  DATABASE  (SQLite — zero extra deps)
# ══════════════════════════════════════════════════════════

DB_PATH = "linked_tags.db"


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def db_init() -> None:
    with _db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS linked_tags (
                discord_id INTEGER PRIMARY KEY,
                bs_tag     TEXT NOT NULL,
                linked_at  TEXT NOT NULL
            )
        """)



def db_get(discord_id: int) -> str | None:
    with _db() as con:
        row = con.execute(
            "SELECT bs_tag FROM linked_tags WHERE discord_id = ?", (discord_id,)
        ).fetchone()
    return row["bs_tag"] if row else None


def db_set(discord_id: int, tag: str) -> None:
    with _db() as con:
        con.execute(
            "INSERT OR REPLACE INTO linked_tags VALUES (?, ?, ?)",
            (discord_id, tag, datetime.now(timezone.utc).isoformat()),
        )


def db_delete(discord_id: int) -> None:
    with _db() as con:
        con.execute("DELETE FROM linked_tags WHERE discord_id = ?", (discord_id,))





# ══════════════════════════════════════════════════════════
#  API WRAPPER
# ══════════════════════════════════════════════════════════


class BSError(Exception):
    def __init__(self, status: int, reason: str, message: str) -> None:
        self.status  = status
        self.reason  = reason
        self.message = message
        super().__init__(f"{status} {reason}: {message}")


def _norm(tag: str) -> str:
    """Strip # and uppercase."""
    return tag.lstrip("#").strip().upper()


def _norm_tag(t: str) -> str:
    return re.sub(r'[^A-Z0-9]', '', t.upper())

def _enc(tag: str) -> str:
    """URL-encode tag for API path."""
    return f"%23{_norm(tag)}"


async def bs_get(session: aiohttp.ClientSession, path: str) -> dict | list:
    url     = f"{BS_BASE}{path}"
    headers = {"Authorization": f"Bearer {BS_API_KEY}"}
    async with session.get(url, headers=headers) as resp:
        data = await resp.json(content_type=None)
        if resp.status != 200:
            raise BSError(
                resp.status,
                data.get("reason", "unknown"),
                data.get("message", str(data)),
            )
        return data


# ══════════════════════════════════════════════════════════
#  BOT SETUP
# ══════════════════════════════════════════════════════════

intents = discord.Intents.default()
bot = commands.Bot(
    command_prefix="bs!",
    intents=intents,
)


@bot.event
async def on_ready() -> None:
    db_init()

    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} global commands.")
    except Exception as e:
        print(f"Sync failed: {e}")

    print(f"Successfully logged in as {bot.user} ({bot.user.id})")


# ══════════════════════════════════════════════════════════
#  SHARED HELPERS
# ══════════════════════════════════════════════════════════


async def resolve_tag(
    interaction: discord.Interaction,
    user: discord.User | None,
    tag: str | None,
) -> str:
    """
    Priority: explicit tag > mentioned user's linked tag > author's linked tag.
    Raises ValueError with a user-friendly message if no tag can be found.
    """
    if tag:
        return _norm(tag)
    target = user or interaction.user
    linked = db_get(target.id)
    if linked:
        return _norm(linked)
    if target == interaction.user:
        raise ValueError(
            "You haven't linked a tag yet. Use `/link <tag>` first, "
            "or pass `tag:` directly in this command."
        )
    raise ValueError(f"{target.mention} hasn't linked a Brawl Stars tag.")


def _embed(title: str = "", desc: str = "", color: int = BS_BLUE) -> discord.Embed:
    em = discord.Embed(title=title, description=desc, color=color)
    em.set_footer(text="Brawl Stars Bot  •  api.brawlstars.com")
    return em


def _err(msg: str) -> discord.Embed:
    return discord.Embed(description=f"<:cross:1497235501214863522>  {msg}", color=BS_RED)


def _items(data: dict | list) -> list:
    if isinstance(data, list):
        return data
    return data.get("items", [])



MODE_EMOJI: dict[str, str] = { # maybe ill go and get emojis for all of them idk
    "gemGrab":       "<:gemgrab:1495579848867975249>",
    "brawlBall":     "<:brawlball:1495579359845679215>",
    "bounty":        "<:bounty:1495581805762449669>",
    "heist":         "<:heist:1495579845499949146>",
    "siege":         "<:siege:1497239492661346504>",
    "hotZone":       "<:hotzone:1495579847131398294>",
    "knockout":      "<:knockout:1495579842505085028>",
    "basketBrawl":   "<:basketbrawl:1495571795553513472>",
    "volleyBrawl":   "<:volleybrawl:1497904782835318884>",
    "duoShowdown":   "<:duoSD:1495579852282007633>",
    "soloShowdown":  "<:soloSD:1495579853993410683>",
    "trioShowdown":  "<:trioSD:1495579850264805487>",
    "superCity":     "<:supercityrampage:1497229696067174400>",
    "roboRumble":    "<:roborumble:1497229699603103854>",
    "bigGame":       "<:biggame:1495581801643642980>",
    "duels":         "<:duels:1495582888513638420>",
    "wipeout":       "<:wipeout:1497905333660549240>",
    "payload":       "<:payload:1497905622417412187>",
    "holdTheTrophy": "<:holdthetrophy:1497239159524294828>",
    "trophyThieves": "<:holdthetrophy:1497239159524294828>",
    "brawlTV":       "<:brawlTV:1495581804327993424>",
    "ranked":        "<:ranked:1495581799441633350>",
    "info":          "<:info:1495581796849553499>",
    "tagTeam":       "<:duels:1495582888513638420>",
}

def _fmt_mode(mode: str) -> str:
    """camelCase → Title Case fallback for unknown modes."""
    return re.sub(r"([A-Z])", r" \1", mode).title().strip()


MODE_NAME: dict[str, str] = {
    "gemGrab":       "Gem Grab",
    "brawlBall":     "Brawl Ball",
    "bounty":        "Bounty",
    "heist":         "Heist",
    "siege":         "Siege",
    "hotZone":       "Hot Zone",
    "knockout":      "Knockout",
    "basketBrawl":   "Basket Brawl",
    "volleyBrawl":   "Volley Brawl",
    "duoShowdown":   "Duo Showdown",
    "soloShowdown":  "Solo Showdown",
    "trioShowdown":  "Trio Showdown",
    "superCity":     "Super City Rampage",
    "roboRumble":    "Robo Rumble",
    "bigGame":       "Big Game",
    "duels":         "Duels",
    "wipeout":       "Wipeout",
    "payload":       "Payload",
    "holdTheTrophy": "Hold The Trophy",
    "trophyThieves": "Trophy Thieves",
    "brawlTV":       "Brawl TV",
    "ranked":        "Ranked",
    "info":          "Info",
    "tagTeam": "Duels",
}

ROLE_EMOJI: dict[str, str] = {
    "president":     "<:clmasters:1497908243756875856>",
    "vicePresident": "<:cldiamond3:1497908231232684114>",
    "senior":        "<:clgold2:1497908224320471081>",
    "member":        "<:clsilver1:1497908217299341432>",
}
ROLE_ORDER: dict[str, int] = {
    "president": 0, "vicePresident": 1, "senior": 2, "member": 3,
}

RESULT_ICON: dict[str, str] = {
    "victory": "<:check:1497235498668789800>", "defeat": "<:cross:1497235501214863522>", "draw": "<:heartfire:1497909601805271180>",
}



# ══════════════════════════════════════════════════════════
#  GRAPH BUILDER
# ══════════════════════════════════════════════════════════




# ══════════════════════════════════════════════════════════
#  GRAPH HELPERS
# ══════════════════════════════════════════════════════════

_BG      = "#0B0C18"
_PLOT_BG = "#11121F"
_GOLD    = "#F7C948"
_GOLDDIM = "#C49B20"
_ACCENT  = "#4FC3F7"
_TEXT_HI = "#FFFFFF"
_TEXT_LO = "#8E90AA"
_GRID    = "#1E2035"

_BS_TIME_FMT = "%Y%m%dT%H%M%S.%fZ"


def _parse_bs_time(raw: str) -> datetime:
    """Parse Brawl Stars battleTime string → UTC datetime."""
    try:
        dt = datetime.strptime(raw, _BS_TIME_FMT)
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def battlelog_to_trophy_history(
    battles: list[dict],
    current_trophies: int,
) -> list[int]:
    """
    Reconstruct trophy counts per ranked battle, ordered oldest → newest.
    X-axis is battle index, not time — avoids distortion from uneven play sessions.
    Returns a list of trophy counts (one per ranked battle + the "before" starting point).
    """
    ranked_tcs: list[int] = []
    for b in battles:
        tc = b.get("battle", {}).get("trophyChange")
        if tc is None:
            continue
        ranked_tcs.append(int(tc))

    if not ranked_tcs:
        return []

    points: list[int] = []
    running = current_trophies
    for tc in ranked_tcs:
        points.append(running)
        running -= tc

    points.append(running)
    points.reverse()
    return points


def build_trophy_graph(
    tag: str,
    player_name: str,
    history: list[int],
    current_trophies: int,
    best_trophies: int,
    battle_count: int,
) -> io.BytesIO:
    """
    Render a dark-themed trophy-per-battle chart.
    X-axis = battle number (1 = oldest), no timestamps.
    Returns a BytesIO PNG.
    """
    trophies = history
    xs       = list(range(len(trophies)))

    median   = sorted(trophies)[len(trophies) // 2]
    trophies = [max(min(t, median * 2), 0) for t in trophies]

    fig, ax = plt.subplots(figsize=(11, 5.2), dpi=150)
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_PLOT_BG)
    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.yaxis.grid(True, color=_GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)

    # ── gradient fill ─────────────────────────────────────
    y_floor  = min(trophies) - (max(trophies) - min(trophies)) * 0.05
    n_strips = 50
    for i in range(n_strips):
        frac  = i / n_strips
        alpha = 0.22 * (1 - frac) ** 1.8
        ax.fill_between(
            xs, y_floor, trophies,
            where=[t >= y_floor + frac * (max(trophies) - y_floor) for t in trophies],
            color=_GOLDDIM, alpha=alpha, zorder=1, linewidth=0,
        )

    # ── glow + line ───────────────────────────────────────
    ax.plot(xs, trophies, color=_GOLD, linewidth=6,   alpha=0.15, zorder=2)
    ax.plot(xs, trophies, color=_GOLD, linewidth=1.9, alpha=1.0,  zorder=3)

    # ── dots — each one is a real battle ─────────────────
    ax.scatter(xs, trophies,
               s=24, color=_PLOT_BG, edgecolors=_GOLD, linewidths=1.4, zorder=4)
    ax.scatter([xs[-1]], [trophies[-1]], s=70, color=_GOLD, zorder=5)

    # ── y-axis limits (must come before PB line check) ───
    spread   = max(trophies) - min(trophies) or 50
    padding  = max(spread * 0.25, 30)
    y_bottom = min(trophies) - padding
    y_top    = max(trophies) + padding
    ax.set_ylim(y_bottom, y_top)

    # ── best-ever line (only if it fits in the visible range) ─
    if best_trophies > max(trophies) and best_trophies <= y_top:
        ax.axhline(best_trophies, color=_ACCENT, linewidth=1.1,
                   linestyle="--", alpha=0.55, zorder=3)
        ax.text(xs[0], best_trophies,
                f"  PB: {best_trophies:,}",
                color=_ACCENT, fontsize=7.5, va="bottom",
                fontfamily="DejaVu Sans")

    # ── x-axis: integer battle numbers ───────────────────
    ax.tick_params(colors=_TEXT_LO, labelsize=8.5, length=0, pad=6)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True, nbins=10))
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(
        lambda v, _: f"#{int(v)}" if 0 < v <= battle_count else ""
    ))

    # ── x-axis labels: "oldest" / "now" ──────────────────
    ax.set_xlim(-0.5, len(xs) - 0.5)
    ax.text(xs[0],  y_bottom, " oldest", color=_TEXT_LO, fontsize=7.5,
            ha="left",  va="bottom", fontfamily="DejaVu Sans")
    ax.text(xs[-1], y_bottom, "now ", color=_TEXT_LO, fontsize=7.5,
            ha="right", va="bottom", fontfamily="DejaVu Sans")

    # ── current value annotation ──────────────────────────
    ax.annotate(
        f"  {trophies[-1]:,}",
        xy=(xs[-1], trophies[-1]),
        xytext=(8, 4), textcoords="offset points",
        color=_GOLD, fontsize=9.5, fontweight="bold",
        fontfamily="DejaVu Sans",
    )

    # ── net delta badge ───────────────────────────────────
    delta     = trophies[-1] - trophies[0]
    delta_str = f"{'▲' if delta >= 0 else '▼'} {abs(delta):,}"
    delta_col = "#69F0AE" if delta >= 0 else "#FF5252"
    ax.text(0.012, 0.96, delta_str,
            transform=ax.transAxes, color=delta_col,
            fontsize=11.5, fontweight="bold", va="top",
            fontfamily="DejaVu Sans")

    # ── watermark ─────────────────────────────────────────
    ax.text(0.99, 0.03,
            f"last {battle_count} ranked battles",
            transform=ax.transAxes, color=_TEXT_LO,
            fontsize=7.5, ha="right", va="bottom",
            fontfamily="DejaVu Sans")

    # ── title ─────────────────────────────────────────────
    fig.text(0.065, 0.965, f"{player_name}  •  #{tag}",
             color=_TEXT_HI, fontsize=14, fontweight="bold",
             va="top", fontfamily="DejaVu Sans")
    fig.text(0.065, 0.895, "Trophy Progress  —  last 25 battles",
             color=_TEXT_LO, fontsize=9, va="top",
             fontfamily="DejaVu Sans")

    plt.tight_layout(rect=[0, 0, 1, 0.87])

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor=_BG, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


# ══════════════════════════════════════════════════════════
#  /link  /unlink  /whoami  /tagof
# ══════════════════════════════════════════════════════════


@bot.tree.command(name="link", description="Link your Brawl Stars tag to your Discord account.")
@app_commands.describe(tag="Your Brawl Stars player tag  (e.g. #ABC123)")
async def link_cmd(interaction: discord.Interaction, tag: str) -> None:
    await log_interaction(interaction, "link")
    await interaction.response.defer(ephemeral=True)
    clean = _norm(tag)
    async with aiohttp.ClientSession() as s:
        try:
            p = await bs_get(s, f"/players/{_enc(clean)}")
        except BSError as e:
            await interaction.followup.send(
                embed=_err(f"Couldn't verify `#{clean}` with the API: {e.message}"),
                ephemeral=True,
            )
            return
    db_set(interaction.user.id, clean)
    em = _embed("<:check:1497235498668789800>  Tag Linked", color=0x2E7D32)
    em.add_field(name="Tag",      value=f"#{clean}",                   inline=True)
    em.add_field(name="Name",     value=p.get("name", "?"),            inline=True)
    em.add_field(name="Trophies", value=f"{p.get('trophies',0):,} <:trophy:1497229732448829580>", inline=True)
    await interaction.followup.send(embed=em, ephemeral=True)


@bot.tree.command(name="unlink", description="Remove your linked Brawl Stars tag.")
async def unlink_cmd(interaction: discord.Interaction) -> None:
    await log_interaction(interaction, "unlink")
    if not db_get(interaction.user.id):
        await interaction.response.send_message(
            embed=_err("You don't have a linked tag."), ephemeral=True
        )
        return
    db_delete(interaction.user.id)
    await interaction.response.send_message(
        embed=discord.Embed(description="<:check:1497235498668789800>  Tag unlinked.", color=0x2E7D32),
        ephemeral=True,
    )


@bot.tree.command(name="whoami", description="Show your currently linked Brawl Stars tag.")
async def whoami_cmd(interaction: discord.Interaction) -> None:
    await log_interaction(interaction, "whoami")
    tag = db_get(interaction.user.id)
    if not tag:
        await interaction.response.send_message(
            embed=_err("No tag linked. Use `/link <tag>`."), ephemeral=True
        )
        return
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"Your linked tag: **#{tag}**", color=BS_BLUE
        ),
        ephemeral=True,
    )


@bot.tree.command(name="tagof", description="See which Brawl Stars tag another Discord user has linked.")
@app_commands.describe(user="The Discord user to look up")
async def tagof_cmd(interaction: discord.Interaction, user: discord.User) -> None:
    await log_interaction(interaction, "tagof")
    tag = db_get(user.id)
    if not tag:
        await interaction.response.send_message(
            embed=_err(f"{user.mention} hasn't linked a tag."), ephemeral=True
        )
        return
    await interaction.response.send_message(
        embed=discord.Embed(
            description=f"{user.mention}'s linked tag: **#{tag}**", color=BS_BLUE
        )
    )


# ══════════════════════════════════════════════════════════
#  /profile
# ══════════════════════════════════════════════════════════


@bot.tree.command(name="profile", description="Full Brawl Stars player profile.")
@app_commands.describe(
    user="Discord user (uses their linked tag)",
    tag="Explicit Brawl Stars player tag",
)
async def profile_cmd(
    interaction: discord.Interaction,
    user: discord.User | None = None,
    tag: str | None = None,
) -> None:
    await log_interaction(interaction, "profile")
    await interaction.response.defer()
    try:
        bs_tag = await resolve_tag(interaction, user, tag)
    except ValueError as e:
        await interaction.followup.send(embed=_err(str(e)))
        return

    async with aiohttp.ClientSession() as s:
        try:
            p = await bs_get(s, f"/players/{_enc(bs_tag)}")
        except BSError as e:
            await interaction.followup.send(embed=_err(f"API {e.status}: {e.message}"))
            return

    club = p.get("club", {})
    em   = _embed(f"{p.get('name','?')}  •  #{bs_tag}")
    em.add_field(name="<:trophy:1497229732448829580> Trophies",        value=f"{p.get('trophies',0):,}",          inline=True)
    em.add_field(name="<:trophyprestige:1497913518912176268> Best Ever",        value=f"{p.get('highestTrophies',0):,}",   inline=True)
    em.add_field(name="<:experience:1497229724752285779> Exp Level",        value=str(p.get("expLevel", "?")),         inline=True)
    em.add_field(name="⚡ 3v3 Wins",         value=f"{p.get('3vs3Victories',0):,}",     inline=True)
    em.add_field(name="<:sdwins:1497912798464704533> Solo Wins",        value=f"{p.get('soloVictories',0):,}",     inline=True)
    em.add_field(name="<:duowins:1497913079218835496> Duo Wins",         value=f"{p.get('duoVictories',0):,}",      inline=True)
    em.add_field(name="🥊 Brawlers",         value=str(len(p.get("brawlers", []))),     inline=True)
    # em.add_field(name="🤖 Best Robo Time",   value=str(p.get("bestRoboRumbleTime", 0)), inline=True)
    # em.add_field(name="👾 Best Big Brawler", value=str(p.get("bestTimeAsBigBrawler",0)),inline=True)
    if club:
        em.add_field(name="<:club:1497225670831374519> Club", value=club.get("name", "?"), inline=False)
    await interaction.followup.send(embed=em)


# ══════════════════════════════════════════════════════════
#  /battlelog
# ══════════════════════════════════════════════════════════


@bot.tree.command(name="battlelog", description="Recent battle log for a player.")
@app_commands.describe(
    user="Discord user (uses their linked tag)",
    tag="Explicit player tag",
    count="Battles to show (1–25, default 15)",
)
async def battlelog_cmd(
    interaction: discord.Interaction,
    user: discord.User | None = None,
    tag: str | None = None,
    count: app_commands.Range[int, 1, 25] = 15,
) -> None:
    await log_interaction(interaction, "battlelog")
    await interaction.response.defer()
    try:
        bs_tag = await resolve_tag(interaction, user, tag)
    except ValueError as e:
        await interaction.followup.send(embed=_err(str(e)))
        return

    async with aiohttp.ClientSession() as s:
        try:
            log_data, p = await asyncio.gather(
                bs_get(s, f"/players/{_enc(bs_tag)}/battlelog"),
                bs_get(s, f"/players/{_enc(bs_tag)}"),
            )
        except BSError as e:
            await interaction.followup.send(embed=_err(f"API {e.status}: {e.message}"))
            return

    battles = _items(log_data)[:count]
    if not battles:
        await interaction.followup.send(embed=_err("No recent battles found."))
        return

    lines: list[str] = []
    for b in battles:
        event  = b.get("event", {})
        battle = b.get("battle", {})
        mode = event.get("mode") or battle.get("mode", "unknown")
        result = battle.get("result")

        all_entries: list[dict] = []

        players = battle.get("players") or []
        teams   = battle.get("teams") or []

        all_entries.extend(players)

        for team in teams:
            if isinstance(team, list):
                all_entries.extend(team)
            elif isinstance(team, dict):
                all_entries.extend(team.get("players", []))
        rank    = battle.get("rank")
        tc      = battle.get("trophyChange")
        brawler = None
        for entry in all_entries:
            if _norm_tag(entry.get("tag", "")) != _norm_tag(bs_tag):
                continue
            if rank is None:
                rank = entry.get("rank")
            if tc is None:
                tc = entry.get("trophyChange")
            brawler_data = entry.get("brawler")
            brawlers_data = entry.get("brawlers")  # duels only

            if isinstance(brawler_data, dict):
                brawler = brawler_data.get("name")
                if tc is None:
                    tc = entry.get("trophyChange")
            elif isinstance(brawlers_data, list) and brawlers_data:
                brawler = " / ".join(b.get("name", "?").title() for b in brawlers_data)
                if tc is None:
                    tc = sum(b.get("trophyChange", 0) for b in brawlers_data)
            break

        label     = (brawler or "brawler error <:warn:1497917334722052136>").title()
        emoji     = MODE_EMOJI.get(mode, "🎮")
        res_icon  = f"`#{rank}`" if rank is not None else RESULT_ICON.get(result, "❓")
        tc_str    = f"  ({'+' if tc and tc > 0 else ''}{tc}<:trophy:1497229732448829580>)" if tc is not None else ""
        mode_name = MODE_NAME.get(mode, "mode name error <:warn:1497917334722052136>")
        lines.append(f"{res_icon} {emoji} **{mode_name}** · {label}{tc_str}")

    em = _embed(f"<:mapmaker:1497229729944571984>  Battle Log — {p.get('name','?')} #{bs_tag}")
    em.description = "\n".join(lines)
    em.set_footer(text=f"Last {len(battles)} battles  •  api.brawlstars.com")
    await interaction.followup.send(embed=em)



# ══════════════════════════════════════════════════════════
#  /brawlers
# ══════════════════════════════════════════════════════════


@bot.tree.command(name="brawlers", description="List all brawlers owned by a player.")
@app_commands.describe(
    user="Discord user (uses their linked tag)",
    tag="Explicit player tag",
    sort="Sort field",
)
@app_commands.choices(sort=[
    app_commands.Choice(name="Trophies",      value="trophies"),
    app_commands.Choice(name="Best trophies", value="highestTrophies"),
    app_commands.Choice(name="Power level",   value="power"),
    app_commands.Choice(name="Rank",          value="rank"),
    app_commands.Choice(name="Name",          value="name"),
])
async def brawlers_cmd(
    interaction: discord.Interaction,
    user: discord.User | None = None,
    tag: str | None = None,
    sort: str = "trophies",
) -> None:
    await log_interaction(interaction, "brawlers")
    await interaction.response.defer()
    try:
        bs_tag = await resolve_tag(interaction, user, tag)
    except ValueError as e:
        await interaction.followup.send(embed=_err(str(e)))
        return

    async with aiohttp.ClientSession() as s:
        try:
            p = await bs_get(s, f"/players/{_enc(bs_tag)}")
        except BSError as e:
            await interaction.followup.send(embed=_err(f"API {e.status}: {e.message}"))
            return

    brawlers: list[dict] = p.get("brawlers", [])
    if sort == "name":
        brawlers.sort(key=lambda b: b.get("name", "").lower())
    else:
        brawlers.sort(key=lambda b: b.get(sort, 0), reverse=True)

    shown = brawlers[:35]
    lines = []
    for b in shown:
        name = b.get("name", "?").title()
        tr   = b.get("trophies", 0)
        ht   = b.get("highestTrophies", 0)
        pw   = b.get("power", 0)
        rk   = b.get("rank", 0)
        lines.append(f"**{name}** — <:trophy:1497229732448829580>{tr:,} ↑{ht:,} · P{pw} R{rk}")

    em = _embed(f"🥊  Brawlers — {p.get('name','?')} #{bs_tag}")
    em.description = "\n".join(lines) or "No brawlers."
    footer_extra = f"top {len(shown)} of " if len(brawlers) > len(shown) else ""
    em.set_footer(text=f"Showing {footer_extra}{len(brawlers)} brawlers · sorted by {sort}  •  api.brawlstars.com")
    await interaction.followup.send(embed=em)


# ══════════════════════════════════════════════════════════
#  /top
# ══════════════════════════════════════════════════════════

@bot.tree.command(name="top", description="Show top brawlers for a player.")
@app_commands.describe(
    length="How many entries to show",
    mode="Sort by current or peak",
    user="Discord user (uses their linked tag)",
    tag="Explicit player tag",
)
@app_commands.choices(
    length=[
        app_commands.Choice(name="Top 5", value=5),
        app_commands.Choice(name="Top 10", value=10),
        app_commands.Choice(name="Top 25", value=25),
    ],
    mode=[
        app_commands.Choice(name="Current trophies", value="current"),
        app_commands.Choice(name="Peak trophies", value="peak"),
    ],
)
async def top_cmd(
    interaction: discord.Interaction,
    length: int = 10,
    mode: str = "current",
    user: discord.User | None = None,
    tag: str | None = None,
) -> None:
    await log_interaction(interaction, "top")
    await interaction.response.defer()

    try:
        bs_tag = await resolve_tag(interaction, user, tag)
    except ValueError as e:
        await interaction.followup.send(embed=_err(str(e)))
        return

    async with aiohttp.ClientSession() as s:
        try:
            p = await bs_get(s, f"/players/{_enc(bs_tag)}")
        except BSError as e:
            await interaction.followup.send(embed=_err(f"API {e.status}: {e.message}"))
            return

    brawlers: list[dict] = p.get("brawlers", [])

    if mode == "current":
        key = "trophies"
        title_mode = "Current Trophies"
    else:
        key = "highestTrophies"
        title_mode = "Peak Trophies"

    brawlers.sort(key=lambda b: b.get(key, 0), reverse=True)
    top_list = brawlers[:length]

    lines = []
    for i, b in enumerate(top_list, 1):
        name = b.get("name", "?").title()
        tr   = b.get("trophies", 0)
        ht   = b.get("highestTrophies", 0)
        lines.append(f"`#{i:02}` **{name}** — <:trophy:1497229732448829580> {tr:,} (↑{ht:,})")

    em = _embed(
        f"<:trophy:1497229732448829580> Top {length} Brawlers — {p.get('name','?')} #{bs_tag}"
    )
    em.description = "\n".join(lines) or "No data."
    em.set_footer(text=f"Sorted by {title_mode}  •  api.brawlstars.com")

    await interaction.followup.send(embed=em)

# ══════════════════════════════════════════════════════════
#  /club  /clubmembers
# ══════════════════════════════════════════════════════════


async def _resolve_club_tag(
    interaction: discord.Interaction,
    session: aiohttp.ClientSession,
    user: discord.User | None,
    tag: str | None,
) -> str:
    if tag and tag.upper().startswith("C:"):
        return _norm(tag[2:])
    bs_tag = await resolve_tag(interaction, user, tag)
    p      = await bs_get(session, f"/players/{_enc(bs_tag)}")
    club   = p.get("club", {})
    if not club or not club.get("tag"):
        raise ValueError("This player is not in a club.")
    return _norm(club["tag"])


@bot.tree.command(
    name="club",
    description="Show a player's club info. Prefix tag with 'C:' to look up a club directly.",
)
@app_commands.describe(
    user="Discord user (uses their linked tag)",
    tag="Player tag, or club tag prefixed with C: (e.g. C:#8VR800VJL)",
)
async def club_cmd(
    interaction: discord.Interaction,
    user: discord.User | None = None,
    tag: str | None = None,
) -> None:
    await log_interaction(interaction, "club")
    await interaction.response.defer()
    async with aiohttp.ClientSession() as s:
        try:
            club_tag = await _resolve_club_tag(interaction, s, user, tag)
            club     = await bs_get(s, f"/clubs/{_enc(club_tag)}")
        except (BSError, ValueError) as e:
            await interaction.followup.send(embed=_err(str(e)))
            return

    em = _embed(f"<:club:1497225670831374519>  {club.get('name','?')}", desc=club.get("description",""), color=BS_GOLD)
    em.add_field(name="<:tag:1497917332918505492> Tag",          value=f"#{club_tag}",                        inline=True)
    em.add_field(name="<:trophy:1497229732448829580> Trophies",     value=f"{club.get('trophies',0):,}",         inline=True)
    em.add_field(name="👥 Members",       value=str(len(club.get("members",[]))),      inline=True)
    em.add_field(name="📋 Type",          value=club.get("type","?").capitalize(),     inline=True)
    em.add_field(name="🔒 Min Trophies",  value=f"{club.get('requiredTrophies',0):,}", inline=True)
    await interaction.followup.send(embed=em)


@bot.tree.command(
    name="clubmembers",
    description="List members of a player's club. Prefix tag with 'C:' for a direct club lookup.",
)
@app_commands.describe(
    user="Discord user (uses their linked tag)",
    tag="Player tag, or C:<club_tag>",
    sort="Sort by",
)
@app_commands.choices(sort=[
    app_commands.Choice(name="Trophies (default)", value="trophies"),
    app_commands.Choice(name="Role",               value="role"),
    app_commands.Choice(name="Name",               value="name"),
])
async def clubmembers_cmd(
    interaction: discord.Interaction,
    user: discord.User | None = None,
    tag: str | None = None,
    sort: str = "trophies",
) -> None:
    await log_interaction(interaction, "clubmembers")
    await interaction.response.defer()
    async with aiohttp.ClientSession() as s:
        try:
            club_tag = await _resolve_club_tag(interaction, s, user, tag)
            club, members_data = await asyncio.gather(
                bs_get(s, f"/clubs/{_enc(club_tag)}"),
                bs_get(s, f"/clubs/{_enc(club_tag)}/members"),
            )
        except (BSError, ValueError) as e:
            await interaction.followup.send(embed=_err(str(e)))
            return

    members: list[dict] = _items(members_data)
    if sort == "role":
        members.sort(key=lambda m: ROLE_ORDER.get(m.get("role", "member"), 9))
    elif sort == "name":
        members.sort(key=lambda m: m.get("name", "").lower())
    else:
        members.sort(key=lambda m: m.get("trophies", 0), reverse=True)

    lines = []
    for m in members[:30]:
        role_icon = ROLE_EMOJI.get(m.get("role", "member"), "👤")
        lines.append(f"{role_icon} **{m.get('name','?')}** — <:trophy:1497229732448829580> {m.get('trophies',0):,}")

    em = _embed(f"👥  {club.get('name','?')} Members", color=BS_GOLD)
    em.description = "\n".join(lines) or "No members found."
    total = len(members)
    shown = min(total, 30)
    em.set_footer(text=f"Showing {shown} of {total} members · sorted by {sort}  •  api.brawlstars.com")
    await interaction.followup.send(embed=em)


# ══════════════════════════════════════════════════════════
#  /events
# ══════════════════════════════════════════════════════════


@bot.tree.command(name="events", description="Show the current Brawl Stars event rotation.")
async def events_cmd(interaction: discord.Interaction) -> None:
    await log_interaction(interaction, "events")
    await interaction.response.defer()
    async with aiohttp.ClientSession() as s:
        try:
            data = await bs_get(s, "/events/rotation")
        except BSError as e:
            await interaction.followup.send(embed=_err(f"API {e.status}: {e.message}"))
            return

    events = data if isinstance(data, list) else data.get("items", [])
    em = _embed("<:calendar:1497229708998475866>  Current Event Rotation", color=0x6A1B9A)
    for ev in events:
        event    = ev.get("event", {})
        slot     = ev.get("slotId", "?")
        mode     = event.get("mode", "?")
        map_name = event.get("map", "?")
        end      = ev.get("endTime", "")
        emoji    = MODE_EMOJI.get(mode, "🎮")
        # Parse BS time format → Unix timestamp for Discord's native <t:...:R>
        try:
            end_dt  = datetime.strptime(end, "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=timezone.utc)
            end_str = f"<t:{int(end_dt.timestamp())}:R>"
        except (ValueError, TypeError):
            end_str = "?"
        em.add_field(
            name=f"{emoji}  Slot {slot} — {MODE_NAME.get(mode, _fmt_mode(mode))}",
            value=f"<:mapmaker:1497229729944571984> {map_name}\n<:time:1497918238439374888> {end_str}",
            inline=True,
        )
    if not events:
        em.description = "No events found."
    await interaction.followup.send(embed=em)


# ══════════════════════════════════════════════════════════
#  /brawlerlist  /brawlerinfo
# ══════════════════════════════════════════════════════════


@bot.tree.command(name="brawlerlist", description="List every Brawl Stars brawler.")
async def brawlerlist_cmd(interaction: discord.Interaction) -> None:
    await log_interaction(interaction, "brawlerlist")
    await interaction.response.defer()
    async with aiohttp.ClientSession() as s:
        try:
            data = await bs_get(s, "/brawlers")
        except BSError as e:
            await interaction.followup.send(embed=_err(f"API {e.status}: {e.message}"))
            return

    brawlers = sorted(_items(data), key=lambda b: b.get("name", ""))
    cols     = [brawlers[i::3] for i in range(3)]
    rows_n   = max(len(c) for c in cols)
    lines    = []
    for i in range(rows_n):
        row = "  ".join(
            cols[j][i]["name"].title().ljust(15) if i < len(cols[j]) else " " * 15
            for j in range(3)
        )
        lines.append(row)

    em = _embed(f"🥊  All Brawlers ({len(brawlers)})")
    em.description = f"```\n{chr(10).join(lines)}\n```"
    await interaction.followup.send(embed=em)


@bot.tree.command(name="brawlerinfo", description="Star powers, gadgets and ID for a specific brawler.")
@app_commands.describe(name="Brawler name (e.g. Shelly, Mortis, El Primo)")
async def brawlerinfo_cmd(interaction: discord.Interaction, name: str) -> None:
    await log_interaction(interaction, "brawlerinfo")
    await interaction.response.defer()
    async with aiohttp.ClientSession() as s:
        try:
            data = await bs_get(s, "/brawlers")
        except BSError as e:
            await interaction.followup.send(embed=_err(f"API {e.status}: {e.message}"))
            return

    brawlers = _items(data)
    nl       = name.lower()
    match    = (
        next((b for b in brawlers if b["name"].lower() == nl), None)
        or next((b for b in brawlers if nl in b["name"].lower()), None)
    )
    if not match:
        await interaction.followup.send(embed=_err(f"No brawler matching `{name}`."))
        return

    em = _embed(f"🥊  {match['name'].title()}")
    em.add_field(name="ID", value=str(match["id"]), inline=True)

    sps = match.get("starPowers", [])
    if sps:
        em.add_field(
            name=f"<:starpower:1497919181537148948> Star Powers ({len(sps)})",
            value="\n".join(f"• {sp['name']} (ID {sp['id']})" for sp in sps) or "—",
            inline=False,
        )
    gadgets = match.get("gadgets", [])
    if gadgets:
        em.add_field(
            name=f"<:gadget:1497919179641061576> Gadgets ({len(gadgets)})",
            value="\n".join(f"• {g['name']} (ID {g['id']})" for g in gadgets) or "—",
            inline=False,
        )
    await interaction.followup.send(embed=em)


# ══════════════════════════════════════════════════════════
#  /rankings_players  /rankings_clubs  /rankings_brawler
#  /powerplay_seasons  /powerplay_season
# ══════════════════════════════════════════════════════════


@bot.tree.command(name="rankings_players", description="Top players globally or by country.")
@app_commands.describe(country="2-letter country code (US, DE, GB…) or 'global'")
async def rankings_players_cmd(
    interaction: discord.Interaction, country: str = "global"
) -> None:
    await log_interaction(interaction, "rankings_players")
    await interaction.response.defer()
    code = country.upper() if country.lower() != "global" else "global"
    async with aiohttp.ClientSession() as s:
        try:
            data = await bs_get(s, f"/rankings/{code}/players")
        except BSError as e:
            await interaction.followup.send(embed=_err(f"API {e.status}: {e.message}"))
            return

    players = _items(data)[:25]
    lines   = []
    for i, p in enumerate(players, 1):
        club = p.get("club", {}).get("name", "—")
        lines.append(f"`#{i:02}` **{p['name']}** — <:trophy:1497229732448829580> {p.get('trophies',0):,}  · {club}")

    em = _embed(f"<:trophy:1497229732448829580>  Top Players — {code}", color=BS_GOLD)
    em.description = "\n".join(lines) or "No data."
    await interaction.followup.send(embed=em)


@bot.tree.command(name="rankings_clubs", description="Top clubs globally or by country.")
@app_commands.describe(country="2-letter country code or 'global'")
async def rankings_clubs_cmd(
    interaction: discord.Interaction, country: str = "global"
) -> None:
    await log_interaction(interaction, "rankings_clubs")
    await interaction.response.defer()
    code = country.upper() if country.lower() != "global" else "global"
    async with aiohttp.ClientSession() as s:
        try:
            data = await bs_get(s, f"/rankings/{code}/clubs")
        except BSError as e:
            await interaction.followup.send(embed=_err(f"API {e.status}: {e.message}"))
            return

    clubs = _items(data)[:25]
    lines = [
        f"`#{i:02}` **{c['name']}** — <:trophy:1497229732448829580> {c.get('trophies',0):,}  · 👥 {c.get('memberCount','?')}"
        for i, c in enumerate(clubs, 1)
    ]
    em = _embed(f"<:club:1497225670831374519>  Top Clubs — {code}", color=BS_GOLD)
    em.description = "\n".join(lines) or "No data."
    await interaction.followup.send(embed=em)


@bot.tree.command(name="rankings_brawler", description="Top players for a specific brawler.")
@app_commands.describe(
    brawler="Brawler name (e.g. Shelly) — bot resolves to ID automatically",
    country="2-letter country code or 'global'",
)
async def rankings_brawler_cmd(
    interaction: discord.Interaction, brawler: str, country: str = "global"
) -> None:
    await log_interaction(interaction, "rankings_brawler")
    await interaction.response.defer()
    code = country.upper() if country.lower() != "global" else "global"

    async with aiohttp.ClientSession() as s:
        try:
            brawler_data = await bs_get(s, "/brawlers")
        except BSError as e:
            await interaction.followup.send(embed=_err(f"API {e.status}: {e.message}"))
            return

        items = _items(brawler_data)
        nl    = brawler.lower()
        match = (
            next((b for b in items if b["name"].lower() == nl), None)
            or next((b for b in items if nl in b["name"].lower()), None)
        )
        if not match:
            await interaction.followup.send(embed=_err(f"Unknown brawler `{brawler}`."))
            return

        brawler_id   = match["id"]
        brawler_name = match["name"].title()

        try:
            data = await bs_get(s, f"/rankings/{code}/brawlers/{brawler_id}")
        except BSError as e:
            await interaction.followup.send(embed=_err(f"API {e.status}: {e.message}"))
            return

    players = _items(data)[:25]
    lines   = [
        f"`#{i:02}` **{p['name']}** — <:trophy:1497229732448829580> {p.get('trophies',0):,}"
        for i, p in enumerate(players, 1)
    ]
    em = _embed(f"⭐  Top {brawler_name} Players — {code}", color=BS_GOLD)
    em.description = "\n".join(lines) or "No data."
    await interaction.followup.send(embed=em)


@bot.tree.command(name="powerplay_seasons", description="[DOESNT WORK RIGHT NOW!]List all Power Play seasons for a country.")
@app_commands.describe(country="2-letter country code or 'global'")
async def powerplay_seasons_cmd(
    interaction: discord.Interaction, country: str = "global"
) -> None:
    await log_interaction(interaction, "powerplay_seasons")
    await interaction.response.defer()
    code = country.upper() if country.lower() != "global" else "global"
    async with aiohttp.ClientSession() as s:
        try:
            data = await bs_get(s, f"/rankings/{code}/powerplay/seasons")
        except BSError as e:
            await interaction.followup.send(embed=_err(f"API {e.status}: {e.message}"))
            return

    seasons = _items(data)
    if not seasons:
        await interaction.followup.send(embed=_err("No seasons found."))
        return

    lines = []
    for s_data in seasons[:20]:
        sid   = s_data.get("id", "?")
        start = str(s_data.get("startTime", "?"))[:10]
        end   = str(s_data.get("endTime", "?"))[:10]
        lines.append(f"**Season {sid}** — {start} → {end}")

    em = _embed(f"🌟  Power Play Seasons — {code}", color=0x7B1FA2)
    em.description = "\n".join(lines)
    await interaction.followup.send(embed=em)


@bot.tree.command(name="powerplay_season", description="[DOESNT WORK RIGHT NOW!]Top players for a specific Power Play season.")
@app_commands.describe(
    season_id="Season ID (see /powerplay_seasons)",
    country="2-letter country code or 'global'",
)
async def powerplay_season_cmd(
    interaction: discord.Interaction, season_id: int, country: str = "global"
) -> None:
    await log_interaction(interaction, "powerplay_seasons")
    await interaction.response.defer()
    code = country.upper() if country.lower() != "global" else "global"
    async with aiohttp.ClientSession() as s:
        try:
            data = await bs_get(s, f"/rankings/{code}/powerplay/seasons/{season_id}")
        except BSError as e:
            await interaction.followup.send(embed=_err(f"API {e.status}: {e.message}"))
            return

    players = _items(data)[:25]
    lines   = [
        f"`#{i:02}` **{p['name']}** — {p.get('trophies',0):,} pts"
        for i, p in enumerate(players, 1)
    ]
    em = _embed(f"🌟  Power Play Season {season_id} — {code}", color=0x7B1FA2)
    em.description = "\n".join(lines) or "No data."
    await interaction.followup.send(embed=em)


# ══════════════════════════════════════════════════════════
#  /compare
# ══════════════════════════════════════════════════════════


@bot.tree.command(name="compare", description="Compare two Brawl Stars players side by side.")
@app_commands.describe(
    tag1="First player tag (blank = your linked tag)",
    tag2="Second player tag",
    user1="First Discord user",
    user2="Second Discord user",
)
async def compare_cmd(
    interaction: discord.Interaction,
    tag1: str | None = None,
    tag2: str | None = None,
    user1: discord.User | None = None,
    user2: discord.User | None = None,
) -> None:
    await log_interaction(interaction, "compare")
    await interaction.response.defer()

    try:
        bs1 = await resolve_tag(interaction, user1, tag1)
    except ValueError as e:
        await interaction.followup.send(embed=_err(f"Player 1: {e}"))
        return

    if tag2 is None and user2 is None:
        await interaction.followup.send(embed=_err("Provide `tag2` or `user2` for the second player."))
        return

    try:
        bs2 = await resolve_tag(interaction, user2, tag2)
    except ValueError as e:
        await interaction.followup.send(embed=_err(f"Player 2: {e}"))
        return

    async with aiohttp.ClientSession() as s:
        try:
            p1, p2 = await asyncio.gather(
                bs_get(s, f"/players/{_enc(bs1)}"),
                bs_get(s, f"/players/{_enc(bs2)}"),
            )
        except BSError as e:
            await interaction.followup.send(embed=_err(f"API {e.status}: {e.message}"))
            return


    def cmp_arrow(a: int, b: int) -> tuple[str, str]:
        if a > b: return "🔺", "🔻"
        if b > a: return "🔻", "🔺"
        return "➖", "➖"

    t1, t2   = p1.get("trophies",0),        p2.get("trophies",0)
    ht1, ht2 = p1.get("highestTrophies",0), p2.get("highestTrophies",0)
    w1, w2   = p1.get("3vs3Victories",0),   p2.get("3vs3Victories",0)
    s1, s2   = p1.get("soloVictories",0),   p2.get("soloVictories",0)
    d1, d2   = p1.get("duoVictories",0),    p2.get("duoVictories",0)

    at, bt  = cmp_arrow(t1, t2)
    aht, _  = cmp_arrow(ht1, ht2)
    aw,  _  = cmp_arrow(w1,  w2)
    as_, _  = cmp_arrow(s1,  s2)
    ad,  _  = cmp_arrow(d1,  d2)

    em = _embed("<:clubleague:1497914300264878224>  Player Comparison")
    em.add_field(
        name=f"{p1.get('name','?')} #{bs1}",
        value=(
            f"{at} <:trophy:1497229732448829580> {t1:,}\n"
            f"{aht} <:trophyprestige:1497913518912176268> {ht1:,}\n"
            f"{aw} ⚡ 3v3: {w1:,}\n"
            f"{as_} <:sdwins:1497912798464704533> Solo: {s1:,}\n"
            f"{ad} <:duowins:1497913079218835496> Duo:  {d1:,}\n"
            f"🥊 {len(p1.get('brawlers',[]))} brawlers"
        ),
        inline=True,
    )
    em.add_field(name="\u200b", value="\u200b", inline=True)
    em.add_field(
        name=f"{p2.get('name','?')} #{bs2}",
        value=(
            f"{bt} <:trophy:1497229732448829580> {t2:,}\n"
            f"{'🔺' if ht2>ht1 else '🔻' if ht1>ht2 else '➖'} <:trophyprestige:1497913518912176268> {ht2:,}\n"
            f"{'🔺' if w2>w1 else '🔻' if w1>w2 else '➖'} ⚡ 3v3: {w2:,}\n"
            f"{'🔺' if s2>s1 else '🔻' if s1>s2 else '➖'} <:sdwins:1497912798464704533> Solo: {s2:,}\n"
            f"{'🔺' if d2>d1 else '🔻' if d1>d2 else '➖'} <:duowins:1497913079218835496> Duo:  {d2:,}\n"
            f"🥊 {len(p2.get('brawlers',[]))} brawlers"
        ),
        inline=True,
    )
    winner = (
        p1.get("name","?") if t1 > t2
        else p2.get("name","?") if t2 > t1
        else "Tie"
    )
    em.set_footer(text=f"Trophy leader: {winner}  •  api.brawlstars.com")
    await interaction.followup.send(embed=em)


# ══════════════════════════════════════════════════════════
#  /stats
# ══════════════════════════════════════════════════════════


@bot.tree.command(name="stats", description="Quick personal stats summary.")
@app_commands.describe(
    user="Discord user (uses their linked tag)",
    tag="Explicit Brawl Stars player tag",
)
async def stats_cmd(
    interaction: discord.Interaction,
    user: discord.User | None = None,
    tag: str | None = None,
) -> None:
    await log_interaction(interaction, "stats")
    await interaction.response.defer()
    try:
        bs_tag = await resolve_tag(interaction, user, tag)
    except ValueError as e:
        await interaction.followup.send(embed=_err(str(e)))
        return

    async with aiohttp.ClientSession() as s:
        try:
            p = await bs_get(s, f"/players/{_enc(bs_tag)}")
        except BSError as e:
            await interaction.followup.send(embed=_err(f"API {e.status}: {e.message}"))
            return

    brawlers   = p.get("brawlers", [])
    max_p9     = sum(1 for b in brawlers if b.get("power", 0) >= 9)
    max_p11    = sum(1 for b in brawlers if b.get("power", 0) == 11)
    total_wins = (
        p.get("3vs3Victories", 0)
        + p.get("soloVictories", 0)
        + p.get("duoVictories", 0)
    )

    em = _embed(f"📊  Quick Stats — {p.get('name','?')} #{bs_tag}")
    em.add_field(name="<:trophy:1497229732448829580> Trophies",     value=f"{p.get('trophies',0):,}",       inline=True)
    em.add_field(name="<:trophyprestige:1497913518912176268> Best Ever",    value=f"{p.get('highestTrophies',0):,}", inline=True)
    em.add_field(name="<:experience:1497229724752285779> Exp Level",   value=str(p.get("expLevel","?")),        inline=True)
    em.add_field(name="🥊 Brawlers",     value=str(len(brawlers)),                inline=True)
    em.add_field(name="⚡ P9+ Brawlers", value=str(max_p9),                       inline=True)
    em.add_field(name="💎 Max (P11)",    value=str(max_p11),                      inline=True)
    em.add_field(name="🎯 Total Wins",   value=f"{total_wins:,}",                 inline=True)
    em.add_field(name="⚡ 3v3 Wins",     value=f"{p.get('3vs3Victories',0):,}",   inline=True)
    em.add_field(name="<:sdwins:1497912798464704533>",    value=f"{p.get('soloVictories',0):,}",   inline=True)
    if p.get("club"):
        em.add_field(name="<:club:1497225670831374519> Club", value=p["club"].get("name","?"), inline=False)
    await interaction.followup.send(embed=em)


# ══════════════════════════════════════════════════════════
#  /trophygraph
# ══════════════════════════════════════════════════════════


@bot.tree.command(
    name="trophygraph",
    description="Trophy progress chart built from the last 25 ladder battles.",
)
@app_commands.describe(
    user="Discord user (uses their linked tag)",
    tag="Explicit Brawl Stars player tag",
)
async def trophygraph_cmd(
    interaction: discord.Interaction,
    user: discord.User | None = None,
    tag: str | None = None,
) -> None:
    await log_interaction(interaction, "trophygraph")
    await interaction.response.defer()

    try:
        bs_tag = await resolve_tag(interaction, user, tag)
    except ValueError as e:
        await interaction.followup.send(embed=_err(str(e)))
        return

    async with aiohttp.ClientSession() as s:
        try:
            p, log_data = await asyncio.gather(
                bs_get(s, f"/players/{_enc(bs_tag)}"),
                bs_get(s, f"/players/{_enc(bs_tag)}/battlelog"),
            )
        except BSError as e:
            await interaction.followup.send(embed=_err(f"API {e.status}: {e.message}"))
            return

    current_trophies = p.get("trophies", 0)
    best_trophies    = p.get("highestTrophies", 0)
    player_name      = p.get("name", bs_tag)
    battles          = _items(log_data)

    history = battlelog_to_trophy_history(battles, current_trophies)

    if len(history) < 2:
        ranked_count = sum(
            1 for b in battles
            if b.get("battle", {}).get("trophyChange") is not None
        )
        em = _embed("No Ranked Battles Found", color=0xF57C00)
        em.description = (
            f"Only **{ranked_count}** ladder battle(s) in the last 25 games "
            f"(need at least 2 with trophy changes).\n\n"
            f"Friendly, special event, and Power League battles are excluded.\n\n"
            f"Current trophies: **{current_trophies:,}** <:trophy:1497229732448829580>"
        )
        await interaction.followup.send(embed=em)
        return

    ranked_count = len(history) - 1

    loop = asyncio.get_running_loop()
    buf  = await loop.run_in_executor(
        None,
        build_trophy_graph,
        bs_tag, player_name, history, current_trophies, best_trophies, ranked_count,
    )

    delta_val = history[-1] - history[0]
    sign      = "+" if delta_val >= 0 else ""
    em = discord.Embed(
        title=f"<:trophy:1497229732448829580>  {player_name}  •  #{bs_tag}",
        description=f"{sign}{delta_val:,} trophies over last **{ranked_count}** ladder battles",
        color=0xF7C948,
    )
    em.set_footer(text="Reconstructed from battle log  •  api.brawlstars.com")

    file = discord.File(buf, filename="trophy_graph.png")
    em.set_image(url="attachment://trophy_graph.png")
    await interaction.followup.send(embed=em, file=file)



# ══════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    missing = [k for k, v in {"DISCORD_TOKEN": DISCORD_TOKEN, "BS_API_KEY": BS_API_KEY}.items() if not v]
    if missing:
        raise SystemExit(f"<:warn:1497917334722052136>  Missing environment variables: {', '.join(missing)}")
    bot.run(DISCORD_TOKEN)