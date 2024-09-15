'''Concatenate video functions




References:
https://trac.ffmpeg.org/wiki/Concatenate
https://ffmpeg.org/ffmpeg-formats.html#Metadata-1

- Chapters:
https://www.caseyliss.com/2021/1/26/joining-files-keeping-chapters-using-ffmpeg
https://gist.github.com/cliss/53136b2c69526eeed561a5517b23cefa

'''
# System imports
import os
import subprocess
import tempfile



def concat_ffmpeg_demuxer(input_files: list[str], output_file: str, 
                          over_write=False, delete_input=False) -> None:
    """Concatenate two video files together using ffmpeg demuxer.

        

    build a file with lines in the following format:
    file '<input #1>.mp4'
    file '<input #2>.mp4'

    assuming the file is called 'temp.txt' the ffmpeg command is the following:

    `ffmpeg -safe 0 -f concat -i temp.txt -c copy <output>.mp4`

    Add '-y' to the begining if overwrite is set.

    Args:
        input (list[str]): _description_
        output (str): _description_
        over_write (bool, optional): _description_. Defaults to False.
    """
    if len(input_files) <= 1:
        raise RuntimeError("Two or more files required to concat")

    with tempfile.NamedTemporaryFile(delete_on_close=False, delete=True, dir='.') as fp:
        for curr_file in input_files:
            fp.write(f"file '{curr_file}'\n".encode('utf-8'))
        fp.close()

        cmd = ['ffmpeg']

        if over_write is True:
            cmd.append('-y')

        cmd.extend([
            '-f','concat',
            # '-safe','0',
            '-i', fp.name,
            '-c', 'copy', output_file
        ])

        result = subprocess.run(cmd)
        if result.returncode == 0:
            # Success
            pass
        else:
            print(f"FFMpeg return code: {result.returncode}")


    return