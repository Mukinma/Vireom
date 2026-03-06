class SerialController:
    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def send(self, payload: str) -> bool:
        if not self.enabled:
            return False
        return True
