from dataclasses import dataclass
import datetime
from typing import Optional
import json
from pathlib import Path
import re
import pytz
from bot.utils.logger import logger
from bot.utils.helpers import clean_system_name
from bot.utils.config import CONFIG
from bot.utils.eve_data import get_region
import asyncio

EVE_TZ = pytz.timezone('UTC')
SAVE_FILE = "/opt/timerbot/data/timerboard_data.json"

@dataclass
class Timer:
    time: datetime.datetime
    description: str
    timer_id: Optional[int] = None
    system: str = ""
    structure_name: str = ""
    notes: str = ""
    message_id: Optional[int] = None
    region: str = ""

    def __post_init__(self):
        """Parse system and structure name from description after initialization"""
        # Parse system and structure name from description
        match = re.match(r'([A-Z0-9-]+)\s*-\s*(.*?)(?:\s+\[.*\])?$', self.description)
        if match:
            self.system = match.group(1)
            self.structure_name = match.group(2).strip()
            self.notes = self.description[len(match.group(0)):].strip()
        else:
            self.system = "Unknown"
            self.structure_name = self.description
            self.notes = ""

    def to_string(self) -> str:
        """Format timer for display"""
        time_str = self.time.strftime('%Y-%m-%d %H:%M:%S')
        clean_system = clean_system_name(self.system)
        system_link = f"[{self.system}](https://evemaps.dotlan.net/system/{clean_system})"
        notes_str = f" {self.notes}" if self.notes else ""
        return f"`{time_str}` {system_link} ({self.region}) - {self.structure_name}{notes_str} ({self.timer_id})"

    def __str__(self) -> str:
        return self.to_string()

    def is_similar(self, other: 'Timer') -> bool:
        time_diff = abs((self.time - other.time).total_seconds()) / 60
        return (time_diff <= 5 and 
                self.system.lower() == other.system.lower() and
                self.structure_name.lower() == other.structure_name.lower())

