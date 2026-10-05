#!/bin/bash

ID=$1
echo "ID: ${ID}"

# Get dynamic persistent ID of external screen (contextual ID 3)
external_id=$(displayplacer list | awk "BEGIN{RS=\"Persistent screen id: \"} /Contextual screen id: ${ID}/{print \$1}")

# Fixed persistent ID for internal MacBook screen
internal_id="37D8832A-2D66-02CA-B9F7-8F30A301B230"

# Safety check
if [ -z "$external_id" ]; then
  echo "❌ External screen (contextual ID ${ID}) not found."
  exit 1
fi

# Step 1: Set external screen to a temporary lower resolution (e.g., 1920x1080)
displayplacer \
"id:${internal_id} res:2056x1329 hz:120 color_depth:8 scaling:on origin:(0,0) degree:0" \
"id:${external_id} res:1920x1080 hz:60 color_depth:8 scaling:off origin:(-1920,-121) degree:0"

# Wait a bit to let the screen reconfigure
sleep 1

# Step 2: Restore external screen to full resolution (3840x2160)
displayplacer \
"id:${internal_id} res:2056x1329 hz:120 color_depth:8 scaling:on origin:(0,0) degree:0" \
"id:${external_id} res:3840x2160 hz:60 color_depth:8 scaling:off origin:(-3840,-121) degree:0"

