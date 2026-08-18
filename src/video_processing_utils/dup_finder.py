'''Find likely-duplicate videos in a media library.

Detects two kinds of duplicate:
  - The same content re-encoded at a different resolution/bitrate/codec.
  - The same content with an intro/outro/credits added at one end (so the
    two files have different durations and don't line up frame-for-frame
    from the start).

Approach: for each file, sample a perceptual hash (dHash) at a fixed time
interval across its whole duration, giving a hash *sequence*. Two files are
compared by sliding one sequence over the other to find the offset with the
lowest average Hamming distance over the overlapping region - this is the
same idea as audio fingerprinting cross-correlation. An offset of ~0 with
full overlap is "same content, different encode"; a non-zero offset with
partial overlap is "same content, shifted by an intro/outro".

This intentionally only *reports* possible duplicate groups - it never
deletes or modifies a file. Perceptual hashing has false positives, and
these are often sentimental/irreplaceable media files, so removing anything
is left to the user after reviewing the report.

Note: an earlier version of this scaffold planned to use the `videohash`
package (already a project dependency) for a fast whole-video hash. As of
writing, `videohash` is broken in this environment - it depends on
`imagedominantcolor`, which calls `PIL.Image.ANTIALIAS`, removed in
Pillow >= 10. Rather than take on fixing (or forking) yet another upstream
dependency, this module implements its own hashing directly via ffmpeg,
which also turned out simpler: a single sequence-alignment method handles
both duplicate scenarios above, rather than needing two separate mechanisms.
'''

# System imports
import argparse
import dataclasses
import itertools
import logging
import os
import pathlib
import pprint

# External imports
import ffmpeg

# Local imports
from . import ffmpeg_utils, utils
from .cli import walk_files
from .convert_video import ACCEPTED_EXTENSIONS

logger = logging.getLogger(__name__)

# Frames are downscaled to FRAME_HASH_WIDTH x FRAME_HASH_HEIGHT greyscale
# before hashing (a dHash needs one extra column to diff against).
FRAME_HASH_HEIGHT = 8
FRAME_HASH_WIDTH = FRAME_HASH_HEIGHT + 1
FRAME_HASH_BYTES = FRAME_HASH_WIDTH * FRAME_HASH_HEIGHT
HASH_BITS = FRAME_HASH_HEIGHT * FRAME_HASH_HEIGHT  # 64 for the 8x8 default


@dataclasses.dataclass
class VideoInfo:
    '''Basic technical info about a video file, used for the report and for
    the cheap duration-based prefilter.
    '''
    path: str
    duration: float
    width: int
    height: int
    size_bytes: int


@dataclasses.dataclass
class DuplicateMatch:
    '''A detected match between two files.'''
    file_a: str
    file_b: str
    distance: float    # average per-frame Hamming distance over the overlap (0-64, lower = more similar)
    offset_seconds: float
    overlap_fraction: float  # fraction of the shorter sequence that overlapped


def probe_video_info(path: str) -> VideoInfo:
    """Fetch basic technical info (resolution/duration/size) for a video file.

    Args:
        path (str): Path to the video file.

    Raises:
        ValueError: If no (non-attached-picture) video stream is found.

    Returns:
        VideoInfo: Technical info about the file.
    """
    metadata = ffmpeg_utils.fetch_file_data(path)
    video_streams = [
        curr_stream for curr_stream in metadata['streams']
        if curr_stream['codec_type'] == 'video' and
            curr_stream['disposition']['attached_pic'] == 0
    ]
    if not video_streams:
        raise ValueError(f"No video stream found in '{path}'")
    stream = video_streams[0]

    duration = metadata.get('format', {}).get('duration') or stream.get('duration')
    if duration is None:
        raise ValueError(f"Could not determine duration of '{path}'")

    return VideoInfo(
        path=path,
        duration=float(duration),
        width=stream.get('width', 0),
        height=stream.get('height', 0),
        size_bytes=os.path.getsize(path),
    )


