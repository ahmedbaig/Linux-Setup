#!/bin/bash

if [ ! "$1" ] || [ ! "$2" ] || [ ! "$3" ] || [ ! "$4" ] || [ ! "$5" ]; then
    echo " Example of use: $0 source app_name dir_to_use output_log_path error_log_path [\"args_list\"]"
    exit 1
fi

SOURCE=$1
APP_NAME=$2
DIR_TO_USE=$3
OUTPUT_LOG_PATH=$4
ERROR_LOG_PATH=$5
ARGS_LIST=
CURRENT_DIR=$PWD
PM2_CONFIG_FILE=$APP_NAME.config.js

if [ -n "$6" ]; then
    ARGS_LIST=$6
fi


if [ -d "$DIR_TO_USE" ]; then
    cd "$DIR_TO_USE" || exit

    # create a temporary pm2 config file
    echo "module.exports = {
              apps : [{
                  name   : '$APP_NAME',
                  script : '$SOURCE',
                  out_file: '$OUTPUT_LOG_PATH',
                  error_file: '$ERROR_LOG_PATH',
                  node_args: '$ARGS_LIST'
              }]
          }" > "$PM2_CONFIG_FILE"

    STATUS=$(pm2 ls | grep "$APP_NAME" | awk '{print $18}')
    echo "STATUS=$STATUS"

    # if STATUS is not empty, del and start it again, rather than 'pm2 restart' as it sometimes can't load latest changes
    if [ -n "$STATUS" ]; then
        echo "Restarting $APP_NAME"
        pm2 del "$PM2_CONFIG_FILE"
    fi

    pm2 start "$PM2_CONFIG_FILE"
    pm2 save --force

    # remove the temporary pm2 config file
    rm "$PM2_CONFIG_FILE"
else
    echo "Couldn't find the directory $DIR_TO_USE"
fi

cd "$CURRENT_DIR" || exit
