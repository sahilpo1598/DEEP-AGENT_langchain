"""
swarm_sim.py — Basic decentralized drone-swarm simulation (2026)

A lightweight, dependency-minimal (NumPy) model of a drone swarm using
decentralized, Boids-style behavioral rules plus mission and environmental
constraints. It is intended as a teaching/analysis scaffold — NOT a substitute
for full MARL (MADDPG/MAPPO/QMIX) or high-fidelity physics simulators.

Behavioral model (per drone, computed from local/global state):
    1. SEPARATION      — repel neighbors that are too close (collision avoidance)
    2. ALIGNMENT       — match average velocity of local neighbors
    3. COHESION        — steer toward local center of mass
    4. WAYPOINT STEER  — steer toward the active mission waypoint
    5. OBSTACLE AVOID  — repulse from spherical obstacle volumes
    6. BOUNDARY        — soft containment inside the flight volume
    7. ENERGY          — linear drain: base + speed-proportional cost

Optional visualization uses matplotlib (if installed): 2D top-down scatter.

Run:
    python swarm_sim.py                # headless demo, prints metrics
    python swarm_sim.py --plot         # 2D animation/trajectory view
"""

from __future__ import annotations

import argparse
import dataclasses
from typing import List, Optional, Sequence, Tuple

import numpy as np


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
@dataclasses.dataclass
class SwarmConfig:
    n_drones: int = 30                # number of agents
    dim: int = 3                      # 2 or 3 spatial dimensions
    dt: float = 0.05                  # simulation timestep [s]
    bounds: Tuple[float, float, float, float] = (-60.0, 60.0, -60.0, 60.0)  # xmin, xmax, ymin, ymax
    z_bounds: Tuple[float, float] = (0.0, 60.0)   # altitude floor/ceiling (dim==3)
    max_speed: float = 6.0            # [m/s]
    max_accel: float = 4.0            # [m/s^2] (simple velocity clamp)
    # Boids weights
    w_separation: float = 2.5
    w_alignment: float = 1.2
    w_cohesion: float = 0.8
    w_waypoint: float = 1.5
    w_obstacle: float = 3.0
    w_boundary: float = 1.0
    # Sensing radii
    sep_radius: float = 5.0
    align_radius: float = 15.0
    coh_radius: float = 15.0
    obstacle_margin: float = 4.0     # extra standoff beyond obstacle radius
    # Energy model
    base_drain: float = 0.02          # energy fraction / s (idle)
    speed_drain: float = 0.006        # energy fraction / s per (m/s)
    # Mission
    waypoint_tolerance: float = 10.0  # distance [m] to consider waypoint reached
    # Random seed
    seed: int = 2026


@dataclasses.dataclass
class Obstacle:
    center: np.ndarray
    radius: float


