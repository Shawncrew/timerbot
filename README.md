# EVE Online Timer Discord Bot

A Discord bot for managing EVE Online structure timers with staging system distance calculations.

## Features

- Add and remove structure timers
- Automatic timer expiry
- Staging system tracking
- Jump distance calculations
- Discord markdown formatting with system links
- Timer notifications
- Persistent storage

## Requirements

- Python 3.8 or higher
- systemd (for running as a service)
- pip (Python package installer)

## Installation

1. Clone the repository:
bash
git clone <repository-url>
cd timerbot

2. Run the installation script:
```bash
chmod +x install.sh
sudo ./install.sh
```

This will:
- Create a timerbot user
- Set up the directory structure in /opt/timerbot
- Install Python dependencies
- Configure the systemd service
- Set up log rotation

3. Configure the bot:

Create a `.env` file in `/opt/timerbot/bot/`:
```bash
sudo -u timerbot tee /opt/timerbot/bot/.env << EOF
DISCORD_TOKEN=your_discord_token_here
EOF
```

Create/edit `config.yaml` in `/opt/timerbot/bot/`:
```yaml
channels:
  timerboard: YOUR_TIMERBOARD_CHANNEL_ID
  commands: YOUR_COMMAND_CHANNEL_ID
check_interval: 60    # How often to check timers (seconds)
notification_time: 60 # When to notify before timer (minutes)
expiry_time: 60      # How long to keep expired timers (minutes)
```

## Service Management

```bash
# Start the bot
sudo systemctl start timerbot

# Stop the bot
sudo systemctl stop timerbot

# Check status
sudo systemctl status timerbot

# View logs
tail -f /opt/timerbot/logs/bot.log
```

## Commands

All commands must be used in the timerboard-cmd channel:

- `!add YYYY-MM-DD HH:MM:SS system - structure [tags]`
  - Example: `!add 2025-03-05 10:56:50 9PX2-F » F-EM4Q - WWW [VAPOR][Ansiblex][FINAL]`

- `!add system structure Reinforced until YYYY.MM.DD HH:MM:SS [tags]`
  - Example: `!add OJOS-T Rorqual Fleet Issue III Reinforced until 2025.03.05 11:30:26 [GWCS][Metanox][Final]`

- `!rm timer_id`
  - Remove a timer by its ID

- `!staging system`
  - Set the staging system for distance calculations

- `!refresh`
  - Refresh the timerboard display

## File Locations

- Bot files: `/opt/timerbot/bot/`
- Logs: `/opt/timerbot/logs/`
- Data: `/opt/timerbot/data/`
- Virtual environment: `/opt/timerbot/venv/`

## Logs

Logs are stored in `/opt/timerbot/logs/bot.log` with daily rotation (7 days retained).

## Security

The bot runs as a dedicated system user (timerbot) with limited permissions.

## Support

For issues or feature requests, please open an issue on GitHub.