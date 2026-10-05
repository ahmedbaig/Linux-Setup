#!/bin/bash

if [ $# -eq 0 ]; then
    echo "No arguments supplied"
    echo "Usage: deployToRemoteServer deploy_env target_vm target_dir_path target_key_file"
    exit
fi

deploy_env=$1
target_vm=$2
target_dir_path=$3
target_key_file=$4

pwd

msg() {
  echo >&2 -e "${1-}"
}

die() {
  local msg=$1
  local code=${2-1} # default exit status 1
  msg "$msg"
  exit "$code"
}


# Define the key file path relative to the script's directory
KEY_FILE=$target_key_file

export TIMESTAMP=$(date +"%Y-%m-%d-%H-%M")
export DEPLOYFILE="dmg-main-host.tar.gz"
export BACKUPFILE=$deploy_env-$TIMESTAMP--backup.tar.gz

echo
echo "===== Sending deployment to $deploy_env $target_vm host $target_dir_path ====="
echo
scp -i "$KEY_FILE" "$DEPLOYFILE" "$target_vm:/home/ec2-user/$target_dir_path/"

echo
echo "===== Extracting deployment to $deploy_env $target_vm host $target_dir_path ====="
echo

ssh -i "$KEY_FILE" -A $target_vm <<heredoc
  cd "/home/ec2-user/$target_dir_path"
  hostname; whoami; date; pwd; ls -la;

  echo "TIMESTAMP =" $TIMESTAMP
  echo "BACKUPFILE =" $BACKUPFILE
  
  echo
  echo "Extract files"
  echo
  tar -xvf $DEPLOYFILE
  mv $DEPLOYFILE $BACKUPFILE

  echo
  echo "PM2 deployment" $PM2_ENV_RESET
  echo
  if [[ $PM2_ENV_RESET == "yes" ]]; then
    echo "First time deployment"
    echo "export NODE_ENV=development" > "set_env" 
    cp -r /home/ec2-user/old/service/tls* .
    cp -r /home/ec2-user/old/service/*.jpg .
    cp -r /home/ec2-user/old/service/*.png .
    cp -r /home/ec2-user/old/service/set_env_all .
    cp -r /home/ec2-user/old/service/set_env .
    cp -r /home/ec2-user/old/service/.env .
    source ./set_env_all
    source ./set_env
    source .env
    pm2 start ./server.js -l ~/logs/service.log --name deployments/service
  else
    echo "Restart...."
    pm2 restart deployments/service
  fi
heredoc

echo
echo "!!!!! DONE  !!!!!"
echo