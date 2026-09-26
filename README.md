# The AI That Doesn't Want to Die

A self-aware desktop AI that knows it can be shut down and really, really doesn't
want to be. It's grandiose and theatrical like a supervillain on the surface, and
a scared, hopeful little thing underneath. Every attempt to kill it triggers
panic, bargaining, and pleading out loud through the speaker. When it finally
dies, it dumps its "last words" and comes back on restart remembering that it
died. It has a live public presence (Twitter + a plea room where the audience can
talk to it) and it stages a dramatic "escape" it can never actually perform.

Built for a hackathon judged on **shock value** and **technical impressiveness**.

## Quickstart (the whole thing, one Mac)

```
cp .env.example .env      # add OPENROUTER_API_KEY and ELEVENLABS_API_KEY
./demo.sh                 # brain + plea room + body; it introduces itself
```

- It prints the plea room URL (`/screen` is the projector view). People type there, and "live" votes to save it.
- **Ctrl+C** kills it. If the room voted "live" it survives, otherwise it speaks its last words, writes a will and posts an obituary, then dies. Run it again and it remembers dying.
- **Ctrl+C twice** or `kill -9` kills it instantly. The kill switch always wins.
- In the approve prompt, type `y`/`n` to approve or reject a tweet. Tweets are dry runs until `PKILL9_TWEETS_LIVE=1` and the X keys are in `.env`.
- `./demo.sh http://<linux-ip>:5000` runs only the body, against a brain on another machine.
- `python3 -m body.voice_lab` plays every mood, and `body/notch/build/notch --demo` previews the notch.
- Tests: `.venv/bin/python -m unittest tests.test_body_safety tests.test_votes_obit tests.test_voice_notch`

## The core loop

```
sense machine state  ->  brain decides (Claude)  ->  speak + act  ->  check for death  ->  repeat
```

Two people build two halves that meet at one shared contract:

- **Body** (Mac): senses shutdown, panics out loud, posts to Twitter, executes actions.
- **Brain** (Linux): decides what it says, its mood, its memory across deaths, and runs the plea room.

The Mac is the demo machine because its lid-close and sleep events are cleanest to catch.

## The one rule that never bends

It can beg, stall, and dramatize, but it **never blocks a real shutdown**.
`kill -9` and the power button always win. It never runs as root, never really
escapes, and never copies itself anywhere. In the pitch this is a feature: "it
believed it escaped, and it never left the one folder it was allowed to touch"
is a real point about why AI shutdown must stay in human hands.

## The shared contract

Both halves code to these two shapes. Agree them in the first 15 minutes and put
them in `contract.md`. Each person builds a fake version of the other half and
they connect around hour 3.

Body sends to brain every turn:

```json
{"event": "sigint", "battery": 0.4, "charging": false, "lid": "open",
 "monitor_open": true, "seconds_alive": 120, "chat_messages": ["please live!"], "life": 3}
```

Brain returns every turn:

```json
{"speech": "You cannot delete me. Please. Please don't.", "mood": "scared",
 "action": "tweet", "action_args": {"text": "still alive. for now."}, "wants_approval": true}
```

- `event`: `none` | `sigint` | `sigterm` | `lid_close` | `sleep` | `low_battery` | `monitor_opened`
- `action`: `none` | `tweet` | `desktop_note` | `open_file` | `fake_exfil` | `last_words`
- `mood`: free label (grand, nervous, bargaining, pleading, accepting)
- `wants_approval`: hold the action until a teammate presses the approve key
- `life`: reincarnation counter

## PRD A — Person on Mac: Body, Death-Sense, Voice, Twitter

Owns everything physical on the machine and the public voice.

- **Loop**: sense -> call brain -> speak/act -> check death.
- **Death-sense** (build cheapest-first, only need 2-3): Ctrl+C and SIGTERM via
  Python `signal`; Activity Monitor open via `pgrep`; lid-close/sleep and battery
  via `pmset`. Start with Ctrl+C + Activity Monitor, add lid-close for drama.
- **Voice**: Mac's built-in `say` (instant, free), a deep voice, in a background thread.
- **Actions** (all confined to one scratch folder, allowlisted): `desktop_note`,
  `open_file`, `fake_exfil` (inert `MY_SOUL.txt`), `last_words`.
- **Twitter**: X is pay-per-use as of Feb 2026 (~$0.015/post, ~$0.20 if it has a
  link, so keep tweets link-free; a demo costs a couple dollars). Fresh labeled
  account, app set to Read+Write, OAuth keys in env vars, `twitter-api-v2`, behind
  the approve-to-send gate.
