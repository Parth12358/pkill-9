"""speak() wrapping macOS `say` in a background thread. (PRD A: Voice)"""


def speak(text: str) -> None:
    # TODO: threading.Thread(target=subprocess.run, args=(["say", "-v", "Daniel", text],)).start()
    print(f"[say] {text}")
