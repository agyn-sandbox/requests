# -*- coding: utf-8 -*-

import select
import socket
from urllib.parse import urlparse

import pytest
import requests

from requests.auth import HTTPProxyAuth, _basic_auth_str
from requests.exceptions import ProxyError

from .testserver.server import Server


def _read_connect_request(sock):
    data = b''
    sock.settimeout(5)

    while b'\r\n\r\n' not in data:
        chunk = sock.recv(65535)
        if not chunk:
            break
        data += chunk

    return data


def _parse_header_lines(header_bytes):
    header_text = header_bytes.decode('latin1')
    lines = header_text.split('\r\n')[1:]
    headers = {}

    for line in lines:
        if not line:
            break
        if ':' not in line:
            continue
        name, value = line.split(':', 1)
        headers[name.strip().lower()] = value.strip()

    return headers, header_text


def _pipe_between(client_sock, upstream_sock):
    sockets = [client_sock, upstream_sock]
    idle_cycles = 0

    while True:
        ready, _, _ = select.select(sockets, [], [], 0.2)
        if not ready:
            idle_cycles += 1
            if idle_cycles > 25:
                break
            continue

        idle_cycles = 0

        if client_sock in ready:
            chunk = client_sock.recv(65535)
            if not chunk:
                break
            upstream_sock.sendall(chunk)

        if upstream_sock in ready:
            chunk = upstream_sock.recv(65535)
            if not chunk:
                break
            client_sock.sendall(chunk)


def _proxy_handler(target_host, target_port, expected_auth, log):
    def handler(sock):
        request_bytes = _read_connect_request(sock)
        headers, header_text = _parse_header_lines(request_bytes)
        log.append(header_text)

        received_auth = headers.get('proxy-authorization')
        if received_auth != expected_auth:
            response = (
                'HTTP/1.1 407 Proxy Authentication Required\r\n'
                'Proxy-Authenticate: Basic realm="proxy"\r\n'
                'Content-Length: 0\r\n'
                'Connection: close\r\n'
                '\r\n'
            )
            sock.sendall(response.encode('latin1'))
            return header_text

        upstream = socket.create_connection((target_host, target_port))

        try:
            sock.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            _pipe_between(sock, upstream)
        finally:
            upstream.close()

        return header_text

    return handler


@pytest.mark.skipif(not hasattr(socket, 'create_connection'), reason='socket unavailable')
def test_proxy_connect_407_without_header_then_ok_with_header(httpbin_secure):
    target_url = httpbin_secure('get')
    parsed_target = urlparse(target_url)
    expected_auth = _basic_auth_str('user', 'pass')
    connect_log = []

    handler = _proxy_handler(parsed_target.hostname, parsed_target.port or 443, expected_auth, connect_log)

    with Server(handler=handler, host='127.0.0.1', port=0, requests_to_handle=3) as (proxy_host, proxy_port):
        proxies = {'https': 'http://{}:{}'.format(proxy_host, proxy_port)}
        session = requests.Session()
        session.trust_env = False
        session.proxies.update(proxies)

        with pytest.raises(ProxyError) as first_error:
            session.get(target_url, timeout=5, verify=False)

        assert '407' in str(first_error.value)

        response = session.get(
            target_url,
            timeout=5,
            verify=False,
            auth=HTTPProxyAuth('user', 'pass')
        )

        assert response.status_code == 200

        with pytest.raises(ProxyError) as third_error:
            session.get(target_url, timeout=5, verify=False)

        assert '407' in str(third_error.value)

    assert len(connect_log) >= 3
    first_connect = connect_log[0].lower()
    second_connect = connect_log[1].lower()
    third_connect = connect_log[2].lower()

    assert 'proxy-authorization' not in first_connect
    assert 'proxy-authorization' in second_connect
    assert 'proxy-authorization' not in third_connect
