

'''

ffmpeg -i video.mp4 -i image.png -map 1 -map 0 -c copy -disposition:0 attached_pic out.mp4

https://www.ffmpeg.org/ffmpeg.html#toc-Main-options
https://trac.ffmpeg.org/wiki/Map

https://superuser.com/questions/597945/set-mp4-thumbnail

https://stackoverflow.com/questions/54717175/how-do-i-add-a-custom-thumbnail-to-a-mp4-file-using-ffmpeg
https://www.bannerbear.com/blog/how-to-set-a-custom-thumbnail-for-a-video-file-using-ffmpeg/
'''
