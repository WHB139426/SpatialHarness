"""Initialize Blender geometry, materials, scene orientation and camera intrinsics."""

from pathlib import Path
from statistics import median


def emission_material(name, color, strength=1):
    import bpy

    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new('ShaderNodeOutputMaterial')
    emission = nodes.new('ShaderNodeEmission')
    emission.inputs['Color'].default_value = (*color, 1)
    emission.inputs['Strength'].default_value = strength
    material.node_tree.links.new(emission.outputs[0], output.inputs['Surface'])
    return material


def create_scene(source, args):
    import bpy
    from mathutils import Vector

    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.wm.ply_import(filepath=str(source), import_colors='SRGB')
    meshes = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    point_nodes = []
    for obj in meshes:
        is_points = len(obj.data.polygons) == 0
        mat = emission_material('ScanColor', (0.6, 0.6, 0.6))
        nodes = mat.node_tree.nodes
        emission = nodes['Emission']
        colors = obj.data.color_attributes
        if colors:
            color_name = (colors.active_color or colors[0]).name
            if is_points:
                color = nodes.new('ShaderNodeAttribute')
                color.attribute_name = color_name
            else:
                color = nodes.new('ShaderNodeVertexColor')
                color.layer_name = color_name
            mat.node_tree.links.new(color.outputs['Color'], emission.inputs['Color'])
        obj.data.materials.clear()
        obj.data.materials.append(mat)
        if is_points:
            # Cycles renders point-cloud primitives directly: no per-point mesh copies.
            group = bpy.data.node_groups.new('PLY_RenderPoints', 'GeometryNodeTree')
            group.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
            group.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
            input_node = group.nodes.new('NodeGroupInput')
            output_node = group.nodes.new('NodeGroupOutput')
            points = group.nodes.new('GeometryNodeMeshToPoints')
            points.mode = 'VERTICES'
            material = group.nodes.new('GeometryNodeSetMaterial')
            material.inputs['Material'].default_value = mat
            group.links.new(input_node.outputs['Geometry'], points.inputs['Mesh'])
            group.links.new(points.outputs['Points'], material.inputs['Geometry'])
            group.links.new(material.outputs['Geometry'], output_node.inputs['Geometry'])
            modifier = obj.modifiers.new('Render Point Cloud', 'NODES')
            modifier.node_group = group
            point_nodes.append(points)
    corners = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    low = Vector([min(c[i] for c in corners) for i in range(3)])
    high = Vector([max(c[i] for c in corners) for i in range(3)])
    center = (low + high) / 2
    extent = (high - low).length
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = 'PERSP'
    # SceneRenderer sets the first-person intrinsics from vggt_cameras.json.
    camera.data.clip_start = 0.001
    scene = bpy.context.scene
    scene.camera = camera
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = False
    scene.render.threads_mode = 'FIXED'
    scene.render.threads = 8
    scene.render.resolution_x = scene.render.resolution_y = args.resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.film_transparent = True
    scene.view_settings.view_transform = 'Standard'
    return meshes, point_nodes, corners, center, extent, camera, scene


def estimate_scene_up(meshes, cameras, extent):
    """Return up, description, and a floor point; use a low-point estimate if no plane fits."""
    import numpy as np

    extrinsics = np.asarray([c['extrinsic'] for c in cameras], dtype=np.float64)
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


def configure_first_person(camera, cameras, cameras_path, panel_width):
    """Keep the video focal lengths while extending its view to a square frame."""
    import bpy

    source_path = Path(cameras_path).parent / cameras[0]['image_path']
    source = bpy.data.images.load(str(source_path), check_existing=False)
    try:
        source_width, source_height = source.size
    finally:
        bpy.data.images.remove(source)

    fx_norm = median(frame['intrinsic'][0][0] / frame['W'] for frame in cameras)
    fy_norm = median(frame['intrinsic'][1][1] / frame['H'] for frame in cameras)
    cx_norm = median(frame['intrinsic'][0][2] / frame['W'] for frame in cameras)
    cy_norm = median(frame['intrinsic'][1][2] / frame['H'] for frame in cameras)

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


def initial_camera_pose(extrinsic, up, floor_normal, floor_point, eye_height):
    """Project the first camera onto the floor along up, then rise by eye_height."""
    from mathutils import Matrix, Vector

    pose = Matrix(extrinsic).inverted()
    position = pose.translation
    direction = pose.to_3x3() @ Vector((0, 0, 1))
    alignment = up.dot(floor_normal)
    if alignment <= 0:
        raise ValueError('Scene up must point away from the estimated floor')
    position += up * (eye_height - (position - floor_point).dot(floor_normal) / alignment)
    return position, direction
