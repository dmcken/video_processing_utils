'''CLI interfaces'''

# System imports
import argparse
import logging
import os
import pathlib
import pprint
import sys

# External imports
import ffmpeg

# Local imports
import video_processing_utils
import video_processing_utils.utils
from video_processing_utils.convert_video import ACCEPTED_EXTENSIONS

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

### CLI video duplicate finder functions
#
# Goal: scan a media library and flag videos that are duplicates of each
# other in content, even when they differ in resolution, container,
# bitrate, codec, or other re-encode artifacts (e.g. the same movie kept
# as both a 480p and a 1080p rip).
#
# Planned approach:
#   1. Walk `args.path` (optionally recursively) and filter to files with
#      a recognised video extension (`ACCEPTED_EXTENSIONS`).
#   2. Perceptually hash each video's visual content, independent of its
#      resolution/bitrate/codec, using the `videohash` package (already a
#      project dependency - see `videohash.VideoHash`).
#   3. Compare hashes pairwise using Hamming distance
#      (`VideoHash.hamming_distance` / `.is_similar`) against
#      `args.threshold` and group files whose distance falls under it.
#   4. Report the duplicate groups (paths + resolution/size of each member)
#      so the user can decide which copies to keep.
#
# None of the hashing/comparison logic is implemented yet - this is just
# the CLI scaffold (argument parsing, file discovery, logging) so the
# `vudupcheck` entry point is functional and the interface is settled.

def video_dup_finder_create_parser() -> argparse.ArgumentParser:
    """Arg handler for the video duplicate finder CLI.

    Returns:
        argparse.ArgumentParser: Parser configured with the finder's options.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Scan a media library for duplicate videos - the same content "
            "stored at different resolutions, bitrates, containers or codecs."
        ),
    )
    parser.add_argument(
        '--path',
        type=pathlib.Path,
        default='.',
        help="Path to the media library to scan (default: %(default)s)",
    )
    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        default=False,
        help="Recurse into subdirectories of --path",
    )
    parser.add_argument(
        '--frame-interval',
        type=float,
        default=1.0,
        help="Frames sampled per second of video when hashing (passed to " +
            "videohash); lower values are faster but less precise " +
            "(default: %(default)s)",
    )
    parser.add_argument(
        '--threshold',
        type=int,
        default=8,
        help="Maximum Hamming distance between two video hashes for them " +
            "to be considered duplicates (default: %(default)s)",
    )
    video_processing_utils.utils.add_common_arguments(parser=parser)

    return parser

def video_dup_finder_parse_cli() -> argparse.Namespace:
    """Return the parsed cli arguments for the video duplicate finder.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = video_dup_finder_create_parser()
    args = parser.parse_args()

    return args

def video_dup_finder_scan(base_path: str, recursive: bool) -> list[str]:
    """Find candidate video files to hash and compare.

    Args:
        base_path (str): Path to scan.
        recursive (bool): Recurse into subdirectories if True, otherwise
            only scan `base_path` itself.

    Returns:
        list[str]: Video files found, filtered to `ACCEPTED_EXTENSIONS`.
    """
    if recursive:
        candidates = walk_files(base_path)
    else:
        candidates = [
            os.path.join(base_path, curr_file)
            for curr_file in os.listdir(base_path)
        ]

    return sorted(
        curr_file for curr_file in candidates
        if os.path.isfile(curr_file) and
            curr_file.rsplit('.', 1)[-1].lower() in ACCEPTED_EXTENSIONS
    )

def video_dup_finder() -> None:
    """CLI entry point for vudupcheck.

    Currently a scaffold: discovers candidate video files under `--path`
    but does not yet hash or compare them - see the module notes above for
    the planned approach.
    """
    args = video_dup_finder_parse_cli()
    video_processing_utils.utils.setup_logging(args=args)
    logger.debug(f"Parsed arguments: {pprint.pformat(args)}")

    file_list = video_dup_finder_scan(str(args.path), args.recursive)
    logger.info(f"Found {len(file_list)} candidate video file(s) under '{args.path}'")

    logger.warning(
        "Duplicate detection (hashing + comparison) is not implemented yet - " +
        "this is currently just a scaffold. See the module docstring in " +
        "cli.py for the planned approach."
    )

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

