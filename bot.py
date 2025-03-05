# First all imports
import discord
from discord.ext import commands
import datetime
import re
from typing import Optional
import asyncio
from dataclasses import dataclass
import pytz
from dotenv import load_dotenv
import os
import requests
from bs4 import BeautifulSoup
import aiohttp
import json
from pathlib import Path
import yaml
import logging
from logging.handlers import RotatingFileHandler
import sys

# Update paths to be absolute
SAVE_FILE = "/opt/timerbot/data/timerboard_data.json"
CONFIG_FILE = "/opt/timerbot/bot/config.yaml"
LOG_DIR = "/opt/timerbot/logs"

# Then logger setup
def setup_logging():
    # Update log directory
    log_dir = LOG_DIR
    os.makedirs(log_dir, exist_ok=True)
    
    # Configure logging
    logger = logging.getLogger('timerbot')
    logger.setLevel(logging.INFO)
    
    # Add rotating file handler (10 files, 10MB each)
    handler = RotatingFileHandler(
        f"{log_dir}/bot.log",
        maxBytes=10_000_000,
        backupCount=10
    )
    
    # Format for log messages
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    # Also log to console
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)
    
    return logger

# Initialize logger
logger = setup_logging()
logger.info("""
=====================================
    EVE Online Timer Discord Bot
=====================================
""")

# Then the rest of the bot code

# Load environment variables and token with better error handling
def load_token():
    """Load Discord token from .env file"""
    try:
        # First try /opt/timerbot/bot/.env
        if os.path.exists('/opt/timerbot/bot/.env'):
            load_dotenv('/opt/timerbot/bot/.env')
            logger.info("Loading token from /opt/timerbot/bot/.env")
        else:
            # Try local .env file
            if os.path.exists('.env'):
                load_dotenv()
                logger.info("Loading token from local .env file")
            else:
                logger.error("No .env file found in either location")
                raise FileNotFoundError("No .env file found")

        token = os.getenv('DISCORD_TOKEN')
        if not token:
            logger.error("DISCORD_TOKEN not found in .env file")
            raise ValueError("DISCORD_TOKEN not found in .env file")
            
        return token

    except Exception as e:
        logger.error(f"Error loading Discord token: {e}")
        raise

# Replace the token loading code
try:
    TOKEN = load_token()
except Exception as e:
    logger.error("Failed to start bot: No valid Discord token")
    sys.exit(1)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=commands.DefaultHelpCommand(command_attrs={'name': 'info'}))

# Replace the hardcoded constants with config loading
def load_config():
    """Load configuration from config.yaml, checking both /opt/timerbot/bot/ and local directory"""
    try:
        # First try the /opt/timerbot/bot/ location
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = yaml.safe_load(f)
                logger.info(f"Loaded configuration from {CONFIG_FILE}")
                return config
                
        # If not found, try local directory
        local_config = "config.yaml"
        if os.path.exists(local_config):
            with open(local_config, 'r') as f:
                config = yaml.safe_load(f)
                logger.info(f"Loaded configuration from {local_config}")
                return config
                
        # If neither exists, use defaults
        logger.error("No config.yaml found in either /opt/timerbot/bot/ or local directory")
        logger.info("Using default configuration")
        return {
            'check_interval': 60,    # seconds
            'notification_time': 60,  # minutes
            'expiry_time': 60        # minutes
        }
    except Exception as e:
        logger.error(f"Error loading config.yaml: {e}")
        logger.info("Using default configuration")
        return {
            'check_interval': 60,
            'notification_time': 60,
            'expiry_time': 60
        }

# Load config at startup
CONFIG = load_config()

# Replace hardcoded values with config values
EVE_TZ = pytz.timezone('UTC')

# Instead, use the config values
TIMERBOARD_CHANNEL_ID = CONFIG['channels']['timerboard']
TIMERBOARD_CMD_CHANNEL_ID = CONFIG['channels']['commands']

