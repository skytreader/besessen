import sys
import time
import logging
import os
import subprocess
from abc import ABC, abstractmethod
from notifypy import Notify
from typing import Tuple
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, LoggingEventHandler

"""
ObsESsively watches your filesystem for node-related files to compile.

Find me at https://github.com/skytreader/besessen
"""

logging.getLogger().setLevel(int(os.environ.get("BESLL", logging.INFO)))

class CompileEventHandler(FileSystemEventHandler, ABC):

    def __init__(self, build_dir=None, file_exts=()):
        super(CompileEventHandler, self).__init__()
        self.build_dir = build_dir[0:-1] if build_dir and build_dir[-1] == "/" else build_dir
        self.extensions: Tuple[str, ...] = tuple(
            (x if x.startswith(".") else "." + x) for x in file_exts
        )
        # Set this property for the extension of the compiled files.
        self._compiles_to_ext: str = ""

        if build_dir is not None:
            if os.path.exists(self.build_dir):
                if not os.path.isdir(self.build_dir):
                    logging.error("Given build dir (%s) is not a directory." % (self.build_dir))
            else:
                logging.info("No build directory found. Building for the first time...")
                os.mkdir(self.build_dir)

    def _compile_all(self):
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
        subprocess.call(["rm", fname])
        logging.info("deleted %s" % fname)

    def __is_filesys_ev(self, event):
        return not event.is_directory and self.__should_observe(event.src_path)

    def on_created(self, event):
        super(CompileEventHandler, self).on_created(event)
        if self.__is_filesys_ev(event):
            logging.debug("detected created event %s" % event)
            self.compile(event.src_path)

    def on_deleted(self, event):
        super(CompileEventHandler, self).on_deleted(event)
        if self.__is_filesys_ev(event):
            logging.debug("detected delete event %s" % event)
            self.__delete(self._change_extension(event.src_path))

    def on_modified(self, event):
        super(CompileEventHandler, self).on_modified(event)
        if self.__is_filesys_ev(event):
            logging.debug("detected modified event %s" % event)
            self.compile(event.src_path)

    def on_moved(self, event):
        """
        This assumes that you did not move a ".js" file to something of another
        extension.
        """
        super(CompileEventHandler, self).on_moved(event)
        if self.__is_filesys_ev(event):
            logging.debug("detected moved event %s" % event)
            self.__delete(self._change_extension(event.src_path))
            if self.__should_observe(event.dest_path):
                self.compile(event.dest_path)

    def _change_extension(self, filename):
        """
        Changes the extension of `filename` to `newext`.
        """
        newext = self._compiles_to_ext if self._compiles_to_ext[0] == "." else "." + self._compiles_to_ext
        filename_parse = filename.split(".")
        sans_extension = ".".join(filename_parse[0:-1])
        if self.build_dir:
            sans_extension_parse = sans_extension.split("/")
            sans_extension_parse[-2] = self.build_dir
            sans_extension = "/".join(sans_extension_parse)
        return sans_extension + newext

    def send_notif(self, title, msg):
        n = Notify()
        n.title = title
        n.message = msg
        n.send()

class TSCompiler(CompileEventHandler):

    def __init__(self, build_dir):
        super().__init__(build_dir, ("ts",))
        self._compiles_to_ext = ".js"
        self._compile_all()
    
    def compile(self, src):
        outfile = self._change_extension(src)
        try:
            subprocess.check_output(
                "./node_modules/typescript/bin/tsc --lib es2015,es2015.iterable,dom --outFile %s %s" % (outfile, src),
                shell=True
            )
            logging.info("compiled %s to %s" % (src, outfile))
            self.send_notif(src, "compiled to %s" % outfile)
        except subprocess.CalledProcessError as cpe:
            logging.error("failed to compile %s" % src)
            logging.error(cpe.output)
            self.send_notif("failure: %s" % src, cpe.output)

class LessCompiler(CompileEventHandler):

    def __init__(self, build_dir):
        super().__init__(build_dir, ("less",))
        self._compiles_to_ext = ".css"
        self._compile_all()

    def compile(self, src):
        outfile = self._change_extension(src)
        try:
            subprocess.check_output(
                "./node_modules/less/bin/lessc %s %s" % (src, outfile),
                shell=True
            )
            logging.info("compiled %s to %s" % (src, outfile))
            self.send_notif(src, "compiled to %s" % outfile)
        except subprocess.CalledProcessError as cpe:
            logging.error("failed to compile %s" % src)
            logging.error(cpe.output)
            self.send_notif("failure: %s" % src, cpe.output)

# This is so custom. Maybe a plugin system?
class JinjaCMSCompiler(CompileEventHandler):

    def __init__(self):
        """
        build_dir does not matter here because all that info is encoded in
        cms.json.
        """
        super().__init__(None, ("jinja", "j2"))
        self._compiles_to_ext = "html"
        self._compile_all()

    def compile(self, src):
        try:
            subprocess.check_output(
                "/home/chad/.virtualenvs/neocities-cms/bin/python ../cms.py cms.json",
                shell=True
            )
            logging.info("Invoked cms for %s" % src)
            self.send_notif(src, "Triggered a cms call.")
        except subprocess.CalledProcessError as cpe:
            logging.error("failed to compile %s" % src)
            logging.error(cpe.output)
            self.send_notif("failure: %s" % src, cpe.output)

if __name__ == "__main__":
    logging.basicConfig(
        format='%(asctime)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    path = sys.argv[1] if len(sys.argv) > 1 else '.'
    observer = Observer()
    observer.schedule(TSCompiler("jsbuild"), path, recursive=True)
    observer.schedule(LessCompiler("css"), path, recursive=True)
    observer.schedule(JinjaCMSCompiler(), path, recursive=True)
    observer.start()
    logging.info("Watching directory...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
