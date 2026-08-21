'''
Convert containers (e.g. .mkv/.m2ts -> .mp4/.mkv) without re-encoding.

From:
https://stackoverflow.com/questions/40077681/ffmpeg-converting-from-mkv-to-mp4-without-re-encoding

ffmpeg -find_stream_info -loglevel warning \
    -i input.mkv \
    -map 0 -codec copy -codec:s mov_text \
    output.mp4

Currently how to change a mkv/m2ts to mp4/mkv
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

# mp4 can only carry subtitles as 'mov_text'; mkv can hold pretty much any
# subtitle codec as-is, so there's no need to transcode them for mkv output.
SUBTITLE_CODEC_FOR_OUTPUT = {
    'mp4': 'mov_text',
    'mkv': 'copy',
}

def process_dir(base_path: str = '.', recursive: bool = False,
                from_extensions: list[str] = None, to_extension: str = 'mp4',
                ) -> None:
    """Convert every file with a `from_extensions` extension under
    `base_path` to `to_extension`, without re-encoding.

    Files that fail to convert are logged and skipped, rather than aborting
    the rest of the batch.

    Args:
        base_path (str, optional): Directory to scan for files to convert.
            Defaults to '.'.
        recursive (bool, optional): Recurse into subdirectories of
            `base_path`. Defaults to False.
        from_extensions (list[str], optional): Extensions (without the
            leading '.') to look for and convert. Defaults to ['mkv'].
        to_extension (str, optional): Output container to convert to, 'mp4'
            or 'mkv'. Defaults to 'mp4'.
    """
    if from_extensions is None:
        from_extensions = ['mkv']

    to_process = []
    for from_extension in from_extensions:
        if recursive:
            pattern = os.path.join(base_path, '**', f'*.{from_extension}')
        else:
            pattern = os.path.join(base_path, f'*.{from_extension}')
        to_process.extend(glob.glob(pattern, recursive=recursive))

    for curr_file in sorted(to_process):
        out_file = f"{os.path.splitext(curr_file)[0]}.{to_extension}"
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
                    'codec:s': SUBTITLE_CODEC_FOR_OUTPUT[to_extension],
                }
            )

        @ffmpeg_run.on("progress")
        def on_progress(progress: ffmpeg.Progress) -> None:
            print(f"{curr_file} => {progress}", end="\r", flush=True)

        @ffmpeg_run.on("terminated")
        def on_terminated():
            # The progress line above ends with '\r', not '\n' - print a bare
            # newline first so this doesn't overwrite its front and leave its
            # tail visible. on_terminated/on_completed fire from inside
            # execute(), before our own code below gets a chance to.
            print(flush=True)
            logger.error(f"Terminated before conversion of '{curr_file}' finished")

        @ffmpeg_run.on("completed")
        def on_completed():
            print(flush=True)
            logger.info(f"Deleting: {curr_file}")
            os.remove(curr_file)

        logger.debug(f"FFmpeg command line: {ffmpeg_run.arguments}")

        try:
            ffmpeg_run.execute()
        except ffmpeg.errors.FFmpegError as exc:
            print(flush=True)
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
        description="Convert video files between containers (e.g. .mkv/.m2ts " +
            "to .mp4/.mkv) without re-encoding (stream copy).",
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
    parser.add_argument(
        '-f', '--from', dest='from_extensions',
        default='mkv',
        help="Comma-separated list of source extensions to look for, " +
            "without the leading '.' (e.g. 'mkv,m2ts') (default: %(default)s)",
    )
    parser.add_argument(
        '-t', '--to', dest='to_extension',
        choices=sorted(SUBTITLE_CODEC_FOR_OUTPUT.keys()),
        default='mp4',
        help="Container to convert to (default: %(default)s)",
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

    args.from_extensions = [
        extension.strip().lstrip('.').lower()
        for extension in args.from_extensions.split(',')
        if extension.strip()
    ]
    if not args.from_extensions:
        parser.error("--from must list at least one extension")
    if args.to_extension in args.from_extensions:
        parser.error(
            f"--to '{args.to_extension}' can't also be listed in --from " +
            f"{args.from_extensions}"
        )

    return args

def main() -> None:
    """CLI entry point for vucontainer.
    """
    args = parse_cli()
    utils.setup_logging(args=args)
    logger.debug(f"Parsed arguments: {pprint.pformat(args)}")

    process_dir(
        base_path=str(args.path),
        recursive=args.recursive,
        from_extensions=args.from_extensions,
        to_extension=args.to_extension,
    )

if __name__ == '__main__':
    main()
