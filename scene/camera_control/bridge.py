"""Sequential JSON camera requests between ordinary Python and Blender."""

import json
import os
from pathlib import Path
import select
import subprocess
import sys


class CameraClient:
    """Own a Blender worker; receive responses separately from its logs."""

    def __init__(self, command, *, log_path, timeout):
        self.log_path = Path(log_path)
        self.timeout = timeout
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        read_fd, write_fd = os.pipe()
        try:
            with self.log_path.open('a') as log:
                self.process = subprocess.Popen(
                    [*command, '--response-fd', str(write_fd)],
                    stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                    text=True, encoding='utf-8', bufsize=1, pass_fds=(write_fd,),
                )
        except BaseException:
            os.close(read_fd)
            raise
        finally:
            os.close(write_fd)
        self.responses = os.fdopen(read_fd, encoding='utf-8')
        try:
            self.initial_state = self._read_result()
        except BaseException:
            self._stop()
            raise

    def _read_result(self):
        try:
            if not select.select([self.responses], [], [], self.timeout)[0]:
                raise TimeoutError(f'Blender response timed out; log: {self.log_path}')
            line = self.responses.readline()
            if not line:
                raise RuntimeError(f'Blender response pipe closed; log: {self.log_path}')
            response = json.loads(line)
            success = response['ok']
            result = response['result'] if success else response['error']
        except BaseException:
            # A lost response would make subsequent requests ambiguous.
            self._stop()
            raise
        if not success:
            raise RuntimeError(f'{result}; log: {self.log_path}')
        return result

    def _request(self, operation, **params):
        request = json.dumps({'op': operation, 'params': params}, allow_nan=False)
        try:
            self.process.stdin.write(request + '\n')
            self.process.stdin.flush()
        except (OSError, ValueError) as exc:
            self._stop()
            raise RuntimeError(f'Cannot send camera request; log: {self.log_path}') from exc
        return self._read_result()

    def observe(self):
        return self._request('observe')

    def execute(self, key, magnitude=None):
        return self._request('execute', key=key, magnitude=magnitude)

    def status(self):
        return self._request('status')

    def reset(self):
        return self._request('reset')

    def set_target(self, observation_id, point, look_at=None):
        return self._request('set_target', observation_id=observation_id, point=point, look_at=look_at)

    def set_route(self, observation_id, points):
        return self._request('set_route', observation_id=observation_id, points=points)

    def _stop(self):
        try:
            self.process.stdin.close()
        except BrokenPipeError:
            pass  # Closing may flush a buffered request after the worker exits.
        self.responses.close()
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()

    def close(self):
        try:
            if self.process.poll() is None:
                self._request('close')
            self.process.wait(timeout=self.timeout)
        finally:
            self._stop()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is None:
            self.close()
        else:
            self._stop()


def serve_camera(session, response_fd):
    """Dispatch requests to an initialized CameraSession in the Blender worker."""
    methods = {
        'observe': session.observe,
        'execute': session.execute,
        'status': session.status,
        'reset': session.reset,
        'set_target': session.set_target,
        'set_route': session.set_route,
        'close': lambda: None,
    }
    with os.fdopen(response_fd, 'w', encoding='utf-8', buffering=1) as responses:
        responses.write(json.dumps({'ok': True, 'result': session.status()}) + '\n')
        for line in sys.stdin:
            closing = False
            try:
                request = json.loads(line)
                result = methods[request['op']](**request.get('params', {}))
                reply = json.dumps({'ok': True, 'result': result})
                closing = request['op'] == 'close'
            except Exception as exc:
                reply = json.dumps({'ok': False, 'error': f'{type(exc).__name__}: {exc}'})
            responses.write(reply + '\n')
            if closing:
                break
    return 0
