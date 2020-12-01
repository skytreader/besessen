import sys
import time
import logging
import os
import subprocess
from abc import ABC
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, LoggingEventHandler

"""
This script watches all Typescript files in the current directory and compiles
them if and when they change.
"""

class CompileEventHandler(FileSystemEventHandler, ABC):

    def __init__(self, build_dir=None, file_exts=()):
        super(CompileEventHandler, self).__init__()
        self.build_dir = build_dir[0:-1] if build_dir and build_dir[-1] == "/" else build_dir
        self.extensions = ((x if x.startswith(".") else "." + x) for x in file_exts)

        if os.path.exists(self.build_dir):
            if not os.path.isdir(self.build_dir):
                logging.error("Given build dir (%s) is not a directory." % (self.build_dir))
        else:
            logging.info("No build directory found. Building for the first time...")
            os.mkdir(self.build_dir)
            for dirpath, dirnames, filenames in os.walk("."):
                split_path = dirpath.split(os.sep)
                if len(split_path) > 1:
                    if dirpath.split(os.sep)[1] == "node_modules":
                        continue

                for name in filenames:
                    if self.__should_observe(name):
                        fullfilename = os.path.join(dirpath, name)
                        self.compile(fullfilename)

    def __should_observe(self, fname):
        for extension in self.extensions:
            if fname.endswith(extension):
                return True
        return False

    @abstractmethod
    def compile(self, src):
        pass
    
    def __delete(self, fname):
        outfile = self.__to_js(fname)
        subprocess.call(["rm", outfile])
        logging.info("deleted %s" % outfile)

    def __is_ts_event(self, event):
        return not event.is_directory and self.__should_observe(event.src_path)

    def on_created(self, event):
        super(CompileEventHandler, self).on_created(event)
        if self.__is_ts_event(event):
            logging.debug("TS created event %s" % event)
            self.__compile(event.src_path)

    def on_deleted(self, event):
        super(CompileEventHandler, self).on_deleted(event)
        if self.__is_ts_event(event):
            logging.debug("TS delete event %s" % event)
            self.__delete(event.src_path)

    def on_modified(self, event):
        super(CompileEventHandler, self).on_modified(event)
        if self.__is_ts_event(event):
            logging.debug("TS modified event %s" % event)
            self.__compile(event.src_path)

    def on_moved(self, event):
        """
        This assumes that you did not move a ".js" file to something of another
        extension.
        """
        super(CompileEventHandler, self).on_moved(event)
        if self.__is_ts_event(event):
            logging.debug("TS moved event %s" % event)
            self.__delete(event.src_path)
            if self.__should_observe(event.dest_path):
                self.__compile(event.dest_path)

class TSCompiler(CompileEventHandler):

    def __init__(sefl, build_dir):
        super().__init__(build_dir, ("ts",))
    
    def __to_js(self, filename):
        """
        Assumes that you give it ".ts" files and changes the extension to ".js".
        """
        filename_parse = filename.split(".")
        sans_extension = ".".join(filename_parse[0:-1])
        if self.build_dir:
            sans_extension_parse = sans_extension.split("/")
            sans_extension_parse[-2] = self.build_dir
            sans_extension = "/".join(sans_extension_parse)
        return sans_extension + ".js"
    
    def compile(self, src):
        outfile = self.__to_js(src)
        subprocess.call([
            "node_modules/typescript/bin/tsc", "--lib", "es2015,es2015.iterable,dom", "--outFile", outfile, src
        ])
        logging.info("compiled %s to %s" % (src, outfile))

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    path = sys.argv[1] if len(sys.argv) > 1 else '.'
    observer = Observer()
    observer.schedule(CompileEventHandler("jsbuild"), path, recursive=True)
    observer.start()
    logging.info("Watching directory...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
