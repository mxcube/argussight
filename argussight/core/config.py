from typing import Union

from pydantic import BaseModel, Field


class RedisConfiguration(BaseModel):
    host: str = Field("localhost", description="redis host")
    port: int = Field(6379, description="redis port")
    channel: str = Field(
        "video-streamer", description="redis-channel to publish stream"
    )


class CollectorConfiguration(BaseModel):
    config_path: str
    redis: RedisConfiguration


def get_config_from_dict(config_data: dict) -> Union[CollectorConfiguration, None]:
    data = CollectorConfiguration(**config_data)
    return data
