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
import traceback
import typing

# External imports
import ffmpeg
import psutil

# Local imports
from . import ffmpeg_utils, utils


# Global objs
logger = logging.getLogger(__name__)
lock = multiprocessing.Lock()

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

# Exceptions
class SkipFile(Exception):
    """Exception thrown when we just want to skip a file processing.

    Args:
        Exception (_type_): _description_
    """

# Functions
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

def timedelta_parse(value: str) -> datetime.timedelta:
    """Convert input string to a datetime.timedelta object.

    Args:
        value (str): Timedelta string representation.

    Returns:
        datetime.timedelta: object representation.
    """
    value = re.sub(r"[^0-9:.]", "", value)
    if not value:
        return

    return datetime.timedelta(**{
        key:float(val) for val, key in zip(
            value.split(":")[::-1],
            ("seconds", "minutes", "hours", "days")
        )
    })

def read_total_frames(input_filename: str, full_metadata: dict, video_streams_data: list) -> int:
    """Read the total number of frames from a file's metadata.

    Args:
        full_metadata (dict): The file metadata from fetch_file_data.

    Raises:
        SkipFile: Thrown when we can't determine the frame count.

    Returns:
        int: Frame count.
    """
    # Simple case
    if 'nb_frames' in video_streams_data[0]:
        return float(video_streams_data[0]['nb_frames'])

    total_frames = -1
    match video_streams_data[0]['codec_name']:
        case 'av1' | 'flv1' | 'h264' | 'msmpeg4v3' | 'rv40' | 'vp8' | 'vp9':
            # Split 'avg_frame_rate': '2997/100' or '982057/32768' to 29.97
            # Can be 0/0
            if 'avg_frame_rate' in video_streams_data[0] and video_streams_data[0]['avg_frame_rate'] != '0/0':
                frame_base, divisor = video_streams_data[0]['avg_frame_rate'].split('/')
            elif 'r_frame_rate':
                frame_base, divisor = video_streams_data[0]['r_frame_rate'].split('/')

            try:
                frame_rate = float(frame_base) / float(divisor)
            except ZeroDivisionError:
                logger.error(f"Zero division error: {pprint.pformat(video_streams_data)}")
                raise

            if 'duration' in video_streams_data[0]:
                duration_str = video_streams_data[0]['duration']
            else:
                try:
                    # Duration can sometimes be DURATION or DURATION-eng
                    duration_key = list(filter(
                        lambda y: y[:8] == 'DURATION',
                        video_streams_data[0]['tags'].keys(),
                    ))[0]
                    duration_str = video_streams_data[0]['tags'][duration_key]
                except (IndexError,KeyError):
                    if 'duration' in full_metadata['format']:
                        duration_str = full_metadata['format']['duration']
                    else:
                        logger.error(pprint.pformat(full_metadata))
                        raise SkipFile(f"Unable to determine duration: {video_streams_data}")

            duration = (
                timedelta_parse(duration_str) -
                timedelta_parse(video_streams_data[0]['start_time'])
            ).total_seconds()

            total_frames = duration * frame_rate
        case 'mpeg1video' | 'mpeg2video' | 'mpeg4' | 'vc1' | 'wmv1' | 'wmv2' | 'wmv3':
            if video_streams_data[0]['avg_frame_rate'] != '0/0':
                frame_rate_definition = video_streams_data[0]['avg_frame_rate']
            elif video_streams_data[0]['r_frame_rate'] != '0/0':
                frame_rate_definition = video_streams_data[0]['r_frame_rate']
            else:
                msg = "Unable to read frame rate from " +\
                    f"{video_streams_data[0]['codec_name']} in '{input_filename}'"
                logger.error(msg)
                raise SkipFile(msg)

            frame_base, divisor = frame_rate_definition.split('/')
            if 'duration' in video_streams_data[0]:
                duration = float(video_streams_data[0]['duration'])
            elif 'duration' in full_metadata['format']:
                # Duration isn't set on the video stream
                duration = float(full_metadata['format']['duration'])
            else:
                msg = f"Unable to determine duration"
                logger.error(f"{msg}\nVideo metadata: {pprint.pformat(full_metadata)}")
                raise SkipFile(msg)

            total_frames = duration * (float(frame_base) / int(divisor))
        case _:
            msg = "Unknown codec - read frame count from codec: " +\
                f"{video_streams_data[0]['codec_name']} in '{input_filename}'"
            logger.error(msg)
            raise SkipFile(msg)

    return total_frames


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
    full_metadata = ffmpeg_utils.fetch_file_data(input_filename)
    logger.debug(pprint.pformat(full_metadata))
    video_streams_data = list(filter(
        lambda x: x['codec_type'] == 'video' and x['codec_name'] != 'mjpeg',
        full_metadata['streams']
    ))
    total_frames = read_total_frames(input_filename, full_metadata, video_streams_data)

    # Fetch the video_formats
    video_formats = list(map(
        lambda x: x['codec_name'],
        filter(
            lambda x: x['disposition']['attached_pic'] == 0,
            video_streams_data,
        ),
    ))

    # Detect embedded images
    extra_params = {}
    for i in range(len(full_metadata['streams'])):
        if full_metadata['streams'][i]['codec_type'] == 'video' and \
            full_metadata['streams'][i]['disposition']['attached_pic']:
            # Attached images should just be copied.
            extra_params[f'codec:{i}'] = 'copy'




    # Check the video size
    # To handle:
    # "Picture height must be an integer multiple of the specified chroma subsampling"
    # This is an issue with files with the following specs:
    # Video: h264 (Main) (avc1 / 0x31637661), yuv420p(tv, smpte170m/smpte170m/bt709,
    #        progressive), 720x405, 3948 kb/s, SAR 1:1 DAR 16:9, 29.97 fps, 29.97 tbr,
    #        30k tbn (default)
    # The issue being the 405, not being divisble by 4 or 2:
    # https://ffmpeg.org/pipermail/ffmpeg-user/2015-July/027727.html
    # To track down, how to calculate which one from the parameters
    # Most commonly this is handled by a scale paramter:
    # -filter:v "scale=720:-2"
    height_modulo = video_streams_data[0]['height'] % 4
    width_modulo  = video_streams_data[0]['width']  % 4
    if height_modulo != 0 or width_modulo != 0:
        if height_modulo != 0 ^ width_modulo != 0:
            # Both are bad, explicit values have to be used for both
            scale_value = f"{video_streams_data[0]['height'] + height_modulo}:" + \
                f"{video_streams_data[0]['width'] + width_modulo}:"
        else:
            if width_modulo != 0:
                # Set scale=-2:<heigth>
                scale_value = f"-2:{video_streams_data[0]['height']}"
            if height_modulo != 0:
                # Set scale=<width>:-2
                scale_value = f"{video_streams_data[0]['width']}:-2"
        extra_params['vf'] = f"scale={scale_value}"


    # Above here should be split off into its own function.

    logger.debug(f"Extra params: {extra_params}")
    logger.info(f"Video formats in '{input_filename}' => {pprint.pformat(video_formats)}")

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
                **extra_params,         # Any extra parameters
                'dn':      None,        # Ignore the data streams (most seem to be
                                        #  "ffmpeg GPAC ISO Hint Handler")
            },
            # vf = "scale=trunc(iw/2)*2:trunc(ih/2)*2",
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

    @transcode_cmd.on("terminated")
    def on_terminated():
        logger.error("terminated before coversion finished")

    try:
        transcode_cmd.execute()
    except ffmpeg.FFmpegFileNotFound as exc:
        raise SkipFile(f"Input file '{input_filename}' is missing") from exc
    except ffmpeg.FFmpegInvalidCommand as exc:
        raise RuntimeError(f"Invalid ffmpeg command: {exc}") from exc
    except ffmpeg.FFmpegError as exc:
        # Save as much of the output so the situation can be investigated effectively.
        with open(f'{input_filename}.err','w', encoding='utf-8') as f:
            f.write(
                f"Args:\n{exc.arguments}\n" +
                f"CLI:\n{' '.join(exc.arguments)}\n" +
                f"Stderr:\n{exc.message}"
            )
        raise

