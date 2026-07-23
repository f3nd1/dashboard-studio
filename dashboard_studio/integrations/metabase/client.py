class MetabaseClient:
    """Server-side Metabase client placeholder.

    Credentials must be supplied through server configuration, never browser code or Git.
    """

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def get_dashboard(self, dashboard_id: int):
        raise NotImplementedError("Implement after the manual SQL migration path is validated")
