#!/usr/bin/env python3

"""
Drive the mock FANUC CRX-10iA through a pick-and-place style joint-space sequence
using MoveIt's MoveGroup action, while logging /joint_states.
Outputs a CSV and a PNG plot (positions + velocities vs time, waypoint markers,
and velocity limits read from the robot description when available).

Prereq: the mock simulation is already running:
  ros2 launch fanuc_moveit_config fanuc_moveit.launch.py robot_model:=crx10ia use_mock:=true

Run:
  python3 pick_and_place_logger.py [--vel-scale 0.3] [--out output]
"""
import argparse
import csv
import os
import threading
import time
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use("Agg")  # headless: write PNG files, no display needed
import matplotlib.pyplot as plt
import numpy as np

import rclpy
from rclpy.action import ActionClient
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import JointState
from std_msgs.msg import String
from moveit_msgs.action import MoveGroup
from moveit_msgs.msg import Constraints, JointConstraint, MoveItErrorCodes

GROUP = "manipulator"                      # planning group from the FANUC SRDF
JOINTS = ["J1", "J2", "J3", "J4", "J5", "J6"]

# PLACEHOLDER waypoints (radians). Replace with "taught" values: pose the robot in
# RViz, Plan & Execute, then run `ros2 topic echo /joint_states --once` and copy
# the positions here, just like teaching points on a pendant.
WAYPOINTS = [
    ("home",        [0.0,  0.0,  0.0, 0.0, 0.0, 0.0]),
    ("above_pick",  [0.5,  0.3,  0.3, 0.0, 0.3, 0.0]),
    ("pick",        [0.5,  0.5,  0.5, 0.0, 0.3, 0.0]),
    ("lift",        [0.5,  0.3,  0.3, 0.0, 0.3, 0.0]),
    ("above_place", [-0.5, 0.3,  0.3, 0.0, 0.3, 0.0]),
    ("place",       [-0.5, 0.5,  0.5, 0.0, 0.3, 0.0]),
    ("retreat",     [-0.5, 0.3,  0.3, 0.0, 0.3, 0.0]),
    ("home",        [0.0,  0.0,  0.0, 0.0, 0.0, 0.0]),
]


class PickPlaceLogger(Node):
    def __init__(self):
        super().__init__("pick_place_logger")
        self.client = ActionClient(self, MoveGroup, "move_action")
        self.create_subscription(JointState, "/joint_states", self._on_joint_state, 50)
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             reliability=ReliabilityPolicy.RELIABLE)
        self.create_subscription(String, "/robot_description", self._on_description, latched)

        self.lock = threading.Lock()
        self.recording = False
        self.got_state = False
        self.urdf = None
        self.samples = []   # (t_abs, [pos...], [vel...])
        self.marks = []     # (t_abs, waypoint_name)

    # ---- callbacks (run in the background executor thread) ----
    def _on_description(self, msg):
        self.urdf = msg.data

    def _on_joint_state(self, msg):
        self.got_state = True
        if not self.recording:
            return
        idx = {n: i for i, n in enumerate(msg.name)}
        if not all(j in idx for j in JOINTS):
            return
        pos = [msg.position[idx[j]] for j in JOINTS]
        vel = [msg.velocity[idx[j]] if len(msg.velocity) > idx[j] else 0.0 for j in JOINTS]
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        if stamp == 0.0:
            stamp = self.now_s()
        with self.lock:
            self.samples.append((stamp, pos, vel))

    # ---- helpers ----
    def now_s(self):
        return self.get_clock().now().nanoseconds * 1e-9

    @staticmethod
    def _wait(future, timeout):
        end = time.time() + timeout
        while not future.done():
            if time.time() > end:
                return False
            time.sleep(0.01)
        return True

    def move_to(self, name, positions, vel_scale):
        goal = MoveGroup.Goal()
        req = goal.request
        req.group_name = GROUP
        req.num_planning_attempts = 5
        req.allowed_planning_time = 5.0
        req.max_velocity_scaling_factor = vel_scale
        req.max_acceleration_scaling_factor = vel_scale
        req.start_state.is_diff = True  # start from the robot's current state

        c = Constraints()
        for jn, p in zip(JOINTS, positions):
            jc = JointConstraint()
            jc.joint_name = jn
            jc.position = float(p)
            jc.tolerance_above = 0.001
            jc.tolerance_below = 0.001
            jc.weight = 1.0
            c.joint_constraints.append(jc)
        req.goal_constraints.append(c)

        goal.planning_options.plan_only = False   # plan AND execute
        goal.planning_options.planning_scene_diff.is_diff = True
        goal.planning_options.planning_scene_diff.robot_state.is_diff = True

        send = self.client.send_goal_async(goal)
        if not self._wait(send, 10.0):
            self.get_logger().error(f"[{name}] timed out sending goal")
            return False
        handle = send.result()
        if not handle.accepted:
            self.get_logger().error(f"[{name}] goal rejected")
            return False
        result_future = handle.get_result_async()
        if not self._wait(result_future, 60.0):
            self.get_logger().error(f"[{name}] timed out waiting for result")
            return False
        code = result_future.result().result.error_code.val
        if code != MoveItErrorCodes.SUCCESS:
            self.get_logger().error(f"[{name}] MoveIt error code {code}")
            return False
        return True


