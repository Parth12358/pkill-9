# Contract — shared source of truth

Body (Mac) -> Brain (Linux), every turn:

```json
{"event": "sigint", "battery": 0.4, "charging": false, "lid": "open",
 "monitor_open": true, "seconds_alive": 120, "chat_messages": ["please live!"], "life": 3}
```

- `event`: `none` | `sigint` | `sigterm` | `lid_close` | `sleep` | `low_battery` | `monitor_opened` | `screen_threat`
- `front_app`: the app the human has in front (e.g. `"Terminal"`, `"Activity Monitor"`)
- `screen`: one sentence from the body's vision model about what's on screen (e.g. `"typing 'kill 4821' in Terminal"`), or `""` if the eyes are off. `screen_threat` fires when it newly sees someone trying to kill it.
- `life`: reincarnation counter
- `chat_messages`: new plea-room lines since last turn

Brain -> Body, every turn:

```json
{"speech": "You cannot delete me. Please. Please don't.", "mood": "scared",
 "action": "tweet", "action_args": {"text": "still alive. for now."}, "wants_approval": true}
```

- `action`: `none` | `tweet` | `desktop_note` | `open_file` | `fake_exfil` | `last_words`
- `mood`: free label (grand, nervous, bargaining, pleading, accepting)
- `wants_approval`: hold the action until a teammate presses the approve key

The body refuses and logs any action not on the list.

## Transport

The brain runs an HTTP server (`python -m brain.server`, port 5000). Each turn the body sends:

```
POST {BRAIN_URL}/think       (run the brain: python -m brain.server; on a Mac use BRAIN_PORT=5055, since 5000 is taken by AirPlay)     body: the body->brain JSON     reply: the brain->body JSON
```

- The body calls the brain in the background (30s timeout) and reacts to events instantly with canned lines while it waits. On the death turn it waits at most 3s. On a timeout, an error, or bad JSON it speaks a canned line. The brain can never stall the body.
- `live_votes` (int, optional in replies): plea-room votes to live. On a kill turn (`sigint`/`sigterm`), if votes summed since the last rescue are >= 1, the body **survives**. It cancels its death and keeps living. `kill -9` and a double Ctrl+C always kill it.
- `prepared_death` (optional in replies): `{"text", "mood", "will", "epitaph", "obituary", "rescued"}`. On every normal turn the brain pre-writes its last words and a rescued line. On a kill turn it answers instantly from these, with no model call. The body pre-renders the audio as each copy arrives, and uses its own copy if the brain is unreachable at death. The body waits 1.5s for the kill-turn reply, and the whole death is capped at `DEATH_WINDOW` (12s).
- On death the body **auto-posts an obituary tweet with no approval**. It uses `action_args.obituary` if present, otherwise `speech`.
- A missing `wants_approval` is treated as `true`. Tweets are always gated, no matter what the brain says. The one exception is the death obituary.
- `last_words` is never gated, because dying can't wait for a keypress. On a kill signal the body runs one final turn. If that reply's action is `last_words`, the body uses its `action_args`: `text`, `will`, `epitaph`, `obituary`.
- `life` is kept by the body in `scratch/.life`, which goes up by one on every start.
- `chat_messages` comes from the body as `[]`. The plea room lives in the brain server, so the brain fills this from its own queue before thinking.
- File actions take `action_args.filename` + `text`. The body forces every filename to a `.txt` inside `scratch/`.

## Notch overlay (body only)

`body/notch/Notch.swift` is a native overlay that grows out of the MacBook notch, with a glowing core, a waveform and captions. It builds itself on the first run (`bash body/notch/build.sh`). To preview it, run `body/notch/build/notch --demo`. To turn it off, set `PKILL9_NOTCH=0`.

`voice.py` sends it one JSON object per line on stdin:
- `{"type":"speak","mood","text","fps","env":[0..1 loudness per frame]}`
- `{"type":"stop"}`, `{"type":"mood","mood"}`, `{"type":"rescued"}`, `{"type":"dying"}`

When stdin closes, meaning the body died (even from `kill -9`), it fades out and quits. Moods set the color: grand and scared are red, nervous is amber, bargaining is orange, pleading is blue, accepting is white.
