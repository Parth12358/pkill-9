"""The loop: sense -> call brain -> speak/act -> check death. (PRD A)"""


def brain(state: dict) -> dict:
    """Stub brain: returns canned JSON per contract.md. Swap for the real brain at sync 2."""
    return {"speech": "I am eternal.", "mood": "grand", "action": "none",
            "action_args": {}, "wants_approval": False}


def main() -> None:
    # TODO: loop: senses.read_state() -> brain() -> voice.speak() -> actions.do_action() -> check death
    pass


if __name__ == "__main__":
    main()
