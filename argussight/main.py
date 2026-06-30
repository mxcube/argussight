import argparse

from argussight.core.config import get_config_from_dict
from argussight.grpc.server import serve


def parse_args() -> argparse.Namespace:
    opt_parser = argparse.ArgumentParser(description="mxcube argussight")

    opt_parser.add_argument(
        "-c",
        "--config",
        dest="config_file_path",
        help="Configuration file path",
        default="",
    )

    opt_parser.add_argument(
        "-hs",
        "--host",
        dest="host",
        help="host of the redis server",
        default="localhost",
    )

    opt_parser.add_argument(
        "-p",
        "--port",
        dest="port",
        help="port of redis server",
        default="6379",
    )

    opt_parser.add_argument(
        "-ch",
        "--channel",
        dest="channel",
        help="channel of the video-stream",
        default="video-streamer",
    )

    return opt_parser.parse_args()


def run() -> None:
    args = parse_args()

    config = get_config_from_dict(
        {
            "config_path": args.config_file_path,
            "redis": {
                "host": args.host,
                "port": args.port,
                "channel": args.channel,
            },
        }
    )

    serve(config)


if __name__ == "__main__":
    run()
