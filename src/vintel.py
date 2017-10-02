#!/usr/bin/env python
###########################################################################
#  Vintel - Visual Intel Chat Analyzer									  #
#  Copyright (C) 2014-15 Sebastian Meyer (sparrow.242.de+eve@gmail.com )  #
#																		  #
#  This program is free software: you can redistribute it and/or modify	  #
#  it under the terms of the GNU General Public License as published by	  #
#  the Free Software Foundation, either version 3 of the License, or	  #
#  (at your option) any later version.									  #
#																		  #
#  This program is distributed in the hope that it will be useful,		  #
#  but WITHOUT ANY WARRANTY; without even the implied warranty of		  #
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the		  #
#  GNU General Public License for more details.							  #
#																		  #
#																		  #
#  You should have received a copy of the GNU General Public License	  #
#  along with this program.	 If not, see <http://www.gnu.org/licenses/>.  #
###########################################################################

import logging
import os
import sys
import traceback
from logging import StreamHandler
from logging.handlers import RotatingFileHandler

from PyQt4 import QtGui
from PyQt4.QtGui import QApplication, QMessageBox

from vi import version
from vi.cache import cache
from vi.cache.cache import Cache
from vi.resources import resourcePath
from vi.ui import viui, systemtray


# TODO repair click auf systemname sollte fenster oeffnen


def except_hook(exception_type, exception_value, traceback_object):
    """
        Global function to catch unhandled exceptions.
    """
    try:
        logging.critical("-- Unhandled Exception --")
        logging.critical(''.join(traceback.format_tb(traceback_object)))
        logging.critical('{0}: {1}'.format(exception_type, exception_value))
        logging.critical("-- ------------------- --")
    except Exception:
        pass


sys.excepthook = except_hook
backGroundColor = "#c6d9ec"


class Application(QApplication):
    def __init__(self, args):
        super(Application, self).__init__(args)

        # Set up paths
        chat_log_directory = ""
        if len(sys.argv) > 1:
            chat_log_directory = sys.argv[1]

        if not os.path.exists(chat_log_directory):
            if sys.platform.startswith("darwin"):
                chat_log_directory = os.path.join(os.path.expanduser("~"), "Documents", "EVE", "logs", "Chatlogs")
                if not os.path.exists(chat_log_directory):
                    chat_log_directory = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "Eve Online",
                                                      "p_drive", "User", "My Documents", "EVE", "logs", "Chatlogs")
            elif sys.platform.startswith("linux"):
                chat_log_directory = os.path.join(os.path.expanduser("~"), "EVE", "logs", "Chatlogs")
            elif sys.platform.startswith("win32") or sys.platform.startswith("cygwin"):
                import ctypes.wintypes
                buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
                ctypes.windll.shell32.SHGetFolderPathW(0, 5, 0, 0, buf)
                documents_path = buf.value
                chat_log_directory = os.path.join(documents_path, "EVE", "logs", "Chatlogs")
        if not os.path.exists(chat_log_directory):
            # None of the paths for logs exist, bailing out
            QMessageBox.critical(None, "No path to Logs", "No logs found at: " + chat_log_directory, "Quit")
            sys.exit(1)

        # Setting local directory for cache and logging
        vintel_directory = os.path.join(os.path.dirname(os.path.dirname(chat_log_directory)), "vintel")
        if not os.path.exists(vintel_directory):
            os.mkdir(vintel_directory)
        cache.Cache.PATH_TO_CACHE = os.path.join(vintel_directory, "cache-2.sqlite3")

        vintel_log_directory = os.path.join(vintel_directory, "logs")
        if not os.path.exists(vintel_log_directory):
            os.mkdir(vintel_log_directory)

        splash = QtGui.QSplashScreen(QtGui.QPixmap(resourcePath("vi/ui/res/logo.png")))

        vintel_cache = Cache()
        log_level = vintel_cache.get_fromcache("logging_level")
        if not log_level:
            log_level = logging.WARN
        back_ground_color = vintel_cache.get_fromcache("background_color")
        if back_ground_color:
            self.setStyleSheet("QWidget { background-color: %s; }" % back_ground_color)

        splash.show()
        self.processEvents()

        # Setup logging for console and rotated log files
        formatter = logging.Formatter('%(asctime)s| %(message)s', datefmt='%m/%d %I:%M:%S')
        root_logger = logging.getLogger()
        root_logger.setLevel(level=log_level)

        log_filename = vintel_log_directory + "/output.log"
        file_handler = RotatingFileHandler(maxBytes=(1048576 * 5), backupCount=7, filename=log_filename, mode='a')
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        console_handler = StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        logging.critical("")
        logging.critical("------------------- Vintel %s starting up -------------------", version.VERSION)
        logging.critical("")
        logging.debug("Looking for chat logs at: %s", chat_log_directory)
        logging.debug("Cache maintained here: %s", cache.Cache.PATH_TO_CACHE)
        logging.debug("Writing logs to: %s", vintel_log_directory)

        tray_icon = systemtray.TrayIcon(self)
        tray_icon.show()
        self.mainWindow = viui.MainWindow(chat_log_directory, tray_icon, back_ground_color)
        self.mainWindow.show()
        self.mainWindow.raise_()
        splash.finish(self.mainWindow)


# The main application
if __name__ == "__main__":
    app = Application(sys.argv)
    sys.exit(app.exec_())
