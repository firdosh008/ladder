from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str

    CORS_ORIGINS: str = "http://localhost:5173"

    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    GOOGLE_API_KEY: str | None = None
    EXA_API_KEY: str | None = None
    SCRAPECREATORS_API_KEY: str | None = None

    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"

    #: Claude structured outputs compile JSON Schema to a grammar; large schemas
    #: (e.g. full ``SceneSkeleton``) sometimes hit 400 "Schema is too complex"
    #: or 503 grammar-compiler overload. Default on; the designer falls back
    #: to prompted JSON + Pydantic when the grammar path errors out. Flip off
    #: via env to skip grammar entirely if it stays unstable.
    SCENE_DESIGNER_STRUCTURED_OUTPUTS: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()  # type: ignore[call-arg]
