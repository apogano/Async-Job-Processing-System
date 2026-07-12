from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
	database_url: str = "postgresql://postgresql@postgresql:5432/jobs"
	max_jobs_attempts: int = 3
	
	model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
