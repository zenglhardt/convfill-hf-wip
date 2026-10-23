# Validation — October 22, 2026

These results distinguish real inference, transport fault injection, simulated
models, and browser checks. The baseline retains quantized
`nvidia/Gemma-4-31B-IT-NVFP4`, not the original BF16 checkpoint.

## Completed checks

- **49 Python tests pass**, including the existing adapter/delivery tests, raw
  prompt preservation, split stop tokens, empty chunks, buffered final text,
  thought filtering, HTTP/SSE failures, a real loopback stalled socket,
  cancellation, Reasoner/Talker overlap, stuck-worker quarantine, cross-origin
  rejection, single-session admission and clean proxy reconnects.
- **5 browser adapter JS tests pass.** The fake-model and loopback tests do not
  claim actual model or browser playback validation.
- **Actual model inference:** three consecutive turns completed. The Talker
  retained the expected sky-color fact and remembered the synthetic user's
  name on a follow-up. Useful Reasoner knowledge arrived while Talker generation
  was active in all three turns. No serialized thought/control tokens appeared
  in the generated Talker fragments.
- **Live transport fault injection with actual models:** all four checks passed. With a three-second injected Reasoner delay, Talker output started at 0.434 s and useful knowledge at 3.850 s. Injected HTTP 503 propagated in 0.227 s; a deliberately cut real response stream failed in 0.671 s; a 0.4-second request deadline returned in 0.787 s, including shutdown. All failed turns left zero history entries. These are controlled faults, not claims about provider uptime.
- **Actual stream cancellation:** a running real inference turn returned in
  0.173 seconds after cancellation, with no error. Session reset cleared history.
- **Actual speech transport:** synthetic microphone PCM passed through real
  Silero/Smart Turn VAD, Qwen3-ASR, ConvFill, Gemma, and Qwen3-TTS. A first turn
  and a follow-up completed with nonempty audio and STT results.
- **Actual barge-in checks passed:** both the first-audio and substantive-text-triggered cases completed with `status=cancelled`. VAD confirmed the injected speech after 523–526 ms, with zero old-response audio frames observed after confirmation. Cancellation and speech-start notifications arrived within 0.1 ms of one another; cancellation was ordered first. These are transport observations, not physical playback guarantees.
- **Additional actual barge-in observation:** synthetic input during an initial audio response
  triggered VAD, cancelled the response, flushed its queue, and cancelled the
  active TTS request. Server logs show response cancellation about 13 ms after
  VAD confirmation, and TTS cancellation about 36 ms after confirmation.
  The client test initially assumed the opposite event order: upstream can
  deliver `response.done` before `input_audio_buffer.speech_started`.
- **Browser UI:** visually checked the Gemma labels and disabled tool controls
  in the in-app browser. The browser reached its microphone permission request;
  this browser profile did not provide a usable mic grant. No human listening
  or physical microphone/playback test is claimed.
- **Hosted speech validation passed:** the private smolagents Space completed two consecutive speech turns and a third after disconnect/reconnect, with actual STT and synthesized audio. Readiness returned HTTP 200 with no active session after the test. All infrastructure operations were scoped to smolagents.

## Timings from actual inference

| Measurement | Turn 1 | Turn 2 | Turn 3 |
| --- | ---: | ---: | ---: |
| First useful Reasoner sentence | 0.702 s | 0.546 s | 0.743 s |
| First Talker sentence (may be filler) | 0.425 s | 0.410 s | 0.545 s |
| Full text inference turn | 2.044 s | 1.171 s | 1.517 s |

Actual speech-end-to-first-audio, measured by the native speech pipeline, was
**3.426 s and 2.631 s** for the two completed local-gateway speech turns.
These include endpointing/Smart Turn delays. First audio arrived **634 ms and
479 ms after the final VAD notification** at the WebSocket client; these smaller
numbers exclude time before that notification and are not full speech-end
latency. They are audio arrival times, not sound-card playback measurements.
The hosted server's first synthetic turn measured **11.292 s**, including its
startup/endpointing path. This is a single cold observation, not a steady-state
latency estimate. No latency percentile is inferred from this sample size.

