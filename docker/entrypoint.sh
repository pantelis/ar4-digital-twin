#!/bin/bash
# Give the container user a home inside the mounted repository, register it with FreeCAD,
# and install the blwfish FreeCAD addon there on first use.
set -e
export HOME=/work/.home
mkdir -p "$HOME" /work/logs
if ! getent passwd "$(id -u)" > /dev/null; then
  echo "twin:x:$(id -u):$(id -g):twin:$HOME:/bin/bash" >> /etc/passwd
fi
MOD="$HOME/.local/share/FreeCAD/v1-1/Mod"
if [ ! -d "$MOD/AICopilot" ]; then
  mkdir -p "$MOD" && cp -r /opt/blwfish/AICopilot "$MOD/"
fi
exec "$@"
