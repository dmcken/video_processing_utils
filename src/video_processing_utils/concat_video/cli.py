'''CLI entry point for concatenation of video.
'''
import argparse
import sys


from concat_video import export, users
from concat_video import users as u

def create_parser():
    '''Arg handler for CLI.
    '''

    parser = argparse.ArgumentParser()
    parser.add_argument('--input', help='the path to the export file')
    parser.add_argument('--output', default='json', choices=['json', 'csv'], type=str.lower)
    return parser

def main():
    '''Main entry point.
    '''


    args = create_parser().parse_args()
    users = u.fetch_users()

    if args.path:
        file = open(
            args.path,
            'w',
            newline='',
            encoding='utf-8',
        )
    else:
        file = sys.stdout

    if args.format == 'json':
        export.to_json_file(file, users)
    else:
        export.to_csv_file(file, users)
