'''
Bulk re-encode my mp4 h264 videos to h265


'encoded_library_name': 'x264'

'''




import logging
import os
import pprint
import psutil
import pymediainfo
import queue
import subprocess
import sys
import threading
import time
import traceback

logger = logging.getLogger(__name__)


def determine_new_filename(fileprefix, ext=u'mp4'):
    '''
    fileprefix
    ext
    '''

    newFileName = u"{0}.{1}".format(fileprefix, ext)

    if not os.path.exists(newFileName):
        return (newFileName, False)

    # The file exists so we need to try an incrementing number
    i = 1
    while True:
        newFileName = u"{0}-{1}.{2}".format(fileprefix, i, ext)
        
        if not os.path.exists(newFileName):
            return (newFileName, True)
        
        i += 1


def is_h265(filename):
    '''
    Determine if the file is in h265 format.

    Params:
    filename: str


    '''

    
    media_info = pymediainfo.MediaInfo.parse(filename)
    all_track_data = list(map(lambda x: x.to_data(), media_info.tracks))
    video_tracks = filter(lambda x: x['track_type'] == 'Video', all_track_data)
    #pprint.pprint(list(video_tracks))
    video_formats = list(map(lambda x: x['codec_id'], video_tracks))

    logger.info("Video formats for '{0}' => {1}".format(filename, video_formats))

    if 'hev1' in video_formats:
        return True
    else:
        return False



def processDir():

    accepted_extensions = [
        '3gp', 'asf', 'avi', 'flv', 'm2v', 'm4v', 'mov', 'mp4', 'mpeg', 'mpg',
        'ogm', 'rm', 'rmvb', 'vob', 'webm', 'wmv', 'xvid',
    ]


    count = 0
    for filename in os.listdir('.'):
        try:
            if os.path.isdir(filename):
                continue

            try:
                fileprefix, exten = filename.rsplit(u'.', 1)
            except ValueError:
                continue

            if exten.lower() not in accepted_extensions:
                continue

            # Check the media, is it not h265?
            if is_h265(filename):
                logger.info("File is already h265")
                continue

            newFileName, tmp_file = determine_new_filename(fileprefix, 'mp4')

            callParams = [
                'ffmpeg', '-y',
                '-i', filename,
                #'-vf', "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                '-c', 'copy',        # Catch all for an extra streams, just copy
                '-c:v', 'libx265',   # Video to H265
                '-c:a', 'aac',       # Audio to AAC
                '-map', '0',         # Map any other streams (e.g. subtitles)
                newFileName,
            ]
            logging.info(u"Starting: {0}".format(filename))
            
            progH = subprocess.Popen(
                callParams,
                stdin=subprocess.PIPE,
                stdout=open(filename + u'.log','w'),
                stderr=subprocess.STDOUT,
            )

            logging.info(u"Started: {0}".format(progH.pid))
            processData = psutil.Process(progH.pid)

            processIdle = 0
            while progH.poll() is None:
                try:
                    if processData.cpu_percent(interval = 1.0) < 2.0:
                        processIdle += 1
                    else:
                        processIdle = 0
                        
                    if processIdle > 20:
                        logging.error(u"Terminating due to inactivity")
                        progH.kill()
                        time.sleep(2)
                        os.remove(newFileName)
                        raise subprocess.CalledProcessError(-1, callParams[0])
                    
                    time.sleep(1)
                except psutil.NoSuchProcess:
                    break

            progH.wait()
            
            if progH.returncode:
                raise subprocess.CalledProcessError(progH.returncode, callParams[0])

            oldSize = os.path.getsize(filename)
            newSize = os.path.getsize(newFileName)

            logging.info(u"Old size '{0:,}', New size: '{1:,}' -> Difference: {2:,}".format(oldSize, newSize, newSize - oldSize))

            os.remove(filename)
            os.remove(filename + u'.log')

            if tmp_file:
                os.rename(newFileName, filename)

            logging.info(u"Completed: {0}".format(newFileName))
            #time.sleep(5)
            count += 1
            if count > 500:
                break
        except subprocess.CalledProcessError as e:
            logging.error(u"Got a issue from ffmpeg: {0}".format(e.returncode))
        except Exception as e:
            logging.error(u"An exception occurred: {0}, {1}".format(e.__class__, e))
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logging.error(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))

def printDir():

    for filename in os.listdir('.'):
        logging.error(u"File found: {0}".format(filename))

if __name__ == '__main__':

    logging.BASIC_FORMAT = '%(asctime)s - %(name)s - %(thread)d - %(levelname)s - %(message)s'
    logging.basicConfig(level = logging.DEBUG, format = logging.BASIC_FORMAT)

    root_dir = os.getcwd()

    dirs_to_process = map(lambda x: x[0], os.walk('.'))
    for curr_dir in dirs_to_process:
        logging.error("Processing directory: {0}".format(curr_dir))
        os.chdir(curr_dir)
        # printDir()
        processDir()
        os.chdir(root_dir)
        

