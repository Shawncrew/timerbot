from dataclasses import dataclass
import datetime
from typing import Optional
import json
from pathlib import Path
import re
import pytz
import shutil
import asyncio

from bot.utils.logger import logger
from bot.utils.helpers import clean_system_name
from bot.utils.config import CONFIG
from bot.utils.eve_data import get_region

try:
    from discord.errors import HTTPException as DiscordHTTPException
except ImportError:
    DiscordHTTPException = None

EVE_TZ = pytz.timezone('UTC')
# Production path; on Windows or when missing, use project-root local file
SAVE_FILE_DEFAULT = "/opt/timerbot/data/timerboard_data.json"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _get_save_path():
    """Use production path if it exists; otherwise project root (for local/Windows runs)."""
    prod = Path(SAVE_FILE_DEFAULT)
    if prod.exists() or prod.parent.exists():
        return str(prod)
    return str(_PROJECT_ROOT / "timerboard_data.json")


SAVE_FILE = _get_save_path()

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
        # Only parse if system wasn't already provided (e.g., from add_timer method)
        if self.system:
            # System already set, just ensure region is set if needed
            if not self.region:
                self.region = get_region(self.system)
            return
        
        # First try to parse Sov Hub format
        sov_hub_match = re.match(r'Sov Hub \((.*?)\)', self.description)
        if sov_hub_match:
            self.system = sov_hub_match.group(1)
            self.structure_name = "Sov Hub"
            
            # Extract tags (everything in square brackets)
            tags_match = re.findall(r'\[(.*?)\]', self.description)
            self.notes = ' '.join(f'[{tag}]' for tag in tags_match) if tags_match else ""
            
            # Get region info if not already set
            if not self.region:
                self.region = get_region(self.system)
        else:
            # Try standard format
            # System names can be alphanumeric with dashes (TFA0-U) or regular names (Getrenjesa)
            match = re.match(r'([A-Za-z0-9-]+)\s*-\s*(.*?)(?=\s*\[|$)', self.description)
            if match:
                self.system = match.group(1)
                self.structure_name = match.group(2).strip()
                
                # Extract tags
                tags_match = re.findall(r'\[(.*?)\]', self.description)
                self.notes = ' '.join(f'[{tag}]' for tag in tags_match) if tags_match else ""
                
                # Get region info
                if not self.region:
                    self.region = get_region(self.system)
            else:
                self.system = "Unknown"
                self.structure_name = self.description
                self.notes = ""
                self.region = ""

    def to_string(self) -> str:
        """Convert timer to string format for display
        Format: <timer><systemName>(region)<StructureName> <tags> (timer_id)
        Where systemName is a clickable hyperlink to evemaps.dotlan
        """
        now = datetime.datetime.now(EVE_TZ)
        time_str = self.time.strftime('%Y-%m-%d %H:%M:%S')
        clean_system = clean_system_name(self.system)
        # System name as clickable markdown link
        system_link = f"[{self.system}](https://evemaps.dotlan.net/system/{clean_system})"
        is_expired = self.time < now

        # Format: timestamp systemLink (region) structureName tags (timer_id)
        # If this is an IHUB timer and the description contains the shield emoji, use the description directly
        if '[IHUB]' in self.description and '🛡️' in self.description:
            # For IHUB, extract structure name from description (it includes the emoji)
            # Description format: "System - Infrastructure Hub [NC][IHUB] 🛡️"
            # We want: timestamp systemLink (region) Infrastructure Hub [NC][IHUB] 🛡️ (timer_id)
            structure_part = self.description.split(' - ', 1)[1] if ' - ' in self.description else self.description
            region_part = f"({self.region})" if self.region else ""
            base_str = f"`{time_str}` {system_link} {region_part} {structure_part}".strip()
        else:
            # Standard format: timestamp systemLink (region) structureName tags (timer_id)
            region_part = f"({self.region})" if self.region else ""
            base_str = f"`{time_str}` {system_link} {region_part} {self.structure_name}".strip()
            if self.notes:
                base_str += f" {self.notes}"
        
        # Add timer ID at the end
            base_str += f" ({self.timer_id})"
        
        if is_expired:
            base_str = f"~~{base_str}~~"
        return base_str

    def __str__(self) -> str:
        return self.to_string()

    def is_similar(self, other: 'Timer') -> bool:
        time_diff = abs((self.time - other.time).total_seconds()) / 60
        return (time_diff <= 5 and 
                self.system.lower() == other.system.lower() and
                self.structure_name.lower() == other.structure_name.lower())

    def to_api_dict(self) -> dict:
        """Export for API/JSON: time (ISO), description, timer_id, system, structure_name, notes, region."""
        return {
            "time": self.time.isoformat(),
            "description": self.description,
            "timer_id": self.timer_id,
            "system": self.system,
            "structure_name": self.structure_name,
            "notes": self.notes,
            "region": self.region,
        }


