import discord
from discord.ext import commands
import datetime
import re
from typing import Optional
import asyncio
from dataclasses import dataclass
import pytz
from dotenv import load_dotenv
import os  # Also needed for os.getenv
import requests
from bs4 import BeautifulSoup
import aiohttp  # Add this import at the top
import json
from pathlib import Path

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

TIMERBOARD_CHANNEL_ID = 1346598996830851072  # Add your channel ID
TIMERBOARD_CMD_CHANNEL_ID = 1346599034990891121  # Add your channel ID
EVE_TZ = pytz.timezone('UTC')  # EVE Online uses UTC

@dataclass
class Timer:
    time: datetime.datetime
    description: str
    timer_id: int
    system: str = ""  # Added field for system name
    structure_name: str = ""  # Added field for structure name
    location: str = ""  # For location tags
    message_id: Optional[int] = None

    def to_string(self) -> str:
        time_str = self.time.strftime('%Y-%m-%d %H:%M:%S')
        # Format: ```time```  **system** - structure_name  notes (id)
        location_str = f" {self.location.strip('[]')}" if self.location else ""
        return f"```{time_str}```  **{self.system}** - {self.structure_name}  {location_str} ({self.timer_id})"

    def is_similar(self, other: 'Timer') -> bool:
        # Check if timers are within 5 minutes of each other and have same system and structure
        time_diff = abs((self.time - other.time).total_seconds()) / 60
        return (time_diff <= 5 and 
                self.system.lower() == other.system.lower() and
                self.structure_name.lower() == other.structure_name.lower())

