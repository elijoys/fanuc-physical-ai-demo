#!/bin/bash
set -e

# Clean up stale X locks from previous runs and make sure the socket dir exists
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1
sudo mkdir -p /tmp/.X11-unix
sudo chmod 1777 /tmp/.X11-unix

# Tell the VNC server which desktop to start
mkdir -p ~/.vnc
cat > ~/.vnc/xstartup <<'XEOF'
#!/bin/sh
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
exec dbus-launch --exit-with-session startxfce4
XEOF
chmod +x ~/.vnc/xstartup

# VNC listens on localhost inside the container only; the browser reaches it via noVNC
vncserver :1 -geometry 1600x900 -depth 24 -localhost yes \
  -SecurityTypes None --I-KNOW-THIS-IS-INSECURE

echo "Desktop ready: open http://localhost:6080/vnc.html"
exec websockify --web=/usr/share/novnc 6080 localhost:5901