class TimerBoard:
    SAVE_FILE = SAVE_FILE
    STARTING_TIMER_ID = 1000
    MAX_MESSAGE_LENGTH = 1900
    
    def __init__(self):
        self.timers = []
        self.next_id = self.STARTING_TIMER_ID
        self.bots = []  # List to store bot instances
        self.last_update = None
        self.load_data()

    def register_bot(self, bot, server_config):
        """Register a bot instance and its config for timerboard updates"""
        self.bots.append((bot, server_config))
        logger.info(f"Registered bot {bot.user if bot.user else 'Unknown'} for timerboard updates")

    async def update_all_timerboards(self):
        """Update timerboards in all registered servers"""
        logger.info(f"Updating timerboards in {len(self.bots)} servers")
        for bot, server_config in self.bots:
            channel = bot.get_channel(server_config['timerboard'])
            if channel:
                logger.info(f"Updating timerboard in {channel.guild.name}")
                await self.update_timerboard([channel])
            else:
                logger.warning(f"Could not find timerboard channel for bot {bot.user}")

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
                    'region': timer.region  # Add region to saved data
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
                        region=timer_data.get('region', get_region(timer_data['system']))  # Load region or look it up
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
            self.next_id = max(max_id + 1, self.STARTING_TIMER_ID)
        else:
            self.next_id = self.STARTING_TIMER_ID

    def sort_timers(self):
        """Sort timers by time"""
        self.timers.sort(key=lambda x: x.time)

    async def add_timer(self, time: datetime.datetime, description: str) -> tuple[Timer, list[Timer]]:
        """Add a new timer and update all timerboards"""
        try:
            # Parse system and structure name from description
            system_match = re.match(r'([A-Z0-9-]+)\s*-\s*(.+?)(?:\s+\[.*\])?$', description)
            if system_match:
                system = system_match.group(1).strip()
                structure_name = system_match.group(2).strip()
                
                # Extract notes (everything after the structure name in square brackets)
                notes_match = re.search(r'(\[.*\](?:\[.*\])*$)', description)
                notes = notes_match.group(1) if notes_match else ""
                
                # Get region info
                region = get_region(system)
                logger.info(f"Adding timer in {system} ({region})")
                logger.info(f"Structure: {structure_name}")
                logger.info(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')} EVE")
                if notes:
                    logger.info(f"Tags: {notes}")
            else:
                system = ""
                structure_name = description
                notes = ""
                logger.warning(f"Could not parse system from description: {description}")

            # Look up region for the system
            region = get_region(system) if system else ""
            
            new_timer = Timer(
                time=time,
                description=description,
                timer_id=self.next_id,
                system=system,
                structure_name=structure_name,
                notes=notes,
                region=region
            )
            
            # Check for duplicates
            similar_timers = [t for t in self.timers if t.is_similar(new_timer)]
            if similar_timers:
                logger.warning(f"Found {len(similar_timers)} similar timers:")
                for t in similar_timers:
                    logger.warning(f"  - ID {t.timer_id}: {t.system} - {t.structure_name} at {t.time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Always add the timer
            self.timers.append(new_timer)
            self.next_id += 1
            self.sort_timers()
            
            # Save and update all timerboards
            self.save_data()
            await self.update_all_timerboards()
            
            logger.info(f"Successfully added timer with ID {new_timer.timer_id}")
            return new_timer, similar_timers
            
        except Exception as e:
            logger.error(f"Error adding timer: {e}")
            raise

    def remove_timer(self, timer_id: int) -> Optional[Timer]:
        """Remove a timer and update all timerboards"""
        timer = None
        for t in self.timers:
            if t.timer_id == timer_id:
                timer = t
                self.timers.remove(t)
                break
                
        if timer:
            self.save_data()
            # Schedule timerboard update
            asyncio.create_task(self.update_all_timerboards())
            
        return timer

    def remove_expired(self) -> list[Timer]:
        """Remove timers that are older than the configured expiry time"""
        now = datetime.datetime.now(EVE_TZ)
        expiry_threshold = now - datetime.timedelta(minutes=CONFIG['expiry_time'])
        
        expired = [t for t in self.timers if t.time < expiry_threshold]
        
        if expired:
            self.timers = [t for t in self.timers if t.time >= expiry_threshold]
            logger.info(f"Removing {len(expired)} expired timers:")
            for timer in expired:
                logger.info(f"  - ID {timer.timer_id}: {timer.system} ({timer.region}) - {timer.structure_name}")
                logger.info(f"    Time: {timer.time.strftime('%Y-%m-%d %H:%M:%S')} EVE")
                if timer.notes:
                    logger.info(f"    Tags: {timer.notes}")
            self.save_data()
        
        return expired

    async def update_timerboard(self, channels):
        """Update the timerboard display"""
        if not isinstance(channels, list):
            channels = [channels]
            
        logger.info(f"Updating timerboard in {len(channels)} channels")
        logger.info(f"Current timers in memory: {len(self.timers)}")
        for timer in self.timers:
            logger.info(f"  Timer: {timer}")
        
        for channel in channels:
            if not channel:
                logger.warning("Skipping update for None channel")
                continue
                
            logger.info(f"Updating timerboard in server: {channel.guild.name} (Channel: {channel.name})")
            try:
                # Create the timerboard message
                now = datetime.datetime.now(EVE_TZ)
                header = f"Current Time: {now.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                
                # Sort timers by time
                sorted_timers = sorted(self.timers, key=lambda x: x.time)
                logger.info(f"Sorted timers for {channel.guild.name}: {len(sorted_timers)} timers")
                
                # Build timer list
                timer_list = []
                for timer in sorted_timers:
                    timer_list.append(timer.to_string())
                    logger.info(f"Added timer to list: {timer}")
                
                # Combine all parts
                message = header + "\n".join(timer_list) if timer_list else header + "No active timers."
                
                # Find and update the most recent bot message
                most_recent_msg = None
                async for msg in channel.history(limit=100):
                    if msg.author == channel.guild.me:
                        most_recent_msg = msg
                        break
                
                if most_recent_msg:
                    logger.info(f"Found existing message in {channel.guild.name}, updating...")
                    logger.info(f"Old content:\n{most_recent_msg.content}")
                    logger.info(f"New content:\n{message}")
                    await most_recent_msg.edit(content=message)
                    logger.info(f"Successfully updated timerboard in {channel.guild.name}")
                else:
                    logger.info(f"No existing message found in {channel.guild.name}, creating new...")
                    await channel.send(message)
                    logger.info(f"Successfully created new timerboard in {channel.guild.name}")
                    
            except Exception as e:
                logger.error(f"Error updating timerboard in {channel.guild.name}: {e}")
                logger.exception("Full traceback:") 