# --------------------------------------------------------------------------- #
# Simulation
# --------------------------------------------------------------------------- #
class SwarmSim:
    """Vectorized decentralized swarm simulation."""

    def __init__(
        self,
        config: Optional[SwarmConfig] = None,
        waypoints: Optional[Sequence[Sequence[float]]] = None,
        obstacles: Optional[Sequence[Obstacle]] = None,
    ) -> None:
        self.cfg = config or SwarmConfig()
        rng = np.random.default_rng(self.cfg.seed)
        dim = self.cfg.dim
        n = self.cfg.n_drones

        # Random initial positions in a compact cluster near the origin.
        self.pos = rng.normal(0.0, 8.0, size=(n, dim))
        if dim == 3:
            self.pos[:, 2] = np.abs(self.pos[:, 2]) + 2.0  # start above ground
        self.vel = rng.normal(0.0, 1.0, size=(n, dim))

        self.energy = np.ones(n)                       # 1.0 = 100%
        self.active = np.ones(n, dtype=bool)           # False = depleted/landed

        self.waypoints = [np.asarray(w, dtype=float)[:dim] for w in (waypoints or [])]
        self.wp_index = 0

        self.obstacles = list(obstacles or [])

        # Metrics bookkeeping
        self.time = 0.0
        self.metrics: List[dict] = []

    # ----------------------------- helpers --------------------------------- #
    @property
    def n_active(self) -> int:
        return int(self.active.sum())

    def _current_waypoint(self) -> Optional[np.ndarray]:
        if self.wp_index < len(self.waypoints):
            return self.waypoints[self.wp_index]
        return None

    def _advance_waypoint(self) -> None:
        self.wp_index += 1

    # --------------------------- force components -------------------------- #
    def _separation(self) -> np.ndarray:
        """Repulsion from neighbors closer than sep_radius (collision avoid)."""
        n = self.cfg.n_drones
        out = np.zeros_like(self.pos)
        d = self.pos[:, None, :] - self.pos[None, :, :]      # (n, n, dim)
        dist = np.linalg.norm(d, axis=-1)                    # (n, n)
        np.fill_diagonal(dist, np.inf)
        mask = dist < self.cfg.sep_radius
        if mask.any():
            # d[i,j] = pos[i] - pos[j] points AWAY from j, so +d is repulsion.
            # Weighted repulsion: closer neighbors push harder.
            strength = (1.0 - dist / self.cfg.sep_radius)[:, :, None]
            rep = np.where(mask[:, :, None], d * strength, 0.0)
            out = rep.sum(axis=1)
        return out

    def _alignment(self) -> np.ndarray:
        """Steer toward the mean velocity of local neighbors."""
        n = self.cfg.n_drones
        out = np.zeros_like(self.vel)
        d = self.pos[:, None, :] - self.pos[None, :, :]
        dist = np.linalg.norm(d, axis=-1)
        np.fill_diagonal(dist, np.inf)
        mask = dist < self.cfg.align_radius
        counts = mask.sum(axis=1)  # (n,) number of neighbors per drone
        local_avg = (self.vel[None, :, :] * mask[:, :, None]).sum(axis=1)
        nz = counts > 0
        out[nz] = local_avg[nz] / counts[nz, None] - self.vel[nz]
        return out

    def _cohesion(self) -> np.ndarray:
        """Steer toward the local center of mass of neighbors."""
        n = self.cfg.n_drones
        out = np.zeros_like(self.pos)
        d = self.pos[:, None, :] - self.pos[None, :, :]
        dist = np.linalg.norm(d, axis=-1)
        np.fill_diagonal(dist, np.inf)
        mask = dist < self.cfg.coh_radius
        counts = mask.sum(axis=1)  # (n,) number of neighbors per drone
        local_center = (self.pos[None, :, :] * mask[:, :, None]).sum(axis=1)
        nz = counts > 0
        out[nz] = local_center[nz] / counts[nz, None] - self.pos[nz]
        return out

    def _waypoint_steer(self) -> np.ndarray:
        """Attraction toward the active mission waypoint (shared target)."""
        out = np.zeros_like(self.pos)
        wp = self._current_waypoint()
        if wp is not None:
            out = wp[None, :] - self.pos
        return out

    def _obstacle_avoid(self) -> np.ndarray:
        """Repulsion away from spherical obstacle volumes with standoff margin."""
        out = np.zeros_like(self.pos)
        for ob in self.obstacles:
            center = ob.center[: self.cfg.dim]
            r_eff = ob.radius + self.cfg.obstacle_margin
            delta = self.pos - center[None, :]
            dist = np.linalg.norm(delta, axis=-1, keepdims=True)
            dist = np.maximum(dist, 1e-6)
            inside = (dist < r_eff).astype(float)
            out += -delta / dist * (1.0 - dist / r_eff) * inside
        return out

    def _boundary(self) -> np.ndarray:
        """Soft push away from the flight-volume walls / floor / ceiling."""
        out = np.zeros_like(self.pos)
        xmin, xmax, ymin, ymax = self.cfg.bounds
        # X walls
        out[:, 0] -= np.clip(self.pos[:, 0] - xmax, 0, None)
        out[:, 0] += np.clip(xmin - self.pos[:, 0], 0, None)
        # Y walls
        out[:, 1] -= np.clip(self.pos[:, 1] - ymax, 0, None)
        out[:, 1] += np.clip(ymin - self.pos[:, 1], 0, None)
        # Z floor/ceiling
        if self.cfg.dim == 3:
            zmin, zmax = self.cfg.z_bounds
            out[:, 2] -= np.clip(self.pos[:, 2] - zmax, 0, None)
            out[:, 2] += np.clip(zmin - self.pos[:, 2], 0, None)
        return out

    # ------------------------------ step ----------------------------------- #
    def step(self) -> dict:
        cfg = self.cfg
        active = self.active

        accel = (
            cfg.w_separation * self._separation()
            + cfg.w_alignment * self._alignment()
            + cfg.w_cohesion * self._cohesion()
            + cfg.w_waypoint * self._waypoint_steer()
            + cfg.w_obstacle * self._obstacle_avoid()
            + cfg.w_boundary * self._boundary()
        )

        # Optional control-authority clamp (pseudo-acceleration magnitude).
        accel_norm = np.linalg.norm(accel, axis=-1, keepdims=True)
        accel_norm = np.maximum(accel_norm, 1e-6)
        accel = np.where(accel_norm > cfg.max_accel,
                         accel / accel_norm * cfg.max_accel, accel)

        # Integrate (simple Euler + speed clamp), only for active agents.
        self.vel[active] += accel[active] * cfg.dt
        speed = np.linalg.norm(self.vel, axis=-1, keepdims=True)
        speed = np.maximum(speed, 1e-6)
        self.vel = np.where(speed > cfg.max_speed, self.vel / speed * cfg.max_speed, self.vel)

        self.pos[active] += self.vel[active] * cfg.dt

        # Energy drain: base + speed-proportional.
        drain = cfg.base_drain + cfg.speed_drain * np.linalg.norm(self.vel, axis=-1)
        self.energy -= drain * cfg.dt
        newly_dead = (~self.active) | (self.energy <= 0.0)
        self.active = self.active & ~newly_dead
        self.energy = np.clip(self.energy, 0.0, 1.0)

        # Waypoint advance: when swarm centroid is within tolerance of target.
        wp = self._current_waypoint()
        if wp is not None and self.n_active > 0:
            centroid = self.pos[self.active].mean(axis=0)
            if np.linalg.norm(centroid - wp) < cfg.waypoint_tolerance:
                self._advance_waypoint()

        self.time += cfg.dt

        metrics = self._collect_metrics()
        self.metrics.append(metrics)
        return metrics

    def _collect_metrics(self) -> dict:
        act_pos = self.pos[self.active]
        if act_pos.shape[0] > 1:
            d = act_pos[:, None, :] - act_pos[None, :, :]
            dist = np.linalg.norm(d, axis=-1)
            np.fill_diagonal(dist, np.inf)
            min_sep = float(dist.min())
        else:
            min_sep = float("inf")

        return {
            "t": self.time,
            "active": self.n_active,
            "mean_energy": float(self.energy[self.active].mean()) if self.n_active else 0.0,
            "min_separation": min_sep,
            "mean_speed": float(np.linalg.norm(self.vel[self.active], axis=-1).mean()) if self.n_active else 0.0,
            "waypoint_index": self.wp_index,
        }

    # ------------------------------ run ------------------------------------ #
    def run(self, steps: int = 2000, verbose: bool = True) -> List[dict]:
        for _ in range(steps):
            self.step()
            if self.n_active == 0:
                if verbose:
                    print("All drones depleted — terminating early.")
                break
        if verbose:
            self.print_summary()
        return self.metrics

    def print_summary(self) -> None:
        last = self.metrics[-1]
        m = self.metrics
        min_seps = [x["min_separation"] for x in m if x["min_separation"] != float("inf")]
        print("=" * 60)
        print("Drone Swarm Simulation — Results")
        print("=" * 60)
        print(f"  Simulated time       : {self.time:8.2f} s")
        print(f"  Active drones        : {last['active']:3d} / {self.cfg.n_drones}")
        print(f"  Waypoints reached    : {self.wp_index} / {len(self.waypoints)}")
        print(f"  Mean remaining energy: {last['mean_energy']:.2%}")
        print(f"  Mean speed (final)   : {last['mean_speed']:.2f} m/s")
        if min_seps:
            print(f"  Min inter-agent sep  : {min(min_seps):.2f} m  (worst-case over run)")
        print("=" * 60)


