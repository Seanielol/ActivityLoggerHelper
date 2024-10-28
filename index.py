import discord
import asyncio
import re
import json
from datetime import datetime, timedelta
import time
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
embed1 = None


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


class ActivityLogger(discord.Client):
    def __init__(self, intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

    async def on_ready(self):
        self.startTime = datetime.utcnow()
        print(f"\033[1mStarted as {self.user}\033[0m")
        await self.change_presence(activity=discord.Game(name="/activity"))


client = ActivityLogger(intents=intents)


async def sendErrorMsg(interaction):
    embed1 = discord.Embed(
        title="Error occured during runtime",
        description="A critical error occured whilst running the command. Please contact `teasippingbrit` on Discord.",
        color=0xFF0000,
    )
    await interaction.response.send_message(embed=embed1, ephemeral=True)


def timeToSeconds(timeStr):
    hours, mins, seconds = map(int, timeStr.split(":"))
    return (hours * 3600) + (mins * 60) + seconds


async def checkDebug():
    global debugMode
    if debugMode == True:
        for i in config["debug_users"]:
            if i == interaction.user.id:
                return True
        if debuggingUserAllowed == False:
            embed1 = discord.Embed(
                title="Debugging Mode",
                description="The bot is currently in a debugging mode for testing or maintenance. Sorry for the inconvenience!",
                color=0xFF0000,
            )
            await interaction.response.send_message(
                embed=embed1, ephemeral=True, delete_after=300
            )
            return False
    else:
        return True


async def ensureFormattedTime(time):
    totalSeconds = int(time.total_seconds())
    hours, remainder = divmod(totalSeconds, 3600)
    mins, seconds = divmod(remainder, 60)
    return f"{hours:02}:{mins:02}:{seconds:02}"


async def fetchActivity(channel, steamID):
    global embed1
    global config
    totalSeconds = 0
    timeframe = datetime.now() - timedelta(days=7)
    async for message in channel.history(limit=None, after=timeframe):
        if message.embeds:
            content = message.embeds[0].description
            match = re.search(
                rf"\({steamID}\).*for `(\d{{2}}:\d{{2}}:\d{{2}})`", content
            )
            if match:
                timeStr = match.group(1)
                totalSeconds += timeToSeconds(timeStr)
    totalActivity = await ensureFormattedTime(timedelta(seconds=totalSeconds))
    channelName = list(config["channelid"].keys())[
        list(config["channelid"].values()).index(channel.id)
    ].upper()
    if channelName == "RS":
        for i in config["longerNames"]:
            if i == channelName.lower():
                channelName = config["longerNames"][i]
                break
    if totalSeconds == 0:
        embed1 = discord.Embed(
            title=f"No Activity Logged ({channelName})",
            description=f"`{steamID}` has not been on {channelName} in the past `1 week`.",
            color=0x0483FB,
        )
    else:
        embed1 = discord.Embed(
            title=f"Activity Logged ({channelName})",
            description=f"`{steamID}` has been on {channelName} for `{totalActivity}` for the past `1 week`",
            color=0x0483FB,
        )


@client.tree.command(
    name="activity", description="Fetch activity for a SteamID in the past week"
)
async def activity(interaction: discord.Interaction, steamid: str):
    global embed1
    guildName = None
    channelType = 1
    channelToBeUsed = None
    guildToBeUsed = None
    inEnabledGuild = False
    debuggingUserAllowed = False

    infologger.info(
        f"{datetime.now()} - {interaction.user.name} ({interaction.user.id}) has searched the activity for {steamid} in {interaction.guild.name} ({interaction.guild.id})"
    )

    x = await checkDebug()
    if not x:
        return

    for i in config["guilds"]:
        if config["guilds"][i] == interaction.guild.id:
            for i1 in config["enabled_dept"]:
                if i1 == i:
                    if interaction.channel.id != config["channelid"][i]:
                        guildToBeUsed = config["guilds"][i]
                        try:
                            guildName = list(config["channelid"].keys())[
                                list(config["channelid"].values()).index(
                                    interaction.channel.id
                                )
                            ]
                        except Exception as e:
                            print(e)
                        inEnabledGuild = True
                        channelType = 2
                        break
                    guildToBeUsed = config["guilds"][i]
                    guildName = i
                    inEnabledGuild = True
                    break
    if inEnabledGuild == False:
        infologger.warning(
            f"{datetime.now()} - Command send in a dissallowed guild: {interaction.user.name} ({interaction.user.id}) has attempted to search the activity for {steamid} in {interaction.guild.name} ({interaction.guild.id})!"
        )
        return
    try:
        ChannelObj = client.get_channel(config["channelid"][guildName])
        if channelType == 2:
            ChannelObj = client.get_channel(config["channelid"][guildName])
    except Exception as e:
        errorlogger.error(f"{datetime.now()} - " + str(e))
        embed1 = discord.Embed(
            title="Incorrect channel",
            description="You must run the `/activity` command in the corresponding activity logging channel (e.g `#activity-log`). If this in error, please contact `teasippingbrit` on Discord.",
            color=0xFF0000,
        )
        await interaction.response.send_message(
            embed=embed1, ephemeral=True, delete_after=1200
        )
        return
    if ChannelObj:
        try:
            caller = interaction.guild.get_member(interaction.user.id)
            if caller:
                permissions = ChannelObj.permissions_for(caller)
                if permissions.read_messages:
                    channelToBeUsed = ChannelObj
                else:
                    embed1 = discord.Embed(
                        title="Permission Denied",
                        description="You do not have the required permsisions to use this bot. If this in error, please contact `teasippingbrit` on Discord.",
                        color=0xFF0000,
                    )
                    await interaction.response.send_message(
                        embed=embed1, ephemeral=True, delete_after=120
                    )
                    return
            else:
                await sendErrorMsg(interaction)
                return
        except Exception as e:
            errorlogger.error(f"Error during permission check: {str(e)}")
            await sendErrorMsg(interaction)
            return
    else:
        errorlogger.error(f"Error during channel check, channel not found.")
        embed1 = discord.Embed(
            title="Channel not found",
            description="The logging channel was not found. This is likely a configuration error, or the result of changes to the logging channels. Please contact `teasippingbrit` on Discord.",
            color=0xFF0000,
        )
        await interaction.response.send_message(embed=embed1, ephemeral=True)

    if channelToBeUsed == None:
        return
    if steamid.startswith("STEAM_"):
        await fetchActivity(channelToBeUsed, steamid)
        await interaction.response.send_message(
            embed=embed1, ephemeral=True, delete_after=1200
        )
    else:
        infologger.info(
            f"{datetime.now()} - {interaction.user.name} ({interaction.user.id}) has used the incorrect format for {steamid} in {interaction.guild.name} ({interaction.guild.id})"
        )
        embed1 = discord.Embed(
            title="Invalid parameters",
            description="The SteamID supplied either does not exist, or is of an invalid format. Please enter the ID in this format: `STEAM_0:0:431471716`",
            color=0x0483FB,
        )
        await interaction.response.send_message(
            embed=embed1, ephemeral=True, delete_after=1200
        )


def loadToken():
    global token
    try:
        infologger.info("Loading token")
        print("\033[1mLoading token...\033[0m")
        with open("token.txt", "r") as f:
            token = f.read()
        return True
    except Exception as e:
        print("\033[1m\033[91mERROR DURING LOADING BOT TOKEN: " + str(e) + "\033[0m")
        errorlogger.error(f"Error during loading bot token: {str(e)}")
        return False


def loadConfig():
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
            with open("config.json", "w") as f:
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
                json.dump(config, f)
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
    loadTokenResult = loadToken()
    if not loadTokenResult:
        return
    print(
        "\033[1mSuccessfully loaded bot token!\n\nLoading configuration files...\033[0m"
    )
    loadConfigResult = loadConfig()
    if not loadConfigResult:
        return
    print("\033[1mSuccessfully loaded configuration!\033[0m\n")
    if config["debug"] == True:
        debugMode = True
        print("\033[1m\033[91mWARNING: Running in debug mode!\033[0m")
    print("\033[1mStarting bot...\033[0m")
    client.run(token)


if __name__ == "__main__":
    main()
