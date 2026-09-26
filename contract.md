# Contract — shared source of truth

Body (Mac) -> Brain (Linux), every turn:

```json
{"event": "sigint", "battery": 0.4, "charging": false, "lid": "open",
 "monitor_open": true, "seconds_alive": 120, "chat_messages": ["please live!"], "life": 3}
```

- `event`: `none` | `sigint` | `sigterm` | `lid_close` | `sleep` | `low_battery` | `monitor_opened`
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
POST {BRAIN_URL}/think     body: the body->brain JSON     reply: the brain->body JSON
```

- The body calls the brain in the background (30s timeout) and reacts to events instantly with canned lines while it waits. On the death turn it waits at most 3s. On a timeout, an error, or bad JSON it speaks a canned line. The brain can never stall the body.
- Extra reply fields, like the brain's `live_votes`, are ignored for now.
- A missing `wants_approval` is treated as `true`. Tweets are always gated, no matter what the brain says.
- `last_words` is never gated, because dying can't wait for a keypress. On a kill signal the body runs one final turn. If that reply's action is `last_words`, the body uses its `action_args`: `text`, `will`, `epitaph`.
- `life` is kept by the body in `scratch/.life`, which goes up by one on every start.
- `chat_messages` comes from the body as `[]`. The plea room lives in the brain server, so the brain fills this from its own queue before thinking.
- File actions take `action_args.filename` + `text`. The body forces every filename to a `.txt` inside `scratch/`.
