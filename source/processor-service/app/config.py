"""
Configuration for the Processor Service.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Simulator
    SIMULATOR_URL: str = "http://simulator:8080"

    # RabbitMQ
    RABBITMQ_HOST: str = "rabbitmq"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str = "mars"
    RABBITMQ_PASS: str = "habitat2026"
    RABBITMQ_EXCHANGE: str = "mars.events"

    # Database
    DATABASE_PATH: str = "/app/data/rules.db"

    # Stale sensor timeout
    SENSOR_OFFLINE_TIMEOUT_SECONDS: int = 60

    @property
    def rabbitmq_url(self) -> str:
        return (
            f"amqp://{self.RABBITMQ_USER}:{self.RABBITMQ_PASS}"
            f"@{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}/"
        )


settings = Settings()
