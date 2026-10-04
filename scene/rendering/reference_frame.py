"""Find the captured video frame closest to the current camera pose."""

import math
from pathlib import Path

POSITION_SCALE = 0.5  # Scene units; approximately meters with metric reconstruction.
DIRECTION_SCALE_DEGREES = 20.0


def nearest_frame(cameras, cameras_path, position, forward):
    """Rank saved frames by camera-center distance and viewing-direction angle."""
    forward_length = math.sqrt(sum(value * value for value in forward))
    forward = [value / forward_length for value in forward]
    best = None

    for frame in cameras:
        extrinsic = frame['extrinsic']  # VGGT world-to-camera matrix.
        rotation = [row[:3] for row in extrinsic[:3]]
        translation = [row[3] for row in extrinsic[:3]]
        center = [-sum(rotation[j][i] * translation[j] for j in range(3))
                  for i in range(3)]
        direction = rotation[2]  # R.T @ (0, 0, 1): camera +Z in world axes.
        direction_length = math.sqrt(sum(value * value for value in direction))
        direction = [value / direction_length for value in direction]
        distance = math.dist(position, center)
        cosine = max(-1.0, min(1.0, sum(a * b for a, b in zip(forward, direction))))
        angle = math.degrees(math.acos(cosine))
        score = (distance / POSITION_SCALE) ** 2 + (angle / DIRECTION_SCALE_DEGREES) ** 2
        if best is None or score < best['score']:
            best = {
                'id': frame['id'],
                'video_frame_index': frame['video_frame_index'],
                'time_seconds': frame['time_seconds'],
                'image_path': str((Path(cameras_path).parent / frame['image_path']).resolve()),
                'source_video': frame['source_video'],
                'position_distance': distance,
                'direction_angle_degrees': angle,
                'score': score,
            }

    return best