class TimerBoard:
    SAVE_FILE = "timerboard_data.json"
    
    def __init__(self):
        self.timers = []
        self.next_id = 1000
        self.last_update = None
        self.staging_system = None
        self.load_data()  # Load data when initializing

    def save_data(self):
        """Save timerboard data to JSON file"""
        data = {
            'next_id': self.next_id,
            'staging_system': self.staging_system,
            'timers': [
                {
                    'time': timer.time.isoformat(),
                    'description': timer.description,
                    'timer_id': timer.timer_id,
                    'system': timer.system,
                    'structure_name': timer.structure_name,
                    'location': timer.location,
                    'message_id': timer.message_id
                }
                for timer in self.timers
            ]
        }
        
        try:
            with open(self.SAVE_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"Saved timerboard data to {self.SAVE_FILE}")
        except Exception as e:
            print(f"Error saving timerboard data: {e}")

    def load_data(self):
        """Load timerboard data from JSON file"""
        try:
            if Path(self.SAVE_FILE).exists():
                print(f"\nLoading data from {self.SAVE_FILE}...")
                with open(self.SAVE_FILE, 'r') as f:
                    data = json.load(f)
                
                self.next_id = data.get('next_id', 1000)
                self.staging_system = data.get('staging_system')
                print(f"Loaded staging system: {self.staging_system}")
                
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
                            location=timer_data['location'],
                            message_id=timer_data.get('message_id')
                        )
                        self.timers.append(timer)
                        print(f"Loaded timer: {timer.system} - {timer.structure_name} at {time} ({timer.timer_id})")
                    except Exception as e:
                        print(f"Error loading timer: {e}")
                        print(f"Timer data: {timer_data}")
                
                print(f"\nSuccessfully loaded {len(self.timers)} timers")
                print(f"Next timer ID set to: {self.next_id}\n")
            else:
                print(f"\nNo save file found at {self.SAVE_FILE}")
                print("Starting with empty timerboard")
                self.next_id = 1000
                self.staging_system = None
                self.timers = []
        except Exception as e:
            print(f"\nError loading timerboard data: {e}")
            print("Starting with empty timerboard")
            self.next_id = 1000
            self.staging_system = None
            self.timers = []

    def update_next_id(self):
        """Update next_id based on highest existing timer ID"""
        if self.timers:
            max_id = max(timer.timer_id for timer in self.timers)
            self.next_id = max(max_id + 1, 1000)  # Never go below 1000
        else:
            self.next_id = 1000

    def sort_timers(self):
        self.timers.sort(key=lambda x: x.time)

    async def add_timer(self, time: datetime.datetime, description: str) -> tuple[Timer, list[Timer]]:
        # Parse system and structure name from description
        system_match = re.match(r'([^\s-]+(?:-[^\s-]+)?)\s*-\s*(.+?)(?:\n|$)', description)
        if system_match:
            system = system_match.group(1).strip()
            structure_name = system_match.group(2).strip()
            print(f"Adding timer with system: {system}")  # Debug print
        else:
            system = ""
            structure_name = description

        # Extract location tags if present
        location_match = re.search(r'\[(.*?)\](?:\[(.*?)\])*$', description)
        location = location_match.group(0) if location_match else ""

        new_timer = Timer(
            time=time,
            description=description,
            timer_id=self.next_id,
            system=system,
            structure_name=structure_name,
            location=location
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
        """Remove timers that are more than 1 hour old"""
        now = datetime.datetime.now(EVE_TZ)
        one_hour_ago = now - datetime.timedelta(hours=1)
        
        expired = [t for t in self.timers if t.time < one_hour_ago]
        
        if expired:
            self.timers = [t for t in self.timers if t.time >= one_hour_ago]
            print(f"Removed {len(expired)} expired timers")
            self.save_data()  # Save after removing expired timers
        
        return expired

    async def set_staging(self, system: str, channel: discord.TextChannel) -> bool:
        """Set the staging system and update the timerboard header"""
        self.staging_system = system
        self.save_data()  # Save after setting staging system
        await self.update_timerboard(channel)
        return True

    async def update_timerboard(self, channel: discord.TextChannel):
        existing_messages = []
        async for message in channel.history(limit=100):
            if message.author == bot.user:
                existing_messages.append(message)
        existing_messages.reverse()

        messages_to_update = []
        # Always start with staging system if set
        current_message = f"Staging System: {self.staging_system}\n" if self.staging_system else ""

        if self.timers:
            for timer in self.timers:
                time_str = timer.time.strftime('%Y-%m-%d %H:%M:%S')
                system_link = f"[{timer.system}](https://evemaps.dotlan.net/system/{timer.system.replace('-', '_')})"
                
                timer_line = (
                    f"`{time_str}` "
                    f"{system_link} - "
                    f"{timer.structure_name} {timer.location} "
                    f"({timer.timer_id})\n"
                )
                
                if len(current_message) + len(timer_line) > 1900:
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
            content = f"Staging System: {self.staging_system}\nNo active timers." if self.staging_system else "No active timers."
            if existing_messages:
                await existing_messages[0].edit(content=content)
                for message in existing_messages[1:]:
                    await message.delete()
            else:
                await channel.send(content)

timerboard = TimerBoard()

async def check_timers():
    await bot.wait_until_ready()
    print("Starting timer check loop...")
    while not bot.is_closed():
        try:
            now = datetime.datetime.now(EVE_TZ)
            
            # Check for timers that are about to happen
            for timer in timerboard.timers:
                time_until = timer.time - now
                minutes_until = time_until.total_seconds() / 60
                
                # If timer is between 60-61 minutes away, send notification
                if 60 <= minutes_until < 61:
                    cmd_channel = bot.get_channel(TIMERBOARD_CMD_CHANNEL_ID)
                    if cmd_channel:
                        system_link = f"[{timer.system}](https://evemaps.dotlan.net/system/{timer.system.replace('-', '_')})"
                        notification = f"⚠️ Timer in 60 minutes: {system_link} - {timer.structure_name} {timer.location} at `{timer.time.strftime('%Y-%m-%d %H:%M:%S')}` (ID: {timer.timer_id})"
                        await cmd_channel.send(notification)
                        print(f"Sent notification for timer {timer.timer_id}")
            
            # Check for expired timers
            expired = timerboard.remove_expired()
            if expired:
                print(f"Removed {len(expired)} expired timers:")
                for timer in expired:
                    print(f"- {timer.to_string()}")
                channel = bot.get_channel(TIMERBOARD_CHANNEL_ID)
                await timerboard.update_timerboard(channel)
            
            await asyncio.sleep(60)  # Check every minute
            
        except Exception as e:
            print(f"Error in timer check loop: {e}")
            await asyncio.sleep(60)  # Still wait before retrying

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    
    # The TimerBoard class will automatically load data from JSON in __init__
    # Just need to start the timer checking loop
    print("Starting timer check loop...")
    bot.loop.create_task(check_timers())
    
    # Update the timerboard display
    channel = bot.get_channel(TIMERBOARD_CHANNEL_ID)
    if channel:
        await timerboard.update_timerboard(channel)
    else:
        print(f"Could not find channel with ID {TIMERBOARD_CHANNEL_ID}")

# Add a commands group with category
class TimerCommands(commands.Cog, name="Basic Commands"):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.check(lambda ctx: ctx.channel.id == TIMERBOARD_CMD_CHANNEL_ID)
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
                similar_list = "\n".join([t.to_string() for t in similar_timers])
                await ctx.send(f"⚠️ Warning: Similar timers found:\n{similar_list}\n"
                             f"Added anyway with ID {new_timer.timer_id}")
            else:
                await ctx.send(f"Timer added with ID {new_timer.timer_id}")
            
            # Update timerboard channel
            timerboard_channel = bot.get_channel(TIMERBOARD_CHANNEL_ID)
            await timerboard.update_timerboard(timerboard_channel)
            
        except ValueError as e:
            await ctx.send("Invalid time format. Use: YYYY-MM-DD HH:MM:SS or system structure Reinforced until YYYY.MM.DD HH:MM:SS [tags]")

    @commands.command()
    @commands.check(lambda ctx: ctx.channel.id == TIMERBOARD_CMD_CHANNEL_ID)
    async def rm(self, ctx, timer_id: int):
        """Remove a timer by its ID"""
        timer = timerboard.remove_timer(timer_id)
        if timer:
            await ctx.send(f"Removed timer: {timer.to_string()}")
            timerboard_channel = bot.get_channel(TIMERBOARD_CHANNEL_ID)
            await timerboard.update_timerboard(timerboard_channel)
        else:
            await ctx.send(f"No timer found with ID {timer_id}")

# Move the commands into the Cog
async def setup():
    await bot.add_cog(TimerCommands(bot))

# Make sure this is at the end of your file
if __name__ == "__main__":
    asyncio.run(setup())
    bot.run(TOKEN)