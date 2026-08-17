'''
Convert containers (e.g. .mkv -> .mp4) without re-encoding.

From:
https://stackoverflow.com/questions/40077681/ffmpeg-converting-from-mkv-to-mp4-without-re-encoding

ffmpeg -find_stream_info -loglevel warning \
    -i input.mkv \
    -map 0 -codec copy -codec:s mov_text \
    output.mp4

Currently how to change a mkv to mp4
'''

# System imports
import argparse
import glob
import logging
import os
import pathlib
import pprint

# External imports
import ffmpeg

# Local imports
from . import utils

logger = logging.getLogger(__name__)

def process_dir(base_path: str = '.', recursive: bool = False) -> None:
    """Convert every .mkv file under `base_path` to .mp4 without re-encoding.

    Files that fail to convert are logged and skipped, rather than aborting
    the rest of the batch.

    Args:
        base_path (str, optional): Directory to scan for .mkv files.
            Defaults to '.'.
        recursive (bool, optional): Recurse into subdirectories of
            `base_path`. Defaults to False.
    """
    if recursive:
        pattern = os.path.join(base_path, '**', '*.mkv')
    else:
        pattern = os.path.join(base_path, '*.mkv')

    to_process = sorted(glob.glob(pattern, recursive=recursive))
    for curr_file in to_process:
        out_file = f"{curr_file[:-3]}mp4"
        logger.info(f"File to convert: {curr_file} -> {out_file}")
        if os.path.exists(out_file):
            logger.info(f"Output file: {out_file} exists, skipping")
            continue

        ffmpeg_run = ffmpeg.FFmpeg().\
            input(curr_file).\
            option('n').\
            option('v', 'error').\
            option('stats').\
            output(
                out_file,
                {
                    'map': '0',
                    'codec': 'copy',
                    'codec:s': 'mov_text',
                }
            )

        @ffmpeg_run.on("progress")
        def on_progress(progress: ffmpeg.Progress) -> None:
            print(f"{curr_file} => {progress}", end="\r", flush=True)

        @ffmpeg_run.on("terminated")
        def on_terminated():
            logger.error(f"Terminated before conversion of '{curr_file}' finished")

        @ffmpeg_run.on("completed")
        def on_completed():
            logger.info(f"Deleting: {curr_file}")
            os.remove(curr_file)

        logger.debug(f"FFmpeg command line: {ffmpeg_run.arguments}")

        try:
            ffmpeg_run.execute()
        except ffmpeg.errors.FFmpegError as exc:
            logger.error(f"Failed to convert '{curr_file}': {exc}")
            if os.path.exists(out_file) and os.path.getsize(out_file) == 0:
                logger.error(f"Deleting zero length output: {out_file}")
                os.remove(out_file)
            continue

def create_parser() -> argparse.ArgumentParser:
    """Arg handler for CLI.

    Returns:
        argparse.ArgumentParser: Parser configured with the converter's options.
    """
    parser = argparse.ArgumentParser(
        description="Convert .mkv files to .mp4 without re-encoding (stream copy).",
    )
    parser.add_argument(
        '--path',
        type=pathlib.Path,
        default='.',
        help="Path to process (default: %(default)s)",
    )
    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        default=False,
        help="Recurse into subdirectories of --path",
    )
    utils.add_common_arguments(parser=parser)

    return parser

def parse_cli() -> argparse.Namespace:
    """Return the parsed cli arguments.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = create_parser()
    args = parser.parse_args()

    return args

def main() -> None:
    """CLI entry point for vucontainer.
    """
    args = parse_cli()
    utils.setup_logging(args=args)
    logger.debug(f"Parsed arguments: {pprint.pformat(args)}")

    process_dir(base_path=str(args.path), recursive=args.recursive)

if __name__ == '__main__':
    main()
