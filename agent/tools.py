"""Camera tools and internal media attachments for a running camera client."""

import mimetypes
from pathlib import Path

from .types import Tool, ToolOutput


def _view_media(path: str) -> ToolOutput:
    media_path = Path(path).expanduser().resolve(strict=True)
    if not media_path.is_file():
        raise ValueError(f"media path is not a file: {media_path}")
    mime_type = mimetypes.guess_type(media_path)[0] or ""
    if mime_type.startswith("image/"):
        content_type = "image_url"
    elif mime_type.startswith("video/"):
        content_type = "video_url"
    else:
        raise ValueError(f"unsupported media type: {mime_type or media_path.suffix}")
    return ToolOutput(
        value={"path": str(media_path), "mime_type": mime_type, "attached": True},
        messages=({
            "role": "user",
            "content": [{"type": content_type, content_type: {"url": media_path.as_uri()}}],
        },),
    )


def _observation(record) -> ToolOutput:
    content = []
    for view, tag in (('first_person', 'first_person_view'), ('top_down', 'top_down_view'),
                      ('nearest_video_frame', 'nearest_video_frame')):
        content.append({'type': 'text', 'text': f'<{tag}>'})
        content.extend(_view_media(record['images'][view]).messages[0]['content'])
        content.append({'type': 'text', 'text': f'</{tag}>'})
    content.append({'type': 'text', 'text': (
        'The first-person and top-down images show the current camera state. '
        'The nearest video frame is a captured reference matched to the current camera pose; '
        'it is not an exact view from the current camera. '
        'On the top-down map, the large cyan dot and wide cyan arrow with white borders and dark outlines '
        'mark the current camera position and forward heading; the arrow is labeled w. '
        'These current-camera markers appear above the planned route, target, and movement history. '
        'Green j and l arcs show left (counterclockwise) and right (clockwise) turns. '
        'The letters stay upright as the heading rotates; these markers show directions, not distances or turn angles. '
        'The top-down map also shows this session\'s movement history. '
        'Magenta lines and arrows show horizontal travel; yellow dots mark path starts. '
        'Reset starts a disconnected segment. Map framing includes historical positions and planning markers and may change between observations.'
        ' Red G marks the planned camera destination; red LOOK and its arrow mark the desired facing point. '
        'Numbered blue points and dashed lines show the planned route, not past movement. '
        f'For map annotations, use observation_id={record["observation_id"]} and normalized [x, y] '
        'coordinates on this top-down image only: top-left [0, 0], bottom-right [1, 1].'
    )})
    return ToolOutput(value=record, messages=({'role': 'user', 'content': content},))


