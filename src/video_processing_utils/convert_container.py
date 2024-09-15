'''
Convert 

From:
https://stackoverflow.com/questions/40077681/ffmpeg-converting-from-mkv-to-mp4-without-re-encoding

ffmpeg -find_stream_info -loglevel warning \
    -i input.mkv \
    -map 0 -codec copy -codec:s mov_text \
    output.mp4
    

'''

