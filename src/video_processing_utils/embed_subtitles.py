'''Embed external subtitle files into an existing .mkv, without re-encoding.

Adds one or more subtitle files (e.g. .srt) to a Matroska (.mkv) video as
new subtitle tracks, alongside whatever subtitles the file already has - it
never replaces or touches existing tracks.

Uses `mkvmerge` (from the mkvtoolnix project) rather than ffmpeg. ffmpeg's
SRT reader silently drops any subtitle-styling syntax it doesn't itself
recognise (e.g. the `{\\fad(...)\\fn...\\pos(...)}`-style override codes some
subtitle files use for title cards or positioned text, borrowed from the ASS
format) - confirmed by testing that this holds regardless of the *output*
subtitle codec chosen, since the loss happens at ffmpeg's demux/parse step,
before any encoding. `mkvmerge` treats the subtitle file as raw text and
preserves it byte-for-byte instead.

This means `mkvtoolnix` (providing the `mkvmerge` binary) is a prerequisite
for this command specifically, on top of the project's usual ffmpeg/ffprobe
prerequisite - see the README.

mkvmerge cli (single subtitle):
```
mkvmerge -o output.mkv video.mkv \
    --language 0:eng --track-name 0:English --sub-charset 0:UTF-8 \
    subtitle.srt
```
'''

# System imports
import argparse
import logging
import os
import pprint
import re
import shutil
import subprocess
import sys

# Local imports
from . import utils
from .convert_video import determine_new_filename

logger = logging.getLogger(__name__)

_LANGUAGE_TAG_PATTERN = re.compile(r'\[([A-Za-z]{2,4})\]')

# mkvmerge exit codes: 0 = ok, 1 = ok but warnings were issued, 2 = error,
# muxing aborted. https://mkvtoolnix.download/doc/mkvmerge.html#mkvmerge.exit_codes
MKVMERGE_EXIT_WARNING = 1
MKVMERGE_EXIT_ERROR = 2


def guess_language_from_filename(path: str) -> str | None:
    """Guess a subtitle's language from a bracketed tag in its filename,
    e.g. 'Movie[ENG].srt' -> 'eng'.

    Args:
        path (str): Subtitle file path.

    Returns:
        str | None: Lowercased language tag if a `[XXX]`-style tag was
            found in the filename, else None.
    """
    match = _LANGUAGE_TAG_PATTERN.search(os.path.basename(path))
    return match.group(1).lower() if match else None


def embed_subtitles(
    video_path: str,
    subtitle_paths: list[str],
    languages: list[str] = None,
    titles: list[str] = None,
    charenc: str = 'UTF-8',
) -> str:
    """Add `subtitle_paths` to `video_path` as new subtitle tracks, without
    re-encoding, leaving any subtitles already in the file untouched.

    Writes to a temporary file first and only replaces `video_path` once
    mkvmerge has finished successfully - `video_path` is left untouched if
    anything fails. The subtitle files themselves are never modified or
    deleted.

    Args:
        video_path (str): Path to the .mkv file to add subtitles to.
        subtitle_paths (list[str]): External subtitle files to embed, in
            the order they should appear.
        languages (list[str], optional): Language tag (e.g. 'eng') for each
            entry in `subtitle_paths`, matched by position. A shorter list
            (or None) leaves the remaining tracks to fall back to a
            `[XXX]`-style tag in that subtitle's own filename, if any.
            Defaults to None.
        titles (list[str], optional): Track title for each entry in
            `subtitle_paths`, matched by position. A shorter list (or None)
            leaves the remaining tracks untitled. Defaults to None.
        charenc (str, optional): Character encoding of the subtitle files.
            Defaults to 'UTF-8'.

    Raises:
        RuntimeError: If `mkvmerge` isn't on PATH, `video_path` isn't a
            .mkv file, or mkvmerge fails to embed the subtitles.

    Returns:
        str: Path to the resulting video (same as `video_path`).
    """
    if shutil.which('mkvmerge') is None:
        raise RuntimeError(
            "mkvmerge not found on PATH - install mkvtoolnix " +
            "(https://mkvtoolnix.download/) to use vuembedsub."
        )

    fileprefix, extension = os.path.splitext(video_path)
    if extension.lower() != '.mkv':
        raise RuntimeError(
            f"'{video_path}' is not a .mkv file - mkvmerge only writes " +
            "Matroska output. Convert it to .mkv first (e.g. with " +
            "vucontainer) if you want to embed subtitles into it."
        )

    languages = list(languages or [])
    titles = list(titles or [])

    new_file_name, is_temp_file = determine_new_filename(fileprefix, 'mkv')

    command = ['mkvmerge', '-o', new_file_name, video_path]
    for index, subtitle_path in enumerate(subtitle_paths):
        language = languages[index] if index < len(languages) else None
        if language is None:
            language = guess_language_from_filename(subtitle_path)
        title = titles[index] if index < len(titles) else None

        if language:
            command += ['--language', f'0:{language}']
        if title:
            command += ['--track-name', f'0:{title}']
        command += ['--sub-charset', f'0:{charenc}']
        command.append(subtitle_path)

    logger.debug(f"mkvmerge command line: {command}")
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.stdout:
        logger.debug(f"mkvmerge stdout:\n{result.stdout}")
    if result.returncode == MKVMERGE_EXIT_WARNING:
        logger.warning(f"mkvmerge reported warnings for '{video_path}':\n{result.stdout}")
    elif result.returncode >= MKVMERGE_EXIT_ERROR:
        if os.path.exists(new_file_name):
            logger.error(f"Deleting failed output: {new_file_name}")
            os.remove(new_file_name)
        raise RuntimeError(
            f"mkvmerge failed (exit {result.returncode}) embedding subtitles " +
            f"into '{video_path}':\n{result.stdout}{result.stderr}"
        )

    if is_temp_file:
        os.replace(new_file_name, video_path)

    return video_path


