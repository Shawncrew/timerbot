import os
import sys
# Add the parent directory to PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord
from discord.ext import commands
import asyncio
import datetime
from discord import app_commands

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
intents.guilds = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Initialize timerboard
timerboard = TimerBoard()
sixty_min_alerted = set()  # Track 60-minute alerts
start_time_alerted = set()  # Track start-time alerts

async def check_timers():
    """Check for timers that are about to start and alert if needed"""
    await bot.wait_until_ready()
    logger.info("Starting timer check loop...")
    
    while not bot.is_closed():
        try:
            now = datetime.datetime.now(EVE_TZ)
            logger.debug(f"Checking timers at {now}")
            
            # Get all timers that are within the next hour
            upcoming_timers = [
                timer for timer in timerboard.timers 
                if timer.time > now 
                and (timer.time - now).total_seconds() <= 3600
            ]
            
            if upcoming_timers:
                logger.debug(f"Found {len(upcoming_timers)} upcoming timers")
                
            for timer in upcoming_timers:
                time_until = (timer.time - now).total_seconds() / 60
                logger.debug(f"Timer {timer.timer_id} is {time_until:.1f} minutes away")
                
                # Alert at 60 minutes if not already alerted
                if 59 <= time_until <= 60 and timer.timer_id not in sixty_min_alerted:
                    logger.info(f"Timer {timer.timer_id} is at 60 minute mark")
                    cmd_channel = bot.get_channel(CONFIG['channels']['commands'])
                    if cmd_channel:
                        await cmd_channel.send(
                            f"⚠️ Timer in 60 minutes: {timer.system} - {timer.structure_name} at {timer.time.strftime('%Y-%m-%d %H:%M:%S')} (ID: {timer.timer_id})"
                        )
                        sixty_min_alerted.add(timer.timer_id)
                        logger.info(f"Added timer {timer.timer_id} to sixty_min_alerted")
                
                # Alert at start time if not already alerted
                elif -1 <= time_until <= 1 and timer.timer_id not in start_time_alerted:
                    logger.info(f"Timer {timer.timer_id} is at start time (time_until={time_until:.1f})")
                    cmd_channel = bot.get_channel(CONFIG['channels']['commands'])
                    if cmd_channel:
                        logger.info(f"Sending start alert to #{cmd_channel.name}")
                        try:
                            await cmd_channel.send(
                                f"🚨 **TIMER STARTING NOW**: {timer.system} - {timer.structure_name} (ID: {timer.timer_id})"
                            )
                            logger.info(f"Successfully sent start alert for timer {timer.timer_id}")
                            start_time_alerted.add(timer.timer_id)
                            logger.info(f"Added timer {timer.timer_id} to start_time_alerted")
                        except Exception as e:
                            logger.error(f"Failed to send start alert: {e}")
                    else:
                        logger.error(f"Could not find commands channel (ID: {CONFIG['channels']['commands']})")
            
            # Clean up expired timers from both alert sets
            expired = timerboard.remove_expired()
            if expired:
                for timer in expired:
                    sixty_min_alerted.discard(timer.timer_id)
                    start_time_alerted.discard(timer.timer_id)
                timerboard_channel = bot.get_channel(CONFIG['channels']['timerboard'])
                if timerboard_channel:
                    await timerboard.update_timerboard(timerboard_channel)
            
            await asyncio.sleep(CONFIG['check_interval'])
            
        except Exception as e:
            logger.error(f"Error in timer check loop: {e}")
            await asyncio.sleep(CONFIG['check_interval'])

@bot.event
async def on_ready():
    logger.info(f"Bot connected as {bot.user}")
    
    # Sync commands after bot is ready
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} commands")
    except Exception as e:
        logger.error(f"Error syncing commands: {e}")
    
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
    cog = TimerCommands(bot, timerboard)
    await bot.add_cog(cog)

if __name__ == "__main__":
    asyncio.run(setup())
    bot.run(TOKEN) 