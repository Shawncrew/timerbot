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
    
    @bot.event
    async def on_ready():
        try:
            logger.info(f"Bot {server_name} connected as {bot.user}")
            logger.info(f"Bot application ID: {bot.user.id}")
            
            # Debug guild info
            logger.info(f"Connected to guilds for {server_name}:")
            for guild in bot.guilds:
                logger.info(f"  Guild: {guild.name} (ID: {guild.id})")
                logger.info(f"  Is bot connected: {guild.me and guild.me.status}")
                logger.info(f"  Bot roles: {[role.name for role in guild.me.roles if guild.me]}")
            
            # Register this bot with the timerboard
            shared_timerboard.register_bot(bot, server_config)
            
            # Initial timerboard update
            logger.info(f"Performing initial timerboard update for {server_name}")
            timerboard_channel = bot.get_channel(server_config['timerboard'])
            if timerboard_channel:
                logger.info(f"Found timerboard channel: {timerboard_channel.name} in {timerboard_channel.guild.name}")
                await shared_timerboard.update_timerboard([timerboard_channel])
            else:
                logger.error(f"Could not find timerboard channel for {server_name}")
                
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
    cog = TimerCommands(bot, shared_timerboard)
    await bot.add_cog(cog)
    
    try:
        logger.info(f"Starting bot for {server_name} with token: {server_config['token'][:20]}...")
        await bot.start(server_config['token'])
    except Exception as e:
        logger.error(f"Error running bot for {server_name}: {e}")
        logger.exception("Full traceback:")

async def main():
    """Run all bot instances"""
    config = load_config()
    
    # Create shared timerboard
    timerboard = TimerBoard()
    
    try:
        # Create tasks for each bot
        tasks = []
        for server_name, server_config in config['servers'].items():
            if server_config['token']:  # Only run if token is configured
                task = run_bot_instance(server_name, server_config, timerboard)
                tasks.append(task)
        
        # Run all bots
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    finally:
        # Cancel the update task if it exists
        if timerboard.update_task:
            timerboard.update_task.cancel()
            try:
                await timerboard.update_task
            except asyncio.CancelledError:
                pass

if __name__ == "__main__":
    asyncio.run(main()) 