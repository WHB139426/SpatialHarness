"""Import PLY geometry and configure Blender's CPU renderer."""


def create_scene(source, args):
    import bpy
    from mathutils import Vector

    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.wm.ply_import(filepath=str(source), import_colors='SRGB')
    meshes = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    if not meshes:
        raise RuntimeError('PLY contains no mesh')
    point_nodes = []
    for obj in meshes:
        is_points = len(obj.data.polygons) == 0
        mat = bpy.data.materials.new('ScanColor')
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        nodes.clear()
        surface = nodes.new('ShaderNodeOutputMaterial')
        emission = nodes.new('ShaderNodeEmission')
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
        else:
            emission.inputs['Color'].default_value = (0.6, 0.6, 0.6, 1)
        mat.node_tree.links.new(emission.outputs[0], surface.inputs['Surface'])
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
    if extent <= 0:
        raise RuntimeError('Mesh has zero extent')
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.data.type = 'PERSP'
    camera.data.sensor_fit = 'HORIZONTAL'
    # run_session sets the first-person intrinsics from vggt_cameras.json.
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
