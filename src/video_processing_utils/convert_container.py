'''
Convert

From:
https://stackoverflow.com/questions/40077681/ffmpeg-converting-from-mkv-to-mp4-without-re-encoding

ffmpeg -find_stream_info -loglevel warning \
    -i input.mkv \
    -map 0 -codec copy -codec:s mov_text \
    output.mp4

Currently how to change a mkv to mp4
'''

# System imports
import glob
import logging
import os

# External imports
import ffmpeg

logger = logging.getLogger(__name__)

def process_dir(base_path: str = '.') -> None:
    """_summary_

    Args:
        base_path (str, optional): _description_. Defaults to '.'.
    """
    to_process = sorted(glob.glob(os.path.join(base_path,'*.mkv')))
    for curr_file in to_process:
        out_file = f"{curr_file[:-3]}mp4"
        print(f"File to convert: {curr_file} -> {out_file}")
        if os.path.exists(out_file):
            print(f"Output file: {out_file} exits, skipping")
            continue

        ffmpeg_run = ffmpeg.FFmpeg().\
            input(curr_file).\
            option('n').\
            output(
                out_file,
                {
                    'map': '0',
                    'codec': 'copy',
                    'codec:s': 'mov_text',
                }
            )

        @ffmpeg_run.on("progress")
        def on_progress(progress: ffmpeg.Progress) -> None:
            print(f"{curr_file} => {progress}", end="\r", flush=True)

        @ffmpeg_run.on("terminated")
        def on_terminated():
            print("terminated")

        @ffmpeg_run.on("completed")
        def on_completed():
            print(f"Deleting: {curr_file}")
            os.remove(curr_file)

        logger.debug(f"FFmpeg command line: {ffmpeg_run.arguments}")

        ffmpeg_run.execute()

        # break

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    process_dir()
