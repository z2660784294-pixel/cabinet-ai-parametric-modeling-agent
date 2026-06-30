"""
Visualize scene_bbox vs abd_bbox from a bbox_diff JSON file in a 3D interactive view.

Scene bbox is drawn with solid edges; abd bbox is drawn with dashed edges.
Same-color pairs share one model (matched by obsBrandGoodId).

Usage: python visualize_bbox_diff.py <path_to_bbox_diff.json>
"""

import json
import sys
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection, Line3DCollection

matplotlib.rcParams["font.sans-serif"] = [
    "Microsoft YaHei", "SimHei", "WenQuanYi Micro Hei", "sans-serif",
]
matplotlib.rcParams["axes.unicode_minus"] = False

COLORS = [
    (0.2, 0.6, 1.0),
    (1.0, 0.4, 0.4),
    (0.3, 0.9, 0.4),
    (1.0, 0.8, 0.2),
    (0.7, 0.3, 0.9),
    (0.1, 0.8, 0.8),
    (1.0, 0.5, 0.0),
    (0.6, 0.6, 0.6),
]


def _pos_size_to_minmax(pos, size):
    """Convert min-corner position (左后下) + size to (min, max) corners."""
    bmin = [pos[i] for i in range(3)]
    bmax = [pos[i] + size[i] for i in range(3)]
    return bmin, bmax


def get_box_faces(bmin, bmax):
    x0, y0, z0 = bmin
    x1, y1, z1 = bmax
    v = [
        [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
    ]
    return [
        [v[0], v[1], v[5], v[4]],
        [v[2], v[3], v[7], v[6]],
        [v[0], v[3], v[7], v[4]],
        [v[1], v[2], v[6], v[5]],
        [v[0], v[1], v[2], v[3]],
        [v[4], v[5], v[6], v[7]],
    ]


def get_box_edges(bmin, bmax):
    x0, y0, z0 = bmin
    x1, y1, z1 = bmax
    v = [
        [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
    ]
    return [
        (v[0], v[1]), (v[1], v[2]), (v[2], v[3]), (v[3], v[0]),
        (v[4], v[5]), (v[5], v[6]), (v[6], v[7]), (v[7], v[4]),
        (v[0], v[4]), (v[1], v[5]), (v[2], v[6]), (v[3], v[7]),
    ]


def _add_box(ax, bmin, bmax, color, alpha_face, linestyle, linewidth, label=None):
    faces = get_box_faces(bmin, bmax)
    poly = Poly3DCollection(
        faces,
        alpha=alpha_face,
        facecolor=color,
        edgecolor="none",
    )
    ax.add_collection3d(poly)

    edges = get_box_edges(bmin, bmax)
    lc = Line3DCollection(
        edges,
        colors=[color] * len(edges),
        linewidths=linewidth,
        linestyles=linestyle,
    )
    ax.add_collection3d(lc)

    if label:
        center = [(bmin[i] + bmax[i]) / 2 for i in range(3)]
        ax.text(
            center[0], center[1], bmax[2],
            label, fontsize=6, ha="center", va="bottom",
            color=color, fontweight="bold",
        )


def main():
    if len(sys.argv) < 2:
        print("Usage: python visualize_bbox_diff.py <bbox_diff.json>")
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        data = json.load(f)

    details = data.get("details", [])
    paired = [d for d in details if "scene_bbox" in d and "abd_bbox" in d]
    if not paired:
        print("No paired bbox entries found.")
        sys.exit(1)

    fig = plt.figure(figsize=(14, 10))
    ax = fig.add_subplot(111, projection="3d")

    all_mins, all_maxs = [], []

    for idx, entry in enumerate(paired):
        color = COLORS[idx % len(COLORS)]
        name = entry.get("name", entry.get("obsBrandGoodId", f"model_{idx}"))
        status = entry.get("status", "")

        sb = entry["scene_bbox"]
        s_pos = [sb["position"]["x"], sb["position"]["y"], sb["position"]["z"]]
        s_size = [sb["size"]["x"], sb["size"]["y"], sb["size"]["z"]]
        s_min, s_max = _pos_size_to_minmax(s_pos, s_size)

        ab = entry["abd_bbox"]
        a_pos = [ab["position"]["x"], ab["position"]["y"], ab["position"]["z"]]
        a_size = [ab["size"]["x"], ab["size"]["y"], ab["size"]["z"]]
        a_min, a_max = _pos_size_to_minmax(a_pos, a_size)

        _add_box(ax, s_min, s_max, color, 0.10, "solid", 1.2,
                 label=f"[scene] {name}")
        _add_box(ax, a_min, a_max, color, 0.06, "dashed", 0.9,
                 label=f"[abd] {name}")

        all_mins.extend([s_min, a_min])
        all_maxs.extend([s_max, a_max])

    all_mins = np.array(all_mins)
    all_maxs = np.array(all_maxs)
    scene_min = all_mins.min(axis=0)
    scene_max = all_maxs.max(axis=0)
    ranges = scene_max - scene_min
    max_range = ranges.max() * 1.15
    mid = (scene_min + scene_max) / 2

    ax.set_xlim(mid[0] - max_range / 2, mid[0] + max_range / 2)
    ax.set_ylim(mid[1] - max_range / 2, mid[1] + max_range / 2)
    ax.set_zlim(mid[2] - max_range / 2, mid[2] + max_range / 2)

    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_zlabel("Z (mm)")

    summary = data.get("summary", {})
    title = (
        f"BBox Diff: {summary.get('identical', '?')} identical, "
        f"{summary.get('different', '?')} different  "
        f"(solid=scene, dashed=abd)"
    )
    ax.set_title(title)

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
