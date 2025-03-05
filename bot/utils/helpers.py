from bot.utils.logger import logger
from bot.utils.config import CONFIG

def clean_system_name(system: str) -> str:
    """Clean system name for URLs and display"""
    # Remove or replace special characters
    system = system.replace('»', '-').replace('«', '-')
    # Remove extra spaces and dashes
    system = '-'.join(filter(None, system.split()))
    return system

async def cmd_channel_check(ctx):
    """Check if command is used in the correct channel"""
    logger.info(f"Command '{ctx.command}' received from {ctx.author} in #{ctx.channel.name}")
    return ctx.channel.id == CONFIG['channels']['commands'] 