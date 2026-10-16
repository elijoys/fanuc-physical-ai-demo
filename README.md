# FANUC CRX ROS 2 Simulation Demo

A containerized, one-command simulation of a FANUC CRX collaborative robot using FANUC's official
ROS 2 driver, plus a small Python client that runs a pick-and-place style sequence and logs and
plots the joint trajectories.

I built this to learn FANUC's ROS 2 stack hands-on. Everything here runs in **mock hardware**
mode: no robot controller is required.

## What it does
- Builds FANUC's open-source ROS 2 packages (`fanuc_description`, `fanuc_driver`) into a Docker image
  with ROS 2 Jazzy on Ubuntu 24.04.
- Gives you a Linux desktop in your browser (noVNC) so RViz works on any machine, including Macs.
- Launches the CRX-10iA with MoveIt 2 and `ros2_control` using FANUC's `use_mock:=true` option.
- Runs `scripts/pick_and_place_logger.py`, which sends joint-space waypoints to MoveIt, records
  `/joint_states`, and saves a CSV and a plot.

## Quick start

### Option A: Docker (any machine)
```bash
git clone <this repo>
cd fanuc-physical-ai-demo
docker compose up --build
```
The first build downloads and compiles a lot: expect roughly **<fill in measured time>** and
**<fill in image size>** of disk. Then open <http://localhost:6080/vnc.html> and click **Connect**.

### Option B: GitHub Codespaces
Open a codespace on this repo (4 cores recommended). When it loads, run this in the terminal and
leave it running (second terminal for everything else):
```bash
/home/dev/start.sh
```
Then open the forwarded port 6080 in the Ports tab and add `/vnc.html` to the address.
(The desktop does not auto-start in Codespaces; see "Problems I hit".)

## Run the simulation
In the desktop, open the terminal icon:
```bash
ros2 launch fanuc_moveit_config fanuc_moveit.launch.py robot_model:=crx10ia use_mock:=true
```
RViz shows the CRX-10iA. Drag the 3-D arrows to a new pose and click **Plan & Execute**.
FANUC's controller is a scaled joint trajectory controller, so you can also slow or pause a motion
mid-trajectory with the speed-scaling slider (10% → 0% → 100%).

## Run the pick-and-place + logging script
With the simulation running, in a second terminal:
```bash
cd ~/scripts        # or the repo's scripts/ folder in Codespaces
python3 pick_and_place_logger.py --vel-scale 0.3
```
It writes `output/joint_log.csv` and `output/joint_trajectories.png` and prints how close each joint
got to its velocity limit.

![Joint trajectories](output/joint_trajectories.png)

**How it works:** the script is a client of the already-running MoveIt. It does not contain its own
MoveIt configuration. It sends joint-space goals to the `/move_action` action server (the same one
RViz's Plan & Execute uses), subscribes to `/joint_states` while moving, then plots position and
velocity against time with markers at each waypoint.

**Waypoints** are placeholder joint angles that I tuned by posing the robot in RViz and reading
`/joint_states`, the same idea as teaching points on a pendant. <edit if you did something different>

**Observations from my run:** <fill in: did all waypoints succeed, peak speeds vs limits, anything surprising>

## Versions tested
| Component | Version |
|---|---|
| Base image | `ros:jazzy` (Ubuntu 24.04, ROS 2 Jazzy) |
| `fanuc_driver` | branch `main`, commit `<hash>` |
| `fanuc_description` | commit `<hash>` |

Pin these via build args: `docker compose build --build-arg FANUC_DRIVER_REF=<hash> --build-arg FANUC_DESC_REF=<hash>`

## Mock vs. real hardware
Everything above is simulation. Per FANUC's documentation, running against a real controller needs:
- Controller: R-30iB Plus / Mate Plus (V9.40P/81+), Mini Plus (V9.40P/77+), or R-50iA (V10.10P/26+)
- Software options: J519 Stream Motion and R912 Remote Motion, or S636 External Control Package
- A network connection to the robot, and launching with `robot_ip:=<address>` instead of `use_mock:=true`

I have not tested on hardware. I'd expect the MoveIt client side to carry over, but I'd want to
validate that on a real CRX before claiming it.

## Problems I hit and how I fixed them
1. **Docker disk on an external drive.** I planned to keep Docker's storage on an exFAT SSD (my Mac
   had little free space). Docker Desktop builds a VM disk image and exFAT isn't recommended for that.
   **Fix:** moved to GitHub Codespaces, which also avoids Apple Silicon (arm64) uncertainty with FANUC's
   binaries and my local disk limit.
2. **Browser desktop returned HTTP 502 on port 6080.** Nothing was listening: the devcontainer's
   `postStartCommand` never launched the desktop (there was no log file at all). Running
   `/home/dev/start.sh` by hand worked immediately. **Workaround:** start it manually in Codespaces.
   Plain `docker compose up` starts it automatically. **Root cause not determined.**
3. **Port 5901 shows "page not found" in the Ports tab.** That's the raw VNC port, not a web page.
   Ignore it; use 6080 only.
4. **Harmless noise:** an `xauth: .Xauthority does not exist` message on first start, and a 404 log line
   from noVNC's web server.
5. **Build warnings.** `colcon build` reported "22 packages had stderr output", and CMake warned that
   `BUILD_EXAMPLES` was unused. All 22 packages built. The stderr output was compiler warnings
   (`-Wreorder` in FANUC's hardware interface). The examples still built, so the flag in the quick
   start appears to be unused.
6. **Docs vs. repo layout.** The example packages live under `fanuc_driver/fanuc_examples/`, not at the
   repo root as I first assumed. I confirmed names (`manipulator`, `J1`-`J6`, `/move_action`) from the
   running system instead of guessing.
7. <add anything you hit while running the script or rebuilding>

## Limitations and next steps
- Mock hardware only; no collision objects or gripper in the scene.
- Joint-space waypoints only. Next: Cartesian targets, and comparing against FANUC's own
  `fanuc_pick_and_place_example`.
- Next: try Stream Motion / real-time control concepts and Roboguide integration on a real or virtual controller.
- Next: auto-start the desktop in Codespaces.