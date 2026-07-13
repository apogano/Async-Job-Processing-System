from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
	database_url: str = "postgresql://postgresql@postgresql:5432/jobs"
	max_jobs_attempts: int = 3
	redis_url: str = "redis://redis:6379/0"
	upload_dir: str = "/tmp/uploads"
	
	model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
