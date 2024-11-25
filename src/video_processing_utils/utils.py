'''General utility functions.

Should be stuff like scanning directories and other non-video specific
functions.
'''

import argparse
import logging

logger = logging.getLogger(__name__)

def setup_logging(args: argparse.Namespace) -> None:
    """Setup logging for invocation.

    Args:
        args (argparse.Namespace): _description_
    """
    if args.debug is True:
        log_level = logging.DEBUG
    else:
        log_level = logging.ERROR

    logging.BASIC_FORMAT = '%(asctime)s - %(name)s - %(thread)d - %(levelname)s - %(message)s'
    #logging.BASIC_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'

    logging.basicConfig(
        encoding='utf-8',
        level=log_level,
        format=logging.BASIC_FORMAT,
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
