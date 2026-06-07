from pydantic import BaseModel


class ProviderStatus(BaseModel):
    connected: bool
    scope: str | None = None


class AuthStatus(BaseModel):
    spotify: ProviderStatus
    ytmusic: ProviderStatus
