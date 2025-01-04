'''CLI interfaces'''

import os

def walk_files(base_path='.') -> list[str]:
    """Walk files in a directory.

    Args:
        path (str, optional): _description_. Defaults to '.'.

    Returns:
        list[str]: _description_
    """
    file_list = []
    for root, _, files in os.walk(base_path):
        for curr_file in files:
            file_list.append(f"{os.path.join(root,curr_file)}")

    return file_list



def video_dup_finder() -> None:
    """Video duplicate finder CLI entry.
    """

    file_list = walk_files()
    print(f"Count: {len(file_list)}")

