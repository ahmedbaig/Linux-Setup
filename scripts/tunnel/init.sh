#!/usr/bin/env bash

#set -Eeuo pipefail
#trap cleanup SIGINT SIGTERM ERR EXIT

SERVICE_PORT=8080

# Get the directory of the script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PEM="$SCRIPT_DIR/../certs/key.pem"
INSTANCE=username@ip

HEIGHT=40
WIDTH=110
CHOICE_HEIGHT=4
TITLE="Select a ports to SSH tunnel"
BACKTITLE="Welcome to service script runner"
MENU="Choose one or more ports to forward from the following options:"

SELECT_SERVICE=SERVICE_NAME

OPTIONS=(
    $SELECT_SERVICE "Service port forwarded $SERVICE_PORT:127.1:$SERVICE_PORT" on
)

CHOICES=$(dialog --clear \
    --backtitle "$BACKTITLE" \
    --title "$TITLE" \
    --checklist "$MENU" \
    $HEIGHT $WIDTH $CHOICE_HEIGHT \
    "${OPTIONS[@]}" \
    2>&1 >/dev/tty)

clear

serviceCheck() {
    local service=$1
    local port=$2
    local timeout=2
    # echo "Checking if the $service 127.1:$port service is up..."
    if nc -zvw $timeout 127.1 $port >/dev/null 2>&1; then
        echo "$service service is up."
    else
        echo "$service service is down."
    fi
}

if [ -z "$CHOICES" ]; then
    echo "Nothing to do. Closing dialog.."
else
    echo "Cleaning up old forwarding requests"
    pkill -f 'ssh -[LR]'

    for CHOICE in $CHOICES; do
        case $CHOICE in

        $SELECT_SERVICE)
            ssh -o ServerAliveInterval=60 -L $SERVICE_PORT:127.1:$SERVICE_PORT -N -f -i $PEM $INSTANCE
            echo "
Service port forward $SERVICE_PORT:127.1:$SERVICE_PORT
"
            serviceCheck $SELECT_SERVICE $SERVICE_PORT

            ;;
        esac

    done

fi
# ps x | grep -i 'ssh -[LR]' | grep -i 'ssh -[LR]'
