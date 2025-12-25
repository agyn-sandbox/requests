import collections
import collections.abc
import hashlib
import threading

from wsgiref.simple_server import make_server

from requests.auth import HTTPDigestAuth
from requests.utils import parse_dict_header
import requests


def _ensure_collections_compatibility():
    required = (
        'Mapping',
        'MutableMapping',
        'MutableSet',
        'Sequence',
        'Callable',
    )
    for name in required:
        if not hasattr(collections, name):
            setattr(collections, name, getattr(collections.abc, name))


_ensure_collections_compatibility()


def _fake_urandom(n):
    return b'0123456789abcdef'[:n]


def _compute_expected_digest(username, password, params, method, body=b''):
    def _md5(value):
        if isinstance(value, str):
            value = value.encode('utf-8')
        return hashlib.md5(value).hexdigest()

    def _kd(secret, data):
        return _md5(f"{secret}:{data}")

    realm = params['realm']
    uri = params['uri']
    nonce = params['nonce']

    ha1 = _md5(f"{username}:{realm}:{password}")
    if params.get('qop') == 'auth-int':
        if isinstance(body, str):
            body = body.encode('utf-8')
        entity_hash = hashlib.md5(body or b'').hexdigest()
        ha2 = _md5(f"{method}:{uri}:{entity_hash}")
    else:
        ha2 = _md5(f"{method}:{uri}")

    qop = params.get('qop')
    if qop:
        noncebit = f"{nonce}:{params['nc']}:{params['cnonce']}:{qop}:{ha2}"
        return _kd(ha1, noncebit)
    return _kd(ha1, f"{nonce}:{ha2}")


def test_digest_auth_prefers_auth_qop(monkeypatch):
    auth = HTTPDigestAuth('user', 'pass')
    auth.chal = {
        'realm': 'test',
        'nonce': 'nonce',
        'qop': 'auth, auth-int',
    }

    monkeypatch.setattr('requests.auth.time.ctime', lambda: '0')
    monkeypatch.setattr('requests.auth.os.urandom', _fake_urandom)

    header = auth.build_digest_header('GET', 'http://example.com/protected')
    assert 'qop=auth' in header

    _, params_str = header.split(' ', 1)
    params = parse_dict_header(params_str)

    assert params['qop'] == 'auth'
    expected = _compute_expected_digest('user', 'pass', params, 'GET')
    assert params['response'] == expected


def test_digest_auth_with_quoted_qop_options(monkeypatch):
    realm = 'test'
    nonce = 'fixednonce'
    opaque = 'opaque'
    challenge = (
        f'Digest realm="{realm}", qop="auth,auth-int", '
        f'nonce="{nonce}", opaque="{opaque}"'
    )

    last_params = {}

    def app(environ, start_response):
        if environ.get('PATH_INFO') != '/protected':
            start_response(
                '404 Not Found',
                [('Content-Length', '0')]
            )
            return [b'']

        authorization = environ.get('HTTP_AUTHORIZATION')
        if not authorization:
            start_response(
                '401 Unauthorized',
                [
                    ('WWW-Authenticate', challenge),
                    ('Content-Length', '0')
                ]
            )
            return [b'']

        scheme, _, param_str = authorization.partition(' ')
        if scheme.lower() != 'digest':
            start_response(
                '401 Unauthorized',
                [
                    ('WWW-Authenticate', challenge),
                    ('Content-Length', '0')
                ]
            )
            return [b'']

        parts = parse_dict_header(param_str)
        last_params.clear()
        last_params.update(parts)
        expected = _compute_expected_digest(
            'user',
            'pass',
            parts,
            environ['REQUEST_METHOD']
        )
        if parts.get('response') != expected:
            start_response(
                '401 Unauthorized',
                [
                    ('WWW-Authenticate', challenge),
                    ('Content-Length', '0')
                ]
            )
            return [b'invalid digest']

        body = b'ok'
        start_response(
            '200 OK',
            [
                ('Content-Type', 'text/plain'),
                ('Content-Length', str(len(body)))
            ]
        )
        return [body]

    server = make_server('127.0.0.1', 0, app)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

    try:
        response = requests.get(
            f'http://127.0.0.1:{port}/protected',
            auth=HTTPDigestAuth('user', 'pass'),
        )
    finally:
        server.shutdown()
        thread.join(timeout=1)

    assert response.status_code == 200
    assert response.text == 'ok'
    assert last_params['qop'] == 'auth'
