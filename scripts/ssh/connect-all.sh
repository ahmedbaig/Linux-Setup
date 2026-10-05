#!/bin/bash

# List of server IP addresses
SERVERS=(
"127.0.0.1" 
)

# SSH username
USERNAME=ec2-user
CURRENT_PATH=$(cd -- "$(dirname "$0")" && pwd -P)
SSH_PATH="$CURRENT_PATH/key.pem"

# Loop through each server and run 'pm2 list'
for SERVER in "${SERVERS[@]}"
do
    echo "Checking PM2 list on server: $SERVER"
    ssh -o ConnectTimeout=6 -i $SSH_PATH $USERNAME@$SERVER 'pm2 ls'
    echo "-------------------------------------------"
done