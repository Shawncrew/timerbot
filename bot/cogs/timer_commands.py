from discord.ext import commands
import datetime
import re
from bot.utils.logger import logger
from bot.utils.helpers import clean_system_name, cmd_channel_check
from bot.models.timer import EVE_TZ
from bot.utils.config import CONFIG  # Import CONFIG directly

class TimerCommands(commands.Cog, name="Basic Commands"):
    def __init__(self, bot, timerboard):
        self.bot = bot
        self.timerboard = timerboard

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
            
            new_timer, similar_timers = await self.timerboard.add_timer(time, description)
            
            if similar_timers:
                logger.info(f"{ctx.author} added timer {new_timer.timer_id} with similar timers warning")
                similar_list = "\n".join([t.to_string() for t in similar_timers])
                await ctx.send(f"⚠️ Warning: Similar timers found:\n{similar_list}\n"
                             f"Added anyway with ID {new_timer.timer_id}")
            else:
                logger.info(f"{ctx.author} added timer {new_timer.timer_id}")
                await ctx.send(f"Timer added with ID {new_timer.timer_id}")
            
            # Update timerboard channel - use CONFIG directly
            timerboard_channel = self.bot.get_channel(CONFIG['channels']['timerboard'])
            await self.timerboard.update_timerboard(timerboard_channel)
            
        except ValueError as e:
            await ctx.send("Invalid time format. Use: YYYY-MM-DD HH:MM:SS or system structure Reinforced until YYYY.MM.DD HH:MM:SS [tags]")

    @commands.command()
    @commands.check(cmd_channel_check)
    async def rm(self, ctx, timer_id: int):
        """Remove a timer by its ID"""
        timer = self.timerboard.remove_timer(timer_id)
        if timer:
            logger.info(f"{ctx.author} removed timer {timer_id}")
            clean_system = clean_system_name(timer.system)
            system_link = f"[{timer.system}](https://evemaps.dotlan.net/system/{clean_system})"
            await ctx.send(f"Removed timer: {system_link} - {timer.structure_name} {timer.notes} at `{timer.time.strftime('%Y-%m-%d %H:%M:%S')}` (ID: {timer.timer_id})")
            # Use CONFIG directly
            timerboard_channel = self.bot.get_channel(CONFIG['channels']['timerboard'])
            await self.timerboard.update_timerboard(timerboard_channel)
        else:
            logger.warning(f"{ctx.author} attempted to remove non-existent timer {timer_id}")
            await ctx.send(f"No timer found with ID {timer_id}")

    @commands.command()
    @commands.check(cmd_channel_check)
    async def refresh(self, ctx):
        """Refresh the timerboard by clearing and recreating all messages"""
        try:
            logger.info(f"{ctx.author} requested timerboard refresh")
            # Use CONFIG directly
            channel = self.bot.get_channel(CONFIG['channels']['timerboard'])
            
            # Delete all bot messages in the channel
            deleted = 0
            async for message in channel.history(limit=100):
                if message.author == self.bot.user:
                    await message.delete()
                    deleted += 1
            
            # Recreate the timerboard
            await self.timerboard.update_timerboard(channel)
            
            logger.info(f"Timerboard refreshed - deleted {deleted} messages and recreated display")
            await ctx.send(f"Timerboard refreshed - deleted {deleted} messages and recreated display")
            
        except Exception as e:
            logger.error(f"Error refreshing timerboard: {e}")
            await ctx.send(f"Error refreshing timerboard: {e}") 