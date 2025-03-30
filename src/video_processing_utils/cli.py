'''CLI interfaces'''

# System imports
import argparse
import logging
import os
import pprint


# Local imports
import video_processing_utils
import video_processing_utils.utils

# Globals
logger = logging.getLogger(__name__)


def walk_files(base_path='.') -> list[str]:
    """Walk files in a directory.

    Args:
        path (str, optional): _description_. Defaults to '.'.

    Returns:
        list[str]: _description_
    """
    file_list = []
    for root, _, files in os.walk(base_path):
        for curr_file in files:
            file_list.append(f"{os.path.join(root,curr_file)}")

    return file_list



def video_dup_finder() -> None:
    """Video duplicate finder CLI entry.
    """

    file_list = walk_files()
    print(f"Count: {len(file_list)}")

def cli_concat_create_parser() -> argparse.ArgumentParser:
    """Arg handler for CLI.

    Returns a filled in argument parser.

    Returns:
        argparse.ArgumentParser: _description_
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
        argparse.Namespace: _description_
    """
    parser = cli_concat_create_parser()
    args = parser.parse_args()

    if len(args.input) <= 1:
        parser.error("Pass more than 1 input filename")

    if args.over_write is False and os.path.exists(args.output):
        parser.error(f"Output file '{args.output}' exists, aborting")

    logger.info(f"Parsed arguments: {pprint.pformat(args)}")

    return args

def cli_concat_setup_logging(args: argparse.Namespace) -> None:
    """Setup logging for invocation.

    Args:
        args (argparse.Namespace): _description_
    """
    if args.debug is True:
        log_level = logging.DEBUG
    else:
        log_level = logging.ERROR

    logging.basicConfig(encoding='utf-8', level=log_level)
    logger.debug(f"Error level: {log_level}")

def cli_concat_main() -> None:
    """CLI entry point for vumerge
    """    
    args = cli_concat_parse_cli()
    print(args)
    cli_concat_setup_logging(args)
    video_processing_utils.concat_ffmpeg_demuxer(
        input_files=args.input,
        output_file=args.output,
        over_write=args.over_write,
    )

