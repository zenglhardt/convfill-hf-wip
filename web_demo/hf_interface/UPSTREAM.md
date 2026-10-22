# Upstream interface

The browser source is synchronized with `huggingface/speech-to-speech` main
`0fb1f0c395796593233d8b2ced0eaa0832de3275`, plus the feature changes in PR #750.
The Apache-2.0 license remains in LICENSE.huggingface-speech-to-speech.
The runtime dependency stays pinned to that main revision.

Local server.py provides a private same-origin WebSocket gateway, one-session
admission, readiness checks, optional server-side Serper search, and a short
startup greeting. Camera is opt-in. The shared UI now includes the current gear
menu and response timing display. The playback additions measure estimated
speech-end to first non-silent frame on the browser output clock, not physical
speaker playback. Dispatched text remains only a best-effort interrupted-history
proxy. Native tools and camera context go only to the Reasoner.

connection-url.js forwards the private Space’s short-lived __sign grant only to
same-origin HTTPS/WSS. The gateway redacts grants from WebSocket logs and selects
the realtime subprotocol. Inference and server search credentials stay server-side.
Tests cover connection, streaming tools, first-audio timing, and UI display.

The hosted index retains its ConvFill branding and actual quantized Gemma, Talker,
STT and TTS labels, rather than the shared demo’s provider/model credits. Tool
controls and the updated gear fields remain from the current shared UI.

Timing now uses one compact First audio disclosure, available before completion.
Talker state is retained across tool continuations; exact sentence echoes are
suppressed before speech and history commits. Quick tool-result continuations
receive a one-second knowledge head start before fillers resume. The Reasoner
supplies new substance rather than repeating acknowledgments or search preambles.
