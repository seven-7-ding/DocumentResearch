"""Minimal local Chromium DevTools transport; no browser package downloads."""
import base64
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time
import urllib.parse
import urllib.request


class Browser:
    def __init__(self, executable, directory):
        self.directory = directory
        directory.mkdir(parents=True)
        self.stderr = open(os.devnull, 'wb')
        self.proc = subprocess.Popen([executable, '--headless=new', '--disable-gpu', '--no-first-run',
            '--no-default-browser-check', '--remote-debugging-port=0',
            '--user-data-dir=' + str(directory / 'profile'), 'about:blank'], stdout=self.stderr, stderr=self.stderr)
        portfile = directory / 'profile' / 'DevToolsActivePort'
        deadline = time.monotonic() + 20
        while not portfile.exists():
            if time.monotonic() > deadline:
                self.proc.kill()
                raise TimeoutError('Chromium did not expose its debug port')
            time.sleep(.1)
        port = portfile.read_text().splitlines()[0]
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/json') as response:
            pages = json.load(response)
        url = urllib.parse.urlsplit(next(page['webSocketDebuggerUrl'] for page in pages if page['type'] == 'page'))
        self.sock = socket.create_connection((url.hostname, url.port), timeout=25)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f'GET {url.path} HTTP/1.1\r\nHost: {url.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        header = b''
        while not header.endswith(b'\r\n\r\n'):
            header += self.sock.recv(1)
        if header.split(b'\r\n', 1)[0].split(b' ')[1:2] != [b'101']:
            self.sock.close()
            self.proc.kill()
            self.stderr.close()
            raise RuntimeError('DevTools WebSocket handshake failed')
        self.sequence = 0

    def exact(self, count):
        result = bytearray()
        while len(result) < count:
            chunk = self.sock.recv(count - len(result))
            if not chunk: raise EOFError('DevTools closed')
            result.extend(chunk)
        return bytes(result)

    def send(self, data, opcode=1):
        mask = os.urandom(4)
        size = len(data)
        header = bytes([0x80 | opcode])
        header += bytes([0x80 | size]) if size < 126 else (b'\xfe' + struct.pack('!H', size) if size < 65536 else b'\xff' + struct.pack('!Q', size))
        self.sock.sendall(header + mask + bytes(value ^ mask[index % 4] for index, value in enumerate(data)))

    def receive(self):
        chunks = []
        while True:
            flags, length = self.exact(2)
            masked = length & 128
            length &= 127
            if length == 126: length = struct.unpack('!H', self.exact(2))[0]
            elif length == 127: length = struct.unpack('!Q', self.exact(8))[0]
            mask = self.exact(4) if masked else None
            data = self.exact(length)
            if mask: data = bytes(value ^ mask[index % 4] for index, value in enumerate(data))
            opcode = flags & 15
            if opcode == 8: raise EOFError('DevTools closed')
            if opcode == 9:
                self.send(data, 10)
                continue
            chunks.append(data)
            if flags & 128: return json.loads(b''.join(chunks))

    def call(self, method, params=None):
        self.sequence += 1
        self.send(json.dumps({'id': self.sequence, 'method': method, 'params': params or {}}).encode())
        while True:
            message = self.receive()
            if message.get('id') == self.sequence:
                if 'error' in message: raise RuntimeError(str(message['error']))
                return message['result']

    def evaluate(self, expression):
        result = self.call('Runtime.evaluate', {'expression': expression, 'returnByValue': True, 'awaitPromise': True})
        if result.get('exceptionDetails'): raise RuntimeError(str(result['exceptionDetails']))
        return result['result'].get('value')

    def capture(self, url, name, width, height):
        self.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height,
            'deviceScaleFactor': 1, 'mobile': width < 600})
        self.call('Page.navigate', {'url': url})
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            ready = self.evaluate("document.readyState === 'complete' && (document.querySelector('.card') || document.querySelector('.katex')) !== null")
            if ready: break
            time.sleep(.15)
        else: raise TimeoutError(name + ': content not rendered')
        data = self.evaluate("({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,cards:document.querySelectorAll('.card').length,katex:document.querySelectorAll('.katex').length,errors:document.querySelectorAll('.katex-error').length})")
        self.call('Page.enable')
        shot = self.call('Page.captureScreenshot', {'format': 'png'})
        self.last_screenshot = base64.b64decode(shot['data'])
        return data

    def close(self):
        try:
            self.call('Browser.close')
        except (EOFError, OSError): pass
        self.sock.close()
        try: self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired: self.proc.kill()
        self.stderr.close()