def compute_frame_hash_sequence(path: str, sample_interval_seconds: float) -> list[int]:
    """Compute a perceptual hash (dHash) for frames sampled at a fixed
    interval across the whole video.

    Args:
        path (str): Path to the video file.
        sample_interval_seconds (float): Seconds between sampled frames.

    Returns:
        list[int]: One hash per sampled frame, in playback order. Each hash
            is a `HASH_BITS`-bit integer.
    """
    fps = 1.0 / sample_interval_seconds
    cmd = ffmpeg.FFmpeg().option('v', 'error').input(path).output(
        'pipe:1',
        {
            'vf': f'fps={fps},scale={FRAME_HASH_WIDTH}:{FRAME_HASH_HEIGHT}:flags=bilinear',
            'f': 'rawvideo',
            'pix_fmt': 'gray',
            'an': None,
        },
    )
    raw_frames = cmd.execute()

    return [
        _dhash_from_frame(raw_frames[offset:offset + FRAME_HASH_BYTES])
        for offset in range(0, len(raw_frames) - FRAME_HASH_BYTES + 1, FRAME_HASH_BYTES)
    ]


def _dhash_from_frame(frame: bytes) -> int:
    """Difference hash of one `FRAME_HASH_WIDTH` x `FRAME_HASH_HEIGHT`
    greyscale frame: one bit per pixel, set if it's brighter than the pixel
    to its right.
    """
    bits = 0
    for row in range(FRAME_HASH_HEIGHT):
        row_start = row * FRAME_HASH_WIDTH
        for col in range(FRAME_HASH_HEIGHT):
            bits = (bits << 1) | (frame[row_start + col] > frame[row_start + col + 1])
    return bits


def hamming_distance(hash_a: int, hash_b: int) -> int:
    """Number of differing bits between two hashes."""
    return (hash_a ^ hash_b).bit_count()


def best_alignment(
    seq_a: list[int], seq_b: list[int], min_overlap_fraction: float,
) -> tuple[int, float, int] | None:
    """Slide `seq_b` over `seq_a` to find the offset with the lowest average
    Hamming distance over the overlapping region.

    Args:
        seq_a (list[int]): Reference frame-hash sequence.
        seq_b (list[int]): Frame-hash sequence to align against `seq_a`.
        min_overlap_fraction (float): Minimum fraction of the shorter
            sequence's length that must overlap for an offset to be
            considered, so near-empty overlaps at extreme offsets don't win
            just by chance.

    Returns:
        tuple[int, float, int] | None: `(offset, avg_distance, overlap_len)`
            for the best-aligning offset found (positive offset means
            `seq_b` starts `offset` samples into `seq_a`, e.g. `seq_a` has an
            intro `seq_b` doesn't), or None if neither sequence has any
            frames, or no offset reaches `min_overlap_fraction`.
    """
    len_a, len_b = len(seq_a), len(seq_b)
    if len_a == 0 or len_b == 0:
        return None

    min_overlap = max(1, int(min_overlap_fraction * min(len_a, len_b)))

    # Ranked by (lowest avg_distance, then largest overlap) so that when two
    # offsets tie on distance - easy to happen by chance over a short/partial
    # overlap - the one backed by more evidence wins, rather than whichever
    # offset the loop happened to reach first.
    best = None
    best_key = None
    for offset in range(-(len_b - 1), len_a):
        start = max(0, offset)
        end = min(len_a, len_b + offset)
        overlap = end - start
        if overlap < min_overlap:
            continue

        total_distance = sum(
            hamming_distance(seq_a[i], seq_b[i - offset])
            for i in range(start, end)
        )
        avg_distance = total_distance / overlap

        key = (avg_distance, -overlap)
        if best_key is None or key < best_key:
            best_key = key
            best = (offset, avg_distance, overlap)

    return best


class DisjointSet:
    """Minimal union-find, used to group pairwise matches into duplicate
    clusters (e.g. the same movie present in three different resolutions).
    """

    def __init__(self, items):
        self._parent = {item: item for item in items}

    def find(self, item):
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, item_a, item_b):
        root_a, root_b = self.find(item_a), self.find(item_b)
        if root_a != root_b:
            self._parent[root_a] = root_b