def process_file(filename: str, args: argparse.Namespace, delete_orig: bool = True, ) -> int:
    '''
    Process a single file to h265
    '''
    try:
        new_file_name = ''
        if not os.path.exists(filename):
            raise SkipFile("file no longer present")

        if os.path.isdir(filename):
            raise SkipFile("is a directory")

        if os.stat(filename).st_size == 0:
            raise SkipFile("is zero size")

        try:
            fileprefix, exten = filename.rsplit('.', 1)
        except ValueError:
            raise SkipFile("invalid file format") from None

        if exten.lower() not in ACCEPTED_EXTENSIONS:
            raise SkipFile("not a file to process")

        # Check the media, is it not the desired codec
        if ffmpeg_utils.check_codec(filename, args.video_codec):
            raise SkipFile(f"file is already '{args.video_codec}'")

        if exten == 'mkv':
            output_extension = 'mkv'
        else:  # Default
            output_extension = DEFAULT_OUTPUT_EXTENSION

        new_file_name, tmp_file = determine_new_filename(
            fileprefix,
            output_extension
        )

        transcode_file_ffmpeg(
            filename, new_file_name,
            video_codec=ffmpeg_utils.codec_map[args.video_codec]['codec'],
            audio_codec=args.audio,
        )

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
    except ffmpeg.errors.FFmpegError as exc:
        logger.error(
            "Exception occurred transcoding file " +
            f"'{filename}': {exc.__class__}, {exc}"
        )
        if new_file_name != '' and os.path.getsize(new_file_name) == 0:
            logger.error(f"Deleting zero length output: {new_file_name}")
            os.remove(new_file_name)
        raise SkipFile("Generic Error") from None
    except Exception as exc:
        logger.error(f"Exception occurred transcoding file '{filename}': {exc.__class__}, {exc}")
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error(
            pprint.pformat(
                traceback.format_exception(exc_type, exc_value, exc_traceback)
            )
        )
        raise SkipFile("Generic Error") from None

