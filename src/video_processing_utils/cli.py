'''CLI interfaces'''

# System imports
import argparse
import logging
import os
import pprint
import sys

# External imports
import ffmpeg

# Local imports
import video_processing_utils
import video_processing_utils.utils

# Globals
logger = logging.getLogger(__name__)

# Utility functions

def walk_files(base_path='.') -> list[str]:
    """Recursively walk files in a directory.

    Args:
        base_path (str, optional): Directory to walk. Defaults to '.'.

    Returns:
        list[str]: Paths of every file found under `base_path`.
    """
    file_list = []
    for root, _, files in os.walk(base_path):
        for curr_file in files:
            file_list.append(f"{os.path.join(root,curr_file)}")

    return file_list

### CLI concat functions

def cli_concat_create_parser() -> argparse.ArgumentParser:
    """Arg handler for the concat CLI.

    Returns:
        argparse.ArgumentParser: Parser configured with the concat options.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-i', '--input',
        default=[],
        action='append',
        help='Input files in order to concatenate (minimum two required)',
        required=True,
        type=lambda filename: video_processing_utils.utils.is_valid_file(parser=parser, filename=filename)
    )
    parser.add_argument(
        '-w', '--over-write',
        help="Overwrite the output file if it exists",
        default=False,
        action='store_true',
    )
    parser.add_argument(
        '-o', '--output',
        help="The output path to output to",
        required=True,
    )
    parser.add_argument(
        '-d', '--debug',
        help="Turn on debugging logging",
        action='store_true',
        default=False,
        required=False,
    )

    return parser

def cli_concat_parse_cli() -> argparse.Namespace:
    """Return the parsed cli arguments.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = cli_concat_create_parser()
    args = parser.parse_args()

    if len(args.input) <= 1:
        parser.error("Pass more than 1 input filename")

    if args.over_write is False and os.path.exists(args.output):
        parser.error(f"Output file '{args.output}' exists, aborting")

    return args

def cli_concat_main() -> None:
    """CLI entry point for vumerge.
    """
    args = cli_concat_parse_cli()
    # Concat's default output has historically been quieter than the other
    # CLIs (errors only) since the ffmpeg progress line already covers
    # normal feedback; --debug still enables full DEBUG logging as usual.
    video_processing_utils.utils.setup_logging(args=args, default_level=logging.ERROR)
    logger.debug(f"Parsed arguments: {pprint.pformat(args)}")
    print(f"Merging: {args.input} to {args.output}")
    try:
        video_processing_utils.concat_ffmpeg_demuxer(
            input_files=args.input,
            output_file=args.output,
            over_write=args.over_write,
        )
    except (RuntimeError, ffmpeg.errors.FFmpegError) as exc:
        logger.error(f"Concat failed: {exc}")
        sys.exit(1)

