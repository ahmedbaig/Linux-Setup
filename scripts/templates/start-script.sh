#!/bin/bash
# Only for use within the build folder

PM="forever"
APP_NAME="service"
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

function usage() {
   echo -e """SERVICE START SCRIPT

Usage:
./start [Options]

Options:
  --pm/-p           Specify which process manager will in used, either PM2 or forever. If not specify forever will be in use.
  --help            Get the Usage information for this script.
"""
}

for arg in "$@"; do
    if [[ $arg == "--help" ]] ; then
        usage
        exit 0
    fi

    if [[ $arg == "--pm" || $arg == "-p" ]]; then
        PM=$2
    fi
done

echo "Application is running on $PM" 

if [[ $PM == "forever" ]]; then
# ~/axis/node_modules/.bin/forever start \
"$SCRIPT_DIR"/node_modules/.bin/forever start \
    --spinSleepTime 10000 \
    --sourceDir "$SCRIPT_DIR" \
    --workingDir "$SCRIPT_DIR"  \
    --append \
    -l "${APP_NAME}".log \
    -c /usr/local/bin/node  \
    server.js
fi

if [[ $PM == "pm2" ]]; then
    "$SCRIPT_DIR"/start-with-pm2 \
    "$SCRIPT_DIR"/server.js \
    $APP_NAME \
    "$SCRIPT_DIR" \
    "$SCRIPT_DIR"/logs/service.log \
    "$SCRIPT_DIR"/logs/service.log \
    "--max-old-space-size=2048 --heapsnapshot-signal=SIGABRT"
fi

if [[ $PM != "forever" && $PM != "pm2" ]]; then
    echo "unknown process maanger, only forever or pm2 can be used."
    exit 0
fi