## GPU memory

Whole-replica OpenMetrics samples during validation showed:

| Service | Maximum sampled bytes | Approximate GiB |
| --- | ---: | ---: |
| Gemma | 85,526,000,000 | 79.65 |
| Talker | 7,854,000,000 | 7.31 |
| STT | 20,983,000,000 | 19.54 |
| TTS | 16,060,000,000 | 14.96 |

These include reserved KV cache/runtime memory. A final twenty-second capture after the rollout lists one Gemma replica. These are
sampled maxima, not an NVML/allocator peak for a single clean steady-state run.
The existing test Gemma endpoint reserves 90% of its GPU. Same-host placement,
shared-GPU contention, and a smaller KV budget have not been benchmarked.

## Remaining validation limits

Earlier validation requests intermittently returned connection refusals or
`ConnectError` from this host. One local reconnect turn failed on a Reasoner
connection error, propagated the failure, and released the session. An early
hosted attempt hit a keepalive timeout. The final hosted protocol run passed
all three speech turns, including reconnect. Audio arrived 167–190 ms after
the final VAD notification; those numbers exclude earlier endpointing time and
are not physical speaker latency. Delivered audio is not proof of human playback.

Physical microphone/playback checks and human verification of filler versus
substantive playback remain to be completed in a browser with a microphone
grant. Scripted initial/substantive
transport interruption checks have passed. The final live
transport fault-injection run passed; earlier attempts encountered upstream
connection errors. Deterministic tests independently cover timeout, HTTP error,
truncated stream and cancellation handling. The included validation scripts retain these checks
for reproduction. There is no missing GPU now: Talker moved to L4 after an A10G
capacity failure.

The delivery ledger records dispatched text/audio, not browser acknowledgements.
Interrupted history remains a best-effort dispatched prefix; it is not an exact
recording of what the listener heard. No inference credentials or full real-user
transcripts are included in the committed results.

Machine-readable observations are in `validation/models.json`, `gpu.json`,
`speech.json`, `hosted-speech.json`, `faults.json`, and `bargein.json`. All prompts/audio used by the scripted speech checks were
synthetic test material.

## Private Space startup regression

A real browser startup failed with `[object Event]`. The WebSocket URL
did not carry the private embedding page's temporary `__sign` grant. API tests
with an Authorization header had hidden this browser-specific difference.
A live reproduction returned HTTP 404 without the page grant; the same-origin
signed socket accepted the browser Origin and SDK subprotocols and emitted
`session.created` and `session.updated` without an Authorization header.

`connection-url.js` now carries the page grant only to its own secure WebSocket,
and the UI turns opaque browser events into an actionable message. Inference
keys remain server-side and WebSocket logs redact access grants. Reproduce the
browser authentication check with `PYTHONPATH=. .venv/bin/python
scripts/validate_browser_access.py`; the script also verifies the deployed
browser module matches the local source.

The user still encountered a connection error after that change. Inspection of
their Chrome session confirmed the signed URL and SDK protocols were present.
The gateway accepted without selecting `realtime`, which the browser handshake
requires when protocols are offered. Python's WebSocket client allowed the
missing selection, so the earlier protocol check was insufficient. The gateway
now selects `realtime`; local and deployed checks explicitly assert this selection
with all three SDK protocol offers. Required suites pass: 49 Python, 5 JavaScript.

After deploying Space revision `53bfc1b2dabff78d084190025801860883c9c53e`,
the live check negotiated `realtime` and received both session events. The user's
existing Chrome tab then started a session with real microphone capture and
Mute/End controls, with no startup error. Server logs confirmed SDK session
configuration. The test session was ended; this verifies browser startup, not
spoken-answer quality or physical playback.
