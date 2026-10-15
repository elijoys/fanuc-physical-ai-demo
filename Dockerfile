FROM ros:jazzy

ENV DEBIAN_FRONTEND=noninteractive \
    DISPLAY=:1 \
    LIBGL_ALWAYS_SOFTWARE=1 \
    QT_X11_NO_MITSHM=1 \
    ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST

# Base tools, RViz, a lightweight desktop, and a VNC server with a browser front end
RUN apt-get update && apt-get install -y --no-install-recommends \
    sudo git git-lfs curl nano ca-certificates \
    ros-dev-tools \
    ros-jazzy-rviz2 \
    python3-matplotlib \
    xfce4 xfce4-terminal dbus-x11 fonts-dejavu \
    tigervnc-standalone-server tigervnc-common \
    novnc websockify \
    libgl1-mesa-dri \
 && rm -rf /var/lib/apt/lists/*

# Make sure rosdep is initialised (the base image usually does this already)
RUN [ -f /etc/ros/rosdep/sources.list.d/20-default.list ] || rosdep init

# Non-root user with passwordless sudo
RUN useradd -m -s /bin/bash -G sudo dev \
 && echo "dev ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/dev \
 && mkdir -p /home/dev/ws_fanuc /home/dev/scripts \
 && chown -R dev:dev /home/dev

# Auto-source ROS 2 and the FANUC workspace (once it has been built) in every shell
RUN echo 'source /opt/ros/jazzy/setup.bash' >> /home/dev/.bashrc \
 && echo '[ -f ~/ws_fanuc/install/setup.bash ] && source ~/ws_fanuc/install/setup.bash' >> /home/dev/.bashrc

COPY --chown=dev:dev start.sh /home/dev/start.sh
RUN chmod +x /home/dev/start.sh

USER dev
WORKDIR /home/dev
RUN rosdep update --rosdistro jazzy

EXPOSE 6080
CMD ["/home/dev/start.sh"]