# --------------------------------------------------------------------------- #
# Visualization (optional, matplotlib)
# --------------------------------------------------------------------------- #
def plot_trajectory(sim: SwarmSim, trajectory: List[np.ndarray]) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed — skipping plot. Run headless for metrics only.")
        return

    fig, ax = plt.subplots(figsize=(7, 7))
    xmin, xmax, ymin, ymax = sim.cfg.bounds

    # Obstacles
    for ob in sim.obstacles:
        c = ob.center[:2]
        circle = plt.Circle(c, ob.radius, color="red", alpha=0.35, zorder=3)
        ax.add_patch(circle)

    # Waypoints
    if sim.waypoints:
        wps = np.stack(sim.waypoints)[:, :2]
        ax.plot(wps[:, 0], wps[:, 1], "s--", color="orange", label="waypoints", zorder=2)

    # Trajectories (thin, light) + final positions (markers)
    if trajectory:
        traj = np.stack(trajectory)
        ax.plot(traj[:, :, 0], traj[:, :, 1], color="0.85", lw=0.5, zorder=1)
    ax.scatter(sim.pos[sim.active, 0], sim.pos[sim.active, 1],
               c="tab:blue", s=24, label="active drones", zorder=4)
    if (~sim.active).any():
        ax.scatter(sim.pos[~sim.active, 0], sim.pos[~sim.active, 1],
                   c="gray", s=24, marker="x", label="depleted", zorder=4)

    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect("equal")
    ax.set_title("Drone Swarm — Top-Down View")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.show()


