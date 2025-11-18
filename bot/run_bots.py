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
from bot.cogs.timer_commands import TimerCommands, backfill_citadel_timers
from bot.cogs.timer_commands import backfill_sov_timers
from bot.cogs.timer_commands import update_existing_ihub_timers_with_alert
from bot.utils.helpers import clean_system_name

print('NC Timerbot: run_bots.py loaded and running!')
logger.info("""
=====================================
         NC Timerbot
   EVE Online Timer Discord Bot
=====================================
""")

async def run_bot_instance(server_name, server_config, shared_timerboard):
    """Run a single bot instance for a server"""
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    
    # Disable default help command to use our custom one
    bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)
    
    @bot.event
    async def on_ready():
        try:
            logger.info("""
====================================================
   TIMERBOT IS ONLINE AND READY!
====================================================
""")
            logger.info(f"Bot {server_name} connected as {bot.user}")
            logger.info(f"Bot application ID: {bot.user.id}")
            
            # Debug guild info
            logger.info(f"Connected to guilds for {server_name}:")
            for guild in bot.guilds:
                logger.info(f"  Guild: {guild.name} (ID: {guild.id})")
                logger.info(f"  Is bot connected: {guild.me and guild.me.status}")
                logger.info(f"  Bot roles: {[role.name for role in guild.me.roles if guild.me]}")
                logger.info(f"Guild: {guild.name} (ID: {guild.id}) - Listing all text channels:")
                for channel in guild.text_channels:
                    logger.info(f"  TextChannel: #{channel.name} (ID: {channel.id})")
                    perms = channel.permissions_for(guild.me)
                    logger.info(f"    Can view: {perms.view_channel}, Can send: {perms.send_messages}, Can read: {perms.read_messages}")

            # Check and log all configured channels, including sov
            for channel_name, channel_id in server_config.items():
                if isinstance(channel_id, int):
                    channel = bot.get_channel(channel_id)
                    if channel:
                        logger.info(f"Found channel '{channel_name}' in {server_name} with ID: {channel_id}")
                    else:
                        logger.error(f"❌ Could not find {channel_name} channel (ID: {channel_id}) for {server_name}")

            logger.info("""
====================================================
   STARTING SOV BACKFILL FOR THIS SERVER
====================================================
""")
            if server_config.get('sov'):
                logger.info(f"Running SOV backfill for {server_name}...")
                await backfill_sov_timers(bot, shared_timerboard, server_config)
                await update_existing_ihub_timers_with_alert(shared_timerboard)
            
            # Register this bot with the timerboard
            shared_timerboard.register_bot(bot, server_config)
            
            # Backfill timers from citadel-attacked channel
            logger.info(f"Starting backfill for {server_name}")
            await backfill_citadel_timers(bot, shared_timerboard, server_config)
            
            # Initial timerboard update
            logger.info(f"Performing initial timerboard update for {server_name}")
            try:
                timerboard_channel = bot.get_channel(server_config['timerboard'])
                if timerboard_channel:
                    logger.info(f"Found timerboard channel: {timerboard_channel.name} in {timerboard_channel.guild.name}")
                    await shared_timerboard.update_timerboard([timerboard_channel])
                    logger.info(f"Successfully updated timerboard for {server_name}")
                else:
                    logger.error(f"Could not find timerboard channel for {server_name}")
            except Exception as e:
                logger.error(f"Error updating timerboard for {server_name}: {e}")
                logger.exception("Full traceback:")
                
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
                    
                    # Check if timer is in a filtered region (skip alerts if filtered)
                    filtered_regions_upper = {r.upper() for r in shared_timerboard.filtered_regions}
                    is_filtered = timer.region and timer.region.upper() in filtered_regions_upper
                    
                    if is_filtered:
                        logger.info(f"  Timer is in filtered region '{timer.region}', skipping alerts")
                        continue
                    
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
    except KeyboardInterrupt:
        logger.info(f"Received keyboard interrupt for {server_name}, shutting down...")
        raise
    except Exception as e:
        logger.error(f"Error running bot for {server_name}: {e}")
        logger.exception("Full traceback:")
        raise

async def main():
    """Run all bot instances"""
    try:
        logger.info("Loading configuration...")
        config = load_config()
        logger.info("Configuration loaded successfully")
        
        # Create shared timerboard
        logger.info("Initializing shared timerboard...")
        timerboard = TimerBoard()
        logger.info("Timerboard initialized successfully")
        
        # Create tasks for each bot
        tasks = []
        for server_name, server_config in config['servers'].items():
            if server_config.get('token'):  # Only run if token is configured
                logger.info(f"Creating bot task for {server_name}...")
                task = run_bot_instance(server_name, server_config, timerboard)
                tasks.append(task)
        
        logger.info(f"Starting {len(tasks)} bot instance(s)...")
        # Run all bots
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Fatal error in main(): {e}")
        logger.exception("Full traceback:")
        raise
    finally:
        # Cancel the update task if it exists
        if 'timerboard' in locals() and timerboard.update_task:
            logger.info("Cancelling timerboard update task...")
            timerboard.update_task.cancel()
            try:
                await timerboard.update_task
            except asyncio.CancelledError:
                pass

if __name__ == "__main__":
    try:
        logger.info("Starting bot application...")
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Fatal error starting application: {e}")
        logger.exception("Full traceback:")
        raise 