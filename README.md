# Video Processing utils
General video processing utilities (mostly using ffmpeg).

## Prerequisites / Install:
* ffmpeg + ffprobe (in case you end up installing manually).
* libmediainfo-dev (being depreciated)
* pip
  * psutil
  * pymediainfo (being depreciated)


## Functions:
### convert_video

Convert video files to a consistent format.

#### python function

#### CLI

Default mode converts all files in the current directory to h.265.
```
python3 /<path to code>/convert_video.py
```

### create_subtitles


### embed_subtitles

### concat_video
Join multiple input files together to a single output video.
