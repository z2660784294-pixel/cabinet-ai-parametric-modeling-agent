"""
Visualize bounding boxes from an abd.json file in a 3D interactive view.

Draws each unit's oriented box (rotate/scale around position pivot); overlap
detection uses the rotation-aware axis-aligned envelope.

Usage: python visualize_abd_bbox.py <path_to_abd_json>
"""

import json
import sys
from itertools import combinations
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

sys.path.insert(0, str(Path(__file__).resolve().parent))
from abd_bbox_geom import abd_aabb_minmax, abd_world_vertices, oriented_box_faces

matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "WenQuanYi Micro Hei", "sans-serif"]
matplotlib.rcParams["axes.unicode_minus"] = False

COLORS = [
    (0.2, 0.6, 1.0), (1.0, 0.4, 0.4), (0.3, 0.9, 0.4), (1.0, 0.8, 0.2),
    (0.7, 0.3, 0.9), (0.1, 0.8, 0.8), (1.0, 0.5, 0.0), (0.6, 0.6, 0.6)]


def get_box_faces(bmin, bmax):
    x0, y0, z0 = bmin
    x1, y1, z1 = bmax
    v = [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
         [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]]
    return [[v[i] for i in f] for f in [(0, 1, 5, 4), (2, 3, 7, 6), (0, 3, 7, 4), (1, 2, 6, 5), (0, 1, 2, 3), (4, 5, 6, 7)]]


def compute_overlap(bmin1, bmax1, bmin2, bmax2):
    omin = [max(bmin1[i], bmin2[i]) for i in range(3)]
    omax = [min(bmax1[i], bmax2[i]) for i in range(3)]
    return (omin, omax) if all(omin[i] < omax[i] for i in range(3)) else None


def main():
    if len(sys.argv) < 2:
        print("Usage: python visualize_abd_bbox.py <abd_json_file>")
        sys.exit(1)
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        data = json.load(f)
    assembly_name = data.get("name", "unknown")
    units = data.get("units", [])
    if not units:
        print("No units found.")
        sys.exit(1)
    fig = plt.figure(figsize=(12, 9))
    ax = fig.add_subplot(111, projection="3d")
    all_mins, all_maxs = [], []
    for idx, unit in enumerate(units):
        vertices = abd_world_vertices(
            unit["position"],
            unit["size"],
            rotate=unit.get("rotate"),
            scale=unit.get("scale"),
        )
        bmin, bmax = abd_aabb_minmax(
            unit["position"],
            unit["size"],
            rotate=unit.get("rotate"),
            scale=unit.get("scale"),
        )
        all_mins.append(bmin)
        all_maxs.append(bmax)
        c = COLORS[idx % len(COLORS)]
        ax.add_collection3d(
            Poly3DCollection(
                oriented_box_faces(vertices),
                alpha=0.15,
                facecolor=c,
                edgecolor=c,
                linewidth=0.8,
            )
        )
        center = [(bmin[i] + bmax[i]) / 2 for i in range(3)]
        ax.text(
            center[0], center[1], bmax[2],
            unit.get("name", "unit_%d" % idx),
            fontsize=7, ha="center", va="bottom", color=c, fontweight="bold",
        )
    for i, j in combinations(range(len(units)), 2):
        ov = compute_overlap(all_mins[i], all_maxs[i], all_mins[j], all_maxs[j])
        if ov:
            ax.add_collection3d(
                Poly3DCollection(
                    get_box_faces(*ov),
                    alpha=0.35,
                    facecolor="red",
                    edgecolor="darkred",
                    linewidth=1.2,
                )
            )
    a0, a1 = np.array(all_mins), np.array(all_maxs)
    smin, smax = a0.min(0), a1.max(0)
    margin = (smax - smin) * 0.1
    r = (smax - smin + 2 * margin).max()
    mid = (smin + smax) / 2
    ax.set_xlim(mid[0] - r / 2, mid[0] + r / 2)
    ax.set_ylim(mid[1] - r / 2, mid[1] + r / 2)
    ax.set_zlim(mid[2] - r / 2, mid[2] + r / 2)
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_zlabel("Z (mm)")
    ax.set_title("%s - %d unit(s) (red=overlap)" % (assembly_name, len(units)))
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