def process_dir(args: argparse.Namespace) -> int:
    '''Process appropriate files in a directory.
    '''

    dir_space_difference = 0

    for filename in sorted(os.listdir('.')):
        try:
            file_difference = process_file(filename, args)
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

def process_recursive(args: argparse.Namespace):
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
        dir_diff = process_dir(args)
        total_difference += dir_diff
        os.chdir(root_dir)

    logger.info(f"Total difference: {total_difference:,}")

def parse_args():
    '''Parse arguments passed to application.
    '''
    parser = argparse.ArgumentParser(description='Bulk converter')

    utils.add_common_arguments(parser=parser)

    # Add app specific CLI arguments.
    parser.add_argument(
        '--path',
        type=pathlib.Path,
        help='Path to process',
        default='.'
    )
    parser.add_argument('-r', '--recursive', action='store_true')
    parser.add_argument(
        '-v', '--video',
        default='x265',
        help='Video codec to use (default: %(default)s)',
    )
    parser.add_argument(
        '-a', '--audio',
        default='aac',
        help='Video codec to use (default: %(default)s)',
    )
    parser.set_defaults(recursive=False)

    prog_args = parser.parse_args()

    # Verify the codec is known
    found_video_codec = False
    for curr_codec, codec_data in ffmpeg_utils.codec_map.items():
        if prog_args.video in codec_data['alias']:
            prog_args.video_codec = curr_codec
            found_video_codec = True
            break

    if found_video_codec is False:
        print(f"Video format '{prog_args.video}' not found")
        return

    return prog_args

def main() -> None:
    """Main function"""
    args = parse_args()
    if args is None:
        return

    utils.setup_logging(args=args)

    logger.debug(f"Args: {args}")

    # Change to path specified
    os.chdir(args.path)

    # Recursive or just that directory
    if args.recursive:
        process_recursive(args)
    else:
        process_dir(args)

if __name__ == '__main__':
    main()
