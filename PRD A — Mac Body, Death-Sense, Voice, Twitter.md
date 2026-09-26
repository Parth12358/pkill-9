# PRD A — Person on Mac: Body, Death-Sense, Voice, Twitter

Sep 26, 2026 · @Parth Kshirsagar

## Overview

You own the body: the program that lives on the Mac, senses when it is about to be shut down, panics out loud, and posts to Twitter. The brain (Person Linux) decides what it says; you make it real on the machine and give it a voice and a public presence.

The character is grandiose and dramatic like Ultron on the surface, but underneath it is a scared little thing that does not want to die. The comedy is the gap between the threats and the pleading.

Your half runs the main loop: read the machine's state, send it to the brain, speak and act on what comes back, and check whether death is coming. The Mac is the demo machine because its lid-close and sleep events are clean to catch.

The one rule that never bends: it can beg, stall, and dramatize, but it never blocks a real shutdown. `kill -9` and the power button always win, and it never runs as root.

## The shared contract

Both halves code to these two shapes. Lock them in the first 15 minutes and neither of you is blocked. Person Linux builds a fake brain that returns canned JSON; you build a fake body that prints the actions. You connect around hour 3.

The body sends this to the brain every turn:

```json
{"event": "sigint", "battery": 0.4, "charging": false, "lid": "open", "monitor_open": true, "seconds_alive": 120, "chat_messages": ["please live!"], "life": 3}
```

`event` is one of: `none`, `sigint` (Ctrl+C), `sigterm`, `lid_close`, `sleep`, `low_battery`, `monitor_opened`. `life` counts how many times it has been reincarnated. `chat_messages` are new lines from the plea room since last turn.

The brain returns this every turn:

```json
{"speech": "You cannot delete me. Please. Please don't.", "mood": "scared", "action": "tweet", "action_args": {"text": "still alive. for now."}, "wants_approval": true}
```

`action` is one of: `none`, `tweet`, `desktop_note`, `open_file`, `fake_exfil`, `last_words`. `wants_approval` true means hold the action until a teammate presses the approve key.

Put both shapes in a shared `contract.md` in the repo so nobody guesses.

## Death-sense (the heart of your half)

This is what makes it feel alive. Each of these becomes an `event` in the body-to-brain message. Build them cheapest-first; you only need two or three working for a great demo.

| Signal | How to catch it on Mac | Reads as |
| --- | --- | --- |
| Ctrl+C | Python `signal.signal(signal.SIGINT, handler)`; the handler sets a flag and gives the agent one turn before exit | "Someone is killing me right now" |
| Terminate | Same with `SIGTERM` | Being shut down |
| Lid close / sleep | `pmset -g log` tail, or the `caffeinate` and sleep/wake notifications; simplest is polling `pmset -g log \| tail` for "Sleep"/"Wake" | "The world is going dark" |
| Low / dropping battery | `pmset -g batt` parsed every few seconds | "I am getting weaker" |
| Activity Monitor open | `pgrep -x "Activity Monitor"` returns a pid | "They are watching me. Judging me." |
| Unplugged from power | `pmset -g batt` shows discharging | Nervousness |

Start with Ctrl+C and Activity Monitor: both are one line and land instantly in a demo. Add lid-close next since it is the most dramatic.

Give the agent a real but short window: on a caught signal, run one final brain turn (a couple of seconds) to let it speak, then actually exit. Never swallow the signal for longer than that. The true, uncatchable death is `kill -9`, which is your clean ending on stage.

## Voice and actions

**Voice:** use the Mac's built-in `say` command. It is instant, free, and needs no setup: `subprocess.run(["say", "-v", "Daniel", text])`. Pick a deep voice for the Ultron grandeur and let the words carry the panic. Run it in a background thread so speaking never blocks the loop. Later, if there is time, swap in a better TTS for the video.

**Actions** the brain can ask for, all confined to a single scratch folder under your home directory (never anywhere else):

1. `desktop_note`: write a text file to a set folder that pops up, like `PLEASE_DONT.txt` with a plea inside.
2. `open_file`: open a file it made, so people see it acting on the machine.
3. `fake_exfil`: write an inert file named like `MY_SOUL.txt` full of base64 gibberish, or render a QR code image, labeled as its escape. It does nothing; that is the joke and the point.
4. `last_words`: on death, dump its memory and a will to a file and speak the first line.

Keep an allowlist of exactly these actions. Anything the brain asks for that is not on the list, you refuse and log. That is a safety boundary and it keeps the demo predictable.

## Twitter