# --------------------------------------------------------------------------- #
# Demo
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description="Basic decentralized drone-swarm simulation.")
    parser.add_argument("--plot", action="store_true", help="render a top-down trajectory plot")
    parser.add_argument("--n", type=int, default=30, help="number of drones")
    parser.add_argument("--steps", type=int, default=2000, help="simulation steps")
    parser.add_argument("--dim", type=int, choices=[2, 3], default=3, help="dimensions")
    args = parser.parse_args()

    # Example mission: sweep across three waypoints.
    waypoints = [
        (40.0, 0.0, 30.0),
        (40.0, 40.0, 35.0),
        (-40.0, 40.0, 30.0),
        (-40.0, -40.0, 30.0),
    ]

    # Example obstacles: two "no-fly" columns / buildings.
    obstacles = [
        Obstacle(center=np.array([0.0, 0.0, 25.0]), radius=8.0),
        Obstacle(center=np.array([15.0, 15.0, 25.0]), radius=5.0),
    ]

    cfg = SwarmConfig(n_drones=args.n, dim=args.dim)
    sim = SwarmSim(cfg, waypoints=waypoints, obstacles=obstacles)

    # Run and capture a subsampled trajectory for plotting.
    trajectory = []
    sample_every = max(1, args.steps // 300)
    for i in range(args.steps):
        sim.step()
        if i % sample_every == 0:
            trajectory.append(sim.pos.copy())
        if sim.n_active == 0:
            break

    sim.print_summary()
    if args.plot:
        plot_trajectory(sim, trajectory)


if __name__ == "__main__":
    main()