class TimerBoard:
    SAVE_FILE = SAVE_FILE
    STARTING_TIMER_ID = 1000
    MAX_MESSAGE_LENGTH = 1900
    UPDATE_INTERVAL = 60  # Update interval in seconds
    
    def __init__(self):
        try:
            logger.info("TimerBoard.__init__() called")
            self.timers = []
            self.next_id = self.STARTING_TIMER_ID
            self.bots = []  # List to store bot instances
            self.last_update = None
            self.update_task = None
            self._pending_update_task = None  # For debounced update_all_timerboards
            self.filtered_regions = set()  # Set of region names to filter out
            logger.info("TimerBoard basic attributes initialized, calling load_data()...")
            self.load_data()
            logger.info("TimerBoard.__init__() completed successfully")
        except Exception as e:
            logger.error(f"Error in TimerBoard.__init__(): {e}")
            logger.exception("Full traceback:")
            # Set defaults on error
            self.timers = []
            self.next_id = self.STARTING_TIMER_ID
            self.bots = []
            self.last_update = None
            self.update_task = None
            self._pending_update_task = None
            self.filtered_regions = set()
            raise

    def register_bot(self, bot, server_config):
        """Register a bot instance and its config for timerboard updates"""
        self.bots.append((bot, server_config))
        logger.info(f"Registered bot {bot.user if bot.user else 'Unknown'} for timerboard updates")
        
        # Start the update task if this is the first bot
        if len(self.bots) == 1:
            self.start_update_task()

    def start_update_task(self):
        """Start the periodic update task. First run is after UPDATE_INTERVAL so boot uses a single explicit update."""
        if not self.update_task:
            logger.info("Starting periodic timerboard update task")
            
            async def update_loop():
                # Don't run immediately on boot; let the single post-backfill update run first
                await asyncio.sleep(self.UPDATE_INTERVAL)
                while True:
                    try:
                        await self._update_all_timerboards_impl()
                        await asyncio.sleep(self.UPDATE_INTERVAL)
                    except Exception as e:
                        logger.error(f"Error in timerboard update loop: {e}")
                        logger.exception("Full traceback:")
                        await asyncio.sleep(self.UPDATE_INTERVAL)
            
            self.update_task = asyncio.create_task(update_loop())
            logger.info("Timerboard update task started")

    _UPDATE_DEBOUNCE_SECONDS = 3

    async def update_all_timerboards(self, immediate: bool = False):
        """Update timerboards in all registered servers.
        When immediate=False (e.g. from add_timer), updates are debounced so many rapid
        calls result in one update. When immediate=True (periodic loop, post-backfill),
        update runs once immediately."""
        if immediate:
            await self._update_all_timerboards_impl()
            return
        # Debounce: cancel any scheduled update and schedule one after a short delay
        if self._pending_update_task and not self._pending_update_task.done():
            self._pending_update_task.cancel()
        async def run_later():
            await asyncio.sleep(self._UPDATE_DEBOUNCE_SECONDS)
            await self._update_all_timerboards_impl()
        self._pending_update_task = asyncio.create_task(run_later())

    async def _update_all_timerboards_impl(self):
        """Internal: perform one full update of all timerboard channels."""
        logger.info(f"Updating timerboards in {len(self.bots)} servers")
        for i, (bot, server_config) in enumerate(self.bots):
            if i > 0:
                await asyncio.sleep(2)  # Space out API calls to avoid 429 rate limits
            channel = bot.get_channel(server_config['timerboard'])
            if channel:
                logger.info(f"Updating timerboard in {channel.guild.name}")
                await self.update_timerboard([channel])
            else:
                logger.warning(f"Could not find timerboard channel for bot {bot.user}")

    def save_data(self):
        """Save timerboard data to JSON file with backup"""
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
            ],
            'filtered_regions': list(self.filtered_regions)  # Save filtered regions
        }
        
        save_path = Path(self.SAVE_FILE)
        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            # Create backup before saving (for safety/recovery purposes, but not used for auto-restore)
            # The backfill function serves as the restoration mechanism by reading from Discord history
            if save_path.exists():
                backup_file = save_path.with_suffix('.json.bak')
                shutil.copy2(self.SAVE_FILE, backup_file)
            
            with open(self.SAVE_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved timerboard data to {self.SAVE_FILE}")
        except Exception as e:
            logger.error(f"Error saving timerboard data: {e}")

    def load_data(self):
        """Load timerboard data from JSON file"""
        try:
            # SAVE_FILE is already resolved (production or project-root local)
            if Path(self.SAVE_FILE).exists():
                logger.info(f"Loading timerboard data from {self.SAVE_FILE}")
                with open(self.SAVE_FILE, 'r') as f:
                    data = json.load(f)
            else:
                logger.info("No save file found")
                logger.info("Starting with empty timerboard")
                self.next_id = self.STARTING_TIMER_ID
                self.timers = []
                return

            # Process the loaded data
            self.next_id = max(data.get('next_id', self.STARTING_TIMER_ID), self.STARTING_TIMER_ID)
            logger.info(f"Next timer ID set to: {self.next_id}")
            
            # Load filtered regions
            self.filtered_regions = set(data.get('filtered_regions', []))
            logger.info(f"Loaded {len(self.filtered_regions)} filtered regions: {self.filtered_regions}")
            
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
            
            # Note: We no longer restore from backup. The backfill function serves as the restoration mechanism
            # by reading from Discord message history and re-adding any missing timers.
            
        except Exception as e:
            logger.error(f"Error loading timerboard data: {e}")
            logger.info("Starting with empty timerboard")
            self.next_id = self.STARTING_TIMER_ID
            self.timers = []
            self.filtered_regions = set()
    
    # Note: Backup restore functionality has been removed.
    # The backfill function now serves as the restoration mechanism by reading from Discord message history.
    # Backup files are still created for safety/recovery purposes but are not automatically restored.

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
            # System names can be alphanumeric with dashes (TFA0-U) or regular names (Getrenjesa)
            system_match = re.match(r'([A-Za-z0-9-]+)\s*-\s*(.+?)(?:\s+\[.*\])?$', description)
            if system_match:
                system = system_match.group(1).strip()
                structure_name = system_match.group(2).strip()
                
                # Extract notes (everything after the structure name in square brackets)
                notes_match = re.search(r'(\[.*\](?:\[.*\])*$)', description)
                notes = notes_match.group(1) if notes_match else ""
            else:
                system = ""
                structure_name = description
                notes = ""
                logger.warning(f"Could not parse system from description: {description}")

            # Look up region for the system (single lookup)
            region = get_region(system) if system else ""
            logger.info(f"Adding timer in {system} ({region})")
            logger.info(f"Structure: {structure_name}")
            logger.info(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')} EVE")
            if notes:
                logger.info(f"Tags: {notes}")
            
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
            
            # Save data (synchronous but fast)
            self.save_data()
            
            # Schedule timerboard update in background (non-blocking)
            # The periodic update task will also handle it, but this ensures immediate update
            asyncio.create_task(self.update_all_timerboards())
            
            logger.info(f"Successfully added timer with ID {new_timer.timer_id}")
            return new_timer, similar_timers
            
        except Exception as e:
            logger.error(f"Error adding timer: {e}")
            raise

    def remove_timer(self, timer_id: int) -> Optional[Timer]:
        """Remove a timer from the list and save data.
        Note: Timerboard update should be handled by the caller."""
        timer = None
        for t in self.timers:
            if t.timer_id == timer_id:
                timer = t
                self.timers.remove(t)
                break
                
        if timer:
            self.save_data()
            # Don't update timerboard here - let the caller handle it
            # This avoids race conditions and duplicate updates
            # Note: Backup file is kept for safety but not used for restoration.
            # The backfill function will restore timers from Discord message history.
            
        return timer

    def remove_expired(self) -> list[Timer]:
        """Remove timers that are more than 4 hours past their expiration time
        Timers are kept for 4 hours after expiration and shown with strikethrough
        """
        now = datetime.datetime.now(EVE_TZ)
        # Remove timers that are MORE than 4 hours past expiration
        # Timers within 4 hours of expiration are kept but shown with strikethrough
        # Safely get expiry_time from CONFIG, default to 240 (4 hours) if not available
        expiry_time = CONFIG.get('expiry_time', 240) if CONFIG else 240
        expiry_threshold = now - datetime.timedelta(minutes=expiry_time)
        
        logger.info(f"Checking for expired timers at {now}")
        logger.info(f"Expiry threshold (4 hours past timer time): {expiry_threshold}")
        
        # Only remove timers that are MORE than 4 hours past their timer time
        expired = [t for t in self.timers if t.time < expiry_threshold]
        
        if expired:
            # Remove expired timers from the list (only those past 4-hour window)
            self.timers = [t for t in self.timers if t.time >= expiry_threshold]
            logger.info(f"Removing {len(expired)} timers that are more than 4 hours past expiration:")
            for timer in expired:
                minutes_past = (now - timer.time).total_seconds() / 60
                logger.info(f"  - ID {timer.timer_id}: {timer.system} ({timer.region}) - {timer.structure_name}")
                logger.info(f"    Time: {timer.time.strftime('%Y-%m-%d %H:%M:%S')} EVE ({minutes_past:.1f} minutes ago)")
                if timer.notes:
                    logger.info(f"    Tags: {timer.notes}")
            
            # Save the updated timer list
            self.save_data()
            
            # Schedule an update of all timerboards
            asyncio.create_task(self.update_all_timerboards())
        else:
            logger.info("No timers found that are more than 4 hours past expiration")
        
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
                
                # Filter out timers from filtered regions
                # Ensure filtered_regions exists (safety check)
                if not hasattr(self, 'filtered_regions'):
                    self.filtered_regions = set()
                filtered_regions_upper = {r.upper() for r in self.filtered_regions}
                filtered_timers = [
                    t for t in sorted_timers 
                    if not t.region or (t.region and t.region.upper() not in filtered_regions_upper)
                ]
                logger.info(f"After filtering: {len(filtered_timers)} timers (filtered out {len(sorted_timers) - len(filtered_timers)})")
                
                # Build timer list
                timer_list = []
                for timer in filtered_timers:
                    timer_list.append(timer.to_string())
                    logger.info(f"Added timer to list: {timer}")
                
                # Split into multiple messages if needed
                messages = []
                current_message = header
                
                for timer_str in timer_list:
                    # Check if adding this timer would exceed the limit
                    if len(current_message) + len(timer_str) + 1 > self.MAX_MESSAGE_LENGTH:
                        # Current message is full, start a new one
                        messages.append(current_message.strip())
                        current_message = timer_str + "\n"
                    else:
                        # Add to current message
                        current_message += timer_str + "\n"
                
                # Add the last message if it has content
                if current_message.strip() and current_message.strip() != header.strip():
                    messages.append(current_message.strip())
                
                # If no timers, create a single message
                if not timer_list:
                    messages = [header + "No active timers."]
                
                # Find existing bot messages
                existing_messages = []
                async for msg in channel.history(limit=100):
                    if msg.author == channel.guild.me:
                        existing_messages.append(msg)
                existing_messages.reverse()  # Oldest first
                
                # Update or create messages
                for i, content in enumerate(messages):
                    if i < len(existing_messages):
                        # Update existing message
                        logger.info(f"Updating message {i+1} in {channel.guild.name}")
                        await existing_messages[i].edit(content=content)
                    else:
                        # Create new message
                        logger.info(f"Creating new message {i+1} in {channel.guild.name}")
                        await channel.send(content)
                
                # Delete any extra messages
                for message in existing_messages[len(messages):]:
                    logger.info(f"Deleting extra message in {channel.guild.name}")
                    await message.delete()
                    
                logger.info(f"Successfully updated timerboard in {channel.guild.name} with {len(messages)} messages")
                    
            except Exception as e:
                logger.error(f"Error updating timerboard in {channel.guild.name}: {e}")
                logger.exception("Full traceback:") 