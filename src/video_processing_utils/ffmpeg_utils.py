'''Video functions.

Underlying video utility functions.



'''
# System imports
import json
import logging
import pathlib
import pprint
import tempfile

# External imports
import ffmpeg

logger = logging.getLogger(__name__)

def fetch_file_metadata(filename: str) -> str:
    """Fetch the raw metadata from a file.

    cli:
    ffmpeg -i <filename> -f ffmetadata -

    Args:
        filename (str): Filename to read metadata from.

    Returns:
        str: metadata.
    """
    cmd = ffmpeg.FFmpeg().input(
            filename
        ).output(
            '-', {'f': 'ffmetadata'}
        )
    metadata_output = cmd.execute()

    return metadata_output


def fetch_file_data(filename: str) -> dict:
    """Fetch file data via ffprobe.

    ffmpeg cli:
    ffprobe -print_format json -show_chapters -show_programs -show_streams -show_format <filename>

    Args:
        filename (str): Filename to read metadata from.

    Raises:
        RuntimeError: _description_

    Returns:
        dict: _description_
    """

    cmd = ffmpeg.FFmpeg(executable="ffprobe").input(
        filename,
        print_format="json",
        show_chapters=None,
        show_format=None,
        show_programs=None,
        show_streams=None,
    )
    media_data = json.loads(cmd.execute())

    return media_data


def concat_ffmpeg_demuxer(input_files: list[str], output_file: str,
                          over_write=False, delete_input=False) -> None:
    """Concatenate two video files together using ffmpeg demuxer.



    build a file with lines in the following format:
    file '<input #1>.mp4'
    file '<input #2>.mp4'

    assuming the file is called 'temp.txt' the ffmpeg command is the following:

    `ffmpeg -safe 0 -f concat -i temp.txt -c copy <output>.mp4`

    Add '-y' to the begining if overwrite is set.

    References:
    https://trac.ffmpeg.org/wiki/Concatenate
    https://ffmpeg.org/ffmpeg-formats.html#Metadata-1

    - Chapters:
    https://www.caseyliss.com/2021/1/26/joining-files-keeping-chapters-using-ffmpeg
    https://gist.github.com/cliss/53136b2c69526eeed561a5517b23cefa


    Random notes:
    https://superuser.com/questions/1699035/ffmpeg-extract-metadata
    https://stackoverflow.com/questions/9464617/retrieving-and-saving-media-metadata-using-ffmpeg
    https://stackoverflow.com/questions/11706049/converting-video-formats-and-copying-tags-with-ffmpeg/50580239#50580239
    https://superuser.com/questions/1691173/extracting-quicktime-mov-text-subtitles-with-ffmpeg
    https://superuser.com/questions/520510/combining-video-and-subtitle-files-as-one-video


    Args:
        input (list[str]): _description_
        output (str): _description_
        over_write (bool, optional): _description_. Defaults to False.
    """
    if len(input_files) <= 1:
        raise RuntimeError("Two or more files required to concat")

    with tempfile.NamedTemporaryFile(delete_on_close=False, delete=True, dir='.') as fp_filelist, \
         tempfile.NamedTemporaryFile(delete_on_close=False, delete=True, dir='.') as fp_metadata:

        # Read the metadata from the first file in the list and save it.
        metadata_output = fetch_file_metadata(input_files[0])
        media_data = fetch_file_data(input_files[0])

        logger.debug(f"Media data:\n{pprint.pformat(media_data['streams'])}")

        file_chapter_start = 0
        # Create the concat input file
        for curr_file in input_files:
            fp_filelist.write(f"file '{curr_file}'\n".encode('utf-8'))
            curr_file_media_data = fetch_file_data(curr_file)
            # Test media_data against the curr_file_media_data

            # Insert main chapter data
            file_chapter_end = round(
                    file_chapter_start + float(
                    curr_file_media_data['format']['duration']
                ),
                3
            )
            chapter_name = pathlib.Path(curr_file_media_data['format']['filename']).stem
            metadata_output += f"""
[CHAPTER]
TIMEBASE=1/1000
START={int(file_chapter_start * 1000)}
END={int(file_chapter_end * 1000)}
title={chapter_name}
""".encode()
            # Copy the chapters from the file if present offset by the file_chapter_start

            file_chapter_start = file_chapter_end + 1

        # Close the concat file
        fp_filelist.close()

        # Write the metadata file
        fp_metadata.write(metadata_output)
        fp_metadata.close()

        # print(f"Metadata: {fp_metadata.name}")
        # time.sleep(60)

        # Main concat call
        cmd = ffmpeg.FFmpeg()

        if over_write is True:
            cmd = cmd.option('y')

        cmd = cmd.option(
                'f','concat'
            ).input(
                fp_filelist.name
            ).input(
                fp_metadata.name
            ).output(
                output_file,
                codec='copy',
                map_metadata='1',
            )

        @cmd.on("progress")
        def on_progress(progress: ffmpeg.Progress):
            print(progress, end="\r", flush=True)

        print(cmd.arguments)

        cmd.execute()
        print()

        if delete_input:
            # Delete the input files
            pass

    return
