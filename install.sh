#!/bin/bash

# Create timerbot user
sudo useradd -r -s /bin/false timerbot

# Create directory structure
sudo mkdir -p /opt/timerbot/{bot,logs,data,venv}

# Copy files
sudo cp bot.py config.yaml requirements.txt /opt/timerbot/bot/

# Set up virtual environment
sudo python3 -m venv /opt/timerbot/venv
sudo /opt/timerbot/venv/bin/pip install -r /opt/timerbot/bot/requirements.txt

# Set permissions
sudo chown -R timerbot:timerbot /opt/timerbot
sudo chmod 755 /opt/timerbot
sudo chmod 640 /opt/timerbot/bot/config.yaml

# Set up service
sudo cp timerbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable timerbot
sudo systemctl start timerbot

# Set up log rotation
sudo tee /etc/logrotate.d/timerbot << EOF
/opt/timerbot/logs/bot.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 640 timerbot timerbot
}
EOF 