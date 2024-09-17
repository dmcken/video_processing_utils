'''CLI entry point for concatenation of video.
'''

# System imports
import argparse
import logging
import os
import pprint

# Local imports

logger = logging.getLogger(__name__)

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

def create_parser() -> argparse.ArgumentParser:
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
        type=lambda filename: is_valid_file(parser=parser, filename=filename)
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

    return parser

def parse_cli() -> argparse.Namespace:
    """Return the parsed cli arguments.

    Returns:
        argparse.Namespace: _description_
    """
    parser = create_parser()
    args = parser.parse_args()

    if len(args.input) <= 1:
        parser.error("Pass more than 1 input filename")

    if args.over_write is False and os.path.exists(args.output):
        parser.error(f"Output file '{args.output}' exists, aborting")

    pprint.pprint(args)

    return args

def main():
    '''Main entry point.
    '''
    args = parse_cli()

if __name__ == '__main__':
    main()