def find_duplicates(
    file_list: list[str],
    sequence_interval: float,
    sequence_threshold: float,
    min_overlap_fraction: float,
    max_duration_diff: float,
) -> tuple[list[list[str]], dict[str, VideoInfo], list[DuplicateMatch]]:
    """Scan `file_list` for likely duplicates.

    Args:
        file_list (list[str]): Video files to compare.
        sequence_interval (float): Seconds between sampled frames when
            hashing each file.
        sequence_threshold (float): Maximum average per-frame Hamming
            distance (0-`HASH_BITS`) over the aligned overlap for two files
            to be considered a match.
        min_overlap_fraction (float): Minimum fraction of the shorter file's
            sampled frames that must align for a match.
        max_duration_diff (float): Only compare pairs whose durations differ
            by less than this many seconds - a cheap prefilter so unrelated
            files never get their (expensive) hash sequences computed.

    Returns:
        tuple[list[list[str]], dict[str, VideoInfo], list[DuplicateMatch]]:
            Duplicate groups (each a list of 2+ paths), technical info per
            file that was successfully probed, and the individual pairwise
            matches that produced the groups.
    """
    infos: dict[str, VideoInfo] = {}
    for path in file_list:
        try:
            infos[path] = probe_video_info(path)
        except (ValueError, ffmpeg.errors.FFmpegError) as exc:
            logger.warning(f"Skipping '{path}': could not read video info ({exc})")

    paths = list(infos.keys())

    # Cheap prefilter: only files with at least one duration-close partner
    # are worth the cost of computing a hash sequence for.
    candidate_pairs = [
        (path_a, path_b)
        for path_a, path_b in itertools.combinations(paths, 2)
        if abs(infos[path_a].duration - infos[path_b].duration) <= max_duration_diff
    ]
    paths_needing_hash = {path for pair in candidate_pairs for path in pair}

    logger.info(
        f"{len(paths)} file(s) probed, {len(paths_needing_hash)} have at " +
        f"least one duration-close candidate and will be hashed " +
        f"({len(candidate_pairs)} pair(s) to compare)."
    )

    sequences: dict[str, list[int]] = {}
    for index, path in enumerate(sorted(paths_needing_hash), start=1):
        logger.info(f"Hashing ({index}/{len(paths_needing_hash)}): '{path}'")
        try:
            sequences[path] = compute_frame_hash_sequence(path, sequence_interval)
        except ffmpeg.errors.FFmpegError as exc:
            logger.warning(f"Skipping '{path}': could not hash frames ({exc})")

    matches: list[DuplicateMatch] = []
    dsu = DisjointSet(paths)

    for path_a, path_b in candidate_pairs:
        seq_a, seq_b = sequences.get(path_a), sequences.get(path_b)
        if seq_a is None or seq_b is None:
            continue

        result = best_alignment(seq_a, seq_b, min_overlap_fraction)
        if result is None:
            continue
        offset, avg_distance, overlap = result

        if avg_distance <= sequence_threshold:
            matches.append(DuplicateMatch(
                file_a=path_a,
                file_b=path_b,
                distance=avg_distance,
                offset_seconds=offset * sequence_interval,
                overlap_fraction=overlap / min(len(seq_a), len(seq_b)),
            ))
            dsu.union(path_a, path_b)

    groups: dict[str, list[str]] = {}
    for path in paths:
        groups.setdefault(dsu.find(path), []).append(path)

    duplicate_groups = [members for members in groups.values() if len(members) > 1]
    return duplicate_groups, infos, matches


def format_size(num_bytes: float) -> str:
    """Human-readable byte size, e.g. '1.3GB'."""
    for unit in ('B', 'KB', 'MB', 'GB'):
        if num_bytes < 1024:
            return f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f}TB"


def format_duration(seconds: float) -> str:
    """HH:MM:SS representation of a duration in seconds."""
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def print_report(
    duplicate_groups: list[list[str]],
    infos: dict[str, VideoInfo],
    matches: list[DuplicateMatch],
) -> None:
    """Print a human-readable report of the duplicate groups found.

    Never deletes or otherwise touches any file - this is a report to
    support manual review only.
    """
    if not duplicate_groups:
        print("No likely duplicates found.")
        return

    match_lookup: dict[str, dict[str, DuplicateMatch]] = {}
    for match in matches:
        match_lookup.setdefault(match.file_a, {})[match.file_b] = match
        match_lookup.setdefault(match.file_b, {})[match.file_a] = match

    total_reclaimable = 0

    print(
        f"Found {len(duplicate_groups)} possible duplicate group(s). " +
        "Review before deleting anything - this is a report only.\n"
    )

    for group_index, members in enumerate(duplicate_groups, start=1):
        members_sorted = sorted(members, key=lambda p: infos[p].size_bytes, reverse=True)
        keeper = members_sorted[0]
        reclaimable = sum(infos[path].size_bytes for path in members_sorted[1:])
        total_reclaimable += reclaimable

        print(f"Group {group_index} - possible space savings: {format_size(reclaimable)}")
        for path in members_sorted:
            info = infos[path]
            marker = "keep? " if path is keeper else "      "
            print(
                f"  {marker}{path}\n" +
                f"        {info.width}x{info.height}  {format_size(info.size_bytes)}  " +
                f"{format_duration(info.duration)}"
            )

        for path_a, path_b in itertools.combinations(members_sorted, 2):
            match = match_lookup.get(path_a, {}).get(path_b)
            if match is not None:
                print(
                    f"      match: '{os.path.basename(path_a)}' <-> " +
                    f"'{os.path.basename(path_b)}' " +
                    f"(distance={match.distance:.1f}/{HASH_BITS}, " +
                    f"offset={match.offset_seconds:+.1f}s, " +
                    f"overlap={match.overlap_fraction:.0%})"
                )
        print()

    print(f"Total possible space savings if one copy is kept per group: {format_size(total_reclaimable)}")
    print("\nThis is a report only - no files have been modified or deleted.")


