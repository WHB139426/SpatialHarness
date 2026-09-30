"""Combine the first-person and overhead Blender renders into one PNG."""

from array import array

import bpy


def stitch_views(left_path, right_path, output_path):
    left = bpy.data.images.load(str(left_path), check_existing=False)
    right = bpy.data.images.load(str(right_path), check_existing=False)
    combined = None
    try:
        if left.size[:] != right.size[:]:
            raise ValueError('First-person and overhead renders have different sizes')
        width, height = left.size
        row = width * 4
        left_pixels = array('f', [0]) * (row * height)
        right_pixels = array('f', [0]) * (row * height)
        left.pixels.foreach_get(left_pixels)
        right.pixels.foreach_get(right_pixels)
        pixels = array('f', [0]) * (row * 2 * height)
        for y in range(height):
            source = y * row
            target = y * row * 2
            pixels[target:target + row] = left_pixels[source:source + row]
            pixels[target + row:target + 2 * row] = right_pixels[source:source + row]
        combined = bpy.data.images.new('First-person and overhead',
                                       width=width * 2, height=height, alpha=True)
        combined.pixels.foreach_set(pixels)
        combined.filepath_raw = str(output_path)
        combined.file_format = 'PNG'
        combined.save()
    finally:
        for image in (left, right, combined):
            if image is not None:
                bpy.data.images.remove(image)
