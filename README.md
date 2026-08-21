# Video Processing utils
General video processing utilities (mostly using ffmpeg).

## Install:

### Prerequisites
* We assume ffmpeg + ffprobe are installed and are on the path.
* `vuembedsub` additionally requires `mkvmerge` (from [mkvtoolnix](https://mkvtoolnix.download/)) on the path.

### Prerequisites (win 11)

```
winget install Git.Git
winget install ffmpeg
```

### Installation via PIP

Depending on your environment a venv may be required, see [venv](https://docs.python.org/3/library/venv.html) for an directions on how to setup and activate a venv.

```bash
pip install -U git+https://github.com/dmcken/video_processing_utils.git
or
python3 -m pip install -U git+https://github.com/dmcken/video_processing_utils.git
```

### Installation via pipx

pipx can manage the environments for you, install directions available [here](https://pipx.pypa.io/stable/).

```bash
pipx install git+https://github.com/dmcken/video_processing_utils.git
```

Output:

```bash
  installed package video_processing_utils 0.0.21, installed using Python 3.12.3
  These apps are now globally available
    - vucheck
    - vuconcat
    - vucontainer
    - vuconvert
    - vudupcheck
    - vuembedsub
```

## Commands Exposed

Most commands are prefixed with vu (video utilities) and their role.

| command | description |
| --------| ----------- |
| vucheck | Check media files for decode errors by fully decoding them via ffmpeg; reports which files have problems. |
| vuconcat | Concatenate multiple video files of the same format together, creating chapter markers at concatenation points. |
| vucontainer | Convert video files between containers (e.g. .mkv/.m2ts to .mp4/.mkv) without re-encoding. |
| vuconvert | Bulk conversion of video files in a folder, output codec can be specified. |
| vudupcheck | Scan a media library and report likely-duplicate videos (different resolution/bitrate/codec, or the same content with an intro/outro added) for manual review. Never deletes anything. |
| vuembedsub | Embed external subtitle files (e.g. .srt) into a .mkv as new subtitle tracks, without re-encoding and without touching any subtitles already in the file. |

### vuembedsub usage

```bash
vuembedsub --video "Movie.mkv" --sub "Movie[ENG].srt" --title English
```

- Only works on `.mkv` files - it shells out to `mkvmerge` rather than ffmpeg, specifically because ffmpeg's own SRT reader silently drops any subtitle-styling syntax it doesn't recognise (e.g. positioned/faded title cards some subtitle files use), while `mkvmerge` preserves the subtitle file's content exactly as authored.
- Repeat `--sub` to embed multiple subtitle files in one pass; `--lang`/`--title` are matched to the `--sub` at the same position.
- If `--lang` is omitted for a given subtitle, a `[XXX]`-style tag in that file's own name is used automatically (e.g. `Movie[ENG].srt` -> language `eng`).
- The video is rewritten via a temporary file and only replaced once mkvmerge finishes successfully; the subtitle file(s) are never modified or deleted.

## Functions:

TODO: move to some auotmatic doc generator from docstrings.
