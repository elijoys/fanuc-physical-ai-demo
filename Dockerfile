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
 && mkdir -p /home/dev/ws_fanuc/src /home/dev/scripts \
 && chown -R dev:dev /home/dev

USER dev
WORKDIR /home/dev
RUN rosdep update --rosdistro jazzy && git lfs install

# ---- FANUC ROS 2 driver workspace (built into the image) ----
# Defaults track the latest main branch. For a reproducible build, pass the exact
# commit hashes you tested with, e.g. --build-arg FANUC_DRIVER_REF=<hash>
ARG FANUC_DESC_REF=fb40c9803a826ba68c7c8e28ba904a25efa7fcd2
ARG FANUC_DRIVER_REF=da5db3f611cdc9dffe687e056c4e79bea584bf5c

RUN cd /home/dev/ws_fanuc/src \
 && git clone https://github.com/FANUC-CORPORATION/fanuc_description.git \
 && git -C fanuc_description checkout ${FANUC_DESC_REF} \
 && git clone --branch main --single-branch https://github.com/FANUC-CORPORATION/fanuc_driver.git \
 && git -C fanuc_driver checkout ${FANUC_DRIVER_REF} \
 && git -C fanuc_driver submodule update --init --recursive

RUN sudo apt-get update \
 && cd /home/dev/ws_fanuc \
 && rosdep install --rosdistro jazzy --ignore-src --from-paths src -y \
 && sudo rm -rf /var/lib/apt/lists/*

# If this step is killed (out of memory), add: --parallel-workers 2
RUN . /opt/ros/jazzy/setup.sh \
 && cd /home/dev/ws_fanuc \
 && colcon build --symlink-install

# Auto-source ROS 2 and the FANUC workspace in every shell
RUN echo 'source /opt/ros/jazzy/setup.bash' >> /home/dev/.bashrc \
 && echo 'source ~/ws_fanuc/install/setup.bash' >> /home/dev/.bashrc

COPY --chown=dev:dev start.sh /home/dev/start.sh
RUN chmod +x /home/dev/start.sh

EXPOSE 6080
CMD ["/home/dev/start.sh"]