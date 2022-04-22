'''
Embed subtitles into the video file:

ffmpeg
    # Video file
    -i Blitz.2011.1080p.BrRip.mp4 
    # We are only working with .srt files and permit unicode
    -sub_charenc UTF-8 -f srt
    # SRT file
    -i Blitz.2011.1080p.BrRip.srt 
    # Copy all the other streams in the video file
    -c copy
    # Embed as a separate stream
    -c:s mov_text
    # Output filename
    Blitz.2011.1080p.BrRip-embeded-sub.mp4

'''
