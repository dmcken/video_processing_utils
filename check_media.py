#!/usr/bin/env python3
'''Check media.

Check media via ffmpeg and 
'''
import argparse
import concurrent.futures
import gc
import glob
import os
import queue
import re
import subprocess
import sys
import time

def enqueue_output(fH, q):
    for line in iter(fH.readline, ''):
        q.put(line)
    file.close()

def read_popen_pipes(p):
    '''

    https://stackoverflow.com/questions/2804543/read-subprocess-stdout-line-by-line
    '''

    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        q_stdout, q_stderr = queue.Queue(), queue.Queue()

        pool.submit(enqueue_output, p.stdout, q_stdout)
        pool.submit(enqueue_output, p.stderr, q_stderr)

        while True:
            if p.poll() is not None and q_stdout.empty() and q_stderr.empty():
                break

            out_line = err_line = ''

            try:
                out_line = q_stdout.get_nowait()
            except queue.Empty:
                pass

            try:
                err_line = q_stderr.get_nowait()
            except queue.Empty:
                pass

            yield (out_line, err_line)

recursive_checking = True
if recursive_checking:
    search_regex = os.path.join('**', sys.argv[1])
else:
    search_regex = sys.argv[1]

print(f"Starting with regex: {search_regex}")
for curr_file in glob.glob(search_regex, recursive=recursive_checking):
    errors_count = 0
    print("Checking file '{0}': {1}".format(curr_file, errors_count), end='\r')

    ffmpeg_cmd = ['ffmpeg', '-v', 'error', '-i', curr_file, '-f', 'null', '-']

    with subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1, text=True) as progH:

        for out_line, err_line in read_popen_pipes(progH):
            if re.search("error", out_line, flags=re.I):
                errors_count += 1

            if re.search("error", err_line, flags=re.I):
                errors_count += 1

            print("Checking file '{0}': {1}".format(curr_file, errors_count), end='\r')

        ret_code = progH.poll()

        time.sleep(2)

    print()
    gc.collect()

print("Done")
