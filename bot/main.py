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
from bot.utils.config import load_config
from bot.utils.logger import logger
from bot.models.timer import TimerBoard, EVE_TZ
from bot.cogs.timer_commands import TimerCommands
from bot.cogs.timer_commands import backfill_sov_timers, backfill_skyhook_timers
from bot.utils.helpers import clean_system_name

# Initialize logger and show startup banner
logger.info("""
=====================================
         NC Timerbot
   EVE Online Timer Discord Bot
=====================================
""")

# Load configuration
CONFIG = load_config()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
# Disable default help command to use our custom one
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

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
            
            # Update timerboards in all servers
            timerboard_channels = [
                bot.get_channel(server_config['timerboard'])
                for server_config in CONFIG['servers'].values()
            ]
            await timerboard.update_timerboard(timerboard_channels)
            
            # Get all command channels for notifications
            cmd_channels = [
                bot.get_channel(server_config['commands'])
                for server_config in CONFIG['servers'].values()
            ]
            
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
                
                # Check if timer is in a filtered region (skip alerts if filtered)
                filtered_regions_upper = {r.upper().strip() for r in timerboard.filtered_regions}
                timer_region_upper = timer.region.upper().strip() if timer.region else None
                is_filtered = timer_region_upper and timer_region_upper in filtered_regions_upper
                
                if is_filtered:
                    logger.info(f"Timer {timer.timer_id} is in filtered region '{timer.region}' (upper: '{timer_region_upper}'), skipping alerts")
                    continue
                
                # Alert at 60 minutes if not already alerted
                if 59 <= time_until <= 60 and timer.timer_id not in sixty_min_alerted:
                    logger.info(f"Timer {timer.timer_id} is at 60 minute mark")
                    for cmd_channel in cmd_channels:
                        if cmd_channel:
                            await cmd_channel.send(
                                f"⚠️ Timer in 60 minutes: {timer.system} - {timer.structure_name} at {timer.time.strftime('%Y-%m-%d %H:%M:%S')} (ID: {timer.timer_id})"
                            )
                            sixty_min_alerted.add(timer.timer_id)
                            logger.info(f"Added timer {timer.timer_id} to sixty_min_alerted")
                
                # Alert at start time if not already alerted
                elif -1 <= time_until <= 1 and timer.timer_id not in start_time_alerted:
                    logger.info(f"Timer {timer.timer_id} is at start time (time_until={time_until:.1f})")
                    for cmd_channel in cmd_channels:
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
                            logger.error(f"Could not find commands channel (ID: {server_config['commands']})")
            
            # Clean up expired timers from both alert sets
            expired = timerboard.remove_expired()
            if expired:
                for timer in expired:
                    sixty_min_alerted.discard(timer.timer_id)
                    start_time_alerted.discard(timer.timer_id)
                for server_config in CONFIG['servers'].values():
                    timerboard_channel = bot.get_channel(server_config['timerboard'])
                    if timerboard_channel:
                        await timerboard.update_timerboard([timerboard_channel])
            
            await asyncio.sleep(CONFIG['check_interval'])
            
        except Exception as e:
            logger.error(f"Error in timer check loop: {e}")
            await asyncio.sleep(CONFIG['check_interval'])

async def check_channel_access(bot, channel_id, channel_name, required_send=False):
    """Check if a channel can be accessed with timeout"""
    try:
        # Wait for channel to become available with 10 second timeout
        for _ in range(10):
            channel = bot.get_channel(channel_id)
            if channel:
                logger.info(f"Found {channel_name} channel: #{channel.name}")
                perms = channel.permissions_for(channel.guild.me)
                logger.info(f"Permissions for #{channel.name}:")
                logger.info(f"  Can send messages: {perms.send_messages}")
                logger.info(f"  Can read messages: {perms.read_messages}")
                
                if not perms.read_messages:
                    logger.error(f"❌ Bot cannot read messages in #{channel.name}!")
                    return False
                if required_send and not perms.send_messages:
                    logger.error(f"❌ Bot cannot send messages in #{channel.name}!")
                    return False
                return True
            
            await asyncio.sleep(1)
            
        logger.error(f"❌ Timed out waiting for {channel_name} channel (ID: {channel_id})!")
        return False
        
    except Exception as e:
        logger.error(f"Error checking {channel_name} channel: {e}")
        return False

