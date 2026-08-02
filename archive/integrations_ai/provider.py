class AIProvider:
    """Provider abstraction for structured dashboard proposals."""

    def propose_metric(self, request_text: str, allowed_metadata: dict):
        raise NotImplementedError(
            "Implement only after the deterministic metric builder and server validation are working"
        )
