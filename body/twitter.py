"""tweet() behind the approve-to-send gate. Keys in env vars, never in repo. (PRD A: Twitter)"""


def tweet(text: str) -> None:
    # TODO: strip links, truncate to 280, approve gate, post via OAuth client
    print(f"[tweet dry-run] {text}")
