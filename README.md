# Video Processing utils
General video processing utilities (mostly using ffmpeg).

## Install:

### Prerequisites:
* We assume ffmpeg + ffprobe are installed and are on the path.

### Installation via PIP

Depending on your environment a venv may be required, see [venv](https://docs.python.org/3/library/venv.html) for an directions on how to setup and activate a venv.

```bash
pip install -U git+https://github.com/dmcken/video_processing_utils.git
```

### Installation via pipx

pipx can manage the environments for you, install directions available [here](https://pipx.pypa.io/stable/).

```bash
pipx install -U git+https://github.com/dmcken/video_processing_utils.git

Output:

  installed package video_processing_utils 0.0.5, installed using Python 3.12.3
  These apps are now globally available
    - vuconcat
    - vucontainer
    - vuconvert
    - vumerge
```

## Commands Exposed

Most commands are prefixed with vu (video utilities) and their role.

| command | description |
| --------| ----------- |
| vuconcat | Concatenate multiple video files of the same format together, creating chapter markers at conatenation points. |
| vucontainer |  |
| vuconvert | Bulk conversion of video files in the folder, output codec can be specified. |
| vumerge |   |

## Functions:

TODO: move to some auotmatic doc generator from docstrings.
