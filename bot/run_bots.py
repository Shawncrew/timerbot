import os
import sys
# Add the parent directory to PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print('NC Timerbot: run_bots.py - Starting imports...')

import asyncio
print('NC Timerbot: asyncio imported')

import discord
print('NC Timerbot: discord imported')

from discord.ext import commands
print('NC Timerbot: commands imported')

import datetime
print('NC Timerbot: datetime imported')

# Use relative imports since we're inside the bot package
print('NC Timerbot: Starting bot package imports...')

from bot.utils.config import load_config, CONFIG
print('NC Timerbot: config imported')

from bot.utils.logger import logger
print('NC Timerbot: logger imported')

from bot.models.timer import TimerBoard, EVE_TZ
print('NC Timerbot: TimerBoard imported')

from bot.cogs.timer_commands import TimerCommands, backfill_citadel_timers
print('NC Timerbot: TimerCommands imported')

from bot.cogs.timer_commands import backfill_sov_timers, backfill_skyhook_timers
print('NC Timerbot: backfill functions imported')

from bot.cogs.timer_commands import update_existing_ihub_timers_with_alert
print('NC Timerbot: update_existing_ihub_timers_with_alert imported')

from bot.utils.helpers import clean_system_name
print('NC Timerbot: helpers imported')

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
    
    # Explicitly remove any default help command if it exists
    if bot.help_command:
        bot.remove_command('help')
    
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

            # Check and log all configured channels, including sov and skyhooks
            logger.info(f"Checking configured channels for {server_name}:")
            channels_found = {}
            channels_missing = {}
            for channel_name, channel_id in server_config.items():
                if channel_name == 'token':
                    continue  # Skip token
                if isinstance(channel_id, int) and channel_id is not None:
                    channel = bot.get_channel(channel_id)
                    if channel:
                        channels_found[channel_name] = channel_id
                        perms = channel.permissions_for(channel.guild.me)
                        logger.info(f"✅ Found channel '{channel_name}' in {server_name}: #{channel.name} (ID: {channel_id})")
                        logger.info(f"   Permissions - Can view: {perms.view_channel}, Can send: {perms.send_messages}, Can read: {perms.read_messages}")
                    else:
                        channels_missing[channel_name] = channel_id
                        logger.error(f"❌ Could not find {channel_name} channel (ID: {channel_id}) for {server_name}")
                elif channel_id is None:
                    logger.info(f"⚠️  Channel '{channel_name}' not configured for {server_name} (set to None)")
            
            logger.info(f"Channel check summary for {server_name}: {len(channels_found)} found, {len(channels_missing)} missing")
            
            logger.info("""
====================================================
   STARTING BACKFILLS FOR THIS SERVER
====================================================
""")
            
            # SOV Backfill
            sov_channel_id = server_config.get('sov')
            if sov_channel_id:
                logger.info(f"[BACKFILL] Checking SOV backfill for {server_name}...")
                sov_channel = bot.get_channel(sov_channel_id)
                if sov_channel:
                    logger.info(f"[BACKFILL] ✅ SOV channel found: #{sov_channel.name} (ID: {sov_channel_id})")
                    logger.info(f"[BACKFILL] Running SOV backfill for {server_name}...")
                    try:
                        await backfill_sov_timers(bot, shared_timerboard, server_config)
                        await update_existing_ihub_timers_with_alert(shared_timerboard)
                        logger.info(f"[BACKFILL] ✅ SOV backfill completed for {server_name}")
                    except Exception as e:
                        logger.error(f"[BACKFILL] ❌ SOV backfill failed for {server_name}: {e}")
                        logger.exception("Full traceback:")
                else:
                    logger.error(f"[BACKFILL] ❌ SOV channel not found (ID: {sov_channel_id}) for {server_name}, skipping SOV backfill")
            else:
                logger.info(f"[BACKFILL] ⚠️  SOV channel not configured for {server_name}, skipping SOV backfill")
            
            # Skyhook Backfill
            logger.info(f"[BACKFILL] Checking server_config for skyhooks key...")
            logger.info(f"[BACKFILL] server_config keys: {list(server_config.keys())}")
            logger.info(f"[BACKFILL] server_config.get('skyhooks'): {server_config.get('skyhooks')}")
            logger.info(f"[BACKFILL] server_config.get('skyhooks') type: {type(server_config.get('skyhooks'))}")
            skyhook_channel_id = server_config.get('skyhooks')
            logger.info(f"[BACKFILL] skyhook_channel_id value: {skyhook_channel_id}, truthy: {bool(skyhook_channel_id)}")
            if skyhook_channel_id:
                logger.info(f"[BACKFILL] Checking Skyhook backfill for {server_name}...")
                skyhook_channel = bot.get_channel(skyhook_channel_id)
                if skyhook_channel:
                    logger.info(f"[BACKFILL] ✅ Skyhook channel found: #{skyhook_channel.name} (ID: {skyhook_channel_id})")
                    logger.info(f"[BACKFILL] Running Skyhook backfill for {server_name}...")
                    try:
                        await backfill_skyhook_timers(bot, shared_timerboard, server_config)
                        logger.info(f"[BACKFILL] ✅ Skyhook backfill completed for {server_name}")
                    except Exception as e:
                        logger.error(f"[BACKFILL] ❌ Skyhook backfill failed for {server_name}: {e}")
                        logger.exception("Full traceback:")
                else:
                    logger.error(f"[BACKFILL] ❌ Skyhook channel not found (ID: {skyhook_channel_id}) for {server_name}, skipping Skyhook backfill")
            else:
                logger.info(f"[BACKFILL] ⚠️  Skyhook channel not configured for {server_name}, skipping Skyhook backfill")
            
            # Register this bot with the timerboard
            shared_timerboard.register_bot(bot, server_config)
            
            # Citadel/Structure Backfill
            citadel_channel_id = server_config.get('citadel_attacked')
            if citadel_channel_id:
                logger.info(f"[BACKFILL] Checking Structure backfill for {server_name}...")
                citadel_channel = bot.get_channel(citadel_channel_id)
                if citadel_channel:
                    logger.info(f"[BACKFILL] ✅ Citadel channel found: #{citadel_channel.name} (ID: {citadel_channel_id})")
                    logger.info(f"[BACKFILL] Running Structure backfill for {server_name}...")
                    try:
                        await backfill_citadel_timers(bot, shared_timerboard, server_config)
                        logger.info(f"[BACKFILL] ✅ Structure backfill completed for {server_name}")
                    except Exception as e:
                        logger.error(f"[BACKFILL] ❌ Structure backfill failed for {server_name}: {e}")
                        logger.exception("Full traceback:")
                else:
                    logger.error(f"[BACKFILL] ❌ Citadel channel not found (ID: {citadel_channel_id}) for {server_name}, skipping Structure backfill")
            else:
                logger.info(f"[BACKFILL] ⚠️  Citadel channel not configured for {server_name}, skipping Structure backfill")
            
            logger.info(f"""
====================================================
   BACKFILLS COMPLETED FOR {server_name}
====================================================
""")
            
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
    try:
        # Explicitly remove help command and any aliases if they exist
        if 'help' in bot.all_commands:
            logger.info(f"Removing existing help command for {server_name}...")
            bot.remove_command('help')
        # Also try to remove from walk_commands in case it's registered differently
        for cmd in list(bot.walk_commands()):
            if cmd.name == 'help' or 'help' in (cmd.aliases or []):
                logger.info(f"Removing help-related command: {cmd.name} for {server_name}...")
                bot.remove_command(cmd.name)
        
        logger.info(f"Creating TimerCommands cog for {server_name}...")
        cog = TimerCommands(bot, shared_timerboard)
        logger.info(f"TimerCommands cog created for {server_name}")
        
        logger.info(f"Adding cog to bot for {server_name}...")
        await bot.add_cog(cog)
        logger.info(f"Cog added successfully for {server_name}")
    except Exception as e:
        logger.error(f"Error adding cog for {server_name}: {e}")
        logger.exception("Full traceback:")
        raise
    
    # Move check_timers inside setup_hook
    async def setup_hook():
        """Setup hook for bot initialization"""
        try:
            logger.info(f"Setup hook called for {server_name}, starting timer check loop...")
            # Start the timer check loop
            asyncio.create_task(check_timers())
            logger.info(f"Timer check loop task created for {server_name}")
        except Exception as e:
            logger.error(f"Error in setup_hook for {server_name}: {e}")
            logger.exception("Full traceback:")
        
    bot.setup_hook = setup_hook
    logger.info(f"Setup hook configured for {server_name}")
    
    async def check_timers():
        """Check for timers that are about to start and alert if needed"""
        await bot.wait_until_ready()
        logger.info(f"Starting timer check loop for {server_name}...")
        logger.info(f"Filtered regions for {server_name}: {shared_timerboard.filtered_regions}")
        
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
                    # Normalize both timer region and filtered regions for comparison
                    if shared_timerboard.filtered_regions:
                        filtered_regions_upper = {r.upper().strip() for r in shared_timerboard.filtered_regions if r}
                        timer_region_upper = timer.region.upper().strip() if timer.region else None
                        is_filtered = timer_region_upper and timer_region_upper in filtered_regions_upper
                        
                        if is_filtered:
                            logger.info(f"  Timer {timer.timer_id} ({timer.system}) is in filtered region '{timer.region}' (normalized: '{timer_region_upper}'), skipping alerts")
                            continue
                        else:
                            logger.debug(f"  Timer {timer.timer_id} region '{timer.region}' (normalized: '{timer_region_upper}') not in filtered regions: {filtered_regions_upper}")
                    else:
                        logger.debug(f"  No filtered regions set, allowing all alerts")
                    
                    # Alert at 60 minutes if not already alerted
                    if 59.0 <= time_until <= 61.0:  # ±1 minute window for 60-minute alert
                        logger.info(f"  Timer is in 60-minute alert window ({time_until:.1f} minutes)")
                        if timer.timer_id not in sixty_min_alerted:
                            logger.info(f"  Sending 60-minute alert for timer {timer.timer_id}")
                            clean_system = clean_system_name(timer.system)
                            system_link = f"[{timer.system}](https://evemaps.dotlan.net/system/{clean_system})"
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
                            system_link = f"[{timer.system}](https://evemaps.dotlan.net/system/{clean_system})"
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
        logger.info(f"Calling bot.start() for {server_name}...")
        await bot.start(server_config['token'])
        logger.info(f"Bot {server_name} has stopped")
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
        try:
            timerboard = TimerBoard()
            logger.info("Timerboard initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing timerboard: {e}")
            logger.exception("Full traceback:")
            raise
        
        # Create tasks for each bot
        tasks = []
        logger.info(f"Processing {len(config['servers'])} server(s)...")
        for server_name, server_config in config['servers'].items():
            logger.info(f"Processing server: {server_name}")
            if server_config.get('token'):  # Only run if token is configured
                try:
                    logger.info(f"Creating bot task for {server_name}...")
                    task = run_bot_instance(server_name, server_config, timerboard)
                    tasks.append(task)
                    logger.info(f"Bot task created for {server_name}")
                except Exception as e:
                    logger.error(f"Error creating bot task for {server_name}: {e}")
                    logger.exception("Full traceback:")
                    raise
            else:
                logger.info(f"Skipping {server_name} - no token configured")
        
        logger.info(f"Starting {len(tasks)} bot instance(s)...")
        if not tasks:
            logger.error("No bot tasks to run! Check your configuration.")
            return
        
        # Run all bots
        try:
            logger.info("Calling asyncio.gather() to start bot tasks...")
            await asyncio.gather(*tasks)
            logger.info("All bot tasks completed")
        except Exception as e:
            logger.error(f"Error running bot tasks: {e}")
            logger.exception("Full traceback:")
            raise
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
    print('NC Timerbot: __main__ block entered')
    try:
        print('NC Timerbot: Calling logger.info("Starting bot application...")')
        logger.info("Starting bot application...")
        print('NC Timerbot: Calling asyncio.run(main())')
        asyncio.run(main())
        print('NC Timerbot: asyncio.run(main()) completed')
    except Exception as e:
        print(f'NC Timerbot: Exception caught in __main__: {e}')
        logger.error(f"Fatal error starting application: {e}")
        logger.exception("Full traceback:")
        raise 
    print('NC Timerbot: __main__ block completed')
else:
    print(f'NC Timerbot: Module imported as {__name__}') 