'''
Bulk re-encode my mp4 h264 videos to h265


'encoded_library_name': 'x264'


Notes:
- H.265 patent situation is still odd, ffmpeg encode of AV1 is moving at 1-2
  frames/sec which would take forever.

TODO:
- Investigate using ffmpeg-python rather than pymediainfo + subprocess
'''

# Built in
import argparse
import logging
import multiprocessing
import os
import pathlib
import subprocess
import sys
import time
import traceback
import typing

# Externals
import psutil
import pymediainfo

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
    '''
    Exception thrown when we just want to skip a file processing
    '''

# Global objs
logger = logging.getLogger(__name__)
lock = multiprocessing.Lock()

def determine_new_filename(fileprefix: str, ext: str='mp4') -> typing.Tuple[str,bool]:
    '''
    fileprefix
    ext
    '''

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
    '''
    Determine if the file is in h265 format.

    Params:
    filename: str


    '''
    media_info = pymediainfo.MediaInfo.parse(filename)
    all_track_data = list(map(lambda x: x.to_data(), media_info.tracks))
    video_tracks = filter(lambda x: x['track_type'] == 'Video', all_track_data)
    # pprint.pprint(list(video_tracks))

    video_formats = []
    for curr_video_track in video_tracks:
        try:
            video_formats.append(curr_video_track['codec_id'])
        except KeyError:
            video_formats.append(curr_video_track['commercial_name'])

    if 'hev1' in video_formats or 'V_MPEGH/ISO/HEVC' in video_formats:
        return True

    logger.info(f"Formats in '{filename}' => {video_formats}")

    # No h265 was found
    return False

def transcode_file(filename, new_file_name):
    '''Handle transcoding a single file.
    '''
    call_params = [
        'ffmpeg',   '-y',
        # '-hwaccel', # 'cuda',
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


def process_file(filename):
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

        new_file_name, tmp_file = determine_new_filename(fileprefix,
                                                         output_extension)

        transcode_file(filename, new_file_name)

        size_old = os.path.getsize(filename)
        size_new = os.path.getsize(new_file_name)

        file_difference = size_new - size_old

        logger.info(f"Size old:'{size_old:,}', new: '{size_new:,}' -> " +
            f"Diff: {file_difference:,} ({file_difference / size_old * 100:.2f}%)")

        os.remove(filename)
        os.remove(filename + '.log')

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
            # logger.error(f"Skipping {filename} for reason {exc}")
            pass

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

if __name__ == '__main__':
    #logging.BASIC_FORMAT = '%(asctime)s - %(name)s - %(thread)d - %(levelname)s - %(message)s'
    logging.BASIC_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=logging.BASIC_FORMAT)

    args = parse_args()

    # Change to path specified
    os.chdir(args.path)

    # Recursive or just that directory
    if args.recursive:
        process_recursive()
    else:
        process_dir()
