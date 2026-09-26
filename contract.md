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
