import discord
import asyncio
import re
import json
from datetime import datetime, timedelta
from discord import app_commands
import logging

config = {}
debugMode = False

logo = """
                          ####+
                        +######+
                      +###########
                    +###############
                  +#+################+
                 ######################+
               ##########################+
             ############+++##############++                                     ++
           +#########+  ++##################+                                +##+
         +########+    +######################+                          -+####
       +######+      +#########################+#                     +######
      +###+        +#############################++               ++#######
    ###+         +##################################+         +##########+
  #+           +######################################+    +##########++
             +############+   +#####################################++
           ++#########+          ++################################+
          +########+                 ++###########################
        #######+                         #######################
      #####+                                +#################
    +###                                        +###########+
  +#+                                               #####++
                                                       ++                           """

token = None

logging.basicConfig(level=logging.INFO)
infologger = logging.getLogger("infologger")
infohandler = logging.FileHandler("info.log")
infohandler.setLevel(logging.INFO)
info_format = logging.Formatter(
    "%(asctime)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
infohandler.setFormatter(info_format)
infologger.addHandler(infohandler)

errorlogger = logging.getLogger("errorlogger")
errorhandler = logging.FileHandler("errors.log")
errorhandler.setLevel(logging.ERROR)
error_format = logging.Formatter(
    "%(asctime)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
errorhandler.setFormatter(error_format)
errorlogger.addHandler(errorhandler)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

# Regex for a valid SteamID2, e.g. STEAM_0:0:431471716
STEAMID_RE = re.compile(r"^STEAM_[0-5]:[01]:\d+$")


class ActivityLogger(discord.Client):
    def __init__(self, intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

    async def on_ready(self):
        self.startTime = datetime.utcnow()
        print(f"\033[1mStarted as {self.user}\033[0m")
        await self.change_presence(activity=discord.Game(name="- Type /activity to use!"))


client = ActivityLogger(intents=intents)


async def sendErrorMsg(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Error occurred during runtime",
        description="A critical error occurred whilst running the command. Please contact `.seanie.` on Discord.",
        color=0xFF0000,
    )
    try:
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        errorlogger.error(f"Failed to send error message to user: {e}")


def timeToSeconds(timeStr: str) -> int:
    hours, mins, seconds = map(int, timeStr.split(":"))
    return (hours * 3600) + (mins * 60) + seconds


async def checkDebug(interaction: discord.Interaction) -> bool:
    """Returns True if the command is allowed to proceed."""
    global debugMode
    if not debugMode:
        return True

    debug_users = {int(uid) for uid in config.get("debug_users", [])}
    if interaction.user.id in debug_users:
        return True

    embed = discord.Embed(
        title="Debugging Mode",
        description="The bot is currently in a debugging mode for testing or maintenance. Sorry for the inconvenience!",
        color=0xFF0000,
    )
    await interaction.followup.send(embed=embed, ephemeral=True)
    return False


def ensureFormattedTime(delta: timedelta) -> str:
    totalSeconds = int(delta.total_seconds())
    hours, remainder = divmod(totalSeconds, 3600)
    mins, seconds = divmod(remainder, 60)
    return f"{hours:02}:{mins:02}:{seconds:02}"


def formatChangeLine(currentSeconds: int, previousSeconds: int) -> str:
    """Builds a human-readable week-over-week comparison line."""
    previousFormatted = ensureFormattedTime(timedelta(seconds=previousSeconds))

    if previousSeconds == 0:
        if currentSeconds == 0:
            return "No activity logged last week either, so there's nothing to compare."
        return f"No activity was logged the week before (previous week: `{previousFormatted}`), so this is a fresh start."

    diffSeconds = currentSeconds - previousSeconds
    percentChange = (diffSeconds / previousSeconds) * 100

    if diffSeconds > 0:
        arrow = "\U0001F53C"  # small up arrow
        word = "up"
    elif diffSeconds < 0:
        arrow = "\U0001F53D"  # small down arrow
        word = "down"
    else:
        return f"That's exactly the same as last week (`{previousFormatted}`)."

    diffFormatted = ensureFormattedTime(timedelta(seconds=abs(diffSeconds)))
    return (
        f"{arrow} {word} `{diffFormatted}` (`{abs(percentChange):.0f}%`) compared to last week's `{previousFormatted}`"
    )


async def fetchActivity(channel: discord.TextChannel, steamID: str) -> discord.Embed:
    """Scans channel history for the current week and the week before it,
    and returns an embed comparing the two. No globals involved, so
    concurrent invocations from different users never clash."""
    currentWeekSeconds = 0
    previousWeekSeconds = 0

    now = datetime.now()
    currentWeekStart = now - timedelta(days=7)
    previousWeekStart = now - timedelta(days=14)

    safe_steamid = re.escape(steamID)
    pattern = re.compile(rf"\({safe_steamid}\).*for `(\d{{2}}:\d{{2}}:\d{{2}})`")

    async for message in channel.history(limit=None, after=previousWeekStart):
        if message.embeds:
            content = message.embeds[0].description
            if content:
                match = pattern.search(content)
                if match:
                    seconds = timeToSeconds(match.group(1))
                    if message.created_at.replace(tzinfo=None) >= currentWeekStart:
                        currentWeekSeconds += seconds
                    else:
                        previousWeekSeconds += seconds

    totalActivity = ensureFormattedTime(timedelta(seconds=currentWeekSeconds))

    channelid_map = config.get("channelid", {})
    try:
        channelName = list(channelid_map.keys())[
            list(channelid_map.values()).index(channel.id)
        ].upper()
    except ValueError:
        channelName = "UNKNOWN"

    if channelName.lower() in config.get("longerNames", {}):
        channelName = config["longerNames"][channelName.lower()]

    comparisonLine = formatChangeLine(currentWeekSeconds, previousWeekSeconds)

    if currentWeekSeconds == 0:
        embed = discord.Embed(
            title=f"No Activity Logged ({channelName})",
            description=(
                f"`{steamID}` has not been on {channelName} in the past `1 week`.\n\n{comparisonLine}"
            ),
            color=0x0483FB,
        )
    else:
        embed = discord.Embed(
            title=f"Activity Logged ({channelName})",
            description=(
                f"`{steamID}` has been on {channelName} for `{totalActivity}` for the past `1 week`\n\n{comparisonLine}"
            ),
            color=0x0483FB,
        )
    return embed


async def sendWithRetries(interaction: discord.Interaction, embed: discord.Embed, attempts: int = 3):
    for attempt in range(1, attempts + 1):
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        except Exception as e:
            print(f"Failed sending message. Attempt number {attempt}. {e}")
            if attempt >= attempts:
                errorlogger.error(f"CRITICAL: Failed to respond after {attempts} attempts | {embed.description} | {e}")
                return
            await asyncio.sleep(3)


@client.tree.command(
    name="activity", description="Fetch activity for a SteamID in the past week"
)
async def activity(interaction: discord.Interaction, steamid: str):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command can only be used inside a server.", ephemeral=True
        )
        return

    channelType = 1
    channelToBeUsed = None
    guildName = None
    inEnabledGuild = False

    infologger.info(
        f"{datetime.now()} - {interaction.user.name} ({interaction.user.id}) has searched the activity for {steamid} in {interaction.guild.name} ({interaction.guild.id})"
    )

    try:
        await interaction.response.defer(ephemeral=True, thinking=True)
    except Exception as e:
        errorlogger.error(f"Failed to defer interaction: {e}")
        return

    if not await checkDebug(interaction):
        return

    guilds_map = config.get("guilds", {})
    enabled_depts = config.get("enabled_dept", [])
    channelid_map = config.get("channelid", {})

    for dept, gid in guilds_map.items():
        if gid != interaction.guild.id:
            continue
        if dept not in enabled_depts:
            continue

        home_channel_id = channelid_map.get(dept)
        if interaction.channel.id != home_channel_id:
            # command run somewhere other than the department's own log channel
            try:
                guildName = list(channelid_map.keys())[
                    list(channelid_map.values()).index(interaction.channel.id)
                ]
            except ValueError:
                guildName = None
            channelType = 2
        else:
            guildName = dept
        inEnabledGuild = True
        break

    if not inEnabledGuild:
        infologger.warning(
            f"{datetime.now()} - Command sent in a disallowed guild: {interaction.user.name} ({interaction.user.id}) has attempted to search the activity for {steamid} in {interaction.guild.name} ({interaction.guild.id})!"
        )
        await interaction.followup.send(
            "This command isn't enabled for this server.", ephemeral=True
        )
        return

    if guildName is None or guildName not in channelid_map:
        errorlogger.error(f"{datetime.now()} - Could not resolve logging channel for guild.")
        embed = discord.Embed(
            title="Incorrect channel",
            description="You must run the `/activity` command in the corresponding activity logging channel (e.g `#activity-log`). If this is in error, please contact `.seanie.` on Discord.",
            color=0xFF0000,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    ChannelObj = client.get_channel(channelid_map[guildName])

    if not ChannelObj:
        errorlogger.error("Error during channel check, channel not found.")
        embed = discord.Embed(
            title="Channel not found",
            description="The logging channel was not found. This is likely a configuration error, or the result of changes to the logging channels. Please contact `.seanie.` on Discord.",
            color=0xFF0000,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    try:
        caller = interaction.guild.get_member(interaction.user.id)
        if not caller:
            await sendErrorMsg(interaction)
            return
        permissions = ChannelObj.permissions_for(caller)
        if not permissions.read_messages:
            embed = discord.Embed(
                title="Permission Denied",
                description="You do not have the required permissions to use this bot. If this is in error, please contact `.seanie.` on Discord.",
                color=0xFF0000,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        channelToBeUsed = ChannelObj
    except Exception as e:
        errorlogger.error(f"Error during permission check: {str(e)}")
        await sendErrorMsg(interaction)
        return

    if channelToBeUsed is None:
        return

    if STEAMID_RE.match(steamid):
        try:
            embed = await fetchActivity(channelToBeUsed, steamid)
        except Exception as e:
            errorlogger.error(f"Error during fetchActivity: {e}")
            await sendErrorMsg(interaction)
            return
        await sendWithRetries(interaction, embed)
    else:
        infologger.info(
            f"{datetime.now()} - {interaction.user.name} ({interaction.user.id}) has used the incorrect format for {steamid} in {interaction.guild.name} ({interaction.guild.id})"
        )
        embed = discord.Embed(
            title="Invalid parameters",
            description="The SteamID supplied either does not exist, or is of an invalid format. Please enter the ID in this format: `STEAM_0:0:431471716`",
            color=0x0483FB,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


@client.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    errorlogger.error(f"Unhandled app command error: {error}")
    try:
        if interaction.response.is_done():
            await sendErrorMsg(interaction)
        else:
            embed = discord.Embed(
                title="Error occurred during runtime",
                description="A critical error occurred whilst running the command. Please contact `.seanie.` on Discord.",
                color=0xFF0000,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        errorlogger.error(f"Failed to report error to user: {e}")


def loadToken() -> bool:
    global token
    try:
        infologger.info("Loading token")
        print("\033[1mLoading token...\033[0m")
        with open("token.txt", "r") as f:
            token = f.read().strip()
        if not token:
            raise ValueError("token.txt is empty")
        return True
    except Exception as e:
        print("\033[1m\033[91mERROR DURING LOADING BOT TOKEN: " + str(e) + "\033[0m")
        errorlogger.error(f"Error during loading bot token: {str(e)}")
        return False


def loadConfig() -> bool:
    global config
    try:
        with open("config.json", "r") as f:
            config = json.load(f)
        return True
    except Exception as e:
        print(
            "\033[93m\033[1mWARNING: Configuration loading failed. Attempting to create configuration files with error: "
            + str(e)
            + "\033[0m"
        )
        errorlogger.warning(
            f"Configuration loading failed, creating default config: {str(e)}"
        )
        print("\033[1mGenerating default configuration...\033[0m")
        try:
            config = {
                "longerNames": {
                    "pd": "Metropolitan Police",
                    "so2": "Crime Support Branch",
                    "sco-19": "Specialist Firearms Command",
                    "sco": "SCO-19",
                    "nca": "National Crime Agency",
                    "nhs": "National Health Service",
                    "rs": "Royal Syndicate",
                    "t": "Terrorists",
                },
                "channelid": {
                    "pd": 1090365529564385310,
                    "so2": 1141061367730806906,
                    "sco": 1081600560060444885,
                    "nca": 1079508453241917653,
                    "nhs": 1117803842646585424,
                    "rs": 1100029126758375485,
                    "t": 1210141399878737920,
                    "test": 1269777958860492883,
                },
                "guilds": {
                    "pd": 472520717515096078,
                    "so2": 472520717515096078,
                    "sco": 472534240576143401,
                    "nca": 473075559409385472,
                    "nhs": 472537475605069825,
                    "rs": 472897608759771146,
                    "t": 472715289516048385,
                    "test": 1264515893610680393,
                },
                "enabled_dept": ["test"],
                "minimum_role_requirement": {
                    "pd": 1179100367083016233,
                    "so2": 811356656276865034,
                    "sco": 811699338253172736,
                    "nca": 1241570118014599278,
                    "nhs": 752960738544451715,
                    "rs": 752961417606332506,
                    "t": 752961594194919478,
                    "test": 1272168995419717713,
                },
                "debug_users": ["743066712810717295"],
                "debug": False,
            }
            with open("config.json", "w") as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e1:
            print(
                "\033[1m\033[91mERROR DURING LOADING CONFIGURATION: "
                + str(e1)
                + "\033[0m"
            )
            errorlogger.error(f"Error during generating configuration: {str(e1)}")
            return False


def main():
    global token
    global debugMode
    infologger.info("Riverside Activity Calculator Bot: Starting...")
    print(
        "\n\033[1m\033[94mRiverside Activity Calculator Bot: Starting...\033[0m\n"
        + logo
    )
    if not loadToken():
        return
    print(
        "\033[1mSuccessfully loaded bot token!\n\nLoading configuration files...\033[0m"
    )
    if not loadConfig():
        return
    print("\033[1mSuccessfully loaded configuration!\033[0m\n")
    if config.get("debug", False):
        debugMode = True
        print("\033[1m\033[91mWARNING: Running in debug mode!\033[0m")
    print("\033[1mStarting bot...\033[0m")
    client.run(token)


if __name__ == "__main__":
    main()
