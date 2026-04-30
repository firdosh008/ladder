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
    #: (e.g. full ``SceneSkeleton``) routinely hit 400 "Schema is too complex"
    #: or 503 grammar-compiler-overloaded errors in practice. Default off so
    #: scene builds skip the retry storm and go straight to the prompted-JSON
    #: + Pydantic path. Flip on via env to try grammar-constrained sampling.
    SCENE_DESIGNER_STRUCTURED_OUTPUTS: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()  # type: ignore[call-arg]