def create_parser() -> argparse.ArgumentParser:
    """Arg handler for CLI.

    Returns:
        argparse.ArgumentParser: Parser configured with the tool's options.
    """
    parser = argparse.ArgumentParser(
        description="Embed one or more external subtitle files into a .mkv " +
            "as new subtitle tracks, without re-encoding and without " +
            "touching any subtitles already in the file. Requires " +
            "mkvmerge (from mkvtoolnix) on PATH.",
    )
    parser.add_argument(
        '--video',
        required=True,
        help="Video (.mkv) file to add subtitles to.",
    )
    parser.add_argument(
        '--sub',
        dest='subs',
        action='append',
        required=True,
        help="Subtitle file to embed. Repeat --sub to embed multiple files, " +
            "in the order they should appear.",
    )
    parser.add_argument(
        '--lang',
        dest='langs',
        action='append',
        default=[],
        help="Language tag (e.g. 'eng') for the --sub at the same position. " +
            "If omitted for a given --sub, a `[XXX]`-style tag in that " +
            "subtitle's filename is used if present (e.g. 'Movie[ENG].srt' " +
            "-> 'eng').",
    )
    parser.add_argument(
        '--title',
        dest='titles',
        action='append',
        default=[],
        help="Track title for the --sub at the same position.",
    )
    parser.add_argument(
        '--charenc',
        default='UTF-8',
        help="Character encoding of the subtitle files (default: %(default)s)",
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

    if not os.path.isfile(args.video):
        parser.error(f"Video file '{args.video}' does not exist")
    for sub_path in args.subs:
        if not os.path.isfile(sub_path):
            parser.error(f"Subtitle file '{sub_path}' does not exist")
    if len(args.langs) > len(args.subs):
        parser.error("More --lang values than --sub files")
    if len(args.titles) > len(args.subs):
        parser.error("More --title values than --sub files")

    return args


def main() -> None:
    """CLI entry point for vuembedsub."""
    args = parse_cli()
    utils.setup_logging(args=args)
    logger.debug(f"Parsed arguments: {pprint.pformat(args)}")

    try:
        embed_subtitles(
            video_path=args.video,
            subtitle_paths=args.subs,
            languages=args.langs,
            titles=args.titles,
            charenc=args.charenc,
        )
    except RuntimeError as exc:
        logger.error(f"Failed to embed subtitles into '{args.video}': {exc}")
        sys.exit(1)

if __name__ == '__main__':
    main()
