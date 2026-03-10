"""
Configuration for the API Gateway.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROCESSOR_SERVICE_URL: str = "http://processor-service:8000"
    SIMULATOR_URL: str = "http://simulator:8080"

    RABBITMQ_HOST: str = "rabbitmq"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str = "mars"
    RABBITMQ_PASS: str = "habitat2026"
    RABBITMQ_EXCHANGE: str = "mars.events"

    @property
    def rabbitmq_url(self) -> str:
        return (
            f"amqp://{self.RABBITMQ_USER}:{self.RABBITMQ_PASS}"
            f"@{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}/"
        )


settings = Settings()
