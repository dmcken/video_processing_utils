#!/usr/bin/env python3
'''Check media.

Check media files by fully decoding them via ffmpeg and reporting any files
that produced decode errors (corrupt streams, truncated files, etc.).
'''

# System imports
import argparse
import concurrent.futures
import gc
import glob
import logging
import os
import pathlib
import pprint
import queue
import re
import subprocess
import time

# Local imports
from . import utils

logger = logging.getLogger(__name__)

def enqueue_output(fH, q):
    for line in iter(fH.readline, ''):
        q.put(line)
    fH.close()

def read_popen_pipes(p):
    '''

    https://stackoverflow.com/questions/2804543/read-subprocess-stdout-line-by-line
    '''

    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        q_stdout, q_stderr = queue.Queue(), queue.Queue()

        pool.submit(enqueue_output, p.stdout, q_stdout)
        pool.submit(enqueue_output, p.stderr, q_stderr)

        while True:
            if p.poll() is not None and q_stdout.empty() and q_stderr.empty():
                break

            out_line = err_line = ''

            try:
                out_line = q_stdout.get_nowait()
            except queue.Empty:
                pass

            try:
                err_line = q_stderr.get_nowait()
            except queue.Empty:
                pass

            yield (out_line, err_line)

def create_parser() -> argparse.ArgumentParser:
    """Arg handler for CLI.

    Returns:
        argparse.ArgumentParser: Parser configured with the checker's options.
    """
    parser = argparse.ArgumentParser(
        description="Check media files for decode errors by fully decoding " +
            "them via ffmpeg.",
    )
    parser.add_argument(
        'pattern',
        help="Glob pattern to match files against (e.g. '*.mp4')",
    )
    parser.add_argument(
        '--path',
        type=pathlib.Path,
        default='.',
        help="Base path to search from (default: %(default)s)",
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
    """CLI entry point.
    """
    args = parse_cli()
    utils.setup_logging(args=args)
    logger.debug(f"Parsed arguments: {pprint.pformat(args)}")

    if args.recursive:
        search_regex = os.path.join(str(args.path), '**', args.pattern)
    else:
        search_regex = os.path.join(str(args.path), args.pattern)

    logger.info(f"Starting with regex: {search_regex}")
    files_with_errors = []
    for curr_file in glob.glob(search_regex, recursive=args.recursive):
        errors_count = 0

        ffmpeg_cmd = ['ffmpeg', '-v', 'error', '-i', curr_file, '-f', 'null', '-']

        with subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            bufsize=1, text=True,
        ) as progH:

            for out_line, err_line in read_popen_pipes(progH):
                if re.search("error", out_line, flags=re.I):
                    errors_count += 1

                if re.search("error", err_line, flags=re.I):
                    errors_count += 1

            progH.poll()

            time.sleep(2)

        if errors_count > 0:
            print(f"'{curr_file}': {errors_count} error(s)")
            files_with_errors.append((curr_file, errors_count))

        gc.collect()

    if files_with_errors:
        print(f"\nDone - {len(files_with_errors)} file(s) with errors:")
        for curr_file, errors_count in files_with_errors:
            print(f"  {curr_file}: {errors_count} error(s)")
    else:
        print("\nDone - no errors found")

if __name__ == '__main__':
    main()
