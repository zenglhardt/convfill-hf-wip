# Upstream interface

The browser interface in this directory is derived from the `demo/` directory
of [huggingface/speech-to-speech](https://github.com/huggingface/speech-to-speech)
at commit `b21e54d6a845c54308bc62500b57f9a2b2aa93ac`.

The upstream project is licensed under Apache-2.0. Its license is retained in
`LICENSE.huggingface-speech-to-speech`. Local integration files are
`server.py`, `test_server.py`, and this notice.


Runtime compatibility is pinned to speech-to-speech commit
`0fb1f0c395796593233d8b2ced0eaa0832de3275` (upstream main on October 22, 2026).
The browser source retains the base revision above. Local server additions provide
a same-origin WebSocket proxy, readiness and one-session admission. Inference
credentials remain server-side. Playback is estimated from dispatched audio;
there is no browser playback acknowledgement and dispatched text is not proof
that a sentence was heard.

`main.js` also disables tool declarations and hides tool settings in normal mode;
the hosted speech-only demo does not request camera access.

`index.html` identifies the hosted quantized Gemma Reasoner and remote speech
models, and hides the unsupported tool controls.