def create_parser() -> argparse.ArgumentParser:
    """Arg handler for the video duplicate finder CLI.

    Returns:
        argparse.ArgumentParser: Parser configured with the finder's options.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Scan a media library for likely-duplicate videos - the same "
            "content at a different resolution/bitrate/codec, or with an "
            "intro/outro added - and report them for manual review. Never "
            "deletes or modifies anything."
        ),
    )
    parser.add_argument(
        '--path',
        type=pathlib.Path,
        default='.',
        help="Path to the media library to scan (default: %(default)s)",
    )
    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        default=False,
        help="Recurse into subdirectories of --path",
    )
    parser.add_argument(
        '--sequence-interval',
        type=float,
        default=5.0,
        help="Seconds between sampled frames when hashing each file; lower " +
            "is slower but more precise (default: %(default)s)",
    )
    parser.add_argument(
        '--sequence-threshold',
        type=float,
        default=10.0,
        help=f"Maximum average per-frame Hamming distance (0-{HASH_BITS}) " +
            "over the aligned overlap to flag two files as a possible " +
            "duplicate (default: %(default)s)",
    )
    parser.add_argument(
        '--min-overlap',
        type=float,
        default=0.5,
        help="Minimum fraction (0-1) of the shorter file's sampled frames " +
            "that must align for a match (default: %(default)s)",
    )
    parser.add_argument(
        '--max-duration-diff',
        type=float,
        default=300.0,
        help="Only compare files whose durations differ by less than this " +
            "many seconds - keeps the scan from hashing files that can't " +
            "plausibly be related (default: %(default)s)",
    )
    utils.add_common_arguments(parser=parser)

    return parser


def parse_cli() -> argparse.Namespace:
    """Return the parsed cli arguments for the video duplicate finder.

    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = create_parser()
    return parser.parse_args()


def scan_for_video_files(base_path: str, recursive: bool) -> list[str]:
    """Find candidate video files to hash and compare.

    Args:
        base_path (str): Path to scan.
        recursive (bool): Recurse into subdirectories if True, otherwise
            only scan `base_path` itself.

    Returns:
        list[str]: Video files found, filtered to `ACCEPTED_EXTENSIONS`.
    """
    if recursive:
        candidates = walk_files(base_path)
    else:
        candidates = [
            os.path.join(base_path, curr_file)
            for curr_file in os.listdir(base_path)
        ]

    return sorted(
        curr_file for curr_file in candidates
        if os.path.isfile(curr_file) and
            curr_file.rsplit('.', 1)[-1].lower() in ACCEPTED_EXTENSIONS
    )


def main() -> None:
    """CLI entry point for vudupcheck."""
    args = parse_cli()
    utils.setup_logging(args=args)
    logger.debug(f"Parsed arguments: {pprint.pformat(args)}")

    file_list = scan_for_video_files(str(args.path), args.recursive)
    logger.info(f"Found {len(file_list)} candidate video file(s) under '{args.path}'")

    duplicate_groups, infos, matches = find_duplicates(
        file_list,
        sequence_interval=args.sequence_interval,
        sequence_threshold=args.sequence_threshold,
        min_overlap_fraction=args.min_overlap,
        max_duration_diff=args.max_duration_diff,
    )

    print_report(duplicate_groups, infos, matches)

if __name__ == '__main__':
    main()
