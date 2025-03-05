import os
import sys
# Add the parent directory to PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord
from discord.ext import commands
import asyncio
import datetime

# Use relative imports since we're inside the bot package
from bot.utils.config import load_config, load_token
from bot.utils.logger import logger
from bot.models.timer import TimerBoard, EVE_TZ
from bot.cogs.timer_commands import TimerCommands
from bot.utils.helpers import clean_system_name

# Initialize logger and show startup banner
logger.info("""
=====================================
    EVE Online Timer Discord Bot
=====================================
""")

# Load configuration
CONFIG = load_config()
TOKEN = load_token()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Initialize timerboard
timerboard = TimerBoard()

async def check_timers():
    await bot.wait_until_ready()
    logger.info("Starting timer check loop...")
    while not bot.is_closed():
        try:
            now = datetime.datetime.now(EVE_TZ)
            
            # Check for timers that are about to happen or starting now
            for timer in timerboard.timers:
                time_until = timer.time - now
                minutes_until = time_until.total_seconds() / 60
                
                # Check for notification time (e.g. 60 minutes before)
                if CONFIG['notification_time'] <= minutes_until < CONFIG['notification_time'] + 1:
                    cmd_channel = bot.get_channel(CONFIG['channels']['commands'])
                    if cmd_channel:
                        clean_system = clean_system_name(timer.system)
                        system_link = f"[{timer.system}](https://evemaps.dotlan.net/system/{clean_system})"
                        notification = f"⚠️ Timer in {CONFIG['notification_time']} minutes: {system_link} - {timer.structure_name} {timer.notes} at `{timer.time.strftime('%Y-%m-%d %H:%M:%S')}` (ID: {timer.timer_id})"
                        await cmd_channel.send(notification)
                        logger.info(f"Sent notification for timer {timer.timer_id}")
                
                # Check for timer start (within 1 minute of start time)
                elif -1 <= minutes_until < 1:  # Within 1 minute of timer time
                    cmd_channel = bot.get_channel(CONFIG['channels']['commands'])
                    if cmd_channel:
                        clean_system = clean_system_name(timer.system)
                        system_link = f"[{timer.system}](https://evemaps.dotlan.net/system/{clean_system})"
                        alert = f"🚨 **TIMER STARTING NOW**: {system_link} - {timer.structure_name} {timer.notes} (ID: {timer.timer_id})"
                        await cmd_channel.send(alert)
                        logger.info(f"Sent start alert for timer {timer.timer_id}")
            
            # Check for expired timers
            expired = timerboard.remove_expired()
            if expired:
                logger.info(f"Removed {len(expired)} expired timers:")
                for timer in expired:
                    logger.info(f"- {timer.to_string()}")
                channel = bot.get_channel(CONFIG['channels']['timerboard'])
                await timerboard.update_timerboard(channel)
            
            await asyncio.sleep(CONFIG['check_interval'])
            
        except Exception as e:
            logger.error(f"Error in timer check loop: {e}")
            await asyncio.sleep(CONFIG['check_interval'])

@bot.event
async def on_ready():
    logger.info(f"Bot connected as {bot.user}")
    
    # Sync commands
    await sync_commands()
    
    # Debug channel information
    logger.info("Checking channels:")
    logger.info(f"Timerboard channel: {CONFIG['channels']['timerboard']}")
    logger.info(f"Commands channel: {CONFIG['channels']['commands']}")
    
    timerboard_channel = bot.get_channel(CONFIG['channels']['timerboard'])
    cmd_channel = bot.get_channel(CONFIG['channels']['commands'])
    
    if timerboard_channel:
        logger.info(f"Found Timerboard channel: #{timerboard_channel.name}")
        logger.info(f"Can send messages: {timerboard_channel.permissions_for(timerboard_channel.guild.me).send_messages}")
    else:
        logger.error("Could not find Timerboard channel!")
        
    if cmd_channel:
        logger.info(f"Found Commands channel: #{cmd_channel.name}")
        logger.info(f"Can send messages: {cmd_channel.permissions_for(cmd_channel.guild.me).send_messages}")
        logger.info(f"Can read messages: {cmd_channel.permissions_for(cmd_channel.guild.me).read_messages}")
    else:
        logger.error("Could not find Commands channel!")
    
    # Start timer check loop
    bot.loop.create_task(check_timers())
    
    # Update the timerboard display
    if timerboard_channel:
        await timerboard.update_timerboard(timerboard_channel)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        logger.warning(f"Unknown command '{ctx.message.content}' attempted by {ctx.author} in #{ctx.channel.name}")
    elif isinstance(error, commands.CheckFailure):
        logger.warning(f"Command '{ctx.command}' by {ctx.author} rejected - wrong channel (#{ctx.channel.name})")
        await ctx.send("This command can only be used in the timerboard-cmd channel.")
    else:
        logger.error(f"Error executing '{ctx.command}' by {ctx.author}: {error}")
        await ctx.send(f"Error executing command: {error}")

async def setup():
    await bot.add_cog(TimerCommands(bot, timerboard))

# Add this function
async def sync_commands():
    """Sync slash commands with Discord"""
    try:
        logger.info("Syncing commands with Discord...")
        await bot.tree.sync()
        logger.info("Commands synced successfully")
    except Exception as e:
        logger.error(f"Error syncing commands: {e}")

if __name__ == "__main__":
    asyncio.run(setup())
    bot.run(TOKEN) 