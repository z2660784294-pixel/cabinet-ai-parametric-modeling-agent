"""
CLI UI tool: confirm cabinet layout candidates.
Launches a local browser UI. Result written to tmp/cabinet_layout_confirmed.json,
stdout outputs the file path only.
"""
import argparse
import json
import logging
import os
import socket
import sys
import threading
import time
import webbrowser
from urllib.parse import quote, urlparse

from flask import Flask, jsonify, request, send_file, send_from_directory, after_this_request

script_dir = os.path.dirname(os.path.abspath(__file__))
skill_dir = os.path.dirname(script_dir)
workspace_root = os.path.abspath(os.path.join(skill_dir, '..', '..'))

app = Flask(__name__, static_folder=None)

result_data = None
initial_input = None
shutdown_event = threading.Event()

SHUTDOWN_DELAY_SEC = 1.5
POST_SHUTDOWN_GRACE_SEC = 0.5
DEFAULT_OUTPUT = os.path.join('tmp', 'cabinet_layout_confirmed.json')

PROFILE_PATH = os.path.join(workspace_root, 'data', 'param-model-library', 'parammodel_image_profile.json')
PRODUCT_PATH = os.path.join(workspace_root, 'data', 'param-model-library', 'parammodel.json')

SAMPLE_INPUT = {
    'name': '组合',
    'referenceImageUrl': '',
    'description': '三列通高组合柜：左右为单门柜，中间为开放柜。',
    'cabinetSize': {'width': 3000, 'height': 2600},
    'units': [
        {
            'name': '单门柜',
            'obsBrandGoodId': '3FO3JCW4TG2N',
            'candidates': ['3FO3JCVOTRLQ', '3FO3JCW4QRFU'],
            'position': {'x': 0, 'y': 0, 'z': 0},
            'size': {'x': 1050, 'y': 400, 'z': 2600},
            'cells': [{'row': 1, 'column': 1}],
        },
        {
            'name': '开放柜',
            'obsBrandGoodId': '3FO3JCVOSJ5D',
            'candidates': ['3FO3JCVONXN0', '3FO3JCW4TG2N'],
            'position': {'x': 1050, 'y': 0, 'z': 0},
            'size': {'x': 900, 'y': 400, 'z': 2600},
            'cells': [{'row': 1, 'column': 2}],
        },
        {
            'name': '单门柜',
            'obsBrandGoodId': '3FO3JCW4TG2N',
            'candidates': ['3FO3JCVOTRLQ', '3FO3JCW4QRFU'],
            'position': {'x': 1950, 'y': 0, 'z': 0},
            'size': {'x': 1050, 'y': 400, 'z': 2600},
            'cells': [{'row': 1, 'column': 3}],
        },
    ],
}


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def read_json_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def resolve_path(path):
    if not path:
        return None
    if os.path.isabs(path):
        return path
    return os.path.join(workspace_root, path)


def is_remote_or_data_url(url):
    parsed = urlparse(url)
    return parsed.scheme in ('http', 'https', 'data', 'blob')


def is_safe_workspace_path(path):
    resolved = os.path.abspath(path)
    try:
        return os.path.commonpath([workspace_root, resolved]) == workspace_root
    except ValueError:
        return False


def is_supported_image_path(path):
    return os.path.splitext(path)[1].lower() in {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}


def is_allowed_reference_path(path):
    resolved = os.path.abspath(path)
    return os.path.isfile(resolved) and is_supported_image_path(resolved)


