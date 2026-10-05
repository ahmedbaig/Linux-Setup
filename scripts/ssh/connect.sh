#!/bin/bash

echo "Connecting to VM... "
echo "========================="


CURRENT_PATH=$(cd -- "$(dirname "$0")" && pwd -P)

IP=$1
KEY_PATH=$2
USER=$3

check_file_exists() {
    local file_path="$1"

    # Check if the file exists
    if [ -f "$file_path" ]; then
        echo "File '$file_path' exists!"
    else
        echo "File '$file_path' does not exist."
        exit 1
    fi
}

SSH_PATH="$KEY_PATH"

check_file_exists $SSH_PATH

ssh -i $SSH_PATH -A $USER@$IP