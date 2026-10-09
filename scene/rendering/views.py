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
        cyan = emission_material('Overhead camera cyan', (0, 1, 1))
        white = emission_material('Overhead camera white outline', (1, 1, 1))
        green = emission_material('Overhead rotation green', (.16, 1, .42))
        dark = emission_material('Overhead movement label background', (.012, .012, .012))
        segments = 32
        for name, radius, depth, material in (
                ('outline', .52, .003, dark), ('border', .44, .004, white),
                ('', .36, .005, cyan)):
            disk = [(0, 0, depth)] + [
                (radius * math.cos(2 * math.pi * i / segments),
                 radius * math.sin(2 * math.pi * i / segments), depth)
                for i in range(segments)]
            _mesh(f'First-person position {name}'.rstrip(), disk,
                  [(0, i + 1, (i + 1) % segments + 1) for i in range(segments)],
                  material, self.marker)
        self.marker_labels = []
        font_file = Path(__file__).resolve().parents[2] / 'assets' / 'fonts' / 'DejaVuSans-Bold.ttf'
        font = bpy.data.fonts.load(str(font_file), check_existing=True)
        self.font = font
        for name, head, shaft, base, shoulder, tip, depth, material in (
                ('outline', .58, .27, .26, 1.42, 2.12, 0, dark),
                ('border', .48, .20, .30, 1.45, 2.02, .001, white),
                ('', .38, .14, .34, 1.48, 1.92, .002, cyan)):
            _mesh(f'Movement w arrow {name}'.rstrip(),
                  [(-head, shoulder, depth), (head, shoulder, depth), (0, tip, depth),
                   (-shaft, base, depth), (shaft, base, depth),
                   (shaft, shoulder, depth), (-shaft, shoulder, depth)],
                  [(0, 1, 2), (3, 4, 5, 6)], material, self.marker)
        labels = [('w', Vector((0, 2.75, .006)), cyan)]

        for key, start, end, sign in (('j', 100, 155, 1), ('l', 80, 25, -1)):
            radius, width, segments = 2.6, .10, 32
            angles = [math.radians(start + (end - start) * i / segments)
                      for i in range(segments + 1)]
            vertices = [(r * math.cos(angle), r * math.sin(angle), 0)
                        for angle in angles for r in (radius - width / 2, radius + width / 2)]
            _mesh(f'Rotation {key} arc', vertices,
                  [(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(segments)],
                  green, self.marker)
            angle = angles[-1]
            end = Vector((radius * math.cos(angle), radius * math.sin(angle), 0))
            tangent = Vector((-math.sin(angle), math.cos(angle), 0)) * sign
            side = Vector((-tangent.y, tangent.x, 0)) * .22
            _mesh(f'Rotation {key} arrow',
                  [end + tangent * .25, end - tangent * .18 + side, end - tangent * .18 - side],
                  [(0, 1, 2)], green, self.marker)
            labels.append((key, Vector((-2.65 if key == 'j' else 2.65, 2.3, .006)), green))

        for key, position, material in labels:
            letters = bpy.data.curves.new(f'Marker {key} text', 'FONT')
            letters.body = key
            letters.font = font
            letters.size = 1.2
            letters.align_x = letters.align_y = 'CENTER'
            letters.materials.append(material)
            label = bpy.data.objects.new(f'Marker {key} text', letters)
            scene.collection.objects.link(label)
            label.parent = self.marker
            label.location = position
            self.marker_labels.append(label)
            _mesh(f'Marker {key} label background',
                  [(-.66, -.57, -.001), (.66, -.57, -.001),
                   (.66, .57, -.001), (-.66, .57, -.001)],
                  [(0, 1, 2, 3)], dark, label)
        self.marker.hide_render = True
        self.trajectory = _mesh('Camera trajectory', [], [],
                                emission_material('Trajectory magenta', (1, .12, .65)), camera)
        self.trajectory.data.materials.append(emission_material('Trajectory start yellow', (1, .85, .04)))
        self.trajectory.location.z = -.06
        self.trajectory.hide_render = True
        self.plan = _mesh('Navigation plan', [], [],
                          emission_material('Plan route blue', (.08, .32, 1), strength=2), camera)
        self.plan.data.materials.append(emission_material('Plan target red', (1, .08, .04), strength=2))
        self.plan.location.z = -.04
        self.plan.hide_render = True
        self.plan_labels = []
        self.plan_label_background = dark

    def frame(self):
        center = self.camera.location - self.up * (self.camera.location - self.center).dot(self.up)
        return {'center': list(center), 'span': self.camera.data.ortho_scale}

    def unproject(self, point, frame):
        """Convert a normalized point on a saved map to the scene's horizontal plane."""
        return (Vector(frame['center']) + self.right * ((point[0] - .5) * frame['span'])
                + self.screen_up * ((.5 - point[1]) * frame['span']))

    def project_plan(self, planning):
        def project(point):
            if point is None:
                return None
            delta = Vector(point) - self.camera.location
            span = self.camera.data.ortho_scale
            return [.5 + delta.dot(self.right) / span, .5 - delta.dot(self.screen_up) / span]
        return {'target': project(planning['target']), 'look_at': project(planning['look_at']),
                'route': [project(point) for point in planning['route']]}

    def draw_plan(self, planning):
        """Draw the persistent goal, facing arrow and numbered dashed route on the map only."""
        span = self.camera.data.ortho_scale
        vertices, faces, materials, labels = [], [], [], []

        def project(point):
            delta = Vector(point) - self.camera.location
            return Vector((delta.dot(self.right), delta.dot(self.screen_up), 0))

        def face(points, material):
            index = len(vertices)
            vertices.extend(points)
            faces.append(tuple(range(index, len(vertices))))
            materials.append(material)

        def stroke(start, end, material, width=span * .0025):
            delta = end - start
            if delta.length < 1e-8:
                return
            side = Vector((-delta.y, delta.x, 0)).normalized() * width / 2
            face((start - side, start + side, end + side, end - side), material)

        route = [project(point) for point in planning['route']]
        dash, gap = span * .012, span * .007
        for start, end in zip(route, route[1:]):
            delta = end - start
            if delta.length < 1e-8:
                continue
            direction = delta.normalized()
            distance = 0
            while distance < delta.length:
                stroke(start + direction * distance,
                       start + direction * min(distance + dash, delta.length), 0)
                distance += dash + gap
        radius = span * .008
        for index, point in enumerate(route[1:], 1):
            face([point + Vector((radius * math.cos(i * math.tau / 24),
                                  radius * math.sin(i * math.tau / 24), 0)) for i in range(24)], 0)
            labels.append((str(index), point, 0))
        if planning['target'] is not None:
            target = project(planning['target'])
            radius = span * .014
            ring = [target + Vector((radius * math.cos(i * math.tau / 32),
                                     radius * math.sin(i * math.tau / 32), 0)) for i in range(32)]
            for start, end in zip(ring, ring[1:] + ring[:1]):
                stroke(start, end, 1, span * .004)
            labels.append(('G', target + Vector((span * .025, 0, 0)), 1))
            if planning['look_at'] is not None:
                look = project(planning['look_at'])
                for direction in (Vector((1, 1, 0)), Vector((1, -1, 0))):
                    stroke(look - direction * radius / 2, look + direction * radius / 2, 1)
                delta = look - target
                if delta.length > 1e-8:
                    direction = delta.normalized()
                    side = Vector((-direction.y, direction.x, 0)) * radius * .5
                    stroke(target, look, 1)
                    face((look, look - direction * radius + side, look - direction * radius - side), 1)
                labels.append(('LOOK', look, 1))
        mesh = self.plan.data
        mesh.clear_geometry()
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        for polygon, material in zip(mesh.polygons, materials):
            polygon.material_index = material
        for index, (body, point, material) in enumerate(labels):
            if index == len(self.plan_labels):
                letters = bpy.data.curves.new('Plan label', 'FONT')
                letters.font = self.font
                letters.align_x = letters.align_y = 'CENTER'
                letters.materials.append(self.plan.data.materials[material])
                label = bpy.data.objects.new('Plan label', letters)
                self.scene.collection.objects.link(label)
                label.parent = self.plan
                _mesh('Plan label background', [(-.55, -.6, 0), (.55, -.6, 0),
                                               (.55, .6, 0), (-.55, .6, 0)],
                      [(0, 1, 2, 3)], self.plan_label_background, label)
                self.plan_labels.append(label)
            label = self.plan_labels[index]
            label.data.body = body
            label.data.materials[0] = self.plan.data.materials[material]
            label.location = point + Vector((0, span * .022, .002))
            size = max(span * .018, span * 12 / self.scene.render.resolution_x)
            label.scale = (size,) * 3
            label.children[0].scale.x = len(body)
            label.children[0].location.z = -.001
            label.hide_render = label.children[0].hide_render = False
        self.plan.hide_render = False

    def update(self, position, forward, history=()):
        """Frame the whole cloud and project the first-person pose onto its map."""
        points = list(self.corners) + [position] + [Vector(p) for p in history]
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
        # Put every camera marker element in front of plans (-.04) and history (-.06).
        # Keep depth independent of map scale so large maps cannot clip the marker.
        self.marker.location = (x, y, -.01)
        scale = self.camera.data.ortho_scale * max(.032, 24 / self.scene.render.resolution_x)
        self.marker.scale = (scale, scale, 1)
        heading_x = forward.dot(self.right)
        heading_y = forward.dot(self.screen_up)
        self.marker.rotation_euler.z = math.atan2(-heading_x, heading_y)
        for label in self.marker_labels:
            label.rotation_euler.z = -self.marker.rotation_euler.z

    def draw_trajectory(self, segments):
        """Project each path segment onto the map; never connect across resets."""
        scale = self.camera.data.ortho_scale
        width = scale * max(.002, 1.8 / self.scene.render.resolution_x)
        radius = scale * max(.006, 3.5 / self.scene.render.resolution_x)
        vertices, faces, starts = [], [], []
        for segment in segments:
            points = []
            for position in segment:
                delta = Vector(position) - self.camera.location
                points.append(Vector((delta.dot(self.right), delta.dot(self.screen_up), 0)))
            for start, end in zip(points, points[1:]):
                delta = end - start
                if delta.length < 1e-8:
                    continue  # Vertical movement has no horizontal extent.
                direction = delta.normalized()
                normal = Vector((-direction.y, direction.x, 0))
                side = normal * width / 2
                index = len(vertices)
                vertices.extend((start - side, start + side, end + side, end - side))
                faces.append((index, index + 1, index + 2, index + 3))
                size = min(width * 5, delta.length * .5)
                middle = (start + end) / 2
                index = len(vertices)
                vertices.extend((middle + direction * size / 2,
                                 middle - direction * size / 2 + normal * size * .45,
                                 middle - direction * size / 2 - normal * size * .45))
                faces.append((index, index + 1, index + 2))
            index = len(vertices)
            vertices.extend(points[0] + Vector((radius * math.cos(i * math.tau / 24),
                                               radius * math.sin(i * math.tau / 24), .001))
                            for i in range(24))
            starts.append(len(faces))
            faces.append(tuple(range(index, index + 24)))
        mesh = self.trajectory.data
        mesh.clear_geometry()
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        for index in starts:
            mesh.polygons[index].material_index = 1
        self.trajectory.hide_render = False


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
