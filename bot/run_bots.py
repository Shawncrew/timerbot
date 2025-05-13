import os
import sys
# Add the parent directory to PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import discord
from discord.ext import commands

# Use relative imports since we're inside the bot package
from bot.utils.config import load_config
from bot.utils.logger import logger
from bot.models.timer import TimerBoard
from bot.cogs.timer_commands import TimerCommands

async def run_bot_instance(server_name, server_config, shared_timerboard):
    """Run a single bot instance for a server"""
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    
    bot = commands.Bot(command_prefix='!', intents=intents)
    
    # Add the cog
    cog = TimerCommands(bot, shared_timerboard)
    await bot.add_cog(cog)
    
    try:
        await bot.start(server_config['token'])
    except Exception as e:
        logger.error(f"Error running bot for {server_name}: {e}")

async def main():
    """Run all bot instances"""
    config = load_config()
    
    # Create shared timerboard
    timerboard = TimerBoard()
    
    # Create tasks for each bot
    tasks = []
    for server_name, server_config in config['servers'].items():
        if server_config['token']:  # Only run if token is configured
            task = run_bot_instance(server_name, server_config, timerboard)
            tasks.append(task)
    
    # Run all bots
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main()) 