def create_tools(camera, *, distance_units='scene units (approximately meters with metric scaling)',
                 move_step=None, look_step=None) -> list[Tool]:
    """Bind environment tools to one CameraClient without owning its lifecycle."""
    action_keys = [*'wjlik', 'undo']
    defaults = ''
    if move_step is not None:
        defaults += f'Default forward step: {move_step:g} {distance_units}. '
    if look_step is not None:
        defaults += f'Default turn and look step: {look_step:g} degrees. '

    def camera_action(key: str, magnitude: float | None = None) -> ToolOutput:
        if key not in action_keys:
            raise ValueError(f'Unsupported camera key: {key!r}; allowed keys: w, j, l, i, k, undo')
        return _observation(camera.execute(key, magnitude))

    no_arguments = {'type': 'object', 'properties': {}, 'additionalProperties': False}
    map_point = {
        'type': 'array', 'items': {'type': 'number', 'minimum': 0, 'maximum': 1},
        'minItems': 2, 'maxItems': 2,
    }
    observation_id = {
        'type': 'integer', 'minimum': 1,
        'description': 'observation_id from the latest rendered observation. Older observations are rejected.',
    }
    return [
        Tool(
            name='camera_action',
            description=(
                'Execute one camera action and return the updated state and three separate images: '
                'first-person view, top-down map with movement history, and matched reference video frame. '
                'Useful, for example, for approaching a location, inspecting an object from another viewpoint, or adjusting viewing direction. '
                'Use undo, for example, to undo an accidental move or turn or restore a previous clearer viewpoint. '
                'All actions apply to the current first-person camera. '
                "Interpret directional keys from that camera's perspective, not the top-down "
                'image axes or the reference video frame. '
                "w: move forward; j: turn toward the camera's own left; l: turn toward its own right; "
                'i: tilt the view up; k: tilt the view down; '
                'undo: restore the full camera state before the latest successful non-undo action. '
                'Undo is single-use and does not accept a magnitude. '
                'Observations, status queries, and planning do not replace the undo backup. '
                'Successful undo or reset clears it; failed actions, undo, or reset preserve it. '
                'Undo retains planning markers and movement history, recording any return movement. '
                'To move sideways or return to an earlier position, turn toward it first, then use w. '
                "Horizontal movement is relative to the current first-person camera's horizontal heading, "
                'so the forward direction changes after turning. Forward movement preserves height, regardless of pitch. '
                'Pitch is limited to -89.9 through 89.9 degrees. '
                + defaults
            ),
            parameters={
                'type': 'object',
                'properties': {
                    'key': {
                        'type': 'string', 'enum': action_keys,
                        'description': 'One camera key or undo. Pass magnitude separately; omit it for undo. Do not pass a key sequence or a combined command such as w0.3.',
                    },
                    'magnitude': {
                        'type': 'number', 'exclusiveMinimum': 0,
                        'description': (
                            f'Optional positive finite distance for w in {distance_units}, or angle in degrees '
                            'for j/l/i/k. Omit to use the configured step. Not accepted for undo.'
                        ),
                    },
                },
                'required': ['key'],
                'additionalProperties': False,
            },
            function=camera_action,
        ),
        Tool(
            name='camera_observe',
            description=('Render the current camera pose and return its state and three separate images: '
                         'first-person view, top-down map with movement history, and matched reference video frame. '
                         'Useful, for example, for inspecting the initial scene or reviewing the current view without moving.'),
            parameters=no_arguments,
            function=lambda: _observation(camera.observe()),
        ),
        Tool(
            name='camera_status',
            description=('Return camera position, yaw, pitch and point radius without rendering. '
                         'Useful, for example, for checking the current pose or confirming an angle without requesting images.'),
            parameters=no_arguments,
            function=camera.status,
        ),
        Tool(
            name='camera_reset',
            description=('Restore the initial camera pose and point radius; return state and three separate images. '
                         'Retain old trajectories and planning markers; start a disconnected path segment at the initial position. '
                         'Clear the undo backup after a successful reset. '
                         'Useful, for example, for returning to the starting viewpoint or beginning a new task from the initial pose.'),
            parameters=no_arguments,
            function=lambda: _observation(camera.reset()),
        ),
        Tool(
            name='camera_set_target',
            description=(
                'Mark a camera destination on the top-down map only, without moving or turning the camera. '
                'Useful, for example, for keeping a destination in view, selecting a useful observation position, or recording a desired viewing direction. '
                'Use normalized [x, y] coordinates on the latest top-down image: '
                '[0, 0] is top-left and [1, 1] is bottom-right. '
                'point is where the camera should stand; optional look_at is the object or location it should face. '
                'Draw a red G at the destination and a red LOOK facing marker. '
                'Replace the previous target and clear its old planned route. Set point=null to clear the whole plan. '
                'Markers persist through movement, observation, and reset. Return an updated three-image observation.'
            ),
            parameters={
                'type': 'object',
                'properties': {
                    'observation_id': observation_id,
                    'point': {**map_point, 'type': ['array', 'null']},
                    'look_at': {**map_point, 'type': ['array', 'null']},
                },
                'required': ['observation_id', 'point'], 'additionalProperties': False,
            },
            function=lambda observation_id, point, look_at=None: _observation(
                camera.set_target(observation_id, point, look_at)),
        ),
        Tool(
            name='camera_set_route',
            description=(
                'Draw or replace a planned route on the top-down map only, without executing any movement. '
                'Useful, for example, for organizing exploration, planning a sequence of viewpoints, or comparing possible paths. '
                'Before planning a route, it is usually recommended to set the destination with camera_set_target first. '
                'Plan every route segment through visibly open floor space and clear passageways, '
                'leaving clearance from walls, partitions, furniture, and fixtures instead of cutting through them. '
                'Missing point-cloud geometry does not prove a passage is clear; check the current first-person view when uncertain. '
                'points is an ordered list of future waypoints, including the final destination, in normalized '
                '[x, y] coordinates on the latest top-down image: top-left [0, 0], bottom-right [1, 1]. '
                'The current camera position is prepended automatically as the route start. '
                'Draw numbered blue waypoints and dashed blue lines. Pass points=[] to clear only the route. '
                'The route persists in scene coordinates through movement, map reframing, and reset; '
                'it is a visual plan, not a collision check or an automatic path follower. '
                'Return an updated three-image observation.'
            ),
            parameters={
                'type': 'object',
                'properties': {
                    'observation_id': observation_id,
                    'points': {'type': 'array', 'items': map_point},
                },
                'required': ['observation_id', 'points'], 'additionalProperties': False,
            },
            function=lambda observation_id, points: _observation(camera.set_route(observation_id, points)),
        ),
    ]
