"""Blender scene setup, per-action rendering, and the interactive prompt."""

import contextlib
import copy
import json
import os
import sys


@contextlib.contextmanager
def render_log(path):
    """Keep Blender progress in a log while leaving the prompt readable."""
    sys.stdout.flush()
    sys.stderr.flush()
    saved = [os.dup(1), os.dup(2)]
    try:
        with open(path, 'a', buffering=1) as log:
            os.dup2(log.fileno(), 1)
            os.dup2(log.fileno(), 2)
            yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        for descriptor, backup in zip((1, 2), saved):
            os.dup2(backup, descriptor)
            os.close(backup)


def run_session(args, source, cameras_path, output, help_text, fallback_up,
                move_step, look_step, point_step, eye_height):
    import bpy
    from mathutils import Matrix, Vector

    from camera_control.actions import parse_actions
    from camera_control.crosshair import create_crosshair
    from camera_control.estimate_up import estimate_scene_up
    from camera_control.intrinsics import configure_first_person
    from camera_control.navigation import Navigator
    from camera_control.overhead import OverheadView
    from camera_control.reference_frame import nearest_frame
    from camera_control.scene import create_scene
    from camera_control.stitch import stitch_views
    from camera_control.view_label import ViewLabel

    log_path = output / 'render.log'
    print(f'Loading PLY: {source}\nSession: {output}', flush=True)
    with render_log(log_path):
        meshes, point_nodes, corners, center, extent, camera, scene = create_scene(source, args)

    radius = args.point_radius if point_nodes else None
    print(f'Geometry: {sum(len(o.data.vertices) for o in meshes):,} vertices, '
          f'{sum(len(o.data.polygons) for o in meshes):,} faces; '
          f'point-cloud objects: {len(point_nodes)}', flush=True)
    try:
        estimated_up, up_source, floor_point = estimate_scene_up(meshes, cameras_path, extent)
        floor_normal = Vector(estimated_up).normalized()
        floor_point = Vector(floor_point)
    except (OSError, ValueError, KeyError, ArithmeticError) as exc:
        estimated_up, up_source = fallback_up, f'fallback; floor estimation failed: {exc}'
        floor_normal = Vector(args.up or fallback_up).normalized()
        floor_point = floor_normal * min(c.dot(floor_normal) for c in corners)
    up = Vector(args.up if args.up is not None else estimated_up).normalized()
    print('Scene up:', list(up), f'({up_source})', flush=True)
    cameras = json.loads(cameras_path.read_text(encoding='utf-8'))
    intrinsics = configure_first_person(camera, cameras, cameras_path, args.resolution)
    print('First-person intrinsics:', json.dumps(intrinsics), flush=True)
    first_pose = Matrix(cameras[0]['extrinsic']).inverted()
    position = first_pose.translation.copy()
    direction = first_pose.to_3x3() @ Vector((0, 0, 1))
    alignment = up.dot(floor_normal)
    if alignment <= 0.1:
        raise ValueError('Scene up must point away from the estimated floor')
    position += up * (eye_height - (position - floor_point).dot(floor_normal) / alignment)
    print(f'Initial eye height: {eye_height:g} scene units above estimated floor', flush=True)
    navigator = Navigator(camera, point_nodes, center, extent, up,
                          radius, move_step, look_step, point_step, position, direction)
    state = copy.deepcopy(navigator.initial)
    overhead = OverheadView(scene, corners, center, up)
    crosshair = create_crosshair(camera, scene)
    overhead_label = ViewLabel(overhead.camera, scene, 'TOP DOWN')
    index = 0

    def show_marker(root, visible):
        for obj in (root, *root.children_recursive):
            obj.hide_render = not visible

    def select_view(mode):
        if mode == 'overhead':
            scene.render.resolution_y = args.resolution
            scene.render.pixel_aspect_y = 1.0
            forward = camera.rotation_euler.to_matrix() @ Vector((0, 0, -1))
            overhead.update(camera.location.copy(), forward)
            overhead_label.update(overhead.camera.data.ortho_scale, .05)
            scene.camera = overhead.camera
            show_marker(overhead.marker, True)
            show_marker(crosshair, False)
            show_marker(overhead_label.root, True)
        else:
            scene.render.resolution_y = intrinsics['height']
            scene.render.pixel_aspect_y = intrinsics['pixel_aspect_y']
            scene.camera = camera
            show_marker(overhead.marker, False)
            show_marker(crosshair, True)
            show_marker(overhead_label.root, False)

    show_marker(crosshair, False)
    show_marker(overhead_label.root, False)

    def render(candidate, command):
        nonlocal index
        navigator.apply(candidate)
        forward = camera.rotation_euler.to_matrix() @ Vector((0, 0, -1))
        match = nearest_frame(cameras, cameras_path, camera.location, forward)
        next_index = index + 1
        action_name = {'+': 'pointsize_plus', '-': 'pointsize_minus'}.get(command, command)
        image_path = output / f'{next_index:04d}_{action_name}.png'
        first_path = output / f'.{next_index:04d}_first.png'
        overhead_path = output / f'.{next_index:04d}_overhead.png'
        print('Rendering first-person, overhead, and nearest video frame...', flush=True)
        try:
            with render_log(log_path):
                for mode, path in (('first_person', first_path), ('overhead', overhead_path)):
                    select_view(mode)
                    bpy.context.view_layer.update()
                    scene.render.filepath = str(path)
                    bpy.ops.render.render(write_still=True)
                stitch_views(first_path, overhead_path, match['image_path'], image_path)
        except Exception:
            navigator.apply(state)
            raise
        finally:
            select_view('first_person')
            first_path.unlink(missing_ok=True)
            overhead_path.unlink(missing_ok=True)
        record = {'command': command, 'views': ['first_person', 'overhead', 'nearest_video_frame'],
                  'layout': 'three_columns', 'state': candidate,
                  'camera_position': list(camera.location), 'camera_forward': list(forward),
                  'lens_mm': camera.data.lens, 'intrinsics': intrinsics,
                  'nearest_frame': match,
                  'image': str(image_path), 'input': str(source)}
        serialized = json.dumps(record, indent=2)
        image_path.with_suffix('.json').write_text(serialized, encoding='utf-8')
        (output / 'state.json').write_text(serialized, encoding='utf-8')
        index = next_index
        print(f'PNG: {image_path}', flush=True)
        print(f'Nearest video frame: {match["image_path"]} '
              f'(frame {match["video_frame_index"]}, '
              f'{match["position_distance"]:.3f} scene units, '
              f'{match["direction_angle_degrees"]:.1f} degrees)', flush=True)
        print('Camera:', json.dumps(candidate), flush=True)

    print(help_text, flush=True)
    render(state, 'initial')
    while True:
        try:
            command = input('camera> ').strip().lower()
        except (EOFError, KeyboardInterrupt):
            print('\nDone. Images saved in:', output, flush=True)
            return 0
        if not command:
            continue
        try:
            if command in ('quit', 'exit'):
                print('Done. Images saved in:', output, flush=True)
                return 0
            if command == 'help':
                print(help_text, flush=True)
                continue
            if command == 'status':
                print(json.dumps(state, indent=2), flush=True)
                continue
            if command == 'reset':
                candidate = copy.deepcopy(navigator.initial)
                render(candidate, command)
                state = candidate
                continue
            actions = parse_actions(command)
            if len(actions) > 1:
                print('Sequence:', ' '.join(label for _, _, label in actions), flush=True)
            for key, magnitude, label in actions:
                candidate = navigator.step(state, key, magnitude)
                render(candidate, label)
                state = candidate
        except (ValueError, RuntimeError, OSError) as exc:
            print(f'Error: {exc}\nRender log: {log_path}', flush=True)
