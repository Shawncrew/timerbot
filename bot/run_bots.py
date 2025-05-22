import os
import sys
# Add the parent directory to PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import discord
from discord.ext import commands
import datetime

# Use relative imports since we're inside the bot package
from bot.utils.config import load_config, CONFIG
from bot.utils.logger import logger
from bot.models.timer import TimerBoard, EVE_TZ
from bot.cogs.timer_commands import TimerCommands
from bot.utils.helpers import clean_system_name

async def run_bot_instance(server_name, server_config, shared_timerboard):
    """Run a single bot instance for a server"""
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    
    bot = commands.Bot(command_prefix='!', intents=intents)
    
    @bot.event
    async def on_ready():
        try:
            logger.info(f"Bot {server_name} connected as {bot.user}")
            logger.info(f"Bot application ID: {bot.user.id}")
            
            # Debug guild info
            logger.info(f"Connected to guilds for {server_name}:")
            for guild in bot.guilds:
                logger.info(f"  Guild: {guild.name} (ID: {guild.id})")
                logger.info(f"  Is bot connected: {guild.me and guild.me.status}")
                logger.info(f"  Bot roles: {[role.name for role in guild.me.roles if guild.me]}")
            
            # Register this bot with the timerboard
            shared_timerboard.register_bot(bot, server_config)
            
            # Initial timerboard update
            logger.info(f"Performing initial timerboard update for {server_name}")
            timerboard_channel = bot.get_channel(server_config['timerboard'])
            if timerboard_channel:
                logger.info(f"Found timerboard channel: {timerboard_channel.name} in {timerboard_channel.guild.name}")
                await shared_timerboard.update_timerboard([timerboard_channel])
            else:
                logger.error(f"Could not find timerboard channel for {server_name}")
                
        except Exception as e:
            logger.error(f"Error in on_ready for {server_name}: {e}")
            logger.exception("Full traceback:")

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
    
    # Add the cog
    cog = TimerCommands(bot, shared_timerboard)
    await bot.add_cog(cog)
    
    # Move check_timers inside setup_hook
    async def setup_hook():
        """Setup hook for bot initialization"""
        # Start the timer check loop
        asyncio.create_task(check_timers())
        
    bot.setup_hook = setup_hook
    
    async def check_timers():
        """Check for timers that are about to start and alert if needed"""
        await bot.wait_until_ready()
        logger.info(f"Starting timer check loop for {server_name}...")
        
        sixty_min_alerted = set()  # Track 60-minute alerts
        start_time_alerted = set()  # Track start-time alerts
        
        while not bot.is_closed():
            try:
                start_time = datetime.datetime.now()
                now = datetime.datetime.now(EVE_TZ)
                logger.info(f"\nTimer check cycle at {now} for {server_name}")
                
                # First check for expired timers
                logger.info("Checking for expired timers...")
                expired = shared_timerboard.remove_expired()
                if expired:
                    for timer in expired:
                        sixty_min_alerted.discard(timer.timer_id)
                        start_time_alerted.discard(timer.timer_id)
                        logger.info(f"Removed expired timer {timer.timer_id} from alert tracking")
                
                # Get command channel for this server
                cmd_channel = bot.get_channel(server_config['commands'])
                if not cmd_channel:
                    logger.error(f"Could not find commands channel for {server_name}")
                    await asyncio.sleep(CONFIG['check_interval'])
                    continue
                
                # Get all timers that are within the next hour or not yet expired
                upcoming_timers = [
                    timer for timer in shared_timerboard.timers 
                    if ((timer.time > now and (timer.time - now).total_seconds() <= 3600) or  # Future timers within 1 hour
                        (timer.time <= now and (now - timer.time).total_seconds() <= CONFIG['expiry_time'] * 60))  # Past timers not yet expired
                ]
                
                logger.info(f"Found {len(upcoming_timers)} upcoming/active timers")
                
                for timer in upcoming_timers:
                    time_until = (timer.time - now).total_seconds() / 60
                    logger.info(f"Checking timer {timer.timer_id}:")
                    logger.info(f"  System: {timer.system} ({timer.region})")
                    logger.info(f"  Structure: {timer.structure_name}")
                    logger.info(f"  Time until: {time_until:.1f} minutes")
                    logger.info(f"  Already alerted 60min: {timer.timer_id in sixty_min_alerted}")
                    logger.info(f"  Already alerted start: {timer.timer_id in start_time_alerted}")
                    
                    # Alert at 60 minutes if not already alerted
                    if 59.0 <= time_until <= 61.0:  # ±1 minute window for 60-minute alert
                        logger.info(f"  Timer is in 60-minute alert window ({time_until:.1f} minutes)")
                        if timer.timer_id not in sixty_min_alerted:
                            logger.info(f"  Sending 60-minute alert for timer {timer.timer_id}")
                            clean_system = clean_system_name(timer.system)
                            system_link = f"[{timer.system}](<https://evemaps.dotlan.net/system/{clean_system}>)"
                            await cmd_channel.send(
                                f"⚠️ Timer in 60 minutes:\n"
                                f"{system_link} ({timer.region}) - {timer.structure_name} {timer.notes}\n"
                                f"Time: `{timer.time.strftime('%Y-%m-%d %H:%M:%S')}` (ID: {timer.timer_id})"
                            )
                            sixty_min_alerted.add(timer.timer_id)
                            logger.info(f"  Added timer {timer.timer_id} to sixty_min_alerted")
                        else:
                            logger.info(f"  60-minute alert already sent for timer {timer.timer_id}")
                    
                    # Alert at start time if not already alerted
                    elif -1.0 <= time_until <= 1.0:  # ±1 minute window for start alert
                        logger.info(f"  Timer is in start alert window ({time_until:.1f} minutes)")
                        if timer.timer_id not in start_time_alerted:
                            logger.info(f"  Sending start alert for timer {timer.timer_id}")
                            clean_system = clean_system_name(timer.system)
                            system_link = f"[{timer.system}](<https://evemaps.dotlan.net/system/{clean_system}>)"
                            await cmd_channel.send(
                                f"🚨 **TIMER STARTING NOW**:\n"
                                f"{system_link} ({timer.region}) - {timer.structure_name} {timer.notes}\n"
                                f"Time: `{timer.time.strftime('%Y-%m-%d %H:%M:%S')}` (ID: {timer.timer_id})"
                            )
                            start_time_alerted.add(timer.timer_id)
                            logger.info(f"  Added timer {timer.timer_id} to start_time_alerted")
                        else:
                            logger.info(f"  Start alert already sent for timer {timer.timer_id}")
                    else:
                        logger.info(f"  Timer not in any alert window")
                
                # Calculate sleep time to ensure we check exactly every minute
                elapsed = (datetime.datetime.now() - start_time).total_seconds()
                sleep_time = max(1, CONFIG['check_interval'] - elapsed)
                logger.info(f"Sleeping for {sleep_time:.1f} seconds until next check")
                await asyncio.sleep(sleep_time)
                
            except Exception as e:
                logger.error(f"Error in timer check loop for {server_name}: {e}")
                logger.exception("Full traceback:")
                await asyncio.sleep(CONFIG['check_interval'])
    
    try:
        logger.info(f"Starting bot for {server_name} with token: {server_config['token'][:20]}...")
        await bot.start(server_config['token'])
    except Exception as e:
        logger.error(f"Error running bot for {server_name}: {e}")
        logger.exception("Full traceback:")

async def main():
    """Run all bot instances"""
    config = load_config()
    
    # Create shared timerboard
    timerboard = TimerBoard()
    
    try:
        # Create tasks for each bot
        tasks = []
        for server_name, server_config in config['servers'].items():
            if server_config['token']:  # Only run if token is configured
                task = run_bot_instance(server_name, server_config, timerboard)
                tasks.append(task)
        
        # Run all bots
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    finally:
        # Cancel the update task if it exists
        if timerboard.update_task:
            timerboard.update_task.cancel()
            try:
                await timerboard.update_task
            except asyncio.CancelledError:
                pass

if __name__ == "__main__":
    asyncio.run(main()) 