@dataclass
class Timer:
    time: datetime.datetime
    description: str
    timer_id: int
    system: str = ""
    structure_name: str = ""
    notes: str = ""
    message_id: Optional[int] = None
    gate_distance: Optional[int] = None

    def to_string(self) -> str:
        time_str = self.time.strftime('%Y-%m-%d %H:%M:%S')
        # Format: ```time```  **system** - structure_name  notes (id)
        notes_str = f" {self.notes.strip('[]')}" if self.notes else ""
        return f"```{time_str}```  **{self.system}** - {self.structure_name}  {notes_str} ({self.timer_id})"

    def is_similar(self, other: 'Timer') -> bool:
        # Check if timers are within 5 minutes of each other and have same system and structure
        time_diff = abs((self.time - other.time).total_seconds()) / 60
        return (time_diff <= 5 and 
                self.system.lower() == other.system.lower() and
                self.structure_name.lower() == other.structure_name.lower())

def clean_system_name(system: str) -> str:
    """Clean system name for URLs and display"""
    # Remove or replace special characters
    system = system.replace('»', '-').replace('«', '-')
    # Remove extra spaces and dashes
    system = '-'.join(filter(None, system.split()))
    return system

class TimerBoard:
    SAVE_FILE = SAVE_FILE
    STARTING_TIMER_ID = 1000  # Fixed starting ID
    MAX_MESSAGE_LENGTH = 1900  # Discord message length limit
    
    def __init__(self):
        self.timers = []
        self.next_id = self.STARTING_TIMER_ID
        self.last_update = None
        self.load_data()

    def save_data(self):
        """Save timerboard data to JSON file"""
        data = {
            'next_id': self.next_id,
            'timers': [
                {
                    'time': timer.time.isoformat(),
                    'description': timer.description,
                    'timer_id': timer.timer_id,
                    'system': timer.system,
                    'structure_name': timer.structure_name,
                    'notes': timer.notes,
                    'message_id': timer.message_id,
                    'gate_distance': timer.gate_distance
                }
                for timer in self.timers
            ]
        }
        
        try:
            with open(self.SAVE_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved timerboard data to {self.SAVE_FILE}")
        except Exception as e:
            logger.error(f"Error saving timerboard data: {e}")

    def load_data(self):
        """Load timerboard data from JSON file"""
        try:
            # First try the /opt/timerbot/data/ location
            if Path(self.SAVE_FILE).exists():
                logger.info(f"Loading timerboard data from {self.SAVE_FILE}")
                with open(self.SAVE_FILE, 'r') as f:
                    data = json.load(f)
            else:
                # Try local directory
                local_file = "timerboard_data.json"
                if Path(local_file).exists():
                    logger.info(f"Loading timerboard data from {local_file}")
                    with open(local_file, 'r') as f:
                        data = json.load(f)
                else:
                    logger.info("No save file found in either location")
                    logger.info("Starting with empty timerboard")
                    self.next_id = self.STARTING_TIMER_ID
                    self.timers = []
                    return

            # Process the loaded data
            self.next_id = max(data.get('next_id', self.STARTING_TIMER_ID), self.STARTING_TIMER_ID)
            logger.info(f"Next timer ID set to: {self.next_id}")
            
            self.timers = []
            for timer_data in data.get('timers', []):
                try:
                    time = datetime.datetime.fromisoformat(timer_data['time'])
                    timer = Timer(
                        time=time,
                        description=timer_data['description'],
                        timer_id=timer_data['timer_id'],
                        system=timer_data['system'],
                        structure_name=timer_data['structure_name'],
                        notes=timer_data.get('notes', ''),
                        message_id=timer_data.get('message_id'),
                        gate_distance=timer_data.get('gate_distance')
                    )
                    self.timers.append(timer)
                    logger.info(f"Loaded timer: {timer.system} - {timer.structure_name} at {time} (ID: {timer.timer_id})")
                except Exception as e:
                    logger.error(f"Error loading timer: {e}")
                    logger.error(f"Timer data: {timer_data}")
            
            logger.info(f"Successfully loaded {len(self.timers)} timers")
        except Exception as e:
            logger.error(f"Error loading timerboard data: {e}")
            logger.info("Starting with empty timerboard")
            self.next_id = self.STARTING_TIMER_ID
            self.timers = []

    def update_next_id(self):
        """Update next_id based on highest existing timer ID"""
        if self.timers:
            max_id = max(timer.timer_id for timer in self.timers)
            self.next_id = max(max_id + 1, self.STARTING_TIMER_ID)  # Never go below starting ID
        else:
            self.next_id = self.STARTING_TIMER_ID

    def sort_timers(self):
        self.timers.sort(key=lambda x: x.time)

    async def add_timer(self, time: datetime.datetime, description: str) -> tuple[Timer, list[Timer]]:
        # Parse system and structure name from description
        # First try to match the full system - structure format with possible Ansiblex name
        system_match = re.match(r'([A-Z0-9-]+)(\s*[»«].*?)(?=\s+\d+,\d+\s+km|\n|$)', description)
        if system_match:
            system = system_match.group(1).strip()
            structure_name = (system + system_match.group(2)).strip()  # Keep full name including the system
            logger.info(f"Adding timer in system: {system} (structure: {structure_name})")
        else:
            # Fallback to regular system - structure format
            system_match = re.match(r'([^\s-]+(?:-[^\s]+)?)\s*-\s*(.+?)(?:\n|$)', description)
            if system_match:
                system = system_match.group(1).strip()
                structure_name = system_match.group(2).strip()
                logger.info(f"Adding timer with system: {system}")
            else:
                system = ""
                structure_name = description

        # Extract notes tags if present
        notes_match = re.search(r'\[(.*?)\](?:\[(.*?)\])*$', description)
        notes = notes_match.group(0) if notes_match else ""

        new_timer = Timer(
            time=time,
            description=description,
            timer_id=self.next_id,
            system=system,
            structure_name=structure_name,
            notes=notes,
            gate_distance=None
        )
        
        # Check for duplicates
        similar_timers = [t for t in self.timers if t.is_similar(new_timer)]
        if not similar_timers:
            self.timers.append(new_timer)
            self.next_id += 1
            self.sort_timers()
            self.save_data()  # Save after adding timer
            return new_timer, []
        return new_timer, similar_timers

    def remove_timer(self, timer_id: int) -> Optional[Timer]:
        for timer in self.timers:
            if timer.timer_id == timer_id:
                self.timers.remove(timer)
                self.save_data()  # Save after removing timer
                return timer
        return None

    def remove_expired(self) -> list[Timer]:
        """Remove timers that are older than the configured expiry time"""
        now = datetime.datetime.now(EVE_TZ)
        expiry_threshold = now - datetime.timedelta(minutes=CONFIG['expiry_time'])
        
        expired = [t for t in self.timers if t.time < expiry_threshold]
        
        if expired:
            self.timers = [t for t in self.timers if t.time >= expiry_threshold]
            logger.info(f"Removed {len(expired)} expired timers")
            self.save_data()  # Save after removing expired timers
        
        return expired

    async def update_timerboard(self, channel: discord.TextChannel):
        existing_messages = []
        async for message in channel.history(limit=100):
            if message.author == bot.user:
                existing_messages.append(message)
        existing_messages.reverse()

        messages_to_update = []
        current_message = ""

        if self.timers:
            for timer in self.timers:
                time_str = timer.time.strftime('%Y-%m-%d %H:%M:%S')
                clean_system = clean_system_name(timer.system)
                system_link = f"[{timer.system}](https://evemaps.dotlan.net/system/{clean_system})"
                
                timer_line = (
                    f"`{time_str}` "
                    f"{system_link} - "
                    f"{timer.structure_name} {timer.notes} "
                    f"({timer.timer_id})\n"
                )
                
                if len(current_message) + len(timer_line) > self.MAX_MESSAGE_LENGTH:
                    messages_to_update.append(current_message.strip())
                    current_message = timer_line
                else:
                    current_message += timer_line

            if current_message:
                messages_to_update.append(current_message.strip())

            # Update or send messages
            for i, content in enumerate(messages_to_update):
                if i < len(existing_messages):
                    await existing_messages[i].edit(content=content)
                else:
                    await channel.send(content)

            # Delete any extra messages
            for message in existing_messages[len(messages_to_update):]:
                await message.delete()
        else:
            content = "No active timers."
            if existing_messages:
                await existing_messages[0].edit(content=content)
                for message in existing_messages[1:]:
                    await message.delete()
            else:
                await channel.send(content)

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
                    cmd_channel = bot.get_channel(TIMERBOARD_CMD_CHANNEL_ID)
                    if cmd_channel:
                        clean_system = clean_system_name(timer.system)
                        system_link = f"[{timer.system}](https://evemaps.dotlan.net/system/{clean_system})"
                        notification = f"⚠️ Timer in {CONFIG['notification_time']} minutes: {system_link} - {timer.structure_name} {timer.notes} at `{timer.time.strftime('%Y-%m-%d %H:%M:%S')}` (ID: {timer.timer_id})"
                        await cmd_channel.send(notification)
                        logger.info(f"Sent notification for timer {timer.timer_id}")
                
                # Check for timer start (within 1 minute of start time)
                elif -1 <= minutes_until < 1:  # Within 1 minute of timer time
                    cmd_channel = bot.get_channel(TIMERBOARD_CMD_CHANNEL_ID)
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
                channel = bot.get_channel(TIMERBOARD_CHANNEL_ID)
                await timerboard.update_timerboard(channel)
            
            await asyncio.sleep(CONFIG['check_interval'])
            
        except Exception as e:
            logger.error(f"Error in timer check loop: {e}")
            await asyncio.sleep(CONFIG['check_interval'])

@bot.event
async def on_ready():
    logger.info(f"Bot connected as {bot.user}")
    
    # Debug channel information
    logger.info("Checking channels:")
    logger.info(f"Timerboard channel: {TIMERBOARD_CHANNEL_ID}")
    logger.info(f"Commands channel: {TIMERBOARD_CMD_CHANNEL_ID}")
    
    timerboard_channel = bot.get_channel(TIMERBOARD_CHANNEL_ID)
    cmd_channel = bot.get_channel(TIMERBOARD_CMD_CHANNEL_ID)
    
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

# Update the cmd_channel_check function
async def cmd_channel_check(ctx):
    logger.info(f"Command '{ctx.command}' received from {ctx.author} in #{ctx.channel.name}")
    return ctx.channel.id == TIMERBOARD_CMD_CHANNEL_ID

# Add a commands group with category
class TimerCommands(commands.Cog, name="Basic Commands"):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.check(cmd_channel_check)
    async def add(self, ctx, *, input_text: str):
        """Add a new timer
        Format: !add YYYY-MM-DD HH:MM:SS system - structure [tags]
        or: !add system structure Reinforced until YYYY.MM.DD HH:MM:SS [tags]"""
        try:
            # Look for "Reinforced until" pattern with optional location tags
            reinforced_match = re.search(r'(.*?)Reinforced until (\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2})(?:\s+(\[.*\]))?', input_text)
            if reinforced_match:
                # Extract system, structure name, and location info
                prefix = reinforced_match.group(1).strip()  # Everything before "Reinforced until"
                time_str = reinforced_match.group(2).replace('.', '-')  # The datetime
                tags = reinforced_match.group(3) if reinforced_match.group(3) else ""  # Location tags if present
                
                # Extract system and structure name from prefix
                system_structure_match = re.match(r'([^\s]+)\s+(.+?)(?:\s+\d+\s*km)?$', prefix)
                if system_structure_match:
                    system = system_structure_match.group(1)
                    structure = system_structure_match.group(2)
                    description = f"{system} - {structure} {tags}"
                else:
                    description = input_text  # Fallback to full text if pattern doesn't match
            else:
                # Try to parse the first part as a direct time input
                parts = input_text.split(' ', 1)
                if len(parts) < 2:
                    await ctx.send("Invalid format. Use: !add YYYY-MM-DD HH:MM:SS description")
                    return
                time_str = parts[0]
                description = parts[1]

            # Parse the time
            time = datetime.datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
            time = EVE_TZ.localize(time)
            
            new_timer, similar_timers = await timerboard.add_timer(time, description)
            
            if similar_timers:
                logger.info(f"{ctx.author} added timer {new_timer.timer_id} with similar timers warning")
                similar_list = "\n".join([t.to_string() for t in similar_timers])
                await ctx.send(f"⚠️ Warning: Similar timers found:\n{similar_list}\n"
                             f"Added anyway with ID {new_timer.timer_id}")
            else:
                logger.info(f"{ctx.author} added timer {new_timer.timer_id}")
                await ctx.send(f"Timer added with ID {new_timer.timer_id}")
            
            # Update timerboard channel
            timerboard_channel = bot.get_channel(TIMERBOARD_CHANNEL_ID)
            await timerboard.update_timerboard(timerboard_channel)
            
        except ValueError as e:
            await ctx.send("Invalid time format. Use: YYYY-MM-DD HH:MM:SS or system structure Reinforced until YYYY.MM.DD HH:MM:SS [tags]")

    @commands.command()
    @commands.check(cmd_channel_check)
    async def rm(self, ctx, timer_id: int):
        """Remove a timer by its ID"""
        timer = timerboard.remove_timer(timer_id)
        if timer:
            logger.info(f"{ctx.author} removed timer {timer_id}")
            clean_system = clean_system_name(timer.system)
            system_link = f"[{timer.system}](https://evemaps.dotlan.net/system/{clean_system})"
            await ctx.send(f"Removed timer: {system_link} - {timer.structure_name} {timer.notes} at `{timer.time.strftime('%Y-%m-%d %H:%M:%S')}` (ID: {timer.timer_id})")
            timerboard_channel = bot.get_channel(TIMERBOARD_CHANNEL_ID)
            await timerboard.update_timerboard(timerboard_channel)
        else:
            logger.warning(f"{ctx.author} attempted to remove non-existent timer {timer_id}")
            await ctx.send(f"No timer found with ID {timer_id}")

    @commands.command()
    @commands.check(cmd_channel_check)
    async def refresh(self, ctx):
        """Refresh the timerboard by clearing and recreating all messages"""
        try:
            logger.info(f"{ctx.author} requested timerboard refresh")
            channel = bot.get_channel(TIMERBOARD_CHANNEL_ID)
            
            # Delete all bot messages in the channel
            deleted = 0
            async for message in channel.history(limit=100):
                if message.author == bot.user:
                    await message.delete()
                    deleted += 1
            
            # Recreate the timerboard
            await timerboard.update_timerboard(channel)
            
            logger.info(f"Timerboard refreshed - deleted {deleted} messages and recreated display")
            await ctx.send(f"Timerboard refreshed - deleted {deleted} messages and recreated display")
            
        except Exception as e:
            logger.error(f"Error refreshing timerboard: {e}")
            await ctx.send(f"Error refreshing timerboard: {e}")

# Move the commands into the Cog
async def setup():
    await bot.add_cog(TimerCommands(bot))

# Make sure this is at the end of your file
if __name__ == "__main__":
    asyncio.run(setup())
    bot.run(TOKEN)

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