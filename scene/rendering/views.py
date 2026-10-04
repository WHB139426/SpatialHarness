"""Create the overhead view, camera marker, crosshair and view labels."""

import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

from .scene import emission_material


def _mesh(name, vertices, faces, material, parent):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    obj.data.materials.append(material)
    return obj


class OverheadView:
    def __init__(self, scene, corners, center, up):
        self.scene = scene
        self.corners = corners
        self.center = center
        self.up = up.normalized()
        reference = Vector((1, 0, 0)) if abs(self.up.x) < .99 else Vector((0, 1, 0))
        self.right = (reference - self.up * reference.dot(self.up)).normalized()
        self.screen_up = self.up.cross(self.right).normalized()

        data = bpy.data.cameras.new('Overhead map camera')
        data.type = 'ORTHO'
        data.clip_start = .001
        camera = bpy.data.objects.new('Overhead map camera', data)
        bpy.context.collection.objects.link(camera)
        camera.rotation_euler = Matrix((self.right, self.screen_up, self.up)).transposed().to_euler()
        self.camera = camera

        self.marker = bpy.data.objects.new('First-person position and heading', None)
        bpy.context.collection.objects.link(self.marker)
        self.marker.parent = camera
        orange = emission_material('Overhead position orange', (1, .42, .02), strength=2)
        cyan = emission_material('Overhead direction cyan', (.02, .85, 1), strength=2)
        segments = 24
        disk = [(0, 0, 0)] + [
            (.3 * math.cos(2 * math.pi * i / segments),
             .3 * math.sin(2 * math.pi * i / segments), 0)
            for i in range(segments)]
        _mesh('First-person position', disk,
              [(0, i + 1, (i + 1) % segments + 1) for i in range(segments)],
              orange, self.marker)
        _mesh('First-person heading',
              [(-.13, .08, 0), (.13, .08, 0), (.13, .9, 0),
               (.45, .9, 0), (0, 1.55, 0), (-.45, .9, 0), (-.13, .9, 0)],
              [(0, 1, 2, 3, 4, 5, 6)], cyan, self.marker)
        self.marker.hide_render = True

    def update(self, position, forward):
        """Frame the whole cloud and project the first-person pose onto its map."""
        points = list(self.corners) + [position]
        horizontal = [(p - self.center).dot(self.right) for p in points]
        vertical = [(p - self.center).dot(self.screen_up) for p in points]
        x_mid = (min(horizontal) + max(horizontal)) / 2
        y_mid = (min(vertical) + max(vertical)) / 2
        span = max(max(horizontal) - min(horizontal),
                   max(vertical) - min(vertical), .01)
        self.camera.data.ortho_scale = span * 1.25
        self.camera.location = (self.center + self.right * x_mid
                                + self.screen_up * y_mid + self.up * (span * 2 + 1))
        self.camera.data.clip_end = span * 5 + 10

        x = (position - self.center).dot(self.right) - x_mid
        y = (position - self.center).dot(self.screen_up) - y_mid
        self.marker.location = (x, y, -.05)
        scale = self.camera.data.ortho_scale * .025
        self.marker.scale = (scale, scale, scale)
        heading_x = forward.dot(self.right)
        heading_y = forward.dot(self.screen_up)
        self.marker.rotation_euler.z = math.atan2(-heading_x, heading_y)


def create_crosshair(camera, scene):
    depth = max(0.08, camera.data.clip_start * 10)
    root = bpy.data.objects.new('First-person crosshair', None)
    scene.collection.objects.link(root)
    root.parent = camera
    root.location = (0, 0, -depth)
    # Local x/y units become fractions of the rendered image width.
    scale = depth * camera.data.sensor_width / camera.data.lens
    root.scale = (scale,) * 3

    gap, end = .006, .018
    arms = [((-end, 0, 0), (-gap, 0, 0)),
            ((gap, 0, 0), (end, 0, 0)),
            ((0, -end, 0), (0, -gap, 0)),
            ((0, gap, 0), (0, end, 0))]

    def strokes(name, color, thickness):
        curve = bpy.data.curves.new(name, 'CURVE')
        curve.dimensions = '3D'
        curve.bevel_depth = thickness
        curve.bevel_resolution = 2
        for start, finish in arms:
            spline = curve.splines.new('POLY')
            spline.points.add(1)
            spline.points[0].co = (*start, 1)
            spline.points[1].co = (*finish, 1)
        curve.materials.append(emission_material(name, color))
        obj = bpy.data.objects.new(name, curve)
        scene.collection.objects.link(obj)
        obj.parent = root
        if name == 'Crosshair white strokes':
            obj.location.z = .01  # Put white closer to the camera than its outline.
        for prop in ('visible_shadow', 'visible_diffuse', 'visible_glossy',
                     'visible_transmission', 'visible_volume_scatter'):
            setattr(obj, prop, False)

    strokes('Crosshair dark outline', (0.005, 0.005, 0.005), .0027)
    strokes('Crosshair white strokes', (1, 1, 1), .0015)
    return root


class ViewLabel:
    def __init__(self, camera, scene, title):
        self.root = bpy.data.objects.new(f'{title} label', None)
        scene.collection.objects.link(self.root)
        self.root.parent = camera

        letters = bpy.data.curves.new(f'{title} text', 'FONT')
        letters.body = title
        letters.size = .055
        letters.materials.append(emission_material(f'{title} white text', (1, 1, 1)))
        font_file = Path(__file__).resolve().parents[2] / 'assets' / 'fonts' / 'DejaVuSans-Bold.ttf'
        letters.font = bpy.data.fonts.load(str(font_file), check_existing=True)
        text = bpy.data.objects.new(f'{title} text', letters)
        scene.collection.objects.link(text)
        text.parent = self.root
        text.location.z = .001  # Closer to the camera than the panel.
        bpy.context.view_layer.update()

        right = text.dimensions.x + .012
        top = max(.038, text.dimensions.y + .008)
        background = bpy.data.meshes.new(f'{title} label background')
        background.from_pydata(
            [(-.008, -.010, 0), (right, -.010, 0),
             (right, top, 0), (-.008, top, 0)],
            [], [(0, 1, 2, 3)])
        background.update()
        background.materials.append(emission_material(f'{title} dark background', (.012, .012, .012)))
        panel = bpy.data.objects.new(f'{title} label background', background)
        scene.collection.objects.link(panel)
        panel.parent = self.root

    def update(self, frame_width, depth):
        self.root.location = (-.47 * frame_width, .43 * frame_width, -depth)
        self.root.scale = (frame_width,) * 3
