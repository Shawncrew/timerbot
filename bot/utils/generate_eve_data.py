import os
import sys
# Add the parent directory to PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import aiohttp
import asyncio
import json
from pathlib import Path
from typing import Dict
from bot.utils.logger import logger

# Add headers for ESI API
HEADERS = {
    'User-Agent': 'EVE Timer Discord Bot - Contact: your_email@example.com',
    'Accept': 'application/json'
}

async def fetch_url(session: aiohttp.ClientSession, url: str) -> dict:
    """Fetch data from a URL"""
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            return None
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        return None

async def fetch_universe_data() -> Dict[str, str]:
    """Fetch system and region data from ESI"""
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            # First get all regions
            logger.info("Fetching list of regions...")
            regions_url = 'https://esi.evetech.net/latest/universe/regions/?datasource=tranquility'
            region_ids = await fetch_url(session, regions_url)
            if not region_ids:
                return {}

            logger.info(f"Found {len(region_ids)} regions, fetching details...")
            
            # Fetch all region data concurrently
            region_tasks = [
                fetch_url(session, f'https://esi.evetech.net/latest/universe/regions/{region_id}/?datasource=tranquility')
                for region_id in region_ids
            ]
            region_data_list = await asyncio.gather(*region_tasks)
            
            # Get all constellation IDs from all regions
            constellation_ids = []
            region_names = {}
            for region_data in region_data_list:
                if region_data and 'constellations' in region_data:
                    constellation_ids.extend(region_data['constellations'])
                    region_names[region_data['region_id']] = region_data['name']
            
            logger.info(f"Fetching {len(constellation_ids)} constellations...")
            
            # Fetch all constellation data concurrently
            const_tasks = [
                fetch_url(session, f'https://esi.evetech.net/latest/universe/constellations/{const_id}/?datasource=tranquility')
                for const_id in constellation_ids
            ]
            const_data_list = await asyncio.gather(*const_tasks)
            
            # Get all system IDs from all constellations
            system_ids = []
            system_to_region_map = {}
            for const_data in const_data_list:
                if const_data and 'systems' in const_data:
                    region_name = region_names.get(const_data['region_id'])
                    for system_id in const_data['systems']:
                        system_ids.append(system_id)
                        system_to_region_map[system_id] = region_name
            
            logger.info(f"Fetching {len(system_ids)} systems...")
            
            # Fetch all system data concurrently
            system_tasks = [
                fetch_url(session, f'https://esi.evetech.net/latest/universe/systems/{sys_id}/?datasource=tranquility')
                for sys_id in system_ids
            ]
            system_data_list = await asyncio.gather(*system_tasks)
            
            # Create final mapping
            system_to_region = {}
            for system_data in system_data_list:
                if system_data:
                    system_name = system_data['name']
                    region_name = system_to_region_map.get(system_data['system_id'])
                    if region_name:
                        system_to_region[system_name] = region_name
                        logger.debug(f"Mapped {system_name} to {region_name}")
            
            return system_to_region

    except Exception as e:
        logger.error(f"Error fetching universe data: {e}")
        return {}

async def main():
    """Generate the eve_systems.json file"""
    logger.info("Starting EVE system data generation...")
    system_to_region = await fetch_universe_data()
    
    if system_to_region:
        # Save to data directory
        data_dir = Path('/opt/timerbot/data')
        data_dir.mkdir(parents=True, exist_ok=True)
        output_file = data_dir / 'eve_systems.json'
        
        with open(output_file, 'w') as f:
            json.dump(system_to_region, f, indent=2, sort_keys=True)
        logger.info(f"Successfully created {output_file} with {len(system_to_region)} systems")
    else:
        logger.error("Failed to generate system data")

if __name__ == "__main__":
    asyncio.run(main()) 