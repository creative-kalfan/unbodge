"""Optional dashboard-enabled ASGI entrypoint; original api.server is unchanged."""
from api.dashboard import create_dashboard_app

app = create_dashboard_app()
