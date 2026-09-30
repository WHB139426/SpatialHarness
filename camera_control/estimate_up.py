"""Estimate scene up from a PLY mesh and VGGT camera poses."""

import json


def estimate_scene_up(meshes, cameras_path, extent):
    """Return up, description, and a floor point; use a low-point estimate if no plane fits."""
    import numpy as np

    cameras = json.loads(cameras_path.read_text(encoding='utf-8'))
    if not isinstance(cameras, list) or not cameras:
        raise ValueError('camera JSON must contain a nonempty list')
    extrinsics = np.asarray([c['extrinsic'] for c in cameras], dtype=np.float64)
    if extrinsics.shape[1:] != (4, 4) or not np.isfinite(extrinsics).all():
        raise ValueError('camera extrinsics must be finite 4x4 matrices')
    rotations = extrinsics[:, :3, :3]
    translations = extrinsics[:, :3, 3]
    camera_centers = -np.einsum('nij,nj->ni', rotations.transpose(0, 2, 1), translations)
    first_camera_up = -rotations[0, 1, :]
    first_camera_up /= np.linalg.norm(first_camera_up)

    arrays = []
    for obj in meshes:
        coords = np.empty(len(obj.data.vertices) * 3, dtype=np.float32)
        obj.data.vertices.foreach_get('co', coords)
        coords = coords.reshape((-1, 3)).astype(np.float64)
        transform = np.asarray(obj.matrix_world, dtype=np.float64)
        arrays.append(coords @ transform[:3, :3].T + transform[:3, 3])
    cloud = np.concatenate(arrays)
    if len(cloud) < 3 or not np.isfinite(cloud).all():
        raise ValueError('point cloud has too few valid points')
    rng = np.random.default_rng(42)
    sample = cloud[rng.choice(len(cloud), min(len(cloud), 12000), replace=False)]
    tolerance = max(extent * 0.003, 1e-8)
    best = None
    for _ in range(500):
        a, b, c = sample[rng.choice(len(sample), 3, replace=False)]
        normal = np.cross(b - a, c - a)
        length = np.linalg.norm(normal)
        if length < 1e-10 * extent * extent:
            continue
        normal /= length
        if normal @ first_camera_up < 0:
            normal = -normal
        if normal @ first_camera_up < 0.75:
            continue
        offset = -normal @ a
        heights = sample @ normal + offset
        inliers = np.abs(heights) < tolerance
        support = int(inliers.sum())
        if support < max(60, len(sample) * 0.03):
            continue
        camera_heights = camera_centers @ normal + offset
        if np.mean(camera_heights > tolerance) < 0.95:
            continue
        if np.mean(heights >= -2 * tolerance) < 0.90:
            continue
        # Prefer a well-supported floor whose other points lie above it.
        score = support * np.mean(heights >= -2 * tolerance)
        if best is None or score > best[0]:
            best = (score, inliers)
    if best is None:
        floor_height = float(np.quantile(sample @ first_camera_up, 0.05))
        floor_point = first_camera_up * floor_height
        return (first_camera_up.tolist(),
                'first camera; approximate floor from lower 5% of points', floor_point.tolist())

    floor = sample[best[1]]
    center = floor.mean(axis=0)
    _, _, basis = np.linalg.svd(floor - center, full_matrices=False)
    normal = basis[-1]
    if normal @ first_camera_up < 0:
        normal = -normal
    camera_above = float(np.mean((camera_centers - center) @ normal > tolerance))
    return normal.tolist(), (f'floor plane: {len(floor):,}/{len(sample):,} sampled points; '
                           f'{camera_above:.0%} cameras above'), center.tolist()

