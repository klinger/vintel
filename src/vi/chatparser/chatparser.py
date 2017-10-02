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

import datetime
import os
import time

import six
from PyQt4.QtGui import QMessageBox
from bs4 import BeautifulSoup
from vi import states

from .parser_functions import parse_status
from .parser_functions import parse_urls, parse_ships, parse_systems

if six.PY2:
    from io import open

# Names the local chatlogs could start with (depends on l10n of the client)
LOCAL_NAMES = ("Local", "Lokal", six.text_type("\u041B\u043E\u043A\u0430\u043B\u044C\u043D\u044B\u0439"))


class ChatParser(object):
    """ ChatParser will analyze every new line that was found inside the Chatlogs.
    """

    def __init__(self, path, rooms, systems):
        """ path = the path with the logs
            rooms = the rooms to parse"""
        self.path = path  # the path with the chatlog
        self.rooms = rooms  # the rooms to watch (excl. local)
        self.systems = systems  # the known systems as dict name: system
        self.fileData = {}  # informations about the files in the directory
        self.knownMessages = []  # message we allready analyzed
        self.locations = {}  # informations about the location of a char
        self.ignoredPaths = []
        self._collect_init_file_data(path)

    def _collect_init_file_data(self, path):
        current_time = time.time()
        max_diff = 60 * 60 * 24  # what is 1 day in seconds
        for filename in os.listdir(path):
            full_path = os.path.join(path, filename)
            file_time = os.path.getmtime(full_path)
            if current_time - file_time < max_diff:
                self.add_file(full_path)

    def add_file(self, path):
        lines = None
        content = ""
        filename = os.path.basename(path)
        roomname = filename[:-20]
        try:
            with open(path, "r", encoding='utf-16-le') as f:
                content = f.read()
        except Exception as e:
            self.ignoredPaths.append(path)
            QMessageBox.warning(None, "Read a log file failed!", "File: {0} - problem: {1}".format(path, six.text_type(e)), "OK")
            return None

        lines = content.split("\n")
        if path not in self.fileData or (roomname in LOCAL_NAMES and "charname" not in self.fileData.get(path, [])):
            self.fileData[path] = {}
            if roomname in LOCAL_NAMES:
                charname = None
                session_start = None
                # for local-chats we need more infos
                for line in lines:
                    if "Listener:" in line:
                        charname = line[line.find(":") + 1:].strip()
                    elif "Session started:" in line:
                        session_str = line[line.find(":") + 1:].strip()
                        session_start = datetime.datetime.strptime(session_str, "%Y.%m.%d %H:%M:%S")
                    if charname and session_start:
                        self.fileData[path]["charname"] = charname
                        self.fileData[path]["sessionstart"] = session_start
                        break
        self.fileData[path]["lines"] = len(lines)
        return lines

    def _line_to_message(self, line, roomname):
        # finding the timestamp
        time_start = line.find("[") + 1
        time_ends = line.find("]")
        time_str = line[time_start:time_ends].strip()
        try:
            timestamp = datetime.datetime.strptime(time_str, "%Y.%m.%d %H:%M:%S")
        except ValueError:
            return None
        # finding the username of the poster
        user_ends = line.find(">")
        username = line[time_ends + 1:user_ends].strip()
        # finding the pure message
        text = line[user_ends + 1:].strip()  # text will the text to work an
        original_text = text
        formated_text = u"<rtext>{0}</rtext>".format(text)
        soup = BeautifulSoup(formated_text, 'html.parser')
        rtext = soup.select("rtext")[0]
        systems = set()
        upper_text = text.upper()

        # KOS request
        if upper_text.startswith("XXX "):
            return Message(roomname, text, timestamp, username, systems, upper_text, status=states.KOS_STATUS_REQUEST)
        elif roomname.startswith("="):
            return Message(roomname, "xxx " + text, timestamp, username, systems, "XXX " + upper_text, status=states.KOS_STATUS_REQUEST)
        if roomname not in self.rooms:
            return None

        message = Message(roomname, "", timestamp, username, systems, text, original_text)
        # May happen if someone plays > 1 account
        if message in self.knownMessages:
            message.status = states.IGNORE
            return message

        while parse_ships(rtext):
            continue
        while parse_urls(rtext):
            continue
        while parse_systems(self.systems, rtext, systems):
            continue
        parsed_status = parse_status(rtext)
        status = parsed_status if parsed_status is not None else states.ALARM

        # If message says clear and no system? Maybe an answer to a request?
        if status == states.CLEAR and not systems:
            max_search = 2  # we search only max_search messages in the room
            for count, oldMessage in enumerate(oldMessage for oldMessage in self.knownMessages[-1::-1] if oldMessage.room == roomname):
                if oldMessage.systems and oldMessage.status == states.REQUEST:
                    for system in oldMessage.systems:
                        systems.add(system)
                    break
                if count > max_search:
                    break
        message.message = six.text_type(rtext)
        message.status = status
        self.knownMessages.append(message)
        if systems:
            for system in systems:
                system.messages.append(message)
        return message

    def _parse_local(self, path, line):
        message = []
        """ Parsing a line from the local chat. Can contain the system of the char
        """
        charname = self.fileData[path]["charname"]
        if charname not in self.locations:
            self.locations[charname] = {"system": "?", "timestamp": datetime.datetime(1970, 1, 1, 0, 0, 0, 0)}

        # Finding the timestamp
        time_start = line.find("[") + 1
        time_ends = line.find("]")
        time_str = line[time_start:time_ends].strip()
        timestamp = datetime.datetime.strptime(time_str, "%Y.%m.%d %H:%M:%S")

        # Finding the username of the poster
        user_ends = line.find(">")
        username = line[time_ends + 1:user_ends].strip()

        # Finding the pure message
        text = line[user_ends + 1:].strip()  # text will the text to work an
        if username in ("EVE-System", "EVE System"):
            if ":" in text:
                system = text.split(":")[1].strip().replace("*", "").upper()
                status = states.LOCATION
            else:
                # We could not determine if the message was system-change related
                system = "?"
                status = states.IGNORE
            if timestamp > self.locations[charname]["timestamp"]:
                self.locations[charname]["system"] = system
                self.locations[charname]["timestamp"] = timestamp
                message = Message("", "", timestamp, charname, [system, ], "", "", status)
        return message

    def file_modified(self, path):
        messages = []
        if path in self.ignoredPaths:
            return []
        # Checking if we must do anything with the changed file.
        # We only need those which name is in the rooms-list
        # EvE names the file like room_20140913_200737.txt, so we don't need
        # the last 20 chars
        filename = os.path.basename(path)
        roomname = filename[:-20]
        if path not in self.fileData:
            # seems eve created a new file. New Files have 12 lines header
            self.fileData[path] = {"lines": 13}
        old_length = self.fileData[path]["lines"]
        lines = self.add_file(path)
        if path in self.ignoredPaths:
            return []
        for line in lines[old_length - 1:]:
            line = line.strip()
            if len(line) > 2:
                message = None
                if roomname in LOCAL_NAMES:
                    message = self._parse_local(path, line)
                else:
                    message = self._line_to_message(line, roomname)
                if message:
                    messages.append(message)
        return messages


class Message(object):
    def __init__(self, room, message, timestamp, user, systems, upper_text, plain_text="", status=states.ALARM):
        self.room = room  # chatroom the message was posted
        self.message = message  # the messages text
        self.timestamp = timestamp  # time stamp of the massage
        self.user = user  # user who posted the message
        self.systems = systems  # list of systems mentioned in the message
        self.status = status  # status related to the message
        self.upperText = upper_text  # the text in UPPER CASE
        self.plainText = plain_text  # plain text of the message, as posted
        # if you add the message to a widget, please add it to widgets
        self.widgets = []

    def __key(self):
        return self.room, self.plainText, self.timestamp, self.user

    def __eq__(x, y):
        return x.__key() == y.__key()

    def __hash__(self):
        return hash(self.__key())
