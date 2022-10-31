'''Concatenate two video files together.

build a file with lines in the following format:
file '<input #1>.mp4'
file '<input #2>.mp4'

assuming the file is called 'temp.txt' the ffmpeg command is the following:

ffmpeg -safe 0 -f concat -i temp.txt -c copy <output>.mp4
'''
