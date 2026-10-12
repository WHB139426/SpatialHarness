"""Render three separate observation images and a three-panel preview."""

import contextlib
import copy
import json
import os
from pathlib import Path
import sys

import bpy
from mathutils import Vector

from .reference_frame import nearest_frame
from .scene import configure_first_person, create_scene, estimate_scene_up, initial_camera_pose
from .stitch import stitch_views
from .views import OverheadView, ViewLabel, create_crosshair


@contextlib.contextmanager
def render_log(path):
    """Keep Python and native Blender progress in a log."""
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


class SceneRenderer:
    """Own the scene, view overlays and output files."""

    def __init__(self, args, source, cameras_path, output, *, eye_height):
        self.args = args
        self.source = Path(source)
        self.cameras_path = Path(cameras_path)
        self.output = Path(output)
        self.log_path = self.output / 'render.log'
        self.index = 0
        self.map_frame = None
        print(f'Loading PLY: {self.source}\nSession: {self.output}', flush=True)
        with render_log(self.log_path):
            meshes, self.point_nodes, self.corners, self.center, self.extent, self.camera, self.scene = create_scene(self.source, args)
        print(f'Geometry: {sum(len(obj.data.vertices) for obj in meshes):,} vertices, '
              f'{sum(len(obj.data.polygons) for obj in meshes):,} faces; '
              f'point-cloud objects: {len(self.point_nodes)}', flush=True)
        self.cameras = json.loads(self.cameras_path.read_text(encoding='utf-8'))
        estimated, self.up_source, floor_point = estimate_scene_up(meshes, self.cameras, self.extent)
        floor_normal = Vector(estimated).normalized()
        self.up = Vector(args.up if args.up is not None else estimated).normalized()
        print('Scene up:', list(self.up), f'({self.up_source})', flush=True)
        self.initial_pose = initial_camera_pose(
            self.cameras[0]['extrinsic'], self.up, floor_normal, Vector(floor_point), eye_height,
        )
        print(f'Initial eye height: {eye_height:g} scene units above estimated floor', flush=True)
        self.intrinsics = configure_first_person(self.camera, self.cameras, self.cameras_path, args.resolution)
        print('First-person intrinsics:', json.dumps(self.intrinsics), flush=True)
        self.setup_views()

    def setup_views(self):
        """Create the overhead view and overlays for the configured camera."""
        self.overhead = OverheadView(self.scene, self.corners, self.center, self.up)
        self.crosshair = create_crosshair(self.camera, self.scene)
        self.overhead_label = ViewLabel(self.overhead.camera, self.scene, 'TOP DOWN')

    @contextlib.contextmanager
    def new_session(self, output):
        """Switch files and worker logs to a fresh session; restore them on failure."""
        previous = self.output, self.log_path, self.index, self.map_frame
        sys.stdout.flush()
        sys.stderr.flush()
        saved = [os.dup(1), os.dup(2)]
        try:
            self.output = Path(output)
            self.log_path = self.output / 'render.log'
            self.index = 0
            self.map_frame = None
            with self.log_path.open('a') as log:
                os.dup2(log.fileno(), 1)
                os.dup2(log.fileno(), 2)
            yield
        except BaseException:
            self.output, self.log_path, self.index, self.map_frame = previous
            sys.stdout.flush()
            sys.stderr.flush()
            for descriptor, backup in zip((1, 2), saved):
                os.dup2(backup, descriptor)
            raise
        finally:
            for backup in saved:
                os.close(backup)

    @staticmethod
    def _show(root, visible):
        for obj in (root, *root.children_recursive):
            obj.hide_render = not visible

    def _forward(self):
        return self.camera.rotation_euler.to_matrix() @ Vector((0, 0, -1))

    def _select_view(self, mode, history=()):
        overhead = mode == 'overhead'
        if overhead:
            self.scene.render.resolution_y = self.args.resolution
            self.scene.render.pixel_aspect_y = 1.0
            self.overhead.update(self.camera.location.copy(), self._forward(), history)
            self.overhead_label.update(self.overhead.camera.data.ortho_scale, .05)
            self.scene.camera = self.overhead.camera
        else:
            self.scene.render.resolution_y = self.intrinsics['height']
            self.scene.render.pixel_aspect_y = self.intrinsics['pixel_aspect_y']
            self.scene.camera = self.camera
        self._show(self.overhead.marker, overhead)
        self._show(self.crosshair, not overhead)
        self._show(self.overhead_label.root, overhead)
        self.overhead.trajectory.hide_render = True
        self._show(self.overhead.plan, False)

    def render(self, state, command, segments, planning=None):
        """Capture the current pose and return its saved observation record."""
        forward = self._forward()
        planning = planning or {'target': None, 'look_at': None, 'route': []}
        match = nearest_frame(self.cameras, self.cameras_path, self.camera.location, forward)
        next_index = self.index + 1
        action_name = {'+': 'pointsize_plus', '-': 'pointsize_minus'}.get(command, command)
        image_path = self.output / f'{next_index:04d}_{action_name}.png'
        views_dir = self.output / '.views'
        views_dir.mkdir(exist_ok=True)
        first_path = views_dir / f'{image_path.stem}_first_person.png'
        overhead_path = views_dir / f'{image_path.stem}_top_down.png'
        record_path = image_path.with_suffix('.json')
        state_path = self.output / 'state.json'
        temporary_state = state_path.with_suffix('.json.tmp')
        print('Rendering first-person and top-down with trajectory; matching the reference frame...', flush=True)
        try:
            with render_log(self.log_path):
                for mode, path in (('first_person', first_path), ('overhead', overhead_path)):
                    if mode == 'overhead':
                        positions = [position for segment in segments for position in segment]
                        positions.extend(planning['route'])
                        positions.extend(point for point in (planning['target'], planning['look_at']) if point is not None)
                        self._select_view('overhead', positions)
                        self.overhead.draw_trajectory(segments)
                        self.overhead.draw_plan(planning)
                    else:
                        self._select_view(mode)
                    bpy.context.view_layer.update()
                    self.scene.render.filepath = str(path)
                    bpy.ops.render.render(write_still=True)
                stitch_views(first_path, overhead_path, match['image_path'], image_path)
            record = {
                'observation_id': next_index,
                'command': command, 'views': ['first_person', 'top_down', 'nearest_video_frame'],
                'layout': 'separate_images', 'state': copy.deepcopy(state),
                'camera_position': list(self.camera.location), 'camera_forward': list(forward),
                'lens_mm': self.camera.data.lens, 'intrinsics': self.intrinsics, 'nearest_frame': match,
                'image': str(image_path), 'input': str(self.source),
                'images': {'first_person': str(first_path), 'top_down': str(overhead_path),
                           'nearest_video_frame': match['image_path']},
                'trajectory': {'segment_count': len(segments),
                               'position_count': sum(len(segment) for segment in segments)},
                'planning': self.overhead.project_plan(planning),
            }
            serialized = json.dumps(record, indent=2)
            record_path.write_text(serialized, encoding='utf-8')
            temporary_state.write_text(serialized, encoding='utf-8')
            temporary_state.replace(state_path)
        except BaseException:
            for path in (first_path, overhead_path, image_path, record_path, temporary_state):
                path.unlink(missing_ok=True)
            raise
        finally:
            self._select_view('first_person')
        self.index = next_index
        self.map_frame = self.overhead.frame()
        print(f'PNG: {image_path}', flush=True)
        print(f'Nearest video frame: {match["image_path"]} '
              f'(frame {match["video_frame_index"]}, '
              f'{match["position_distance"]:.3f} scene units, '
              f'{match["direction_angle_degrees"]:.1f} degrees)', flush=True)
        print('Camera:', json.dumps(state), flush=True)
        return record
