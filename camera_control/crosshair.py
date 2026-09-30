"""A small, camera-fixed crosshair for first-person renders."""

import bpy


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
        material = bpy.data.materials.new(name)
        material.use_nodes = True
        nodes = material.node_tree.nodes
        nodes.clear()
        emission = nodes.new('ShaderNodeEmission')
        emission.inputs['Color'].default_value = (*color, 1)
        output = nodes.new('ShaderNodeOutputMaterial')
        material.node_tree.links.new(emission.outputs[0], output.inputs['Surface'])

        curve = bpy.data.curves.new(name, 'CURVE')
        curve.dimensions = '3D'
        curve.bevel_depth = thickness
        curve.bevel_resolution = 2
        for start, finish in arms:
            spline = curve.splines.new('POLY')
            spline.points.add(1)
            spline.points[0].co = (*start, 1)
            spline.points[1].co = (*finish, 1)
        curve.materials.append(material)
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
