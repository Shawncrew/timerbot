from discord.ext import commands
import datetime
import re
from bot.utils.logger import logger
from bot.utils.helpers import clean_system_name, cmd_channel_check
from bot.models.timer import EVE_TZ
from bot.utils.config import CONFIG
from discord import app_commands
from discord import Interaction
import discord
import pytz

# Structure mapping for tags
STRUCTURE_TAGS = {
    'KEEPSTAR': 'KEEPSTAR',
    'FORTIZAR': 'FORTIZAR',
    'AZBEL': 'AZBEL',
    'TATARA': 'TATARA',
    'ASTRAHUS': 'ASTRAHUS',
    'ATHANOR': 'ATHANOR',
    'RAITARU': 'RAITARU',
    'SOTIYO': 'SOTIYO',
    'ANSIBLEX': 'ANSI',
    'CYNO BEACON': 'CYNO BEACON',
    'CYNO JAMMER': 'CYNO JAMMER',
    'SKYHOOK': 'SKYHOOK',
    'METENOX': 'METENOX',
    'IHUB': 'IHUB',
}

# Define regions for alert
ALERT_REGIONS = {"THE SPIRE", "MALPAIS", "OUTER PASSAGE", "OASA", "ETHERIUM REACH"}

def extract_ticker(name):
    """Extract a ticker from an alliance or corp name (first two uppercase letters)."""
    if not name:
        return "[UNK]"
    # Remove punctuation and split
    import re
    words = re.findall(r'[A-Z]', name.upper())
    if len(words) >= 2:
        return f"[{''.join(words[:2])}]"
    elif words:
        return f"[{words[0]}]"
    else:
        return "[UNK]"

def parse_timer_message(content):
    """Parse structure type, structure name, system, timer type, timer time, and alliance/corp from a timer notification message."""
    # Structure type: after 'The ' and before first bold
    struct_type_match = re.search(r'The ([^*\n]+)', content)
    structure_type = struct_type_match.group(1).strip() if struct_type_match else None
    # Structure name: first bold after structure type (handle both **name** and **name.**)
    struct_name_match = re.search(r'\*\*([^*\n]+)\*\*', content)
    structure_name = struct_name_match.group(1).strip() if struct_name_match else None
    # System: look for bold text after "in" or markdown link
    system_match = re.search(r'in \*\*([^*\n]+)\*\*', content)
    if not system_match:
        system_match = re.search(r'in \[([A-Z0-9-]+)\]', content)
    system = system_match.group(1).strip() if system_match else None
    # Timer type and time
    timer_type = None
    timer_time = None
    if 'Hull timer end at:' in content:
        timer_type = 'HULL'
        timer_time_match = re.search(r'Hull timer end at: \*\*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\*\*', content)
    elif 'Armor timer end at:' in content:
        timer_type = 'ARMOR'
        timer_time_match = re.search(r'Armor timer end at: \*\*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\*\*', content)
    else:
        timer_time_match = None
    timer_time_str = timer_time_match.group(1).strip() if timer_time_match else None
    # Alliance/corp: after 'belonging to [' and before ']' or after 'belonging to' and before '.'
    alliance_match = re.search(r'belonging to \[([^\]]+)\]', content)
    if not alliance_match:
        alliance_match = re.search(r'belonging to ([^.\n]+)', content)
    alliance = alliance_match.group(1).strip() if alliance_match else None
    return structure_type, structure_name, system, timer_type, timer_time_str, alliance

def extract_ticker_from_message(content):
    """Return [WA] if 'Weaponised Holdings.' in content, else [NC]."""
    if 'Weaponised Holdings.' in content:
        return '[WA]'
    return '[NC]'

