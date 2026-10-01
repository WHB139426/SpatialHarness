"""Configure a stable first-person camera from reconstructed video intrinsics."""

import math
from pathlib import Path
from statistics import median


def configure_first_person(camera, cameras, cameras_path, panel_width):
    """Keep the video focal lengths while extending its view to a square frame."""
    import bpy

    if not cameras:
        raise ValueError('Camera JSON contains no frames')
    source_path = Path(cameras_path).parent / cameras[0]['image_path']
    source = bpy.data.images.load(str(source_path), check_existing=False)
    try:
        source_width, source_height = source.size
    finally:
        bpy.data.images.remove(source)
    if source_width <= 0 or source_height <= 0:
        raise ValueError(f'Cannot read source frame dimensions: {source_path}')

    try:
        fx_norm = median(frame['intrinsic'][0][0] / frame['W'] for frame in cameras)
        fy_norm = median(frame['intrinsic'][1][1] / frame['H'] for frame in cameras)
        cx_norm = median(frame['intrinsic'][0][2] / frame['W'] for frame in cameras)
        cy_norm = median(frame['intrinsic'][1][2] / frame['H'] for frame in cameras)
    except (KeyError, IndexError, TypeError, ZeroDivisionError) as exc:
        raise ValueError('Camera JSON has invalid intrinsics') from exc
    if not all(math.isfinite(value) for value in
               (fx_norm, fy_norm, cx_norm, cy_norm)) or fx_norm <= 0 or fy_norm <= 0:
        raise ValueError('Camera JSON has non-finite or non-positive focal lengths')

    width = height = panel_width
    video_height = max(1, round(width * source_height / source_width))
    # Keep the original horizontal field of view and central video projection.
    # Extra rows above and below it expand the view without stretching pixels.
    fx = fx_norm * width
    fy = fy_norm * video_height
    cx = cx_norm * width
    cy = cy_norm * video_height + (height - video_height) / 2
    pixel_aspect_y = fx / fy

    camera.data.sensor_fit = 'HORIZONTAL'
    camera.data.sensor_width = 36.0
    camera.data.lens = camera.data.sensor_width * fx_norm
    camera.data.shift_x = .5 - cx_norm
    camera.data.shift_y = (cy - height / 2) * pixel_aspect_y / width

    return {
        'source': 'median_vggt_cameras',
        'width': width, 'height': height,
        'fx': fx, 'fy': fy, 'cx': cx, 'cy': cy,
        'pixel_aspect_y': pixel_aspect_y,
    }
