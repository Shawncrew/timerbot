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

class TimerCommands(commands.GroupCog, name="timer"):
    def __init__(self, bot, timerboard):
        self.bot = bot
        self.timerboard = timerboard
        super().__init__()

    @commands.command()
    @commands.check(cmd_channel_check)
    async def add(self, ctx, *, input_text: str):
        """Add a new timer
        Format: !add YYYY-MM-DD HH:MM:SS system - structure [tags]
        or: !add system structure Reinforced until YYYY.MM.DD HH:MM:SS [tags]
        or: !add structure_name\ndistance\nReinforced until YYYY.MM.DD HH:MM:SS [tags]"""
        try:
            # Look for the new format first (structure name on first line, distance on second, reinforced on third)
            lines = input_text.split('\n')
            if len(lines) >= 3 and 'Reinforced until' in lines[2]:
                # Keep the exact structure name from first line
                structure_name = lines[0].strip()
                logger.debug(f"Parsed structure name: {structure_name}")
                
                # Extract system from structure name - handle special characters like »
                system_match = re.match(r'([A-Z0-9-]+)(?:\s*[»>]\s*.*)?(?:\s*-\s*.*)?$', structure_name)
                if system_match:
                    system = system_match.group(1).strip()
                    # Keep the full structure name as is
                    structure_name = structure_name[len(system):].strip()
                    if structure_name.startswith('»'):
                        structure_name = structure_name.strip('» ')
                    if structure_name.startswith('-'):
                        structure_name = structure_name.strip('- ')
                else:
                    await ctx.send("Could not parse system name from structure")
                    return
                logger.debug(f"Extracted system: {system}, structure: {structure_name}")
                
                # Extract time and tags from the "Reinforced until" line
                time_match = re.search(r'Reinforced until (\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2})\s*(\[.*\](?:\[.*\])*)?$', lines[2])
                if time_match:
                    time_str = time_match.group(1).replace('.', '-')
                    reinforced_tags = time_match.group(2) if time_match.group(2) else ""
                    logger.debug(f"Extracted reinforced tags: {reinforced_tags}")
                    
                    # Create description with system and structure name
                    description = f"{system} - {structure_name}"
                    if reinforced_tags:  # Only add reinforced tags if they exist
                        description += f" {reinforced_tags}"
                    logger.debug(f"Final description: {description}")
                else:
                    await ctx.send("Invalid reinforced time format")
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
                    # Try to parse the first part as a direct time input
                    parts = input_text.split(' ', 1)
                    if len(parts) < 2:
                        await ctx.send("Invalid format. Use: !add YYYY-MM-DD HH:MM:SS description")
                        return
                    time_str = parts[0]
                    description = parts[1]

            # Parse the time
            try:
                if 'time_str' in locals():
                    time = datetime.datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
                else:
                    await ctx.send("Could not parse time from input")
                    return
                time = EVE_TZ.localize(time)
            except ValueError as e:
                await ctx.send(f"Invalid time format: {e}")
                return
            
            new_timer, similar_timers = await self.timerboard.add_timer(time, description)
            
            if similar_timers:
                similar_list = "\n".join([t.to_string() for t in similar_timers])
                await ctx.send(f"⚠️ Warning: Similar timers found:\n{similar_list}\n"
                             f"Added anyway with ID {new_timer.timer_id}")
            else:
                await ctx.send(f"Timer added with ID {new_timer.timer_id}")
            
            # Update timerboard channel
            timerboard_channel = self.bot.get_channel(CONFIG['channels']['timerboard'])
            await self.timerboard.update_timerboard(timerboard_channel)
            
        except Exception as e:
            logger.error(f"Error adding timer: {e}")
            await ctx.send(f"Error adding timer: {e}")

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

    @app_commands.command()
    async def add_sov(
        self, 
        interaction: discord.Interaction, 
        timer: str,
        system: str,
        owner: str,
        adm: str
    ):
        """Add a SOV timer"""
        try:
            # Parse the time
            try:
                time = datetime.strptime(timer, '%Y.%m.%d %H:%M')
                time = EVE_TZ.localize(time)
            except ValueError:
                await interaction.response.send_message(
                    "❌ Invalid time format. Use: YYYY.MM.DD HH:MM", 
                    ephemeral=True
                )
                return

            # Validate ADM
            try:
                adm_value = float(adm)
                if not (1 <= adm_value <= 6):
                    raise ValueError
            except ValueError:
                await interaction.response.send_message(
                    "❌ ADM must be a number between 1 and 6", 
                    ephemeral=True
                )
                return

            # Create description with ownership and ADM info
            description = f"{system} - SOV Timer [{owner}-ADM{adm}]"
            
            # Add the timer
            new_timer, similar_timers = await self.timerboard.add_timer(time, description)
            
            if similar_timers:
                similar_list = "\n".join([t.to_string() for t in similar_timers])
                await interaction.response.send_message(
                    f"⚠️ Warning: Similar timers found:\n{similar_list}\n"
                    f"Added anyway with ID {new_timer.timer_id}"
                )
            else:
                await interaction.response.send_message(
                    f"✅ Timer added with ID {new_timer.timer_id}"
                )
            
            # Update timerboard channel
            timerboard_channel = self.bot.get_channel(CONFIG['channels']['timerboard'])
            await self.timerboard.update_timerboard(timerboard_channel)
            
        except Exception as e:
            logger.error(f"Error adding SOV timer: {e}")
            await interaction.response.send_message(
                f"❌ Error adding timer: {str(e)}", 
                ephemeral=True
            ) 