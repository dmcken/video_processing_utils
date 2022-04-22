'''
Bulk re-encode my mp4 h264 videos to h265


'encoded_library_name': 'x264'


Notes:
- H.265 patent situation is still odd, ffmpeg encode of AV1 is moving at 1-2
  frames/sec which would take forever.
'''

# Built in
import logging
import multiprocessing
import os
import subprocess
import sys
import time
import traceback

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
    'vob',
    'webm', 'wmv',
    'xvid',
]
DEFAULT_OUTPUT_EXTENSION = 'mp4'

class SkipFile(Exception):
    '''
    Exception thrown when we just want to skip a file processing
    '''

# Global objs
logger = logging.getLogger(__name__)
lock = multiprocessing.Lock()

def determine_new_filename(fileprefix, ext='mp4'):
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

def is_h265(filename):
    '''
    Determine if the file is in h265 format.

    Params:
    filename: str


    '''
    media_info = pymediainfo.MediaInfo.parse(filename)
    all_track_data = list(map(lambda x: x.to_data(), media_info.tracks))
    video_tracks = filter(lambda x: x['track_type'] == 'Video', all_track_data)
    # pprint.pprint(list(video_tracks))
    video_formats = list(map(lambda x: x['codec_id'], video_tracks))

    logger.info(f"Video formats for '{filename}' => {video_formats}")

    if 'hev1' in video_formats:
        return True

    # No h265 was found
    return False

def transcode_file(filename, new_file_name):
    '''
    '''
    try:
        call_params = [
            'ffmpeg', '-y',
            '-hwaccel', 'cuda',
            '-i', filename,
            #'-vf', "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            '-c', 'copy',        # Catch all for an extra streams, just copy
            '-c:v', 'libx265',   # Video to H265
            '-c:a', 'aac',       # Audio to AAC
            '-map', '0',         # Map any other streams (e.g. subtitles)
            new_file_name,
        ]

        logger.info(f"Transcoding: {filename}")

        lock.acquire()
        psutil.Process().nice(psutil.IDLE_PRIORITY_CLASS)
        prog_h = subprocess.Popen(
            call_params,
            stdin=subprocess.PIPE,
            stdout=open(filename + '.log', 'w', encoding="utf8"),
            stderr=subprocess.STDOUT,
        )
        psutil.Process().nice(psutil.NORMAL_PRIORITY_CLASS)
        lock.release()

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
            raise subprocess.CalledProcessError(prog_h.returncode,
                                                call_params[0])
    except subprocess.CalledProcessError as exc:
        logger.error(f"Got a issue from ffmpeg: {exc.returncode}")

def process_file(filename):
    '''
    Process a single file to h265
    '''
    try:
        if not os.path.exists(filename):
            raise SkipFile("File no longer present")

        if os.path.isdir(filename):
            raise SkipFile("Is a directory")

        try:
            fileprefix, exten = filename.rsplit('.', 1)
        except ValueError:
            raise SkipFile("Invalid file format")

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
            f"Diff: {file_difference:,}")

        os.remove(filename)
        os.remove(filename + '.log')

        if tmp_file:
            os.rename(new_file_name, filename)

        logger.info(f"Completed: {new_file_name}")

        return file_difference
    except Exception as exc:
        logger.error(f"An exception occurred processing file '{filename}': {exc.__class__}, {exc}")
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error(repr(traceback.format_exception(
            exc_type, exc_value, exc_traceback)))
        raise exc

def process_dir(dir_to_process):
    '''
    '''

    dir_space_difference = 0

    os.chdir(dir_to_process)

    for filename in os.listdir('.'):
        try:
            file_difference = process_file(filename)
            dir_space_difference += file_difference
        except SkipFile:
            pass

    logger.info("Dir difference: {0:,}".format(dir_space_difference))
    return dir_space_difference

def print_dir():

    for filename in os.listdir('.'):
        logger.error(f"File found: {filename}")


if __name__ == '__main__':

    BASIC_FORMAT = '%(asctime)s - %(name)s - %(thread)d - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=logging.BASIC_FORMAT)

    root_dir = os.getcwd()

    total_difference = 0
    dirs_to_process = map(lambda x: x[0], os.walk('.'))
    for curr_dir in dirs_to_process:
        logger.error(f"Processing directory: {curr_dir}")
        dir_diff = process_dir(curr_dir)
        total_difference += dir_diff
        os.chdir(root_dir)

    logger.info("Total difference: {0:,}".format(total_difference))
