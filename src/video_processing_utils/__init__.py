'''Main module init'''

__version__ = "0.0.12"

from .ffmpeg_utils import concat_ffmpeg_demuxer, \
    fetch_file_metadata, \
    fetch_file_data
