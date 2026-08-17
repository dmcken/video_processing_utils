'''General utility functions.

Should be stuff like scanning directories and other non-video specific
functions.
'''

# System imports
import argparse
import logging
import os

logger = logging.getLogger(__name__)

def setup_logging(args: argparse.Namespace, default_level: int = logging.INFO) -> None:
    """Setup logging for invocation.

    Args:
        args (argparse.Namespace): Parsed CLI arguments, expected to carry a
            `debug` flag (see `add_common_arguments`).
        default_level (int, optional): Logging level to use when `--debug`
            was not passed. Individual CLIs that want quieter default output
            (e.g. only warnings/errors) can override this. Defaults to
            logging.INFO.
    """
    if args.debug is True:
        log_level = logging.DEBUG
        log_format = '%(asctime)s - %(name)s - %(thread)d - %(levelname)s - %(message)s'
    else:
        log_level = default_level
        log_format = '%(asctime)s - %(levelname)s - %(message)s'

    logging.basicConfig(
        encoding='utf-8',
        level=log_level,
        format=log_format,
    )
    logger.debug(f"Error level: {log_level}")

def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    """_summary_

    Args:
        parser (argparse.ArgumentParser): _description_
    """

    # Common arguments
    parser.add_argument(
        '-d', '--debug',
        help="Turn on debugging logging",
        action='store_true',
        default=False,
        required=False,
    )

def is_valid_file(parser: argparse.ArgumentParser, filename: str) -> str:
    """Check for valid input file.

    Args:
        parser (argparse.ArgumentParser): CLI argparser.
        filename (str): Filename to check.

    Returns:
        str: Filename (cleaned).
    """
    if not os.path.exists(filename):
        parser.error(f"File {filename} does not exist")
        return ""
    else:
        return filename
