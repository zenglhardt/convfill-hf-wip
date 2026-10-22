# Upstream interface

The browser source is synchronized with `huggingface/speech-to-speech` main
`44d6010cd20046b84ac58cf89ae2ac9ef5e2e150`, plus the feature changes in PR #750.
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

The user-authorized startup greeting is an explicit exception to Talker-only TTS:
`speech_to_speech.startup_greeting=true` on the first response routes Gemma’s
filtered greeting directly to TTS, with no Talker, fillers, or tools. Its greeting
prompt is separate from the Reasoner knowledge prompt. Both histories retain the
reply; ordinary turns continue to speak only the Talker. No text matching is used
to choose this route, and the same cancellation/deadline controls apply.

The hosted header names “ConvFill's Talker and Gemma 4 Reasoner” above
“on Hugging Face's speech-to-speech”, with a project-repository link. The
phone layout keeps both lines visible and places controls on the next row.

PR #751's default-on Faster interruptions setting, local Silero v6 detector,
output gain control, and pinned model/worklet/WASM dependencies are synchronized
with upstream main. The private gateway serves the same asset allowlist from
node_modules copied into Docker. Local VAD only ducks volume; server VAD still
owns cancellation/history. The browser test locates its audio fixture from the
installed speech-to-speech package for this repository layout.

The demo holds assistant output for 500 ms after a Smart Turn complete decision
and 1700 ms after an incomplete decision, 300 ms below each upstream default.
Override with `CONVFILL_COMPLETE_HOLD_MS` / `CONVFILL_INCOMPLETE_HOLD_MS`. The
600 ms incomplete-turn processing delay stays inside the incomplete hold window;
it is not added afterward. Model generation may overlap these windows, so measured
residual hold and first-audio latency will vary with inference time.
