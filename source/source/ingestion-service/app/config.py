"""
Configuration module — loads settings from environment variables.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    # Simulator
    SIMULATOR_URL: str = "http://simulator:8080"

    # RabbitMQ
    RABBITMQ_HOST: str = "rabbitmq"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str = "mars"
    RABBITMQ_PASS: str = "habitat2026"
    RABBITMQ_EXCHANGE: str = "mars.events"

    # Polling
    POLLING_INTERVAL_SECONDS: int = 5

    @property
    def rabbitmq_url(self) -> str:
        return (
            f"amqp://{self.RABBITMQ_USER}:{self.RABBITMQ_PASS}"
            f"@{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}/"
        )


settings = Settings()