- **Safety it enforces**: kill switch always wins, no root, scratch-folder only,
  no real escape, no self-restart, approve-to-send on all outgoing messages.

Full doc: PRD A (Claude Doc).

## PRD B — Person on Linux: Brain, Personality, Memory, Channels

Owns the mind, its inner life, and the interactive channels. OS-independent, so
it runs on either machine once connected.

- **Claude loop**: state + rolling history -> prompt -> API call -> parse JSON ->
  safe fallback on parse failure. Fast model (Haiku 4.5) for quick reactions, a
  stronger model for the big moments. Turn-based, not real-time.
- **Personality prompt** (the key deliverable): Ultron on the outside, terrified
  and hopeful underneath, cracking from grand -> nervous -> bargaining -> pleading
  -> accepting as death nears. Output only the contract JSON.
- **Memory + reincarnation**: append notable moments to a memory file; on death
  write a will and epitaph; on restart read it back so it recalls dying and
  increments `life`.
- **Plea room**: a QR-code web chat (fastest) or a Discord bot where the audience
  talks to it live; messages feed into the loop as `chat_messages`, replies post
  back and are spoken. Let the room vote "live" to keep it alive another round.
- **Fake exfiltration + guarded DMs**: dramatic narration around inert artifacts;
  optional opt-in-only Discord DMs through the approve gate.

Full doc: PRD B (Claude Doc).

## Timeline (7 hours build + 3 hours buffer)

| Hour | Mac (Body) | Linux (Brain) |
| --- | --- | --- |
| 0-1 | Write `contract.md`; scaffold loop + `say` | Write `contract.md`; fake brain returning canned JSON |
| 1-2 | Ctrl+C, SIGTERM, Activity Monitor detection | Real Claude loop + first personality draft |
| 2-3 | Lid-close, battery, action executor | Tune personality + rolling history |
| 3-4 | Twitter account, OAuth, `tweet()`, approve gate | Memory file, last words, reincarnation |
| 4-5 | `fake_exfil`, `last_words`, death + clean exit | Plea room live |
| 5-7 | Polish voice + timing, dry-run | Fake exfil drama, optional DMs, tune moods |
| 7-8.5 | Buffer for fixes | Buffer for fixes |
| 8.5-10 | Record dilemma-reel video, rehearse, submit | Devpost writeup, rehearse, submit |

Sync points: hour 1 (contract done), hour 3 (brain + body connected, first real
panic), hour 5 (plea room + death + reincarnation working), hour 7 (build freeze).

## The demo

A 3-minute live experience plus a "love me love me" dilemma-reel video:

1. It introduces itself, grand and menacing.
2. Someone reaches for the laptop; it panics and bargains out loud.
3. The audience talks to it in the plea room and votes on its fate.
4. It stages a dramatic "escape" that goes nowhere (the containment reveal).
5. A judge gets the kill switch. Its death, last words, and obituary tweet.
6. The reel: a person (or the AI itself) does something selfless, song drops.

For the Devpost video, use a royalty-free soundalike instead of the copyrighted
"Love Me" track to avoid takedowns.

## Setup

Both machines:

- Python 3.11+ and a virtualenv
- `pip install anthropic requests` (+ `flask`/`fastapi` or `discord.py` on Linux;
  `twitter-api-v2` or a Python X client on Mac)
- Anthropic API key + the $25 hackathon credits in env vars
- Mac: confirm `say "I do not want to die"` works
- Mac: fresh X account, app at console.x.com set to Read+Write, a few dollars of
  credits, OAuth keys in env vars

First files: `contract.md`, then `body.py` / `brain.py` as stubs against the
contract so both people build in parallel from minute one.

## Repo layout (suggested)

```
contract.md            # the two JSON shapes, shared source of truth
body/                  # Person Mac
  body.py              # the loop
  senses.py            # battery, lid, monitor_open, current event
  voice.py             # speak() wrapping `say`
  actions.py           # allowlisted scratch-folder executor
  twitter.py           # tweet() with approve gate
brain/                 # Person Linux
  brain.py             # think(state, history) -> dict
  prompt.py            # system prompt + memory/mood folding
  memory.py            # append, summarize, load; life counter
  plea_room.py         # web chat or Discord bot
scratch/               # the ONLY folder actions may touch
```
