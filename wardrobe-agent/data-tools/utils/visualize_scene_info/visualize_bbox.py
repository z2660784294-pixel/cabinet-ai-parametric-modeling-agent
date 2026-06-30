"""
Visualize bounding boxes from a scene info JSON file in a 3D interactive view.
Usage: python visualize_bbox.py <path_to_json>
"""

import json
import sys
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from itertools import combinations

matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "WenQuanYi Micro Hei", "sans-serif"]
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


def get_box_faces(bmin, bmax):
    """Return the 6 faces of an axis-aligned bounding box as vertex lists."""
    x0, y0, z0 = bmin
    x1, y1, z1 = bmax
    vertices = [
        [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
    ]
    faces = [
        [vertices[0], vertices[1], vertices[5], vertices[4]],  # front
        [vertices[2], vertices[3], vertices[7], vertices[6]],  # back
        [vertices[0], vertices[3], vertices[7], vertices[4]],  # left
        [vertices[1], vertices[2], vertices[6], vertices[5]],  # right
        [vertices[0], vertices[1], vertices[2], vertices[3]],  # bottom
        [vertices[4], vertices[5], vertices[6], vertices[7]],  # top
    ]
    return faces


def compute_overlap(bbox1, bbox2):
    """Compute the overlap region of two AABBs, return None if no overlap."""
    omin = [max(bbox1["min"][a], bbox2["min"][a]) for a in ("x", "y", "z")]
    omax = [min(bbox1["max"][a], bbox2["max"][a]) for a in ("x", "y", "z")]
    if all(omin[i] < omax[i] for i in range(3)):
        return omin, omax
    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python visualize_bbox.py <json_file>")
        sys.exit(1)

    json_path = sys.argv[1]
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    instances = data.get("modelInstances", [])
    if not instances:
        print("No modelInstances found in JSON.")
        sys.exit(1)

    fig = plt.figure(figsize=(12, 9))
    ax = fig.add_subplot(111, projection="3d")

    all_mins = []
    all_maxs = []

    for idx, inst in enumerate(instances):
        bbox = inst["bbox"]
        name = inst.get("name", f"model_{idx}")
        bmin = [bbox["min"]["x"], bbox["min"]["y"], bbox["min"]["z"]]
        bmax = [bbox["max"]["x"], bbox["max"]["y"], bbox["max"]["z"]]
        all_mins.append(bmin)
        all_maxs.append(bmax)

        color = COLORS[idx % len(COLORS)]
        faces = get_box_faces(bmin, bmax)
        poly = Poly3DCollection(faces, alpha=0.15, facecolor=color, edgecolor=color, linewidth=0.8)
        ax.add_collection3d(poly)

        center = [(bmin[i] + bmax[i]) / 2 for i in range(3)]
        ax.text(center[0], center[1], bmax[2], name,
                fontsize=7, ha="center", va="bottom", color=color, fontweight="bold")

    # Highlight overlapping regions in red
    for i, j in combinations(range(len(instances)), 2):
        overlap = compute_overlap(instances[i]["bbox"], instances[j]["bbox"])
        if overlap:
            omin, omax = overlap
            faces = get_box_faces(omin, omax)
            poly = Poly3DCollection(faces, alpha=0.35, facecolor="red", edgecolor="darkred", linewidth=1.2)
            ax.add_collection3d(poly)

    all_mins = np.array(all_mins)
    all_maxs = np.array(all_maxs)
    scene_min = all_mins.min(axis=0)
    scene_max = all_maxs.max(axis=0)
    margin = (scene_max - scene_min) * 0.1

    ax.set_xlim(scene_min[0] - margin[0], scene_max[0] + margin[0])
    ax.set_ylim(scene_min[1] - margin[1], scene_max[1] + margin[1])
    ax.set_zlim(scene_min[2] - margin[2], scene_max[2] + margin[2])

    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_zlabel("Z (mm)")
    ax.set_title("BBox Visualization (red = overlap region)")

    # Equal aspect ratio
    ranges = scene_max - scene_min + 2 * margin
    max_range = ranges.max()
    mid = (scene_min + scene_max) / 2
    ax.set_xlim(mid[0] - max_range / 2, mid[0] + max_range / 2)
    ax.set_ylim(mid[1] - max_range / 2, mid[1] + max_range / 2)
    ax.set_zlim(mid[2] - max_range / 2, mid[2] + max_range / 2)

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
