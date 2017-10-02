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

import time

from PyQt4 import QtGui
from PyQt4.QtCore import SIGNAL
from PyQt4.QtGui import QAction, QActionGroup
from PyQt4.QtGui import QIcon, QSystemTrayIcon
from six.moves import range
from vi import states
from vi.resources import resourcePath


class TrayContextMenu(QtGui.QMenu):
    instances = set()

    def __init__(self, tray_icon):
        """ trayIcon = the object with the methods to call
        """
        QtGui.QMenu.__init__(self)
        TrayContextMenu.instances.add(self)
        self.trayIcon = tray_icon
        self._build_menu()

    def _build_menu(self):
        self.framelessCheck = QtGui.QAction("Frameless Window", self, checkable=True)
        self.connect(self.framelessCheck, SIGNAL("triggered()"), self.trayIcon.change_frameless)
        self.addAction(self.framelessCheck)
        self.addSeparator()
        self.requestCheck = QtGui.QAction("Show status request notifications", self, checkable=True)
        self.requestCheck.setChecked(True)
        self.addAction(self.requestCheck)
        self.connect(self.requestCheck, SIGNAL("triggered()"), self.trayIcon.switch_request)
        self.alarmCheck = QtGui.QAction("Show alarm notifications", self, checkable=True)
        self.alarmCheck.setChecked(True)
        self.connect(self.alarmCheck, SIGNAL("triggered()"), self.trayIcon.switch_alarm)
        self.addAction(self.alarmCheck)
        distance_menu = self.addMenu("Alarm Distance")
        self.distanceGroup = QActionGroup(self)
        for i in range(0, 6):
            action = QAction("{0} Jumps".format(i), None, checkable=True)
            if i == 0:
                action.setChecked(True)
            action.alarmDistance = i
            self.connect(action, SIGNAL("triggered()"), self.change_alarm_distance)
            self.distanceGroup.addAction(action)
            distance_menu.addAction(action)
        self.addMenu(distance_menu)
        self.addSeparator()
        self.quitAction = QAction("Quit", self)
        self.connect(self.quitAction, SIGNAL("triggered()"), self.trayIcon.quit)
        self.addAction(self.quitAction)

    def change_alarm_distance(self):
        for action in self.distanceGroup.actions():
            if action.isChecked():
                self.trayIcon.alarmDistance = action.alarmDistance
                self.trayIcon.change_alarm_distance()


class TrayIcon(QtGui.QSystemTrayIcon):
    # Min seconds between two notifications
    MIN_WAIT_NOTIFICATION = 15

    def __init__(self, app):
        self.icon = QIcon(resourcePath("vi/ui/res/logo_small.png"))
        QSystemTrayIcon.__init__(self, self.icon, app)
        self.setToolTip("Vintel Recon Citadel")
        self.lastNotifications = {}
        self.setContextMenu(TrayContextMenu(self))
        self.showAlarm = True
        self.showRequest = True
        self.alarmDistance = 0

    def change_alarm_distance(self):
        distance = self.alarmDistance
        self.emit(SIGNAL("alarm_distance"), distance)

    def change_frameless(self):
        self.emit(SIGNAL("change_frameless"))

    @property
    def distance_group(self):
        return self.contextMenu().distance_group

    def quit(self):
        self.emit(SIGNAL("quit"))

    def switch_alarm(self):
        new_value = not self.showAlarm
        for cm in TrayContextMenu.instances:
            cm.alarmCheck.setChecked(new_value)
        self.showAlarm = new_value

    def switch_request(self):
        new_value = not self.showRequest
        for cm in TrayContextMenu.instances:
            cm.requestCheck.setChecked(new_value)
        self.showRequest = new_value

    def show_notification(self, message, system, char, distance):
        if message is None:
            return
        room = message.room
        title = None
        text = None
        icon = None
        text = ""
        if message.status == states.ALARM and self.showAlarm and self.lastNotifications.get(states.ALARM,
                                                                                            0) < time.time() - self.MIN_WAIT_NOTIFICATION:
            title = "ALARM!"
            icon = 2
            speech_text = (u"{0} alarmed in {1}, {2} jumps from {3}".format(system, room, distance, char))
            text = speech_text + (u"\nText: %s" % text)
            self.lastNotifications[states.ALARM] = time.time()
        elif message.status == states.REQUEST and self.showRequest and self.lastNotifications.get(states.REQUEST,
                                                                                                  0) < time.time() - self.MIN_WAIT_NOTIFICATION:
            title = "Status request"
            icon = 1
            text = (u"Someone is requesting status of {0} in {1}.".format(system, room))
            self.lastNotifications[states.REQUEST] = time.time()
        if not (title is None or text is None or icon):
            text = text.format(**locals())
            self.showMessage(title, text, icon)