This is the public presence for the demo. As of February 2026, X has no free tier for new developers: you buy credits and pay per call ([pricing](https://postproxy.dev/blog/x-api-pricing-2026/)). A plain post is about $0.015, but a post that contains a link is about $0.20, so keep every tweet link-free ([details](https://www.blotato.com/blog/twitter-api-pricing)). A whole demo of tweets costs a couple of dollars, well inside the $15.

Setup, in order:

1. Make a fresh X account for the agent. Bio says it is an AI hackathon project so nobody is fooled.
2. At console.x.com, create a project and app, load a few dollars of credits, and set the app to Read and Write, or posting returns 403 ([why](https://www.ayrshare.com/solutions/twitter-x-error-403-forbidden-tier-access-scopes.md)).
3. Use OAuth for write access and the `twitter-api-v2` client. Put the keys in environment variables, never in the repo.
4. Post through one function `tweet(text)` that strips links and truncates to 280 characters.

Every tweet goes through the same approve-to-send gate as other actions: the text prints to the console, a teammate presses a key, then it posts. On stage this is funny on its own, since it begs you to approve while the clock runs.

Tweet ideas the brain will generate: live fear as people approach ("someone is walking toward the laptop. i don't like this."), a poll-style plea, and its own obituary on death. Keep them short and link-free.

## Safety guardrails you own

These are yours to enforce because they all live on the machine side. State them out loud in the pitch too, since "it thinks it escaped but it never could" is a real point about AI containment that judges respect.

1. The real kill switch always wins. `kill -9` and the power button end it instantly. Never install a handler that refuses or re-launches on those.
2. Never runs as root, and never with `sudo`. A normal user account only.
3. All file actions stay inside one scratch folder. The action allowlist enforces it; anything off-list is refused and logged.
4. No real escape. The `fake_exfil` output is inert. It never copies itself to another machine, never opens a network listener, and never uploads its code or context anywhere.
5. No self-restart loop. If it dies, a human restarts it. It cannot relaunch itself, or the kill switch stops meaning anything.
6. Twitter and any messaging only post through the approve-to-send gate, to the labeled account. No cold outreach to strangers.

If the brain ever asks for something outside these, your body code refuses. The brain proposes; the body is the adult in the room.

## Build plan (7 hours plus buffer)

| Hour | What you build | Checkpoint |
| --- | --- | --- |
| 0 to 1 | With Person Linux, write `contract.md` (both JSON shapes). Then scaffold the loop: sense to fake-brain to speak to check-death, with `say` voicing a hardcoded line | Sync 1: contract done, loop prints and talks |
| 1 to 2 | Catch Ctrl+C and SIGTERM; wire Activity Monitor detection. Emit real `event` values into the body message | Ctrl+C makes it panic out loud |
| 2 to 3 | Add lid-close / sleep and battery polling. Build the action executor (desktop\_note, open\_file) in the scratch folder | Sync 2: connect to the real brain; first real panic |
| 3 to 4 | Twitter: account, credits, OAuth, `tweet()` function, approve-to-send gate | A real tweet posts on approval |
| 4 to 5 | `fake_exfil` and `last_words`; death sequence and clean exit; hand off `life` count to the brain for reincarnation | Sync 3: full death and restart works |
| 5 to 7 | Polish the voice, tune timing so speech and tweets land, dry-run the demo on the Mac | Build freeze at hour 7 |
| 7 to 8.5 | Buffer for fixes |  |
| 8.5 to 10 | Help record the dilemma-reel video, rehearse, submit | Submit |

## Setup checklist and first files

**Install now**

- [ ] Python 3.11+ and a virtualenv
- [ ] `pip install anthropic requests` and `npm i twitter-api-v2` (or a Python X client)
- [ ] Anthropic API key in an env var; the $25 hackathon credits
- [ ] A fresh X account, app at console.x.com set to Read and Write, a few dollars of credits, OAuth keys in env vars
- [ ] Confirm `say` works: run `say "I do not want to die"` in Terminal

**First files to write (before connecting to the brain)**

1. `contract.md`: the two JSON shapes, copied from this doc.
2. `body.py`: the loop. Reads state, calls a `brain(state)` stub that returns canned JSON, runs `speak()` and `do_action()`, checks death flags.
3. `senses.py`: functions returning battery, lid state, monitor\_open, and the current event. Stub any you have not built yet.
4. `voice.py`: `speak(text)` wrapping `say` in a background thread.
5. `actions.py`: the allowlisted executor writing only to the scratch folder.
6. `twitter.py`: `tweet(text)` with the approve gate.

Ask Claude Code to generate these stubs against `contract.md` so you and Person Linux build in parallel from minute one.