@bot.event
async def on_ready():
    try:
        logger.info("""
====================================================
   TIMERBOT IS ONLINE AND READY!
====================================================
""")
        logger.info(f"Bot connected as {bot.user}")
        logger.info(f"Bot application ID: {bot.user.id}")
        
        # Debug guild info
        logger.info("Connected to guilds:")
        logger.info(f"Total guilds: {len(bot.guilds)}")
        for guild in bot.guilds:
            logger.info(f"  Guild: {guild.name} (ID: {guild.id})")
            logger.info(f"  Is bot connected: {guild.me and guild.me.status}")
            logger.info(f"  Bot roles: {[role.name for role in guild.me.roles if guild.me]}")
            logger.info("  Visible channels:")
            for channel in guild.channels:
                if isinstance(channel, discord.TextChannel):
                    logger.info(f"    - #{channel.name} (ID: {channel.id})")
                    perms = channel.permissions_for(guild.me)
                    logger.info(f"      Can view: {perms.view_channel}")
                    logger.info(f"      Can send: {perms.send_messages}")
        
        # Wait a moment for the bot to fully connect
        await asyncio.sleep(2)
        
        # Sync commands after bot is ready
        try:
            synced = await bot.tree.sync()
            logger.info(f"Synced {len(synced)} commands")
        except Exception as e:
            logger.error(f"Error syncing commands: {e}")
        
        # Debug channel information
        logger.info("Checking channels...")

        # List all text channels the bot can see in each guild
        for guild in bot.guilds:
            logger.info(f"Guild: {guild.name} (ID: {guild.id}) - Listing all text channels:")
            for channel in guild.text_channels:
                logger.info(f"  TextChannel: #{channel.name} (ID: {channel.id})")
                perms = channel.permissions_for(guild.me)
                logger.info(f"    Can view: {perms.view_channel}, Can send: {perms.send_messages}, Can read: {perms.read_messages}")

        # Check channels for each server
        for server_name, server_config in CONFIG['servers'].items():
            logger.info(f"Checking channels for {server_name}:")
            
            # Define channels to check with their requirements
            channels_to_check = {
                'timerboard': (server_config['timerboard'], True),
                'commands': (server_config['commands'], True),
                'citadel_attacked': (server_config['citadel_attacked'], False),
                'citadel_info': (server_config['citadel_info'], False),
                'sov': (server_config.get('sov'), False),
                'skyhooks': (server_config.get('skyhooks'), False)
            }
            
            # Check all channels
            for channel_name, (channel_id, required_send) in channels_to_check.items():
                if channel_id is None:
                    logger.info(f"Channel '{channel_name}' not configured for {server_name}")
                    continue
                    
                channel = bot.get_channel(channel_id)
                if not channel:
                    logger.error(f"❌ Could not find {channel_name} channel (ID: {channel_id}) for {server_name}")
                    continue
                    
                logger.info(f"Found channel '{channel_name}' in {server_name} with ID: {channel_id}")
                perms = channel.permissions_for(channel.guild.me)
                logger.info(f"Permissions for #{channel.name}:")
                logger.info(f"  Can send messages: {perms.send_messages}")
                logger.info(f"  Can read messages: {perms.read_messages}")
                
                if not perms.read_messages:
                    logger.error(f"❌ Bot cannot read messages in #{channel.name}!")
                if required_send and not perms.send_messages:
                    logger.error(f"❌ Bot cannot send messages in #{channel.name}!")
        
        logger.info("Channel checks completed, starting bot services...")
        
        # Start timer check loop
        bot.loop.create_task(check_timers())
        
        # Update all timerboards
        timerboard_channels = [
            bot.get_channel(server_config['timerboard'])
            for server_config in CONFIG['servers'].values()
            if server_config['timerboard'] is not None
        ]
        if timerboard_channels:
            await timerboard.update_timerboard(timerboard_channels)
            logger.info("Updated timerboard displays")
        else:
            logger.error("❌ Could not update timerboards - no channels found")

        logger.info("""
====================================================
   STARTING SOV BACKFILL FOR ALL CONFIGURED SERVERS
====================================================
""")
        # Run sov backfill for each server with a sov channel (after bot is fully ready)
        for server_name, server_config in CONFIG['servers'].items():
            if server_config.get('sov'):
                logger.info(f"Running SOV backfill for {server_name}...")
                await backfill_sov_timers(bot, timerboard, server_config)
            # Run skyhook backfill for each server with a skyhooks channel
            if server_config.get('skyhooks'):
                logger.info(f"Running Skyhook backfill for {server_name}...")
                await backfill_skyhook_timers(bot, timerboard, server_config)
    except Exception as e:
        logger.error(f"Error in on_ready: {e}")
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

@bot.event
async def on_guild_join(guild):
    """Log when bot joins a guild"""
    logger.info(f"Bot joined guild: {guild.name} (ID: {guild.id})")
    logger.info(f"Guild owner: {guild.owner}")
    logger.info(f"Member count: {guild.member_count}")
    logger.info(f"Bot's roles: {[role.name for role in guild.me.roles]}")

@bot.event
async def on_guild_remove(guild):
    """Log when bot leaves a guild"""
    logger.info(f"Bot removed from guild: {guild.name} (ID: {guild.id})")

async def setup():
    """Initialize bot and cogs"""
    try:
        logger.info("Initializing bot cogs...")
        cog = TimerCommands(bot, timerboard)
        await bot.add_cog(cog)
        logger.info("Successfully initialized cogs")
    except Exception as e:
        logger.error(f"Error initializing cogs: {e}")

def run_bot():
    """Run the bot"""
    try:
        # Set up the bot first
        asyncio.run(setup())
        logger.info("Starting bot...")
        # Then run it with the server1 token
        bot.run(CONFIG['servers']['server1']['token'], log_handler=None)  # Use server1's token
    except Exception as e:
        logger.error(f"Error running bot: {e}")

if __name__ == "__main__":
    print('NC Timerbot: main.py loaded and running!')
    run_bot() 