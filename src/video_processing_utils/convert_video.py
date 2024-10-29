'''
Bulk re-encode my mp4 h264 videos to h265


'encoded_library_name': 'x264'


Notes:
- H.265 patent situation is still odd, ffmpeg encode of AV1 is moving at 1-2
  frames/sec which would take forever.

TODO:
- Investigate using ffmpeg-python rather than pymediainfo + subprocess
- Handle specific errors:
  - Mov not present
    - https://stackoverflow.com/questions/18294912/ffmpeg-generate-moov-atom
'''

# Built in
import argparse
import datetime
import logging
import multiprocessing
import os
import pathlib
import pprint
import re
import subprocess
import sys
import time
import traceback
import typing

# External imports
import ffmpeg
import psutil

# Local imports
from . import ffmpeg_utils

# Global definitions
ACCEPTED_EXTENSIONS = [
    '3gp',
    'asf', 'avi',
    'flv',
    'm2v', 'm4v', 'mkv', 'mov', 'mp4', 'mpeg', 'mpg',
    'ogm',
    'rm', 'rmvb',
    'ts',
    'vob',
    'webm', 'wmv',
    'xvid',
]
DEFAULT_OUTPUT_EXTENSION = 'mp4'

if psutil.WINDOWS:
    PRIORITY_LOWER  = psutil.IDLE_PRIORITY_CLASS
    PRIORITY_NORMAL = psutil.NORMAL_PRIORITY_CLASS
elif psutil.LINUX:
    PRIORITY_LOWER = 10
    PRIORITY_NORMAL = 0
else:
    print("Unsupported platform")
    sys.exit(-1)


class SkipFile(Exception):
    """Exception thrown when we just want to skip a file processing.

    Args:
        Exception (_type_): _description_
    """

# Global objs
logger = logging.getLogger(__name__)
lock = multiprocessing.Lock()

def determine_new_filename(fileprefix: str, ext: str='mp4') -> typing.Tuple[str,bool]:
    """Determine temp output filename during encode.

    Args:
        fileprefix (str): Prefix to use.
        ext (str, optional): output extension. Defaults to 'mp4'.

    Returns:
        typing.Tuple[str,bool]: filename as index 0, index 1 will be True if this is a
            temporary filename, False if this will be the final filename.
    """
    new_file_name = f"{fileprefix}.{ext}"

    if not os.path.exists(new_file_name):
        return (new_file_name, False)

    # The file exists so we need to try an incrementing number
    i = 1
    while True:
        new_file_name = f"{fileprefix}-{i}.{ext}"

        if not os.path.exists(new_file_name):
            return (new_file_name, True)

        i += 1

def is_h265(filename: str) -> bool:
    """Determine if the file has its video in h265 format.

    Args:
        filename (str): Filename to check.

    Returns:
        bool: True if h.265 found, False otherwise.
    """
    fdata = ffmpeg_utils.fetch_file_data(filename)
    # logger.info(pprint.pformat(fdata))
    video_formats = list(map(
        lambda x: x['codec_name'],
        filter(lambda x: x['codec_type'] == 'video', fdata['streams']),
    ))

    if 'hevc' in video_formats or 'V_MPEGH/ISO/HEVC' in video_formats:
        return True

    logger.info(f"Video formats in '{filename}' => {pprint.pformat(video_formats)}")

    # No h265 was found
    return False

def timedelta_parse(value: str) -> datetime.timedelta:
    """
    convert input string to timedelta
    """
    value = re.sub(r"[^0-9:.]", "", value)
    if not value:
        return

    return datetime.timedelta(
        **{
            key:float(val)
            for val, key in zip(
                value.split(":")[::-1],
                ("seconds", "minutes", "hours", "days")
            )
          }
        )