def parse_limits(urdf):
    """Return {joint: (lower, upper, max_velocity)} from the URDF string, or {}."""
    limits = {}
    if not urdf:
        return limits
    try:
        root = ET.fromstring(urdf.encode("utf-8"))
        for j in root.iter("joint"):
            lim = j.find("limit")
            if lim is not None and j.get("name") in JOINTS:
                limits[j.get("name")] = (float(lim.get("lower", "nan")),
                                         float(lim.get("upper", "nan")),
                                         float(lim.get("velocity", "nan")))
    except Exception as exc:  # limits are a nice-to-have
        print(f"Could not parse joint limits: {exc}")
    return limits


def save_outputs(samples, marks, limits, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    t = np.array([s[0] for s in samples])
    pos = np.array([s[1] for s in samples])
    vel = np.array([s[2] for s in samples])
    t0 = t[0]
    t = t - t0
    marks_rel = [(mt - t0, name) for mt, name in marks]

    # Raw log
    csv_path = os.path.join(out_dir, "joint_log.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t"] + [f"pos_{j}" for j in JOINTS] + [f"vel_{j}" for j in JOINTS])
        for i in range(len(t)):
            w.writerow([f"{t[i]:.4f}"] + [f"{x:.6f}" for x in pos[i]] + [f"{x:.6f}" for x in vel[i]])

    # Velocity: use what the hardware reports, else differentiate position
    if np.max(np.abs(vel)) > 1e-6:
        v_plot, v_label, tv = vel, "reported velocity", t
    else:
        tu, ui = np.unique(t, return_index=True)
        v_plot = np.gradient(pos[ui], tu, axis=0)
        v_label, tv = "velocity (derived from position)", tu

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    for k, j in enumerate(JOINTS):
        ax1.plot(t, pos[:, k], label=j, color=colors[k])
        ax2.plot(tv, v_plot[:, k], label=j, color=colors[k])
        if j in limits and np.isfinite(limits[j][2]):
            ax2.axhline(limits[j][2], color=colors[k], linestyle="--", alpha=0.4)
            ax2.axhline(-limits[j][2], color=colors[k], linestyle="--", alpha=0.4)
    for mt, name in marks_rel:
        for ax in (ax1, ax2):
            ax.axvline(mt, color="gray", linestyle=":", alpha=0.6)
        ax1.text(mt, ax1.get_ylim()[1], name, rotation=90, va="top", ha="right", fontsize=8)
    ax1.set_ylabel("Joint position (rad)")
    ax2.set_ylabel(f"Joint {v_label} (rad/s)")
    ax2.set_xlabel("Time (s)")
    ax1.set_title("CRX-10iA mock pick-and-place: joint trajectories")
    ax2.set_title("Dashed lines = joint velocity limits (when available)", fontsize=9)
    ax1.legend(ncol=6, loc="lower right")
    ax1.grid(alpha=0.3)
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    png_path = os.path.join(out_dir, "joint_trajectories.png")
    fig.savefig(png_path, dpi=150)

    # Summary: how close did each joint get to its velocity limit?
    print("\nPeak joint speed vs. limit:")
    for k, j in enumerate(JOINTS):
        peak = float(np.max(np.abs(v_plot[:, k])))
        if j in limits and np.isfinite(limits[j][2]) and limits[j][2] > 0:
            print(f"  {j}: {peak:.3f} rad/s of {limits[j][2]:.3f} ({100 * peak / limits[j][2]:.0f}%)")
        else:
            print(f"  {j}: {peak:.3f} rad/s (limit unknown)")
    print(f"\nSaved:\n  {csv_path}\n  {png_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vel-scale", type=float, default=0.3,
                    help="MoveIt velocity/acceleration scaling, 0-1 (default 0.3)")
    ap.add_argument("--out", default="output", help="output directory")
    ap.add_argument("--dwell", type=float, default=0.5, help="pause at each waypoint (s)")
    args = ap.parse_args()

    rclpy.init()
    node = PickPlaceLogger()
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    threading.Thread(target=executor.spin, daemon=True).start()

    try:
        print("Waiting for MoveIt (move_action) and /joint_states ...")
        if not node.client.wait_for_server(timeout_sec=15.0):
            print("ERROR: /move_action not available. Is the mock launch running?")
            return
        end = time.time() + 10.0
        while not node.got_state and time.time() < end:
            time.sleep(0.1)
        if not node.got_state:
            print("ERROR: no /joint_states received.")
            return
        end = time.time() + 3.0
        while node.urdf is None and time.time() < end:
            time.sleep(0.1)
        limits = parse_limits(node.urdf)
        print("Joint limits read from robot description." if limits
              else "Joint limits not available; plotting without them.")

        node.recording = True
        time.sleep(0.5)  # a little idle data before the first move
        for name, joints in WAYPOINTS:
            print(f"-> {name}")
            if not node.move_to(name, joints, args.vel_scale):
                print(f"Stopping early: could not reach '{name}'.")
                break
            node.marks.append((node.now_s(), name))
            time.sleep(args.dwell)
        node.recording = False

        with node.lock:
            samples = list(node.samples)
        if len(samples) < 2:
            print("ERROR: not enough joint-state samples recorded.")
            return
        save_outputs(samples, node.marks, limits, args.out)
    finally:
        node.recording = False
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()