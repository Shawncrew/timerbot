# EVE Online Timer Discord Bot

A Discord bot for managing EVE Online structure timers with staging system distance calculations.

## Features

- Add and remove structure timers
- Automatic timer expiry
- Staging system tracking with jump distance calculations
- Discord markdown formatting with system links
- Timer notifications
- Persistent storage

## Bot Commands

All commands must be used in the timerboard-cmd channel:

- Add a timer (two formats supported):
```
!add YYYY-MM-DD HH:MM:SS system - structure [tags]
Example: !add 2025-03-05 10:56:50 9PX2-F » F-EM4Q - WWW [VAPOR][Ansiblex][FINAL]

!add system structure Reinforced until YYYY.MM.DD HH:MM:SS [tags]
Example: !add OJOS-T Rorqual Fleet Issue III Reinforced until 2025.03.05 11:30:26 [GWCS][Metanox][Final]
```

- Remove a timer:
```
!rm timer_id
```

- Set staging system:
```
!staging system_name
```

- Refresh display:
```
!refresh
```

## Configuration

The bot requires two configuration files in `/opt/timerbot/bot/`:

1. `.env` file with Discord token:
```
DISCORD_TOKEN=your_discord_token_here
```

2. `config.yaml` with channel IDs and settings:
```yaml
channels:
  timerboard: YOUR_TIMERBOARD_CHANNEL_ID  # Channel where timer list is displayed
  commands: YOUR_COMMAND_CHANNEL_ID       # Channel where commands are accepted
check_interval: 60    # How often to check timers (seconds)
notification_time: 60 # When to notify before timer (minutes)
expiry_time: 60      # How long to keep expired timers (minutes)
```

## Installation

1. Install System Requirements:
```bash
# Update system and install required packages
sudo apt update && sudo apt install -y python3-venv python3-pip git
```

2. Set Up Service:
```bash
# Create directory structure
sudo mkdir -p /opt/timerbot/{bot,logs,data,venv}

# Copy files
sudo cp bot.py requirements.txt timerbot.service /opt/timerbot/bot/
sudo cp config.yaml /opt/timerbot/bot/
sudo cp .env /opt/timerbot/bot/

# Set up Python environment
python3 -m venv /opt/timerbot/venv
/opt/timerbot/venv/bin/pip install -r /opt/timerbot/bot/requirements.txt

# Set ownership
sudo chown -R shawn:shawn /opt/timerbot
sudo chmod 755 /opt/timerbot

# Set up service
sudo cp timerbot.service /etc/systemd/system/
sudo sed -i 's/User=timerbot/User=shawn/' /etc/systemd/system/timerbot.service
sudo sed -i 's/Group=timerbot/Group=shawn/' /etc/systemd/system/timerbot.service
sudo systemctl daemon-reload
sudo systemctl enable timerbot
sudo systemctl start timerbot
```

3. Verify Installation:
```bash
# Check service status
sudo systemctl status timerbot

# View logs
tail -f /opt/timerbot/logs/bot.log
```

## File Locations

- Bot files: `/opt/timerbot/bot/`
- Log Files: `/opt/timerbot/logs/bot.log`
- Timer Data: `/opt/timerbot/data/timerboard_data.json`

## Troubleshooting

Common issues:
- Invalid Discord token: Check .env file
- Incorrect channel IDs: Verify in config.yaml
- Permission issues: Check file ownership and permissions
- Service not starting: Check logs with `journalctl -u timerbot`

## Service Management

```bash
# Start/Stop/Restart
sudo systemctl start timerbot
sudo systemctl stop timerbot
sudo systemctl restart timerbot

# View status and logs
sudo systemctl status timerbot
tail -f /opt/timerbot/logs/bot.log
```

## Support

For issues or feature requests, please open an issue on GitHub.