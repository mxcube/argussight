from typing import Optional, Union

from pydantic import BaseModel, Field


class RedisConfiguration(BaseModel):
    host: str = Field("localhost", description="redis host")
    port: int = Field(6379, description="redis port")
    channel: str = Field(
        "video-streamer", description="redis-channel to publish stream"
    )


class StreamAuthConfiguration(BaseModel):
    type: str = Field(description="authentication type passed to video-streamer")
    username: str = Field("", description="username for the camera")
    password: str = Field("", description="password for the camera")


class StreamConfiguration(BaseModel):
    name: str = Field(description="unique name of the stream in the streams layer")
    uri: str = Field(description="input uri of the camera, passed to video-streamer")
    port: Optional[int] = Field(
        None, description="port of the video-streamer, a free one is used if unset"
    )
    quality: int = Field(4, description="compression rate/quality")
    size: Optional[str] = Field(
        None, description="output size 'width, height', camera size if unset"
    )
    auth: Optional[StreamAuthConfiguration] = None


class CollectorConfiguration(BaseModel):
    config_path: str
    redis: RedisConfiguration


def get_config_from_dict(config_data: dict) -> Union[CollectorConfiguration, None]:
    data = CollectorConfiguration(**config_data)
    return data