def transcode_file_ffmpeg(input_filename: str, output_filename: str,
                          video_codec: str='libx265', audio_codec: str='aac'
                          ) -> None:
    """Handle transcoding a single file (using the ffmpeg module).

    todo: candidate to move to ffmpeg_utils module.

    Args:
        input_filename (str): Input filename to transcode from.
        output_filename (str): Output filename to transcode to.
        video_codec (str, optional): Video codec for output. Defaults to 'libx265'.
        audio_codec (str, optional): Audio codec for output. Defaults to 'aac'.

    Raises:
        SkipFile: Raised if the input file is missing.
        RuntimeError: Rauised if the ffmpeg command line is invalid.
    """
    original_metadata = ffmpeg_utils.fetch_file_data(input_filename)
    video_data = list(filter(
        lambda x: x['codec_type'] == 'video',
        original_metadata['streams']
    ))
    try:
        total_frames = float(video_data[0]['nb_frames'])
    except KeyError:
        match video_data[0]['codec_name']:
            case 'vp8' | 'vp9':
                # Split 'avg_frame_rate': '2997/100' to 29.97
                frame_base, divisor = video_data[0]['avg_frame_rate'].split('/')
                frame_rate = float(frame_base) / float(divisor)

                duration = (
                    timedelta_parse(video_data[0]['tags']['DURATION']) -
                    timedelta_parse(video_data[0]['start_time'])
                ).total_seconds()

                total_frames = duration * frame_rate
            case _:
                msg = "Unable to read frame count from codec: " +\
                    f"{video_data[0]['codec_name']}"
                logger.error(msg)
                # This isn't linked to the key error
                # pylint: disable=W0707
                raise SkipFile(msg)

    transcode_cmd = ffmpeg.FFmpeg().\
        option("y").\
        input(input_filename).\
        output(
            output_filename,
            {
                # Catch-all for an extra streams, for those just copy
                'c':       'copy',      # Copy streams by default
                'codec:v': video_codec, # Transcode video to specified format
                'codec:a': audio_codec, # Transcode audio to specified format
                'codec:s': 'copy',      # Copy the subtitles
                'dn':      None,        # Ignore the data streams (most seem to be
                                        #  "ffmpeg GPAC ISO Hint Handler")
            },
            vf = "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            map=['0'],  # Map any other streams (e.g. subtitles)
        )

    @transcode_cmd.on("start")
    def on_start(arguments: list[str]):
        if psutil.WINDOWS:
            psutil.Process().nice(PRIORITY_LOWER)

        logger.debug(f"FFMpeg arguments: {arguments}")

    @transcode_cmd.on("started")
    def on_started(process: subprocess.Popen):
        if psutil.WINDOWS:
            psutil.Process().nice(PRIORITY_NORMAL)
        elif psutil.LINUX:
            os.setpriority(os.PRIO_PROCESS, process.pid, PRIORITY_LOWER)

    # These are the raw ffmpeg lines.
    # @transcode_cmd.on("stderr")
    # def on_stderr(line: str):
    #     logger.error(f"FFMpeg stderr: {line}")

    # Feeds a status which looks like the following:
    # Progress(
    #   frame=223,
    #   fps=50.0,
    #   size=786432,    # Output bytes (at completion size of output file)
    #   time=datetime.timedelta(seconds=9, microseconds=200000),
    #   bitrate=683.3,
    #   speed=2.05
    # )
    @transcode_cmd.on("progress")
    def on_progress(progress: ffmpeg.Progress):
        percentage = (progress.frame / total_frames) * 100
        curr_time = datetime.datetime.now()
        curr_time_str = curr_time.strftime("%Y-%m-%d %H:%M:%S,%f")
        print(
            f"{curr_time_str} - {percentage:6.2f}% - {progress.fps: >6.1f} fps - " +
            f"{progress.speed: >6.3f}x - {progress.bitrate: >8.2f} bps",
            end="\r", flush=True,
        )

    # @transcode_cmd.on("completed")
    # def on_completed():
    #     # The final status line will remain
    #     print()

    # @transcode_cmd.on("terminated")
    # def on_terminated():
    #     print("terminated")

    try:
        transcode_cmd.execute()
    except ffmpeg.FFmpegFileNotFound as exc:
        raise SkipFile(f"Input file '{input_filename}' is missing") from exc
    except ffmpeg.FFmpegInvalidCommand as exc:
        raise RuntimeError(f"Invalid ffmpeg command: {exc}") from exc

def transcode_file(filename, new_file_name):

    '''Handle transcoding a single file.
    '''
    call_params = [
        'ffmpeg',   '-y',
        # '-hwaccel', # 'cuda',
        # '-hwaccel', 'vaapi',
        '-i',       filename,
        '-vf',      "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        # Catch-all for an extra streams, for those just copy
        '-c',       'copy',
        '-c:v',     'libx265',   # Video to H265
        '-c:a',     'aac',       # Audio to AAC
        '-c:s',     'copy',      # Copy the subtitles
        '-dn',                   # Ignore the data streams (most seem to be
                                 #  "ffmpeg GPAC ISO Hint Handler")
        '-map',     '0',         # Map any other streams (e.g. subtitles)
        new_file_name,
    ]

    # logger.info(f"Transcoding: {filename} with command line\n{call_params}")

    with open(filename + '.log', 'w', encoding="utf8") as f_stdout:

        if psutil.WINDOWS:
            lock.acquire()
            psutil.Process().nice(PRIORITY_LOWER)
            prog_h = subprocess.Popen(
                call_params,
                stdin=subprocess.PIPE,
                stdout=f_stdout,
                stderr=subprocess.STDOUT,
            )
            psutil.Process().nice(PRIORITY_NORMAL)
            lock.release()
        elif psutil.LINUX:
            # PermissionError is thrown when attempting to return to the normal
            # priority that is being done above on windows.
            # We are since python 3.3 able to just set the priority of the ffmpeg
            # process directly so this will likely become the default going
            # forward.
            prog_h = subprocess.Popen(
                call_params,
                stdin=subprocess.PIPE,
                stdout=f_stdout,
                stderr=subprocess.STDOUT,
            )
            os.setpriority(os.PRIO_PROCESS, prog_h.pid, PRIORITY_LOWER)
        else:
            print("Unsupported platform")
            sys.exit(-1)

        #logger.info(f"Started: {prog_h.pid}")
        process_data = psutil.Process(prog_h.pid)

        process_idle = 0
        while prog_h.poll() is None:
            try:
                if process_data.cpu_percent(interval=1.0) < 2.0:
                    process_idle += 1
                else:
                    process_idle = 0

                if process_idle > 20:
                    logging.error("Terminating due to inactivity")
                    prog_h.kill()
                    time.sleep(2)
                    os.remove(new_file_name)
                    raise subprocess.CalledProcessError(-1, call_params[0])

                time.sleep(1)
            except psutil.NoSuchProcess:
                break

        prog_h.wait()

        if prog_h.returncode:
            raise RuntimeError(f"Got a issue from ffmpeg: {prog_h.returncode}")

    # Purge the log file
    os.remove(filename + '.log')


