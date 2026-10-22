"""Validate private-Space startup as a browser, without API auth on its socket.

The Hub token stays in this test process. Only the existing short-lived Space
page grant is supplied to the same-origin WSS URL. Never print that URL/token.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request

import websockets


async def main():
    host = 'smolagents-convfill-speech-demo.hf.space'
    headers = {'Authorization': 'Bearer ' + os.environ['HF_TOKEN']}
    request = urllib.request.Request('https://huggingface.co/api/spaces/smolagents/convfill-speech-demo/jwt', headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        grant = json.load(response)['token']
    root = Path(__file__).resolve().parents[1]
    code = "import { withSpaceAccess } from './web_demo/hf_interface/connection-url.js'; let input=''; for await (const c of process.stdin) input+=c; const x=JSON.parse(input); process.stdout.write(withSpaceAccess(x.socket,x.page));"
    generated = subprocess.run(['node', '--input-type=module', '-e', code], cwd=root,
        input=json.dumps({'socket': 'wss://' + host + '/v1/realtime', 'page': 'https://' + host + '/?__sign=' + grant}),
        capture_output=True, text=True, check=True).stdout
    for attempt in range(3):
        try:
            async with websockets.connect(generated, origin='https://' + host,
                subprotocols=['realtime', 'openai-insecure-api-key.s2s-local'], open_timeout=10, ping_interval=None) as socket:
                assert json.loads(await asyncio.wait_for(socket.recv(), 8))['type'] == 'session.created'
                await socket.send(json.dumps({'type': 'session.update', 'session': {'type': 'realtime', 'tools': []}}))
                while True:
                    event = json.loads(await asyncio.wait_for(socket.recv(), 8))
                    if event['type'] == 'error':
                        raise RuntimeError('Session update rejected')
                    if event['type'] == 'session.updated':
                        break
            break
        except OSError:
            if attempt == 2:
                raise RuntimeError('Could not reach the private Space') from None
            await asyncio.sleep(0.5)
    request = urllib.request.Request('https://' + host + '/connection-url.js', headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        deployed = response.read()
    expected = (root / 'web_demo/hf_interface/connection-url.js').read_bytes()
    assert hashlib.sha256(deployed).digest() == hashlib.sha256(expected).digest(), 'Deployed browser module differs'
    result = {'space': 'smolagents/convfill-speech-demo', 'browser_origin_and_sdk_protocols': True,
              'socket_authorization_header': False, 'private_page_grant': True,
              'session_created': True, 'session_updated': True, 'deployed_module_matches': True}
    Path('/tmp/convfill-browser-access-validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as error:
        # Transport exception strings may contain a signed URL.
        print(json.dumps({'passed': False, 'error_type': type(error).__name__}))
        raise SystemExit(1)
