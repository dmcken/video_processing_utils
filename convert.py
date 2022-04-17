import logging
import os
import psutil
import subprocess
import sys
import threading
import time
import traceback

try:
    import Queue
except ImportError:
    import queue

logging.BASIC_FORMAT = '%(asctime)s - %(name)s - %(thread)d - %(levelname)s - %(message)s'
logging.basicConfig(level = logging.DEBUG, format = logging.BASIC_FORMAT)

def processDir():
    count = 0
    for filename in os.listdir('.'):
        try:
            try:
                fileprefix, exten = filename.rsplit(u'.',1)
            except ValueError:
                continue

            newFileName = fileprefix + u'.mp4'
            
            if exten.lower() not in ['3gp', 'asf', 'avi', 'flv', 'm2v', 'm4v', 'mov', 'mpeg', 'mpg', 'ogm', 'rm', 'rmvb', 'vob', 'webm', 'wmv', 'xvid']:
                continue
            callParams = [
                'ffmpeg', '-y',
                '-i', filename,
                #'-vf', "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                '-c', 'copy',
                '-c:v', 'libx265',
                '-c:a', 'aac',
                '-map', '0',
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
    root_dir = os.getcwd()

    dirs_to_process = map(lambda x: x[0], os.walk('.'))
    for curr_dir in dirs_to_process:
        logging.error("Processing directory: {0}".format(curr_dir))
        os.chdir(curr_dir)
        # printDir()
        processDir()
        os.chdir(root_dir)
        