def validate_absolute_reference_path(value):
    """referenceImageUrl must be an absolute path to an existing allowed image file."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError('referenceImageUrl is required and must be an absolute file path')
    raw = value.strip()
    if raw.startswith('/workspace-file/') or raw.startswith('/reference-image'):
        return None
    if is_remote_or_data_url(raw):
        raise ValueError(
            'referenceImageUrl must be an absolute file path; '
            'http(s)/data/blob URLs are not supported'
        )
    if not os.path.isabs(raw):
        raise ValueError(
            f'referenceImageUrl must be an absolute path (got relative path): {raw}'
        )
    resolved = os.path.abspath(raw)
    if not os.path.isfile(resolved):
        raise ValueError(f'referenceImageUrl file not found: {resolved}')
    if not is_allowed_reference_path(resolved):
        raise ValueError(f'referenceImageUrl must point to an existing image file: {resolved}')
    return resolved


def to_servable_image_url(value):
    if not isinstance(value, str) or not value.strip():
        return value
    raw = value.strip()
    if raw.startswith('/workspace-file/') or raw.startswith('/reference-image'):
        return raw
    resolved = validate_absolute_reference_path(raw)
    if resolved is None:
        return raw
    if is_safe_workspace_path(resolved):
        rel_path = os.path.relpath(resolved, workspace_root).replace(os.sep, '/')
        return f'/workspace-file/{quote(rel_path, safe="/")}'
    return f'/reference-image?path={quote(resolved, safe="")}'


def to_workspace_file_url(value):
    return to_servable_image_url(value)


def normalize_initial_input(data):
    if isinstance(data, dict):
        image_url = data.get('referenceImageUrl') or data.get('imageUrl') or data.get('inputImageUrl')
        normalized_url = to_workspace_file_url(image_url)
        if normalized_url != image_url:
            data = dict(data)
            data['referenceImageUrl'] = normalized_url
    return data


def load_initial_input(input_path):
    resolved = resolve_path(input_path)
    if not resolved:
        raise ValueError('--input is required')
    with open(resolved, 'r', encoding='utf-8') as f:
        return normalize_initial_input(json.load(f))


@app.route('/')
def index():
    return send_from_directory(script_dir, 'index.html')


@app.route('/<path:filename>')
def static_file(filename):
    return send_from_directory(script_dir, filename)


@app.route('/api/input')
def api_input():
    return jsonify(initial_input)


@app.route('/workspace-file/<path:filename>')
def workspace_file(filename):
    resolved = resolve_path(filename)
    if not resolved or not os.path.isfile(resolved) or not is_safe_workspace_path(resolved):
        return jsonify({'error': 'file not found'}), 404
    return send_file(resolved)


@app.route('/reference-image')
def reference_image():
    raw_path = request.args.get('path')
    if not raw_path:
        return jsonify({'error': 'path required'}), 400
    resolved = os.path.abspath(raw_path)
    if not is_allowed_reference_path(resolved):
        return jsonify({'error': 'image file not allowed'}), 403
    return send_file(resolved)


@app.route('/api/model_profiles')
def api_model_profiles():
    if not os.path.isfile(PROFILE_PATH):
        return jsonify({'error': 'parammodel_image_profile.json not found'}), 404
    return jsonify(read_json_file(PROFILE_PATH))


@app.route('/api/model_products')
def api_model_products():
    if not os.path.isfile(PRODUCT_PATH):
        return jsonify({'error': 'parammodel.json not found'}), 404
    return jsonify(read_json_file(PRODUCT_PATH))


@app.route('/submit', methods=['POST'])
def submit():
    global result_data
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': 'JSON body required'}), 400
    units = payload.get('units')
    if not isinstance(units, list):
        return jsonify({'error': 'units must be a list'}), 400
    result_data = payload

    @after_this_request
    def _schedule_shutdown(response):
        threading.Timer(SHUTDOWN_DELAY_SEC, shutdown_event.set).start()
        return response

    return jsonify({'status': 'ok'})


_UNIT_OUTPUT_OMIT_KEYS = frozenset({'candidates', 'description'})
_ROOT_OUTPUT_OMIT_KEYS = frozenset({'description', 'referenceImageUrl'})


def sanitize_abd_output(data):
    """Strip UI-only / draft fields before writing confirmed abd.json."""
    if not isinstance(data, dict):
        return data
    out = {k: v for k, v in data.items() if k not in _ROOT_OUTPUT_OMIT_KEYS}
    units = out.get('units')
    if isinstance(units, list):
        sanitized_units = []
        for unit in units:
            if isinstance(unit, dict):
                sanitized_units.append(
                    {k: v for k, v in unit.items() if k not in _UNIT_OUTPUT_OMIT_KEYS}
                )
            else:
                sanitized_units.append(unit)
        out['units'] = sanitized_units
    return out


def write_result(output_rel_path):
    if result_data is None:
        raise RuntimeError('No confirmed layout was submitted.')
    out_path = resolve_path(output_rel_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(sanitize_abd_output(result_data), f, ensure_ascii=False, indent=2)


def main():
    global initial_input

    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True,
                        help='Input JSON path relative to workspace root')
    parser.add_argument('--output', default=DEFAULT_OUTPUT,
                        help='Output file path relative to workspace root')
    args = parser.parse_args()

    initial_input = load_initial_input(args.input)

    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    app.logger.setLevel(logging.ERROR)

    port = find_free_port()
    url = f'http://127.0.0.1:{port}'

    server = threading.Thread(
        target=lambda: app.run(host='127.0.0.1', port=port, debug=False),
        daemon=True,
    )
    server.start()
    print(f'[confirm_abd] Browser: {url}', file=sys.stderr)
    webbrowser.open(url)

    shutdown_event.wait()
    time.sleep(POST_SHUTDOWN_GRACE_SEC)

    write_result(args.output)
    print(args.output)


if __name__ == '__main__':
    main()