def process_file(filename: str, delete_orig: bool = True):
    '''
    Process a single file to h265
    '''
    try:
        if not os.path.exists(filename):
            raise SkipFile("File no longer present")

        if os.path.isdir(filename):
            raise SkipFile("Is a directory")

        if os.stat(filename).st_size == 0:
            raise SkipFile("Is zero size")

        try:
            fileprefix, exten = filename.rsplit('.', 1)
        except ValueError:
            raise SkipFile("Invalid file format") from None

        if exten.lower() not in ACCEPTED_EXTENSIONS:
            raise SkipFile("Not a file to process")

        # Check the media, is it not h265?
        if is_h265(filename):
            raise SkipFile("File is already h265")

        if exten == 'mkv':
            output_extension = 'mkv'
        else:  # Default
            output_extension = DEFAULT_OUTPUT_EXTENSION

        new_file_name, tmp_file = determine_new_filename(
            fileprefix,
            output_extension
        )

        transcode_file_ffmpeg(filename, new_file_name)

        size_old = os.path.getsize(filename)
        size_new = os.path.getsize(new_file_name)

        file_difference = size_new - size_old

        logger.info(f"Size old:'{size_old:,}', new: '{size_new:,}' -> " +
            f"Diff: {file_difference:,} ({file_difference / size_old * 100:.2f}%)")

        if delete_orig:
            os.remove(filename)

        if tmp_file:
            os.rename(new_file_name, filename)

        #logger.info(f"Completed: {new_file_name}")

        return file_difference
    except SkipFile as exc:
        #logger.info(f"{filename} -> Skipped -> {exc}")
        raise exc
    except Exception as exc:
        logger.error(f"An exception occurred processing file '{filename}': {exc.__class__}, {exc}")
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error(repr(traceback.format_exception(
            exc_type, exc_value, exc_traceback)))
        raise SkipFile("Generic Error") from None

def process_dir():
    '''Process appropriate files in a directory.
    '''

    dir_space_difference = 0

    for filename in sorted(os.listdir('.')):
        try:
            file_difference = process_file(filename)
            dir_space_difference += file_difference
        except SkipFile as exc:
            logger.debug(f"Skipping {filename} for reason {exc}")

    logger.info(f"Dir difference: {dir_space_difference:,}")
    return dir_space_difference

def print_dir():
    '''Print all files in directory (placeholder handler function).
    '''

    for filename in os.listdir('.'):
        logger.error(f"File found: {filename}")

def process_recursive():
    '''Process appropriate files in a directory recursively.
    '''
    root_dir = os.getcwd()

    total_difference = 0
    dirs_to_process = sorted(map(lambda x: x[0], os.walk('.')))
    for curr_dir in dirs_to_process:
        logger.info(f"Processing directory: {curr_dir}")
        try:
            os.chdir(curr_dir)
        except FileNotFoundError:
            logger.error(f"Folder '{curr_dir}' no longer present, skipping.")
            continue
        dir_diff = process_dir()
        total_difference += dir_diff
        os.chdir(root_dir)

    logger.info(f"Total difference: {total_difference:,}")

def parse_args():
    '''Parse arguments passed to application.
    '''
    parser = argparse.ArgumentParser(description='Bulk converter')
    parser.add_argument(
        '--path',
        type=pathlib.Path,
        help='Path to process',
        default='.'
    )
    parser.add_argument('-r', '--recursive', action='store_true')
    parser.set_defaults(recursive=False)

    prog_args = parser.parse_args()

    return prog_args


def main() -> None:
    """Main function"""
    #logging.BASIC_FORMAT = '%(asctime)s - %(name)s - %(thread)d - %(levelname)s - %(message)s'
    logging.BASIC_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.INFO, format=logging.BASIC_FORMAT)

    args = parse_args()

    # Change to path specified
    os.chdir(args.path)

    # Recursive or just that directory
    if args.recursive:
        process_recursive()
    else:
        process_dir()

if __name__ == '__main__':
    main()