class TimerCommands(commands.Cog, name="timer"):
    def __init__(self, bot, timerboard):
        self.bot = bot
        self.timerboard = timerboard
        super().__init__()

    HELP_TEXT = """**Invalid format. Please use one of these formats:**

**Format 1: Direct time and description**
```
!add YYYY-MM-DD HH:MM:SS system - structure [tags]
```
Example: `!add 2024-01-15 14:30:00 Jita - Keepstar [NC][KEEPSTAR][ARMOR]`

**Format 2: Reinforced/Anchoring format**
```
!add system structure Reinforced until YYYY.MM.DD HH:MM:SS [tags]
```
Example:
```
!add 4M-QXK - PRIVATE MATSUNOMI P4M3
38.4 AU
Reinforced until 2024.01.01 01:08:33 [HORDE][ATHANOR][HULL]
```

**Format 3: Multi-line structure format**
Copy the structure name, distance, and reinforced line:
```
Structure Name
Distance
Reinforced until YYYY.MM.DD HH:MM:SS [alliance ticker][structure type][timer type]
```
Example:
```
4M-QXK - PRIVATE MATSUNOMI P4M3
38.4 AU
Reinforced until 2024.01.01 01:08:33 [HORDE][ATHANOR][HULL]
```

**Format 4: Mercenary Den**
```
!add Merc Den <systemName> <planet> <hours> <minutes> [TAG]
```
Examples:
- `!add Merc Den Jita Planet I 2 30 [NC]`
- `!add Merc Den Jita Planet I 2 30 [DECOY]`
- `!add Merc Den Jita Planet I 2 30` (defaults to [NC] if no tag)

**Tags format:**
- Alliance ticker: `[NC]`, `[HORDE]`, `[DECOY]`, etc.
- Structure type: `[KEEPSTAR]`, `[FORTIZAR]`, `[AZBEL]`, `[ATHANOR]`, `[IHUB]`, `[MERCENARY DEN]`, etc.
- Timer type: `[ARMOR]`, `[HULL]`, `[SHIELD]`

**Note:** Medium structures should use `[HULL]` since there is only one timer."""

    @commands.command()
    @commands.check(cmd_channel_check)
    async def add(self, ctx, *, input_text: str):
        """Add a new timer to the timerboard.

**Supported formats:**

**1. Direct time format:**
```
!add YYYY-MM-DD HH:MM:SS system - structure [tags]
```
Example: `!add 2024-01-15 14:30:00 Jita - Keepstar [NC][KEEPSTAR][ARMOR]`

**2. Reinforced/Anchoring format:**
```
!add system structure Reinforced until YYYY.MM.DD HH:MM:SS [tags]
```
Example:
```
!add 4M-QXK - PRIVATE MATSUNOMI P4M3
38.4 AU
Reinforced until 2024.01.01 01:08:33 [HORDE][ATHANOR][HULL]
```

**3. Multi-line structure format (copy from game):**
Copy structure name, distance, and reinforced line:
```
Structure Name
Distance
Reinforced until YYYY.MM.DD HH:MM:SS [alliance][structure][timer type]
```

**4. Mercenary Den format:**
```
!add Merc Den <systemName> <planet> <hours> <minutes> [TAG]
```
Examples:
- `!add Merc Den Jita Planet I 2 30 [NC]`
- `!add Merc Den Jita Planet I 2 30 [DECOY]`
- `!add Merc Den Jita Planet I 2 30` (defaults to [NC] if tag omitted)

**Tags:** `[alliance ticker][structure type][timer type]`
- Alliance: `[NC]`, `[HORDE]`, `[DECOY]`, etc.
- Structure: `[KEEPSTAR]`, `[FORTIZAR]`, `[AZBEL]`, `[ATHANOR]`, `[IHUB]`, `[MERCENARY DEN]`, etc.
- Timer: `[ARMOR]`, `[HULL]`, `[SHIELD]`

**Note:** Medium structures use `[HULL]` only (single timer)."""
        try:
            # Check for Mercenary Den format: !add Merc Den <systemName> <planet> <h> <m> [TAG]
            merc_den_match = re.match(r'^Merc Den\s+([A-Z0-9-]+)\s+([^\s]+)\s+(\d+)\s+(\d+)(?:\s+(\[[^\]]+\]))?\s*$', input_text.strip())
            if merc_den_match:
                system = merc_den_match.group(1)
                planet = merc_den_match.group(2)
                hours = int(merc_den_match.group(3))
                minutes = int(merc_den_match.group(4))
                alliance_tag = merc_den_match.group(5)  # Optional alliance tag like [NC] or [DECOY]
                
                # Default to [NC] if no tag provided
                if not alliance_tag:
                    alliance_tag = "[NC]"
                
                # Calculate timer time (current time + hours + minutes)
                now = datetime.datetime.now(EVE_TZ)
                timer_time = now + datetime.timedelta(hours=hours, minutes=minutes)
                
                # Create description for Mercenary Den
                description = f"{system} - {planet} {alliance_tag}[MERCENARY DEN]"
                
                new_timer, similar_timers = await self.timerboard.add_timer(timer_time, description)
                
                # Send confirmation
                if similar_timers:
                    similar_list = "\n".join([t.to_string() for t in similar_timers])
                    await ctx.send(
                        f"⚠️ Warning: Similar timers found:\n{similar_list}\n"
                        f"Added anyway with ID {new_timer.timer_id}"
                    )
                else:
                    await ctx.send(f"✅ Mercenary Den timer added: {system} - {planet} at {timer_time.strftime('%Y-%m-%d %H:%M:%S')} (ID: {new_timer.timer_id})")
                
                # Update all timerboards
                timerboard_channels = [
                    self.bot.get_channel(server_config['timerboard'])
                    for server_config in CONFIG['servers'].values()
                    if server_config['timerboard'] is not None
                ]
                await self.timerboard.update_timerboard(timerboard_channels)
                return
            
            # Look for the new format first (structure name on first line, distance on second, reinforced/anchoring on third)
            lines = input_text.split('\n')
            # Check if "Reinforced until" or "Anchoring until" is on line 2 (index 1) or line 3 (index 2)
            reinforced_line_idx = None
            for i, line in enumerate(lines):
                if 'Reinforced until' in line or 'Anchoring until' in line:
                    reinforced_line_idx = i
                    break
            
            if reinforced_line_idx is not None and len(lines) >= reinforced_line_idx + 1:
                # Keep the exact structure name from first line
                structure_name = lines[0].strip()
                logger.debug(f"Parsed structure name: {structure_name}")
                
                # Check if this is a Customs Office format: "Customs Office (DT-TCD IX) [alliance]"
                customs_office_match = re.match(r'^Customs Office\s+\(([A-Z0-9-]+)\s+([IVX]+)\)', structure_name)
                if customs_office_match:
                    system = customs_office_match.group(1).strip()
                    planet_num = customs_office_match.group(2).strip()
                    # Construct structure name as "Customs Office Planet IX"
                    structure_name = f"Customs Office Planet {planet_num}"
                    logger.debug(f"Parsed Customs Office - system: {system}, structure: {structure_name}")
                else:
                    # Extract system from structure name - handle special formats
                    system_match = re.match(r'(?:.*?\(([A-Z0-9-]+)[^\)]*\))|([A-Z0-9-]+)(?:\s*[»>]\s*.*)?', structure_name)
                    if system_match:
                        # Get system from either the parentheses group or the direct match
                        system = (system_match.group(1) or system_match.group(2)).strip()
                        
                        # Check if this is an Ansiblex (has » character or [Ansiblex] tag)
                        is_ansiblex = '»' in structure_name or '[Ansiblex]' in lines[reinforced_line_idx]
                        # Check if this is a Skyhook (has "Orbital Skyhook" in name)
                        is_skyhook = 'Orbital Skyhook' in structure_name
                        
                        if is_ansiblex:
                            # For Ansiblex, keep the full structure name including the system
                            structure_name = structure_name.strip()
                        elif is_skyhook:
                            # For Skyhook, format as "Orbital Skyhook Planet X"
                            planet_match = re.search(r'\(.*?\s+([IVX]+)\)', structure_name)
                            if planet_match:
                                planet_num = planet_match.group(1)
                                structure_name = f"Orbital Skyhook Planet {planet_num}"
                            else:
                                structure_name = "Orbital Skyhook"
                        else:
                            # For other structures, remove the system name and dash
                            structure_name = structure_name[len(system):].strip()
                            if structure_name.startswith('-'):
                                structure_name = structure_name[1:].strip()
                                
                        logger.debug(f"Parsed system: {system}, structure: {structure_name}, is_ansiblex: {is_ansiblex}, is_skyhook: {is_skyhook}")
                    else:
                        await ctx.send("Could not parse system name from structure")
                        return
                    
                # Extract time and tags from the "Reinforced until" or "Anchoring until" line
                time_match = re.search(r'(?:Reinforced|Anchoring) until (\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2})\s*(\[.*\](?:\[.*\])*)?$', lines[reinforced_line_idx])
                if time_match:
                    time_str = time_match.group(1).replace('.', '-')
                    reinforced_tags = time_match.group(2) if time_match.group(2) else ""
                    logger.debug(f"Extracted tags: {reinforced_tags}")
                    
                    # Create description with system and structure name
                    description = f"{system} - {structure_name}"
                    if reinforced_tags:  # Only add tags if they exist
                        description += f" {reinforced_tags}"
                    logger.debug(f"Final description: {description}")
                else:
                    await ctx.send("Invalid time format")
                    return
                    
            else:
                # Try existing formats
                reinforced_match = re.search(r'(.*?)Reinforced until (\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2})(?:\s+(\[.*\]))?', input_text)
                if reinforced_match:
                    # Extract system, structure name, and location info
                    prefix = reinforced_match.group(1).strip()
                    time_str = reinforced_match.group(2).replace('.', '-')
                    tags = reinforced_match.group(3) if reinforced_match.group(3) else ""
                    
                    # Extract system and structure name from prefix
                    system_structure_match = re.match(r'([^\s]+)\s+(.+?)(?:\s+\d+\s*km)?$', prefix)
                    if system_structure_match:
                        system = system_structure_match.group(1)
                        structure = system_structure_match.group(2)
                        description = f"{system} - {structure} {tags}"
                    else:
                        description = input_text
                else:
                    # Try to parse the direct time input format: YYYY-MM-DD HH:MM:SS <description>
                    direct_time_match = re.match(
                        r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(.+)$',
                        input_text.strip()
                    )
                    if not direct_time_match:
                        await ctx.send(self.HELP_TEXT)
                        return
                    time_str = direct_time_match.group(1)
                    description = direct_time_match.group(2)

            # Parse the time
            try:
                if 'time_str' in locals():
                    time = datetime.datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
                else:
                    await ctx.send(self.HELP_TEXT)
                    return
                time = EVE_TZ.localize(time)
            except ValueError as e:
                await ctx.send(f"Invalid time format. {self.HELP_TEXT}")
                return
            
            new_timer, similar_timers = await self.timerboard.add_timer(time, description)
            
            # Send confirmation immediately (non-blocking)
            if similar_timers:
                similar_list = "\n".join([t.to_string() for t in similar_timers])
                await ctx.send(
                    f"⚠️ Warning: Similar timers found:\n{similar_list}\n"
                    f"Added anyway with ID {new_timer.timer_id}"
                )
            else:
                await ctx.send(f"✅ Timer added with ID {new_timer.timer_id}")

            # Timerboard update is already scheduled in add_timer() as a background task
            # No need to update again here - it would be redundant and slow
            
        except Exception as e:
            logger.error(f"Error adding timer: {e}")
            await ctx.send(f"Error adding timer: {str(e)}")

    @commands.command()
    @commands.check(cmd_channel_check)
    async def rm(self, ctx, timer_id: int):
        """Remove a timer from the timerboard by its ID.

**Usage:**
```
!rm <timer_id>
```

**Example:**
```
!rm 1001
```

The timer ID is shown in parentheses at the end of each timer entry in the timerboard."""
        timer = self.timerboard.remove_timer(timer_id)
        if timer:
            logger.info(f"{ctx.author} removed timer {timer_id}")
            clean_system = clean_system_name(timer.system)
            system_link = f"[{timer.system}](https://evemaps.dotlan.net/system/{clean_system})"
            await ctx.send(f"Removed timer: {system_link} - {timer.structure_name} {timer.notes} at `{timer.time.strftime('%Y-%m-%d %H:%M:%S')}` (ID: {timer.timer_id})")
            
            # Update all timerboards
            timerboard_channels = [
                self.bot.get_channel(server_config['timerboard'])
                for server_config in CONFIG['servers'].values()
                if server_config['timerboard'] is not None
            ]
            await self.timerboard.update_timerboard(timerboard_channels)
        else:
            logger.warning(f"{ctx.author} attempted to remove non-existent timer {timer_id}")
            await ctx.send(f"No timer found with ID {timer_id}")

    @commands.command()
    @commands.check(cmd_channel_check)
    async def refresh(self, ctx):
        """Refresh the timerboard display by clearing and recreating all messages.

**Usage:**
```
!refresh
```

This command will:
- Delete all existing bot messages in timerboard channels
- Recreate the timerboard display with current timers
- Update all configured timerboard channels across all servers

Use this if the timerboard display becomes out of sync or corrupted."""
        try:
            logger.info(f"{ctx.author} requested timerboard refresh")
            
            # Get all timerboard channels, filtering out None values
            timerboard_channels = []
            for server_config in CONFIG['servers'].values():
                channel_id = server_config.get('timerboard')
                if channel_id is not None:
                    channel = self.bot.get_channel(channel_id)
                    if channel is not None:
                        timerboard_channels.append(channel)
            
            if not timerboard_channels:
                await ctx.send("❌ No timerboard channels found. Please check your configuration.")
                logger.warning("No timerboard channels found for refresh")
                return
            
            logger.info(f"Refreshing {len(timerboard_channels)} timerboard channel(s)")
            
            # Delete all bot messages in each channel
            total_deleted = 0
            for channel in timerboard_channels:
                try:
                    deleted = 0
                    async for message in channel.history(limit=100):
                        if message.author == self.bot.user:
                            await message.delete()
                            deleted += 1
                    total_deleted += deleted
                    logger.info(f"Deleted {deleted} messages from {channel.name} in {channel.guild.name}")
                except Exception as e:
                    logger.error(f"Error deleting messages from {channel.name} in {channel.guild.name}: {e}")
                    await ctx.send(f"⚠️ Error deleting messages from {channel.name}: {e}")
            
            # Recreate the timerboards
            await self.timerboard.update_timerboard(timerboard_channels)
            
            logger.info(f"Timerboards refreshed - deleted {total_deleted} messages and recreated displays")
            await ctx.send(f"✅ Timerboards refreshed - deleted {total_deleted} messages and recreated displays in {len(timerboard_channels)} channel(s)")
            
        except Exception as e:
            logger.error(f"Error refreshing timerboards: {e}")
            logger.exception("Full traceback:")
            await ctx.send(f"Error refreshing timerboards: {e}")

    @commands.command()
    @commands.check(cmd_channel_check)
    async def filter(self, ctx):
        """Filter timers from specific regions to hide them from the timerboard and disable alerts.

**Usage:**
```
!filter
```

**Filtered regions:**
- The Kalevala Expanse
- Oasa
- Cobalt Edge
- The Spire
- Malpais
- Etherium Reach
- Perrigen Falls

**Effects:**
- Timers from these regions are hidden from the timerboard display
- No alerts are sent for filtered timers (60-minute warnings or "timer starting now")
- Timers remain in the database and can be restored with `!unfilter`

**Note:** This command filters all specified regions at once. Use `!unfilter` to restore them."""
        try:
            regions_to_filter = {
                'The Kalevala Expanse',
                'Oasa',
                'Cobalt Edge',
                'The Spire',
                'Malpais',
                'Etherium Reach',
                'Perrigen Falls'
            }
            
            # Add regions to filtered set
            added_regions = []
            for region in regions_to_filter:
                if region.upper() not in {r.upper() for r in self.timerboard.filtered_regions}:
                    self.timerboard.filtered_regions.add(region)
                    added_regions.append(region)
            
            if added_regions:
                self.timerboard.save_data()
                
                # Update all timerboards
                timerboard_channels = [
                    self.bot.get_channel(server_config['timerboard'])
                    for server_config in CONFIG['servers'].values()
                    if server_config['timerboard'] is not None
                ]
                await self.timerboard.update_timerboard(timerboard_channels)
                
                logger.info(f"{ctx.author} filtered regions: {added_regions}")
                await ctx.send(f"✅ Filtered {len(added_regions)} region(s): {', '.join(added_regions)}")
            else:
                await ctx.send("All specified regions are already filtered.")
                
        except Exception as e:
            logger.error(f"Error filtering regions: {e}")
            await ctx.send(f"Error filtering regions: {e}")

    @commands.command(name='timerhelp', aliases=['commands'])
    @commands.check(cmd_channel_check)
    async def help(self, ctx, command_name: str = None):
        """Display help information for all timerbot commands.

**Usage:**
```
!timerhelp
```
or
```
!timerhelp <command>
```
(You can also use `!commands` as an alias)

**Available commands:**
- `!add` - Add a new timer (multiple formats supported)
- `!rm` - Remove a timer by ID
- `!refresh` - Refresh the timerboard display
- `!filter` - Filter timers from specific regions
- `!unfilter` - Unfilter timers from specific regions

Use `!timerhelp <command>` for detailed information about a specific command.
Example: `!timerhelp add`"""
        try:
            if command_name:
                command_name = command_name.lower()
                # Show specific command help
                help_texts = {
                    'add': """**!add** - Add a new timer to the timerboard.

**Supported formats:**

**1. Direct time format:**
```
!add YYYY-MM-DD HH:MM:SS system - structure [tags]
```
Example: `!add 2024-01-15 14:30:00 Jita - Keepstar [NC][KEEPSTAR][ARMOR]`

**2. Reinforced/Anchoring format:**
```
!add system structure Reinforced until YYYY.MM.DD HH:MM:SS [tags]
```
Example:
```
!add 4M-QXK - PRIVATE MATSUNOMI P4M3
38.4 AU
Reinforced until 2024.01.01 01:08:33 [HORDE][ATHANOR][HULL]
```

**3. Multi-line structure format (copy from game):**
Copy structure name, distance, and reinforced line:
```
Structure Name
Distance
Reinforced until YYYY.MM.DD HH:MM:SS [alliance][structure][timer type]
```

**4. Mercenary Den format:**
```
!add Merc Den <systemName> <planet> <hours> <minutes> [TAG]
```
Examples:
- `!add Merc Den Jita Planet I 2 30 [NC]`
- `!add Merc Den Jita Planet I 2 30 [DECOY]`
- `!add Merc Den Jita Planet I 2 30` (defaults to [NC] if tag omitted)

**Tags:** `[alliance ticker][structure type][timer type]`
- Alliance: `[NC]`, `[HORDE]`, `[DECOY]`, etc.
- Structure: `[KEEPSTAR]`, `[FORTIZAR]`, `[AZBEL]`, `[ATHANOR]`, `[IHUB]`, `[MERCENARY DEN]`, etc.
- Timer: `[ARMOR]`, `[HULL]`, `[SHIELD]`

**Note:** Medium structures use `[HULL]` only (single timer).""",
                    'rm': """**!rm** - Remove a timer from the timerboard by its ID.

**Usage:**
```
!rm <timer_id>
```

**Example:**
```
!rm 1001
```

The timer ID is shown in parentheses at the end of each timer entry in the timerboard.""",
                    'refresh': """**!refresh** - Refresh the timerboard display by clearing and recreating all messages.

**Usage:**
```
!refresh
```

This command will:
- Delete all existing bot messages in timerboard channels
- Recreate the timerboard display with current timers
- Update all configured timerboard channels across all servers

Use this if the timerboard display becomes out of sync or corrupted.""",
                    'filter': """**!filter** - Filter timers from specific regions to hide them from the timerboard and disable alerts.

**Usage:**
```
!filter
```

**Filtered regions:**
- The Kalevala Expanse
- Oasa
- Cobalt Edge
- The Spire
- Malpais
- Etherium Reach
- Perrigen Falls

**Effects:**
- Timers from these regions are hidden from the timerboard display
- No alerts are sent for filtered timers (60-minute warnings or "timer starting now")
- Timers remain in the database and can be restored with `!unfilter`

**Note:** This command filters all specified regions at once. Use `!unfilter` to restore them.""",
                    'unfilter': """**!unfilter** - Unfilter timers from specific regions to restore them to the timerboard and enable alerts.

**Usage:**
```
!unfilter
```

**Unfiltered regions:**
- The Kalevala Expanse
- Oasa
- Cobalt Edge
- The Spire
- Malpais
- Etherium Reach
- Perrigen Falls

**Effects:**
- Timers from these regions are restored to the timerboard display
- Alerts are re-enabled for unfiltered timers
- All timers from these regions become visible again

**Note:** This command unfilters all specified regions at once. Use `!filter` to hide them again."""
                }
                
                if command_name in help_texts:
                    await ctx.send(help_texts[command_name])
                else:
                    await ctx.send(f"Command '{command_name}' not found. Use `!timerhelp` to see all commands.")
            else:
                # Show general help
                help_text = """**Timerbot Commands**

**!add** - Add a new timer
```
!add YYYY-MM-DD HH:MM:SS system - structure [tags]
!add system structure Reinforced until YYYY.MM.DD HH:MM:SS [tags]
!add Merc Den <systemName> <planet> <hours> <minutes> [TAG]
```
Use `!help add` for full format details.

**!rm** - Remove a timer by ID
```
!rm <timer_id>
```

**!refresh** - Refresh timerboard display
```
!refresh
```

**!filter** - Filter timers from specific regions (hides from display and disables alerts)
```
!filter
```

**!unfilter** - Unfilter timers from specific regions (restores to display and enables alerts)
```
!unfilter
```

Use `!timerhelp <command>` for detailed information about any command."""
                await ctx.send(help_text)
        except Exception as e:
            logger.error(f"Error in help command: {e}")
            logger.exception("Full traceback:")
            await ctx.send(f"Error displaying help: {e}")

    @commands.command()
    @commands.check(cmd_channel_check)
    async def unfilter(self, ctx):
        """Unfilter timers from specific regions to restore them to the timerboard and enable alerts.

**Usage:**
```
!unfilter
```

**Unfiltered regions:**
- The Kalevala Expanse
- Oasa
- Cobalt Edge
- The Spire
- Malpais
- Etherium Reach
- Perrigen Falls

**Effects:**
- Timers from these regions are restored to the timerboard display
- Alerts are re-enabled for unfiltered timers
- All timers from these regions become visible again

**Note:** This command unfilters all specified regions at once. Use `!filter` to hide them again."""
        try:
            regions_to_unfilter = {
                'The Kalevala Expanse',
                'Oasa',
                'Cobalt Edge',
                'The Spire',
                'Malpais',
                'Etherium Reach',
                'Perrigen Falls'
            }
            
            # Remove regions from filtered set (case-insensitive)
            removed_regions = []
            filtered_regions_upper = {r.upper() for r in self.timerboard.filtered_regions}
            
            for region in regions_to_unfilter:
                if region.upper() in filtered_regions_upper:
                    # Find the exact region name in the set (case-insensitive match)
                    for filtered_region in list(self.timerboard.filtered_regions):
                        if filtered_region.upper() == region.upper():
                            self.timerboard.filtered_regions.remove(filtered_region)
                            removed_regions.append(filtered_region)
                            break
            
            if removed_regions:
                self.timerboard.save_data()
                
                # Update all timerboards
                timerboard_channels = [
                    self.bot.get_channel(server_config['timerboard'])
                    for server_config in CONFIG['servers'].values()
                    if server_config['timerboard'] is not None
                ]
                await self.timerboard.update_timerboard(timerboard_channels)
                
                logger.info(f"{ctx.author} unfiltered regions: {removed_regions}")
                await ctx.send(f"✅ Unfiltered {len(removed_regions)} region(s): {', '.join(removed_regions)}")
            else:
                await ctx.send("None of the specified regions are currently filtered.")
                
        except Exception as e:
            logger.error(f"Error unfiltering regions: {e}")
            await ctx.send(f"Error unfiltering regions: {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        """Monitor citadel channels for structure messages and auto-add timers"""
        try:
            # Only process messages from configured citadel_attacked channels
            for server_config in CONFIG['servers'].values():
                if message.channel.id == server_config.get('citadel_attacked'):
                    content = message.content
                    # If content is empty or doesn't contain keywords, try to extract from embed
                    if (not content or ("Structure lost shield" not in content and "Structure lost armor" not in content)) and message.embeds:
                        embed = message.embeds[0]
                        embed_text = []
                        if embed.title:
                            embed_text.append(embed.title)
                        if embed.description:
                            embed_text.append(embed.description)
                        for field in getattr(embed, 'fields', []):
                            embed_text.append(f"{field.name} {field.value}")
                        content = "\n".join(embed_text)
                        logger.info(f"[LIVE] Extracted embed content: {content}")
                    # Detect shield or armor loss
                    if ("Structure lost shield" in content or "Structure lost armor" in content):
                        # Use improved parsing
                        structure_type, structure_name, system, timer_type, timer_time_str, alliance = parse_timer_message(content)
                        logger.info(f"[LIVE] Parsed: structure_type={structure_type}, structure_name={structure_name}, system={system}, timer_type={timer_type}, timer_time={timer_time_str}, alliance={alliance}")
                        if not (structure_type and structure_name and system and timer_type and timer_time_str):
                            logger.warning(f"[LIVE] Failed to parse all fields. Message: {content}")
                            return
                        # Structure tag
                        structure_tag = None
                        for key in STRUCTURE_TAGS:
                            if key in structure_type.upper():
                                structure_tag = STRUCTURE_TAGS[key]
                                break
                        if not structure_tag:
                            structure_tag = structure_type.upper().split()[0]  # fallback
                        # Parse time
                        try:
                            timer_time = datetime.datetime.strptime(timer_time_str, "%Y-%m-%d %H:%M")
                            timer_time = EVE_TZ.localize(timer_time)
                        except Exception as e:
                            logger.warning(f"[LIVE] Could not parse timer time: {timer_time_str} | Error: {e} | Message: {content}")
                            return
                        # Build tags
                        tags = f"{extract_ticker_from_message(content)}[{structure_tag.upper()}][{timer_type.upper()}]"
                        description = f"{system} - {structure_name} {tags}"
                        # Add timer
                        new_timer, similar_timers = await self.timerboard.add_timer(timer_time, description)
                        # Notify command channel
                        cmd_channel = self.bot.get_channel(server_config['commands'])
                        if cmd_channel:
                            add_cmd = f"!add {timer_time.strftime('%Y-%m-%d %H:%M:%S')} {system} - {structure_name} {tags}"
                            await cmd_channel.send(
                                f"✅ Auto-added timer: {system} - {structure_name} at {timer_time.strftime('%Y-%m-%d %H:%M')} {tags} (ID: {new_timer.timer_id})\nAdd command: {add_cmd}"
                            )
                        logger.info(f"Auto-added timer from citadel-attacked: {description}")
                        return
                    break
                # --- New sov channel logic ---
                if message.channel.id == server_config.get('sov'):
                    logger.info(f"[SOV] Received message in sov channel: {message.id} | Author: {message.author} | Content: {message.content} | Embeds: {len(message.embeds)}")
                    content = message.content
                    # If content is empty or doesn't contain keywords, try to extract from embed
                    if (not content or "Infrastructure Hub" not in content) and message.embeds:
                        embed = message.embeds[0]
                        embed_text = []
                        if embed.title:
                            embed_text.append(embed.title)
                        if embed.description:
                            embed_text.append(embed.description)
                        for field in getattr(embed, 'fields', []):
                            embed_text.append(f"{field.name} {field.value}")
                        content = "\n".join(embed_text)
                        logger.info(f"[SOV] Extracted embed content: {content}")
                    else:
                        logger.info(f"[SOV] Using message content for parsing: {content}")
                    # Improved regex: match both Markdown and plain text, and 'has been reinforced'
                    match = re.search(r'Infrastructure Hub.*?in \[([A-Z0-9-]+)\][^\n]*?has been reinforced', content, re.IGNORECASE)
                    if match:
                        system = match.group(1)
                        logger.info(f"[SOV] Matched system: {system}")
                        # Try to extract timer time
                        timer_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2})', content)
                        if timer_match:
                            timer_time_str = timer_match.group(1)
                            try:
                                timer_time = datetime.datetime.strptime(timer_time_str, "%Y-%m-%d %H:%M")
                                timer_time = EVE_TZ.localize(timer_time)
                            except Exception as e:
                                logger.warning(f"[SOV] Could not parse timer time: {timer_time_str} | Error: {e} | Message: {content}")
                                return
                            # Try to get region from content (look for parenthesis after system link)
                            region_match = re.search(r'\[' + re.escape(system) + r'\][^\n]*?\(([^)]+)\)', content)
                            region = region_match.group(1).strip().upper() if region_match else None
                            alert_emoji = " 🚨" if region and region in ALERT_REGIONS else ""
                            tags = f"[NC][IHUB] 🛡️{alert_emoji}"
                            description = f"{system} - Infrastructure Hub {tags}"
                            new_timer, similar_timers = await self.timerboard.add_timer(timer_time, description)
                            logger.info(f"[SOV] Added timer: {description} at {timer_time}")
                            # Notify command channel
                            cmd_channel = self.bot.get_channel(server_config['commands'])
                            if cmd_channel:
                                add_cmd = f"!add {timer_time.strftime('%Y-%m-%d %H:%M:%S')} {system} - Infrastructure Hub {tags}"
                                await cmd_channel.send(
                                    f"✅ Auto-added SOV timer: {system} - Infrastructure Hub at {timer_time.strftime('%Y-%m-%d %H:%M')} {tags} (ID: {new_timer.timer_id})\nAdd command: {add_cmd}"
                                )
                            logger.info(f"Auto-added timer from SOV: {description}")
                        else:
                            logger.warning(f"[SOV] Could not find timer time in message: {content}")
                    else:
                        logger.info(f"[SOV] No match for Infrastructure Hub reinforced pattern in content: {content}")
                    break
                # --- Skyhook channel logic ---
                if message.channel.id == server_config.get('skyhooks'):
                    logger.info(f"[SKYHOOK] Received message in skyhooks channel: {message.id} | Author: {message.author} | Content: {message.content} | Embeds: {len(message.embeds)}")
                    content = message.content
                    # If content is empty or doesn't contain keywords, try to extract from embed
                    if (not content or ("Skyhook lost shield" not in content and "Customs Office" not in content)) and message.embeds:
                        embed = message.embeds[0]
                        embed_text = []
                        if embed.title:
                            embed_text.append(embed.title)
                        if embed.description:
                            embed_text.append(embed.description)
                        for field in getattr(embed, 'fields', []):
                            embed_text.append(f"{field.name} {field.value}")
                        content = "\n".join(embed_text)
                        logger.info(f"[SKYHOOK] Extracted embed content: {content}")
                    else:
                        logger.info(f"[SKYHOOK] Using message content for parsing: {content}")
                    
                    # Check for "Customs Office" reinforcement
                    if "Customs Office" in content and "has been reinforced" in content:
                        logger.info(f"[SKYHOOK] Found 'Customs Office' reinforcement in message")
                        # Extract system and planet from "The Customs Office at TFA0-U III in TFA0-U"
                        customs_match = re.search(
                            r'The Customs Office at\s+([A-Z0-9-]+)\s+([IVX]+)\s+in\s+([A-Z0-9-]+)',
                            content,
                            re.IGNORECASE
                        )
                        if customs_match:
                            system = customs_match.group(3).strip()  # System is the third group (after "in")
                            planet = customs_match.group(2).strip()
                            logger.info(f"[SKYHOOK] Matched Customs Office - system: {system}, planet: {planet}")
                            # Extract timer time from "will come out at: 2026-01-26 11:50"
                            timer_match = re.search(r'will come out at:\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})', content, re.IGNORECASE)
                            if timer_match:
                                timer_time_str = timer_match.group(1)
                                try:
                                    timer_time = datetime.datetime.strptime(timer_time_str, "%Y-%m-%d %H:%M")
                                    timer_time = EVE_TZ.localize(timer_time)
                                except Exception as e:
                                    logger.warning(f"[SKYHOOK] Could not parse Customs Office timer time: {timer_time_str} | Error: {e} | Message: {content}")
                                    return
                                # Build description with [INIT][POCO][FINAL] tags
                                tags = "[INIT][POCO][FINAL]"
                                structure_name = f"Customs Office Planet {planet}"
                                description = f"{system} - {structure_name} {tags}"
                                new_timer, similar_timers = await self.timerboard.add_timer(timer_time, description)
                                logger.info(f"[SKYHOOK] Added Customs Office timer: {description} at {timer_time}")
                                # Notify command channel
                                cmd_channel = self.bot.get_channel(server_config['commands'])
                                if cmd_channel:
                                    await cmd_channel.send(
                                        f"✅ Auto-added Customs Office timer: {system} - {structure_name} at {timer_time.strftime('%Y-%m-%d %H:%M')} {tags} (ID: {new_timer.timer_id})"
                                    )
                                logger.info(f"Auto-added Customs Office timer from skyhooks: {description}")
                            else:
                                logger.warning(f"[SKYHOOK] Could not find timer time in Customs Office message: {content}")
                        else:
                            logger.warning(f"[SKYHOOK] Could not parse system and planet from Customs Office message: {content}")
                    # Check for "Skyhook lost shield" indicator
                    elif "Skyhook lost shield" in content:
                        logger.info(f"[SKYHOOK] Found 'Skyhook lost shield' in message")
                        # Extract system and planet from "The Orbital Skyhook at 1-EVAX III in 1-EVAX"
                        # Pattern handles both markdown and plain text:
                        # "The Orbital Skyhook at **QRH-BF V** in [QRH-BF]" or
                        # "The Orbital Skyhook at QRH-BF V in QRH-BF"
                        skyhook_match = re.search(
                            r'The Orbital Skyhook at\s+(?:\*\*)?([A-Z0-9-]+)\s+(?:Planet\s+)?([IVX]+)(?:\*\*)?\s+in\s+(?:\[|\*\*)?([A-Z0-9-]+)(?:\]|\*\*)?', 
                            content, 
                            re.IGNORECASE
                        )
                        if skyhook_match:
                            system = skyhook_match.group(1).strip()
                            planet = skyhook_match.group(2).strip()
                            logger.info(f"[SKYHOOK] Matched system: {system}, planet: {planet}")
                            # Extract timer time from "reinforcement state until : 2025-11-14 21:52"
                            # Pattern handles both markdown and plain text:
                            # "reinforcement state until : **2026-01-04 23:55**" or
                            # "reinforcement state until : 2026-01-04 23:55"
                            timer_match = re.search(r'reinforcement state until\s*:\s*\*?\*?(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\*?\*?', content, re.IGNORECASE)
                            if timer_match:
                                timer_time_str = timer_match.group(1)
                                try:
                                    timer_time = datetime.datetime.strptime(timer_time_str, "%Y-%m-%d %H:%M")
                                    timer_time = EVE_TZ.localize(timer_time)
                                except Exception as e:
                                    logger.warning(f"[SKYHOOK] Could not parse timer time: {timer_time_str} | Error: {e} | Message: {content}")
                                    return
                                # Build description with [NC][Skyhook][Final] tags
                                tags = "[NC][Skyhook][Final]"
                                structure_name = f"Orbital Skyhook Planet {planet}"
                                description = f"{system} - {structure_name} {tags}"
                                new_timer, similar_timers = await self.timerboard.add_timer(timer_time, description)
                                logger.info(f"[SKYHOOK] Added timer: {description} at {timer_time}")
                                # Notify command channel
                                cmd_channel = self.bot.get_channel(server_config['commands'])
                                if cmd_channel:
                                    add_cmd = f"!add {tags} {timer_time.strftime('%Y-%m-%d %H:%M:%S')} {system} - {structure_name}"
                                    await cmd_channel.send(
                                        f"✅ Auto-added Skyhook timer: {system} - {structure_name} at {timer_time.strftime('%Y-%m-%d %H:%M')} {tags} (ID: {new_timer.timer_id})\nAdd command: {add_cmd}"
                                    )
                                logger.info(f"Auto-added timer from skyhooks: {description}")
                            else:
                                logger.warning(f"[SKYHOOK] Could not find timer time in message: {content}")
                        else:
                            logger.warning(f"[SKYHOOK] Could not parse system and planet from message: {content}")
                    else:
                        logger.info(f"[SKYHOOK] No match for 'Skyhook lost shield' or 'Customs Office' pattern in content: {content}")
                    break
        except Exception as e:
            logger.error(f"Error processing citadel-attacked message: {e}")

    async def handle_armor_loss(self, message):
        """Handle armor loss messages and add timers"""
        try:
            logger.info("Processing armor loss message")
            
            # Extract structure info and timer from the message
            match = re.search(
                r'The (.*?) in ([A-Z0-9-]+) \((.*?)\).*?timer end at: (\d{4}-\d{2}-\d{2} \d{2}:\d{2})',
                message.content
            )
            
            if not match:
                logger.warning(f"Could not parse armor loss message: {message.content}")
                return
                
            structure_type = match.group(1)
            system = match.group(2)
            region = match.group(3)
            time_str = match.group(4)
            
            # For Ansiblex gates, keep the full name and add proper tags
            if 'Ansiblex' in structure_type:
                structure_name = structure_type.replace('The Ansiblex Jump Gate ', '')
                description = f"{system} - {structure_name} [NC][Ansiblex][HULL]"
            else:
                structure_name = structure_type
                description = f"{system} - {structure_name} [NC][HULL]"
            
            # Parse the time
            time = datetime.datetime.strptime(time_str, '%Y-%m-%d %H:%M')
            time = EVE_TZ.localize(time)
            
            # Add the timer
            new_timer, similar_timers = await self.timerboard.add_timer(time, description)
            
            # Send confirmation to all command channels
            for server_config in CONFIG['servers'].values():
                cmd_channel = self.bot.get_channel(server_config['commands'])
                if cmd_channel:
                    if similar_timers:
                        similar_list = "\n".join([t.to_string() for t in similar_timers])
                        await cmd_channel.send(
                            f"⚠️ Auto-added timer from armor loss (with similar timers):\n{similar_list}\n"
                            f"Added anyway with ID {new_timer.timer_id}"
                        )
                    else:
                        clean_system = clean_system_name(system)
                        system_link = f"[{system}](https://evemaps.dotlan.net/system/{clean_system})"
                        await cmd_channel.send(f"✅ Auto-added timer from armor loss: {system_link} - {structure_name} at {time.strftime('%Y-%m-%d %H:%M:%S')} (ID: {new_timer.timer_id})")
                    
            # Update all timerboards
            timerboard_channels = [
                self.bot.get_channel(server_config['timerboard'])
                for server_config in CONFIG['servers'].values()
                if server_config['timerboard'] is not None
            ]
            await self.timerboard.update_timerboard(timerboard_channels)
            
            logger.info(f"Successfully added timer from armor loss message: {system} - {structure_name}")
            
        except Exception as e:
            logger.error(f"Error processing armor loss message: {e}")

    async def handle_structure_repair(self, message):
        """Handle structure repair messages and remove timers"""
        try:
            logger.info("Processing structure repair message")
            
            # Extract structure info from the message
            match = re.search(
                r'The (.*?) in ([A-Z0-9-]+)',
                message.content
            )
            
            if not match:
                logger.warning(f"Could not parse repair message: {message.content}")
                return
                
            structure_type = match.group(1)
            system = match.group(2)
            
            # Only process Ansiblex repairs
            if 'Ansiblex' not in structure_type:
                return
                
            structure_name = structure_type.replace('The Ansiblex Jump Gate ', '')
            
            # Find and remove matching NC Ansiblex timer
            removed = False
            for timer in self.timerboard.timers[:]:  # Create a copy of the list to modify it
                if (timer.system == system and 
                    '[NC]' in timer.description and  # Only remove NC tagged timers
                    '[Ansiblex]' in timer.description and 
                    structure_name in timer.description):
                    self.timerboard.timers.remove(timer)
                    removed = True
                    logger.info(f"Removed repaired NC Ansiblex timer: {timer.system} - {timer.structure_name}")
                    
                    # Send confirmation to commands channel
                    cmd_channel = self.bot.get_channel(CONFIG['channels']['commands'])
                    if cmd_channel:
                        clean_system = clean_system_name(system)
                        system_link = f"[{system}](https://evemaps.dotlan.net/system/{clean_system})"
                        await cmd_channel.send(
                            f"✅ Removed timer for repaired NC Ansiblex: {system_link} - {structure_name} (ID: {timer.timer_id})"
                        )
            
            if removed:
                # Update timerboard
                self.timerboard.save_data()
                timerboard_channel = self.bot.get_channel(CONFIG['channels']['timerboard'])
                await self.timerboard.update_timerboard(timerboard_channel)
            
        except Exception as e:
            logger.error(f"Error processing structure repair message: {e}") 

async def backfill_citadel_timers(bot, timerboard, server_config):
    """Backfill timers from the last 5 days of citadel-attacked channel messages."""
    logger.info(f"[CITADEL-BACKFILL] ========== Starting Structure Backfill ==========")
    logger.info(f"[CITADEL-BACKFILL] Server config: {server_config}")
    channel_id = server_config.get('citadel_attacked')
    cmd_channel_id = server_config.get('commands')
    if not channel_id:
        logger.warning(f"[CITADEL-BACKFILL] No citadel_attacked channel configured for backfill.")
        return
    
    logger.info(f"[CITADEL-BACKFILL] Looking for citadel_attacked channel with ID: {channel_id}")
    channel = bot.get_channel(channel_id)
    logger.info(f"[CITADEL-BACKFILL] Looking for commands channel with ID: {cmd_channel_id}")
    cmd_channel = bot.get_channel(cmd_channel_id)
    
    if not channel:
        logger.error(f"[CITADEL-BACKFILL] ❌ Could not find citadel_attacked channel (ID: {channel_id}) for backfill.")
        return
    
    logger.info(f"[CITADEL-BACKFILL] ✅ Found citadel channel: #{channel.name} (ID: {channel_id}) in guild: {channel.guild.name}")
    if cmd_channel:
        logger.info(f"[CITADEL-BACKFILL] ✅ Found commands channel: #{cmd_channel.name} (ID: {cmd_channel_id})")
    else:
        logger.warning(f"[CITADEL-BACKFILL] ⚠️  Could not find commands channel (ID: {cmd_channel_id})")
    now = datetime.datetime.now(pytz.UTC)
    five_days_ago = now - datetime.timedelta(days=5)
    added = 0
    already = 0
    failed = 0
    details = []
    async for message in channel.history(limit=1000, after=five_days_ago):
        content = message.content
        # If content is empty or doesn't contain keywords, try to extract from embed
        if (not content or ("Structure lost shield" not in content and "Structure lost armor" not in content)) and message.embeds:
            embed = message.embeds[0]
            embed_text = []
            if embed.title:
                embed_text.append(embed.title)
            if embed.description:
                embed_text.append(embed.description)
            for field in getattr(embed, 'fields', []):
                embed_text.append(f"{field.name} {field.value}")
            content = "\n".join(embed_text)
            logger.info(f"[BACKFILL] Extracted embed content: {content}")
        logger.info(f"[BACKFILL] Considering message: {content}")
        if ("Structure lost shield" in content or "Structure lost armor" in content):
            # Use improved parsing
            structure_type, structure_name, system, timer_type, timer_time_str, alliance = parse_timer_message(content)
            logger.info(f"[BACKFILL] Parsed: structure_type={structure_type}, structure_name={structure_name}, system={system}, timer_type={timer_type}, timer_time={timer_time_str}, alliance={alliance}")
            if not (structure_type and structure_name and system and timer_type and timer_time_str):
                logger.warning(f"[BACKFILL] Failed to parse all fields. Message: {content}")
                failed += 1
                continue
            # Structure tag
            structure_tag = None
            for key in STRUCTURE_TAGS:
                if key in structure_type.upper():
                    structure_tag = STRUCTURE_TAGS[key]
                    break
            if not structure_tag:
                structure_tag = structure_type.upper().split()[0]  # fallback
            # Parse time
            try:
                timer_time = datetime.datetime.strptime(timer_time_str, "%Y-%m-%d %H:%M")
                timer_time = EVE_TZ.localize(timer_time)
            except Exception as e:
                logger.warning(f"[BACKFILL] Could not parse timer time: {timer_time_str} | Error: {e} | Message: {content}")
                failed += 1
                continue
            # Skip expired timers
            now_utc = datetime.datetime.now(EVE_TZ)
            if timer_time < now_utc:
                logger.info(f"[BACKFILL] Skipping expired timer: {system} - {structure_name} at {timer_time}")
                continue
            # Build tags
            tags = f"{extract_ticker_from_message(content)}[{structure_tag.upper()}][{timer_type.upper()}]"
            description = f"{system} - {structure_name} {tags}"
            # Check for duplicate
            duplicate = False
            for t in timerboard.timers:
                if (
                    t.system.upper() == system.upper()
                    and t.structure_name.upper() == structure_name.upper()
                    and abs((t.time - timer_time).total_seconds()) < 60
                ):
                    duplicate = True
                    break
            if duplicate:
                logger.info(f"[BACKFILL] Skipping duplicate: {description} at {timer_time}")
                already += 1
                continue
            # Add timer
            try:
                new_timer, _ = await timerboard.add_timer(timer_time, description)
                logger.info(f"[BACKFILL] Added timer: {description} at {timer_time}")
                added += 1
                add_cmd = f"!add {timer_time.strftime('%Y-%m-%d %H:%M:%S')} {system} - {structure_name} {tags}"
                details.append(f"{system} - {structure_name} at {timer_time.strftime('%Y-%m-%d %H:%M')} {tags}\nAdd command: {add_cmd}")
            except Exception as e:
                logger.warning(f"[BACKFILL] Failed to add timer: {description} at {timer_time} | Error: {e}")
                failed += 1
                continue
        else:
            logger.info(f"[BACKFILL] Message does not contain relevant keywords. Skipping.")
    # Send summary
    logger.info(f"[CITADEL-BACKFILL] Processing complete. Results: {added} added, {already} already present, {failed} failed")
    if cmd_channel:
        try:
            summary = (
                f"Structure backfill complete: {added} timers added, {already} already present, {failed} failed."
            )
            if added > 0:
                summary += "\nAdded timers:\n" + "\n".join(details)
            await cmd_channel.send(summary)
            logger.info(f"[CITADEL-BACKFILL] ✅ Sent summary to commands channel: #{cmd_channel.name}")
        except Exception as e:
            logger.error(f"[CITADEL-BACKFILL] ❌ Error sending summary: {e}")
    else:
        logger.warning(f"[CITADEL-BACKFILL] ⚠️  No commands channel found, skipping summary message")
    logger.info(f"[CITADEL-BACKFILL] ========== Structure Backfill Complete ==========") 

async def backfill_sov_timers(bot, timerboard, server_config):
    """Backfill timers from the last 5 days of sov channel messages."""
    logger.info(f"[SOV-BACKFILL] ========== Starting SOV Backfill ==========")
    logger.info(f"[SOV-BACKFILL] Server config: {server_config}")
    channel_id = server_config.get('sov')
    cmd_channel_id = server_config.get('commands')
    if not channel_id:
        logger.warning(f"[SOV-BACKFILL] No sov channel configured for backfill.")
        return
    
    logger.info(f"[SOV-BACKFILL] Looking for sov channel with ID: {channel_id}")
    channel = bot.get_channel(channel_id)
    logger.info(f"[SOV-BACKFILL] Looking for commands channel with ID: {cmd_channel_id}")
    cmd_channel = bot.get_channel(cmd_channel_id)
    
    if not channel:
        logger.error(f"[SOV-BACKFILL] ❌ Could not find sov channel (ID: {channel_id}) for backfill.")
        return
    
    logger.info(f"[SOV-BACKFILL] ✅ Found sov channel: #{channel.name} (ID: {channel_id}) in guild: {channel.guild.name}")
    if cmd_channel:
        logger.info(f"[SOV-BACKFILL] ✅ Found commands channel: #{cmd_channel.name} (ID: {cmd_channel_id})")
    else:
        logger.warning(f"[SOV-BACKFILL] ⚠️  Could not find commands channel (ID: {cmd_channel_id})")
    now = datetime.datetime.now(pytz.UTC)
    five_days_ago = now - datetime.timedelta(days=5)
    added = 0
    already = 0
    failed = 0
    details = []
    async for message in channel.history(limit=1000, after=five_days_ago):
        content = message.content
        # If content is empty or doesn't contain keywords, try to extract from embed
        if (not content or "Infrastructure Hub" not in content) and message.embeds:
            embed = message.embeds[0]
            embed_text = []
            if embed.title:
                embed_text.append(embed.title)
            if embed.description:
                embed_text.append(embed.description)
            for field in getattr(embed, 'fields', []):
                embed_text.append(f"{field.name} {field.value}")
            content = "\n".join(embed_text)
            logger.info(f"[SOV-BACKFILL] Extracted embed content: {content}")
        logger.info(f"[SOV-BACKFILL] Considering message: {content}")
        # Improved regex: match both Markdown and plain text, and 'has been reinforced'
        match = re.search(r'Infrastructure Hub.*?in \[([A-Z0-9-]+)\][^\n]*?has been reinforced', content, re.IGNORECASE)
        if match:
            system = match.group(1)
            logger.info(f"[SOV-BACKFILL] Matched system: {system}")
            # Try to extract timer time
            timer_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2})', content)
            if timer_match:
                timer_time_str = timer_match.group(1)
                logger.info(f"[SOV-BACKFILL] Matched timer time: {timer_time_str}")
                try:
                    timer_time = datetime.datetime.strptime(timer_time_str, "%Y-%m-%d %H:%M")
                    timer_time = EVE_TZ.localize(timer_time)
                except Exception as e:
                    logger.warning(f"[SOV-BACKFILL] Could not parse timer time: {timer_time_str} | Error: {e} | Message: {content}")
                    failed += 1
                    continue
                # Skip expired timers
                now_utc = datetime.datetime.now(EVE_TZ)
                if timer_time < now_utc:
                    logger.info(f"[SOV-BACKFILL] Skipping expired timer: {system} - Infrastructure Hub at {timer_time}")
                    continue
                # Try to get region from content (look for parenthesis after system link)
                region_match = re.search(r'\[' + re.escape(system) + r'\][^\n]*?\(([^)]+)\)', content)
                region = region_match.group(1).strip().upper() if region_match else None
                alert_emoji = " 🚨" if region and region in ALERT_REGIONS else ""
                tags = f"[NC][IHUB] 🛡️{alert_emoji}"
                description = f"{system} - Infrastructure Hub {tags}"
                # Check for duplicate
                duplicate = False
                for t in timerboard.timers:
                    if (
                        t.system.upper() == system.upper()
                        and t.structure_name.upper() == "INFRASTRUCTURE HUB"
                        and abs((t.time - timer_time).total_seconds()) < 60
                    ):
                        duplicate = True
                        break
                if duplicate:
                    logger.info(f"[SOV-BACKFILL] Skipping duplicate: {description} at {timer_time}")
                    already += 1
                    continue
                # Add timer
                try:
                    new_timer, _ = await timerboard.add_timer(timer_time, description)
                    logger.info(f"[SOV-BACKFILL] Added timer: {description} at {timer_time}")
                    added += 1
                    add_cmd = f"!add {timer_time.strftime('%Y-%m-%d %H:%M:%S')} {system} - Infrastructure Hub {tags}"
                    details.append(f"{system} - Infrastructure Hub at {timer_time.strftime('%Y-%m-%d %H:%M')} {tags}\nAdd command: {add_cmd}")
                except Exception as e:
                    logger.warning(f"[SOV-BACKFILL] Failed to add timer: {description} at {timer_time} | Error: {e}")
                    failed += 1
                    continue
            else:
                logger.warning(f"[SOV-BACKFILL] Could not find timer time in message: {content}")
        else:
            logger.info(f"[SOV-BACKFILL] Message does not match Infrastructure Hub reinforced pattern. Skipping.")
    # Send summary
    if cmd_channel:
        summary = (
            f"SOV Backfill complete: {added} timers added, {already} already present, {failed} failed."
        )
        if added > 0:
            summary += "\nAdded timers:\n" + "\n".join(details)
        await cmd_channel.send(summary)
    logger.info(f"SOV Backfill summary: {added} added, {already} already present, {failed} failed.") 

async def backfill_skyhook_timers(bot, timerboard, server_config):
    """Backfill timers from the last 3 days of skyhooks channel messages."""
    logger.info(f"[SKYHOOK-BACKFILL] ========== Starting Skyhook Backfill ==========")
    logger.info(f"[SKYHOOK-BACKFILL] Server config: {server_config}")
    channel_id = server_config.get('skyhooks')
    cmd_channel_id = server_config.get('commands')
    
    if not channel_id:
        logger.warning(f"[SKYHOOK-BACKFILL] No skyhooks channel configured for backfill.")
        return
    
    logger.info(f"[SKYHOOK-BACKFILL] Looking for skyhooks channel with ID: {channel_id}")
    channel = bot.get_channel(channel_id)
    logger.info(f"[SKYHOOK-BACKFILL] Looking for commands channel with ID: {cmd_channel_id}")
    cmd_channel = bot.get_channel(cmd_channel_id)
    
    if not channel:
        logger.error(f"[SKYHOOK-BACKFILL] ❌ Could not find skyhooks channel (ID: {channel_id}) for backfill.")
        if cmd_channel:
            await cmd_channel.send("❌ Skyhook backfill failed: Could not find skyhooks channel.")
        return
    
    logger.info(f"[SKYHOOK-BACKFILL] ✅ Found skyhooks channel: #{channel.name} (ID: {channel_id}) in guild: {channel.guild.name}")
    
    # Check bot permissions for the skyhooks channel
    perms = channel.permissions_for(channel.guild.me)
    logger.info(f"[SKYHOOK-BACKFILL] Bot permissions for #{channel.name}:")
    logger.info(f"[SKYHOOK-BACKFILL]   - Can view channel: {perms.view_channel}")
    logger.info(f"[SKYHOOK-BACKFILL]   - Can read message history: {perms.read_message_history}")
    logger.info(f"[SKYHOOK-BACKFILL]   - Can read messages: {perms.read_messages}")
    
    if not perms.read_message_history:
        logger.error(f"[SKYHOOK-BACKFILL] ❌ Bot does not have permission to read message history in #{channel.name}")
        if cmd_channel:
            await cmd_channel.send("❌ Skyhook backfill failed: Bot does not have permission to read message history.")
        return
    
    if not cmd_channel:
        logger.warning(f"[SKYHOOK-BACKFILL] ⚠️  Could not find commands channel (ID: {cmd_channel_id}) for backfill notifications.")
    else:
        logger.info(f"[SKYHOOK-BACKFILL] ✅ Found commands channel: #{cmd_channel.name} (ID: {cmd_channel_id})")
    
    now = datetime.datetime.now(pytz.UTC)
    seven_days_ago = now - datetime.timedelta(days=7)
    logger.info(f"[SKYHOOK-BACKFILL] Checking messages from {seven_days_ago} to {now}")
    added = 0
    already = 0
    failed = 0
    details = []
    message_count = 0
    # Collect timers to add (without updating timerboard immediately)
    timers_to_add = []
    logger.info(f"[SKYHOOK-BACKFILL] Starting to iterate through channel history...")
    try:
        async for message in channel.history(limit=1000, after=seven_days_ago):
            message_count += 1
            if message_count % 50 == 0:
                logger.info(f"[SKYHOOK-BACKFILL] Processed {message_count} messages so far...")
            content = message.content
            # If content is empty or doesn't contain keywords, try to extract from embed
            if (not content or ("Skyhook lost shield" not in content and "Customs Office" not in content)) and message.embeds:
                embed = message.embeds[0]
                embed_text = []
                if embed.title:
                    embed_text.append(embed.title)
                if embed.description:
                    embed_text.append(embed.description)
                for field in getattr(embed, 'fields', []):
                    embed_text.append(f"{field.name} {field.value}")
                content = "\n".join(embed_text)
                logger.info(f"[SKYHOOK-BACKFILL] Extracted embed content: {content}")
            logger.info(f"[SKYHOOK-BACKFILL] Considering message: {content}")
            
            # Check for "Customs Office" reinforcement
            if "Customs Office" in content and "has been reinforced" in content:
                logger.info(f"[SKYHOOK-BACKFILL] Found 'Customs Office' reinforcement in message")
                # Extract system and planet from "The Customs Office at TFA0-U III in TFA0-U"
                customs_match = re.search(
                    r'The Customs Office at\s+([A-Z0-9-]+)\s+([IVX]+)\s+in\s+([A-Z0-9-]+)',
                    content,
                    re.IGNORECASE
                )
                if customs_match:
                    system = customs_match.group(3).strip()  # System is the third group (after "in")
                    planet = customs_match.group(2).strip()
                    logger.info(f"[SKYHOOK-BACKFILL] Matched Customs Office - system: {system}, planet: {planet}")
                    # Extract timer time from "will come out at: 2026-01-26 11:50"
                    timer_match = re.search(r'will come out at:\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})', content, re.IGNORECASE)
                    if timer_match:
                        timer_time_str = timer_match.group(1)
                        logger.info(f"[SKYHOOK-BACKFILL] Matched Customs Office timer time: {timer_time_str}")
                        try:
                            timer_time = datetime.datetime.strptime(timer_time_str, "%Y-%m-%d %H:%M")
                            timer_time = EVE_TZ.localize(timer_time)
                        except Exception as e:
                            logger.warning(f"[SKYHOOK-BACKFILL] Could not parse Customs Office timer time: {timer_time_str} | Error: {e} | Message: {content}")
                            failed += 1
                            continue
                        # Skip expired timers
                        now_utc = datetime.datetime.now(EVE_TZ)
                        if timer_time < now_utc:
                            logger.info(f"[SKYHOOK-BACKFILL] Skipping expired timer: {system} - Customs Office Planet {planet} at {timer_time}")
                            continue
                        # Build description with [INIT][POCO][FINAL] tags
                        tags = "[INIT][POCO][FINAL]"
                        structure_name = f"Customs Office Planet {planet}"
                        description = f"{system} - {structure_name} {tags}"
                        # Check for duplicate
                        duplicate = False
                        for t in timerboard.timers:
                            if (
                                t.system.upper() == system.upper()
                                and t.structure_name.upper() == structure_name.upper()
                                and abs((t.time - timer_time).total_seconds()) < 60
                            ):
                                duplicate = True
                                break
                        if duplicate:
                            logger.info(f"[SKYHOOK-BACKFILL] Skipping duplicate: {description} at {timer_time}")
                            already += 1
                            continue
                        # Collect timer to add later (don't add immediately)
                        timers_to_add.append({
                            'time': timer_time,
                            'description': description,
                            'system': system,
                            'structure_name': structure_name,
                            'tags': tags
                        })
                        logger.info(f"[SKYHOOK-BACKFILL] Collected Customs Office timer to add: {description} at {timer_time}")
                        add_cmd = f"!add {timer_time.strftime('%Y-%m-%d %H:%M:%S')} {system} - {structure_name} {tags}"
                        details.append(f"{system} - {structure_name} at {timer_time.strftime('%Y-%m-%d %H:%M')} {tags}\nAdd command: {add_cmd}")
                    else:
                        logger.warning(f"[SKYHOOK-BACKFILL] Could not find timer time in Customs Office message: {content}")
                else:
                    logger.warning(f"[SKYHOOK-BACKFILL] Could not parse system and planet from Customs Office message: {content}")
            # Check for "Skyhook lost shield" indicator
            elif "Skyhook lost shield" in content:
                logger.info(f"[SKYHOOK-BACKFILL] Found 'Skyhook lost shield' in message")
                # Extract system and planet from "The Orbital Skyhook at 1-EVAX III in 1-EVAX"
                # Pattern handles both markdown and plain text:
                # "The Orbital Skyhook at **QRH-BF V** in [QRH-BF]" or
                # "The Orbital Skyhook at QRH-BF V in QRH-BF"
                skyhook_match = re.search(
                    r'The Orbital Skyhook at\s+(?:\*\*)?([A-Z0-9-]+)\s+(?:Planet\s+)?([IVX]+)(?:\*\*)?\s+in\s+(?:\[|\*\*)?([A-Z0-9-]+)(?:\]|\*\*)?', 
                    content, 
                    re.IGNORECASE
                )
                if skyhook_match:
                    system = skyhook_match.group(1).strip()
                    planet = skyhook_match.group(2).strip()
                    logger.info(f"[SKYHOOK-BACKFILL] Matched system: {system}, planet: {planet}")
                    # Extract timer time from "reinforcement state until : 2025-11-14 21:52"
                    # Pattern handles both markdown and plain text:
                    # "reinforcement state until : **2026-01-04 23:55**" or
                    # "reinforcement state until : 2026-01-04 23:55"
                    timer_match = re.search(r'reinforcement state until\s*:\s*\*?\*?(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\*?\*?', content, re.IGNORECASE)
                    if timer_match:
                        timer_time_str = timer_match.group(1)
                        logger.info(f"[SKYHOOK-BACKFILL] Matched timer time: {timer_time_str}")
                        try:
                            timer_time = datetime.datetime.strptime(timer_time_str, "%Y-%m-%d %H:%M")
                            timer_time = EVE_TZ.localize(timer_time)
                        except Exception as e:
                            logger.warning(f"[SKYHOOK-BACKFILL] Could not parse timer time: {timer_time_str} | Error: {e} | Message: {content}")
                            failed += 1
                            continue
                        # Skip expired timers
                        now_utc = datetime.datetime.now(EVE_TZ)
                        if timer_time < now_utc:
                            logger.info(f"[SKYHOOK-BACKFILL] Skipping expired timer: {system} - Orbital Skyhook Planet {planet} at {timer_time}")
                            continue
                        # Build description with [NC][Skyhook][Final] tags
                        tags = "[NC][Skyhook][Final]"
                        structure_name = f"Orbital Skyhook Planet {planet}"
                        description = f"{system} - {structure_name} {tags}"
                        # Check for duplicate
                        duplicate = False
                        for t in timerboard.timers:
                            if (
                                t.system.upper() == system.upper()
                                and t.structure_name.upper() == structure_name.upper()
                                and abs((t.time - timer_time).total_seconds()) < 60
                            ):
                                duplicate = True
                                break
                        if duplicate:
                            logger.info(f"[SKYHOOK-BACKFILL] Skipping duplicate: {description} at {timer_time}")
                            already += 1
                            continue
                        # Collect timer to add later (don't add immediately)
                        timers_to_add.append({
                            'time': timer_time,
                            'description': description,
                            'system': system,
                            'structure_name': structure_name,
                            'tags': tags
                        })
                        logger.info(f"[SKYHOOK-BACKFILL] Collected timer to add: {description} at {timer_time}")
                        add_cmd = f"!add {timer_time.strftime('%Y-%m-%d %H:%M:%S')} {system} - {structure_name} {tags}"
                        details.append(f"{system} - {structure_name} at {timer_time.strftime('%Y-%m-%d %H:%M')} {tags}\nAdd command: {add_cmd}")
                    else:
                        logger.warning(f"[SKYHOOK-BACKFILL] Could not find timer time in message: {content}")
                else:
                    logger.warning(f"[SKYHOOK-BACKFILL] Could not parse system and planet from message: {content}")
            else:
                logger.info(f"[SKYHOOK-BACKFILL] Message does not contain 'Skyhook lost shield' or 'Customs Office'. Skipping.")
    except Exception as e:
        logger.error(f"[SKYHOOK-BACKFILL] ❌ Error iterating through messages: {e}")
        logger.exception("Full traceback:")
    
    logger.info(f"[SKYHOOK-BACKFILL] Finished processing {message_count} total messages from channel history")
    logger.info(f"[SKYHOOK-BACKFILL] Collected {len(timers_to_add)} timers to add")
    
    if message_count == 0:
        logger.warning(f"[SKYHOOK-BACKFILL] ⚠️  No messages found in the last 3 days in #{channel.name}")
        if cmd_channel:
            await cmd_channel.send("⚠️ Skyhook backfill: No messages found in the last 3 days.")
    
    # Now process all collected timers: verify they're still current, then add them
    now_utc = datetime.datetime.now(EVE_TZ)
    from bot.models.timer import Timer
    from bot.utils.eve_data import get_region
    
    logger.info(f"[SKYHOOK-BACKFILL] Verifying {len(timers_to_add)} collected timers are still current...")
    for timer_data in timers_to_add:
        # Double-check timer is still current (not expired)
        if timer_data['time'] < now_utc:
            logger.info(f"[SKYHOOK-BACKFILL] Skipping expired timer: {timer_data['description']} at {timer_data['time']}")
            failed += 1
            continue
        
        # Check for duplicates again (in case something changed during processing)
        duplicate = False
        for t in timerboard.timers:
            if (
                t.system.upper() == timer_data['system'].upper()
                and t.structure_name.upper() == timer_data['structure_name'].upper()
                and abs((t.time - timer_data['time']).total_seconds()) < 60
            ):
                duplicate = True
                break
        
        if duplicate:
            logger.info(f"[SKYHOOK-BACKFILL] Skipping duplicate: {timer_data['description']} at {timer_data['time']}")
            already += 1
            continue
        
        # Add timer directly to timerboard (without triggering update)
        try:
            region = get_region(timer_data['system'])
            new_timer = Timer(
                time=timer_data['time'],
                description=timer_data['description'],
                timer_id=timerboard.next_id,
                system=timer_data['system'],
                structure_name=timer_data['structure_name'],
                notes=timer_data['tags'],
                region=region
            )
            timerboard.timers.append(new_timer)
            timerboard.next_id += 1
            added += 1
            logger.info(f"[SKYHOOK-BACKFILL] Added timer: {timer_data['description']} at {timer_data['time']} (ID: {new_timer.timer_id})")
        except Exception as e:
            logger.warning(f"[SKYHOOK-BACKFILL] Failed to add timer: {timer_data['description']} at {timer_data['time']} | Error: {e}")
            failed += 1
            continue
    
    # Sort timers and save data
    if added > 0:
        timerboard.sort_timers()
        timerboard.save_data()
        logger.info(f"[SKYHOOK-BACKFILL] Saved {added} new timers to timerboard")
        
        # Update timerboard once at the end
        logger.info(f"[SKYHOOK-BACKFILL] Updating timerboard display...")
        timerboard_channels = [
            bot.get_channel(server_config['timerboard'])
            for server_config in CONFIG['servers'].values()
            if server_config.get('timerboard') is not None
        ]
        await timerboard.update_timerboard(timerboard_channels)
        logger.info(f"[SKYHOOK-BACKFILL] ✅ Timerboard updated with {added} new timers")
    
    # Send summary
    logger.info(f"[SKYHOOK-BACKFILL] Processing complete. Results: {added} added, {already} already present, {failed} failed")
    if cmd_channel:
        try:
            summary = (
                f"Skyhook Backfill complete: {added} timers added, {already} already present, {failed} failed."
            )
            if added > 0:
                summary += "\nAdded timers:\n" + "\n".join(details)
            await cmd_channel.send(summary)
            logger.info(f"[SKYHOOK-BACKFILL] ✅ Sent summary to commands channel: #{cmd_channel.name}")
        except Exception as e:
            logger.error(f"[SKYHOOK-BACKFILL] ❌ Error sending summary: {e}")
    else:
        logger.warning(f"[SKYHOOK-BACKFILL] ⚠️  No commands channel found, skipping summary message")
    logger.info(f"[SKYHOOK-BACKFILL] ========== Skyhook Backfill Complete ==========")

async def update_existing_ihub_timers_with_alert(timerboard):
    """Retroactively update IHUB timers in alert regions to include the shield and alert emoji."""
    updated = 0
    for timer in timerboard.timers:
        # Only update IHUB timers
        if '[NC]' in timer.description and '[IHUB]' in timer.description:
            region = timer.region.strip().upper() if timer.region else None
            # Ensure shield emoji is present after [IHUB]
            if '🛡️' not in timer.description:
                # Insert after [IHUB]
                timer.description = timer.description.replace('[IHUB]', '[IHUB] 🛡️')
                updated += 1
            # Ensure alert emoji is present or absent as appropriate
            if region and region in ALERT_REGIONS:
                if '🚨' not in timer.description:
                    timer.description = timer.description.replace('🛡️', '🛡️ 🚨')
                    updated += 1
            else:
                if '🚨' in timer.description:
                    timer.description = timer.description.replace('🛡️ 🚨', '🛡️')
                    updated += 1
    if updated > 0:
        timerboard.save_data()
    logger.info(f"Retroactively updated {updated} IHUB timers with shield and alert emoji.") 