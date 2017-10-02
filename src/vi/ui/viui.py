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
import logging
import sys
import time
import webbrowser

import requests
import six
import vi.version
from PyQt4 import QtGui, uic, QtCore
from PyQt4.QtCore import QPoint, SIGNAL
from PyQt4.QtGui import *
from PyQt4.QtGui import QAction
from PyQt4.QtGui import QMessageBox
from PyQt4.QtWebKit import QWebPage
from vi import dotlan, filewatcher
from vi import evegate
from vi import states
from vi.cache.cache import Cache
from vi.chatparser import ChatParser
from vi.resources import resourcePath
from vi.ui.systemtray import TrayContextMenu

# Timer intervals
MESSAGE_EXPIRY_SECS = 20 * 60
MAP_UPDATE_INTERVAL_MSECS = 4 * 1000
CLIPBOARD_CHECK_INTERVAL_MSECS = 4 * 1000


class MainWindow(QtGui.QMainWindow):
    def __init__(self, path_to_logs, tray_icon, back_ground_color):

        QtGui.QMainWindow.__init__(self)
        self.cache = Cache()

        if back_ground_color:
            self.setStyleSheet("QWidget { background-color: %s; }" % back_ground_color)
        uic.loadUi(resourcePath('vi/ui/MainWindow.ui'), self)
        self.setWindowTitle("Vintel " + vi.version.VERSION + "{dev}".format(dev="-SNAPSHOT" if vi.version.SNAPSHOT else ""))
        self.taskbarIconQuiescent = QtGui.QIcon(resourcePath("vi/ui/res/logo_small.png"))
        self.taskbarIconWorking = QtGui.QIcon(resourcePath("vi/ui/res/logo_small_green.png"))
        self.setWindowIcon(self.taskbarIconQuiescent)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        self.pathToLogs = path_to_logs
        self.mapTimer = QtCore.QTimer(self)
        self.connect(self.mapTimer, SIGNAL("timeout()"), self.update_map_view)
        self.clipboardTimer = QtCore.QTimer(self)
        self.oldClipboardContent = ""
        self.trayIcon = tray_icon
        self.trayIcon.activated.connect(self.system_tray_activated)
        self.clipboard = QtGui.QApplication.clipboard()
        self.clipboard.clear(mode=self.clipboard.Clipboard)
        self.alarmDistance = 0
        self.lastStatisticsUpdate = 0
        self.chatEntries = []
        self.frameButton.setVisible(False)
        self.scanIntelForKosRequestsEnabled = True
        self.initialMapPosition = None
        self.mapPositionsDict = {}

        # Load user's toon names
        self.knownPlayerNames = self.cache.get_fromcache("known_player_names")
        if self.knownPlayerNames:
            self.knownPlayerNames = set(self.knownPlayerNames.split(","))
        else:
            self.knownPlayerNames = set()
            diag_text = "Vintel scans EVE system logs and remembers your characters as they change systems.\n\nSome features (clipboard KOS checking, alarms, etc.) may not work until your character(s) have been registered. Change systems, with each character you want to monitor, while Vintel is running to remedy this."
            QMessageBox.warning(None, "Known Characters not Found", diag_text, "Ok")

        # Set up user's intel rooms
        roomnames = self.cache.get_fromcache("room_names")
        if roomnames:
            roomnames = roomnames.split(",")
        else:
            roomnames = (u"TheCitadel", u"North Provi Intel", u"North Catch Intel", "North Querious Intel")
            self.cache.put_into_cache("room_names", u",".join(roomnames), 60 * 60 * 24 * 365 * 5)
        self.roomnames = roomnames

        # Set up Transparency menu - fill in opacity values and make connections
        self.opacityGroup = QActionGroup(self.menu)
        for i in (100, 80, 60, 40, 20):
            action = QAction("Opacity {0}%".format(i), None, checkable=True)
            if i == 100:
                action.setChecked(True)
            action.opacity = i / 100.0
            self.connect(action, SIGNAL("triggered()"), self.change_opacity)
            self.opacityGroup.addAction(action)
            self.menuTransparency.addAction(action)

        #
        # Platform specific UI resizing - we size items in the resource files to look correct on the mac,
        # then resize other platforms as needed
        #
        if sys.platform.startswith("win32") or sys.platform.startswith("cygwin"):
            font = self.statisticsButton.font()
            font.setPointSize(8)
            self.statisticsButton.setFont(font)
        elif sys.platform.startswith("linux"):
            pass

        self.wire_up_uiconnections()
        self.recall_cached_settings()
        self.setup_threads()
        self.setup_map(True)

    def paintEvent(self, event):
        opt = QStyleOption()
        opt.initFrom(self)
        painter = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt, painter, self)

    def recall_cached_settings(self):
        try:
            self.cache.recall_and_apply_settings(self, "settings")
        except Exception as e:
            logging.error(e)
            # todo: add a button to delete the cache / DB
            self.trayIcon.showMessage("Settings error", "Something went wrong loading saved state:\n {0}".format(str(e)), 1)

    def wire_up_uiconnections(self):
        # Wire up general UI connections
        self.connect(self.clipboard, SIGNAL("changed(QClipboard::Mode)"), self.clipboard_changed)
        self.connect(self.autoScanIntelAction, SIGNAL("triggered()"), self.change_auto_scan_intel)
        self.connect(self.zoomInButton, SIGNAL("clicked()"), self.zoom_map_in)
        self.connect(self.zoomOutButton, SIGNAL("clicked()"), self.zoom_map_out)
        self.connect(self.statisticsButton, SIGNAL("clicked()"), self.change_statistics_visibility)
        self.connect(self.chatLargeButton, SIGNAL("clicked()"), self.chat_larger)
        self.connect(self.chatSmallButton, SIGNAL("clicked()"), self.chat_smaller)
        self.connect(self.infoAction, SIGNAL("triggered()"), self.show_info)
        self.connect(self.alwaysOnTopAction, SIGNAL("triggered()"), self.change_always_on_top)
        self.connect(self.chooseChatRoomsAction, SIGNAL("triggered()"), self.show_chatroom_chooser)
        self.connect(self.immenseaRegionAction, SIGNAL("triggered()"),
                     lambda: self.handle_region_menu_item_selected(self.immenseaRegionAction))
        self.connect(self.tenerifisRegionAction, SIGNAL("triggered()"),
                     lambda: self.handle_region_menu_item_selected(self.tenerifisRegionAction))
        self.connect(self.detoridRegionAction, SIGNAL("triggered()"),
                     lambda: self.handle_region_menu_item_selected(self.detoridRegionAction))
        self.connect(self.catchRegionAction, SIGNAL("triggered()"), lambda: self.handle_region_menu_item_selected(self.catchRegionAction))
        self.connect(self.providenceRegionAction, SIGNAL("triggered()"),
                     lambda: self.handle_region_menu_item_selected(self.providenceRegionAction))
        self.connect(self.queriousRegionAction, SIGNAL("triggered()"),
                     lambda: self.handle_region_menu_item_selected(self.queriousRegionAction))
        self.connect(self.providenceCatchRegionAction, SIGNAL("triggered()"),
                     lambda: self.handle_region_menu_item_selected(self.providenceCatchRegionAction))
        self.connect(self.providenceCatchCompactRegionAction, SIGNAL("triggered()"),
                     lambda: self.handle_region_menu_item_selected(self.providenceCatchCompactRegionAction))
        self.connect(self.chooseRegionAction, SIGNAL("triggered()"), self.show_region_chooser)
        self.connect(self.showChatAction, SIGNAL("triggered()"), self.change_chat_visibility)
        self.connect(self.trayIcon, SIGNAL("alarm_distance"), self.change_alarm_distance)
        self.connect(self.framelessWindowAction, SIGNAL("triggered()"), self.change_frameless)
        self.connect(self.trayIcon, SIGNAL("change_frameless"), self.change_frameless)
        self.connect(self.frameButton, SIGNAL("clicked()"), self.change_frameless)
        self.connect(self.quitAction, SIGNAL("triggered()"), self.close)
        self.connect(self.trayIcon, SIGNAL("quit"), self.close)
        self.mapView.page().scrollRequested.connect(self.map_position_changed)

    def setup_threads(self):
        # Set up threads and their connections
        self.filewatcherThread = filewatcher.FileWatcher(self.pathToLogs)
        self.connect(self.filewatcherThread, SIGNAL("file_change"), self.log_file_changed)
        self.filewatcherThread.start()

    def setup_map(self, initialize=False):
        self.mapTimer.stop()
        self.filewatcherThread.paused = True

        logging.info("Finding map file")
        region_name = self.cache.get_fromcache("region_name")
        if not region_name:
            region_name = "Providence"
        svg = None
        try:
            with open(resourcePath("vi/ui/res/mapdata/{0}.svg".format(region_name))) as svgFile:
                svg = svgFile.read()
        except Exception as e:
            pass

        try:
            self.dotlan = dotlan.Map(region_name, svg)
        except dotlan.DotlanException as e:
            logging.error(e)
            QMessageBox.critical(None, "Error getting map", six.text_type(e), "Quit")
            sys.exit(1)

        if self.dotlan.outdatedCacheError:
            e = self.dotlan.outdatedCacheError
            diag_text = "Something went wrong getting map data. Proceeding with older cached data. " \
                        "Check for a newer version and inform the maintainer.\n\nError: {0} {1}".format(type(e), six.text_type(e))
            logging.warn(diag_text)
            QMessageBox.warning(None, "Using map from cache", diag_text, "Ok")

        self.systems = self.dotlan.systems
        logging.critical("Creating chat parser")
        self.chatparser = ChatParser(self.pathToLogs, self.roomnames, self.systems)

        # Menus - only once
        if initialize:
            logging.critical("Initializing contextual menus")

            # Add a contextual menu to the mapView
            def map_context_menu_event(event):
                # if QApplication.activeWindow() or QApplication.focusWidget():
                self.mapView.contextMenu.exec_(self.mapToGlobal(QPoint(event.x(), event.y())))

            self.mapView.contextMenuEvent = map_context_menu_event
            self.mapView.contextMenu = self.trayIcon.contextMenu()

            # Clicking links
            self.mapView.connect(self.mapView, SIGNAL("link_clicked(const QUrl&)"), self.map_link_clicked)

            # Also set up our app menus
            if not region_name:
                self.providenceCatchRegionAction.setChecked(True)
            elif region_name.startswith("Providencecatch"):
                self.providenceCatchRegionAction.setChecked(True)
            elif region_name.startswith("Immensea"):
                self.immenseaRegionAction.setChecked(True)
            elif region_name.startswith("Tenerifis"):
                self.tenerifisRegionAction.setChecked(True)
            elif region_name.startswith("Detorid"):
                self.detoridRegionAction.setChecked(True)
            elif region_name.startswith("Catch"):
                self.catchRegionAction.setChecked(True)
            elif region_name.startswith("Providence"):
                self.providenceRegionAction.setChecked(True)
            elif region_name.startswith("Querious"):
                self.queriousRegionAction.setChecked(True)
            else:
                self.chooseRegionAction.setChecked(True)
        self.statisticsButton.setChecked(False)

        # Update the new map view, then clear old statistics from the map and request new
        logging.critical("Updating the map")
        self.update_map_view()
        self.set_initial_map_position_for_region(region_name)
        self.mapTimer.start(MAP_UPDATE_INTERVAL_MSECS)
        # Allow the file watcher to run now that all else is set up
        self.filewatcherThread.paused = False
        logging.critical("Map setup complete")

    def start_clipboard_timer(self):
        """
            Start a timer to check the keyboard for changes and kos check them,
            first initializing the content so we dont kos check from random content
        """
        self.oldClipboardContent = tuple(six.text_type(self.clipboard.text()))
        self.connect(self.clipboardTimer, SIGNAL("timeout()"), self.clipboard_changed)
        self.clipboardTimer.start(CLIPBOARD_CHECK_INTERVAL_MSECS)

    def stop_clipboard_timer(self):
        if self.clipboardTimer:
            self.disconnect(self.clipboardTimer, SIGNAL("timeout()"), self.clipboard_changed)
            self.clipboardTimer.stop()

    def closeEvent(self, event):
        """
            Persisting things to the cache before closing the window
        """
        # Known playernames
        if self.knownPlayerNames:
            value = ",".join(self.knownPlayerNames)
            self.cache.put_into_cache("known_player_names", value, 60 * 60 * 24 * 30)

        # Program state to cache (to read it on next startup)
        settings = ((None, "restoreGeometry", str(self.saveGeometry())), (None, "restoreState", str(self.saveState())),
                    ("splitter", "restoreGeometry", str(self.splitter.saveGeometry())),
                    ("splitter", "restoreState", str(self.splitter.saveState())),
                    ("mapView", "setZoomFactor", self.mapView.zoomFactor()),
                    (None, "change_chat_font_size", ChatEntryWidget.TEXT_SIZE),
                    (None, "change_opacity", self.opacityGroup.checkedAction().opacity),
                    (None, "change_always_on_top", self.alwaysOnTopAction.isChecked()),
                    (None, "changeShowAvatars", self.showChatAvatarsAction.isChecked()),
                    (None, "change_alarm_distance", self.alarmDistance),
                    (None, "change_chat_visibility", self.showChatAction.isChecked()),
                    (None, "load_initial_map_positions", self.mapPositionsDict),
                    (None, "change_frameless", self.framelessWindowAction.isChecked()),
                    (None, "changeUseSpokenNotifications", self.useSpokenNotificationsAction.isChecked()),
                    (None, "change_auto_scan_intel", self.scanIntelForKosRequestsEnabled))
        self.cache.put_into_cache("settings", str(settings), 60 * 60 * 24 * 30)

        # Stop the threads
        try:
            self.avatarFindThread.quit()
            self.avatarFindThread.wait()
            self.filewatcherThread.quit()
            self.filewatcherThread.wait()
            self.kosRequestThread.quit()
            self.kosRequestThread.wait()
            self.versionCheckThread.quit()
            self.versionCheckThread.wait()
            self.statisticsThread.quit()
            self.statisticsThread.wait()
        except Exception:
            pass
        self.trayIcon.hide()
        event.accept()

    def change_chat_visibility(self, new_value=None):
        if new_value is None:
            new_value = self.showChatAction.isChecked()
        self.showChatAction.setChecked(new_value)
        self.chatbox.setVisible(new_value)

    def change_auto_scan_intel(self, new_value=None):
        if new_value is None:
            new_value = self.autoScanIntelAction.isChecked()
        self.autoScanIntelAction.setChecked(new_value)
        self.scanIntelForKosRequestsEnabled = new_value

    def change_opacity(self, new_value=None):
        if new_value is not None:
            for action in self.opacityGroup.actions():
                if action.opacity == new_value:
                    action.setChecked(True)
        action = self.opacityGroup.checkedAction()
        self.setWindowOpacity(action.opacity)

    def change_always_on_top(self, new_value=None):
        if new_value is None:
            new_value = self.alwaysOnTopAction.isChecked()
        self.hide()
        self.alwaysOnTopAction.setChecked(new_value)
        if new_value:
            self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & (~QtCore.Qt.WindowStaysOnTopHint))
        self.show()

    def change_frameless(self, new_value=None):
        if new_value is None:
            new_value = not self.frameButton.isVisible()
        self.hide()
        if new_value:
            self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
            self.change_always_on_top(True)
        else:
            self.setWindowFlags(self.windowFlags() & (~QtCore.Qt.FramelessWindowHint))
        self.menubar.setVisible(not new_value)
        self.frameButton.setVisible(new_value)
        self.framelessWindowAction.setChecked(new_value)

        for cm in TrayContextMenu.instances:
            cm.framelessCheck.setChecked(new_value)
        self.show()

    def change_chat_font_size(self, new_size):
        if new_size:
            for entry in self.chatEntries:
                entry.change_font_size(new_size)
            ChatEntryWidget.TEXT_SIZE = new_size

    def chat_smaller(self):
        new_size = ChatEntryWidget.TEXT_SIZE - 1
        self.change_chat_font_size(new_size)

    def chat_larger(self):
        new_size = ChatEntryWidget.TEXT_SIZE + 1
        self.change_chat_font_size(new_size)

    def change_alarm_distance(self, distance):
        self.alarmDistance = distance
        for cm in TrayContextMenu.instances:
            for action in cm.distance_group.actions():
                if action.alarmDistance == distance:
                    action.setChecked(True)
        self.trayIcon.alarmDistance = distance

    def change_statistics_visibility(self):
        new_value = self.dotlan.change_statistics_visibility()
        self.statisticsButton.setChecked(new_value)
        self.update_map_view()
        if new_value:
            self.statisticsThread.requestStatistics()

    def clipboard_changed(self, mode=0):
        if not (mode == 0 and self.clipboard.mimeData().hasText()):
            return
        content = six.text_type(self.clipboard.text())
        content_tuple = tuple(content)
        # Limit redundant kos checks
        if content_tuple != self.oldClipboardContent:
            parts = tuple(content.split("\n"))
            known_players = self.knownPlayerNames
            for part in parts:
                # Make sure user is in the content (this is a check of the local system in Eve).
                # also, special case for when you have no knonwnPlayers (initial use)
                if not known_players or part in known_players:
                    self.trayIcon.setIcon(self.taskbarIconWorking)
                    self.kosRequestThread.addRequest(parts, "clipboard", True)
                    break
            self.oldClipboardContent = content_tuple

    def map_link_clicked(self, url):
        system_name = six.text_type(url.path().split("/")[-1]).upper()
        system = self.systems[str(system_name)]
        sc = SystemChat(self, SystemChat.SYSTEM, system, self.chatEntries, self.knownPlayerNames)
        sc.connect(self, SIGNAL("chat_message_added"), sc.add_chat_entry)
        sc.connect(self, SIGNAL("avatar_loaded"), sc.newAvatarAvailable)
        sc.connect(sc, SIGNAL("location_set"), self.set_location)
        sc.show()

    def mark_system_on_map(self, systemname):
        self.systems[six.text_type(systemname)].mark()
        self.update_map_view()

    def set_location(self, char, new_system):
        for system in self.systems.values():
            system.remove_located_character(char)
        if not new_system == "?" and new_system in self.systems:
            self.systems[new_system].add_located_character(char)
            self.set_map_content(self.dotlan.svg)

    def set_map_content(self, content):
        if self.initialMapPosition is None:
            scroll_position = self.mapView.page().mainFrame().scrollPosition()
        else:
            scroll_position = self.initialMapPosition
        self.mapView.setContent(content)
        self.mapView.page().mainFrame().setScrollPosition(scroll_position)
        self.mapView.page().setLinkDelegationPolicy(QWebPage.DelegateAllLinks)

        # Make sure we have positioned the window before we nil the initial position;
        # even though we set it, it may not take effect until the map is fully loaded
        scroll_position = self.mapView.page().mainFrame().scrollPosition()
        if scroll_position.x() or scroll_position.y():
            self.initialMapPosition = None

    def load_initial_map_positions(self, new_dictionary):
        self.mapPositionsDict = new_dictionary

    def set_initial_map_position_for_region(self, region_name):
        try:
            if not region_name:
                region_name = self.cache.get_fromcache("region_name")
            if region_name:
                xy = self.mapPositionsDict[region_name]
                self.initialMapPosition = QPoint(xy[0], xy[1])
        except Exception:
            pass

    def map_position_changed(self, dx, dy, rect_to_scroll):
        region_name = self.cache.get_fromcache("region_name")
        if region_name:
            scroll_position = self.mapView.page().mainFrame().scrollPosition()
            self.mapPositionsDict[region_name] = (scroll_position.x(), scroll_position.y())

    def show_chatroom_chooser(self):
        chooser = ChatroomsChooser(self)
        chooser.connect(chooser, SIGNAL("rooms_changed"), self.changed_roomnames)
        chooser.show()

    def handle_region_menu_item_selected(self, menu_action=None):
        self.catchRegionAction.setChecked(False)
        self.providenceRegionAction.setChecked(False)
        self.immenseaRegionAction.setChecked(False)
        self.tenerifisRegionAction.setChecked(False)
        self.detoridRegionAction.setChecked(False)
        self.queriousRegionAction.setChecked(False)
        self.providenceCatchRegionAction.setChecked(False)
        self.providenceCatchCompactRegionAction.setChecked(False)
        self.chooseRegionAction.setChecked(False)
        if menu_action:
            menu_action.setChecked(True)
            region_name = six.text_type(menu_action.property("regionName").toString())
            region_name = dotlan.convert_region_name(region_name)
            Cache().put_into_cache("region_name", region_name, 60 * 60 * 24 * 365)
            self.setup_map()

    def show_region_chooser(self):
        def handle_region_chosen():
            self.handle_region_menu_item_selected(None)
            self.chooseRegionAction.setChecked(True)
            self.setup_map()

        self.chooseRegionAction.setChecked(False)
        chooser = RegionChooser(self)
        self.connect(chooser, SIGNAL("new_region_chosen"), handle_region_chosen)
        chooser.show()

    def add_message_to_intel_chat(self, message):
        scroll_to_bottom = False
        if self.chatListWidget.verticalScrollBar().value() == self.chatListWidget.verticalScrollBar().maximum():
            scroll_to_bottom = True
        chat_entry_widget = ChatEntryWidget(message)
        list_widget_item = QtGui.QListWidgetItem(self.chatListWidget)
        list_widget_item.setSizeHint(chat_entry_widget.sizeHint())
        self.chatListWidget.addItem(list_widget_item)
        self.chatListWidget.setItemWidget(list_widget_item, chat_entry_widget)
        self.avatarFindThread.add_chat_entry(chat_entry_widget)
        self.chatEntries.append(chat_entry_widget)
        self.connect(chat_entry_widget, SIGNAL("mark_system"), self.mark_system_on_map)
        self.emit(SIGNAL("chat_message_added"), chat_entry_widget)
        self.prune_messages()
        if scroll_to_bottom:
            self.chatListWidget.scrollToBottom()

    def prune_messages(self):
        try:
            now = time.mktime(evegate.currentEveTime().timetuple())
            for row in range(self.chatListWidget.count()):
                chat_list_widget_item = self.chatListWidget.item(0)
                chat_entry_widget = self.chatListWidget.itemWidget(chat_list_widget_item)
                message = chat_entry_widget.message
                if now - time.mktime(message.timestamp.timetuple()) > MESSAGE_EXPIRY_SECS:
                    self.chatEntries.remove(chat_entry_widget)
                    self.chatListWidget.takeItem(0)

                    for widgetInMessage in message.widgets:
                        widgetInMessage.removeItemWidget(chat_list_widget_item)
                else:
                    break
        except Exception as e:
            logging.error(e)

    def changed_roomnames(self, new_roomnames):
        self.cache.put_into_cache("room_names", u",".join(new_roomnames), 60 * 60 * 24 * 365 * 5)
        self.chatparser.rooms = new_roomnames

    def show_info(self):
        info_dialog = QtGui.QDialog(self)
        uic.loadUi(resourcePath("vi/ui/Info.ui"), info_dialog)
        info_dialog.versionLabel.setText(u"Version: {0}".format(vi.version.VERSION))
        info_dialog.logoLabel.setPixmap(QtGui.QPixmap(resourcePath("vi/ui/res/logo.png")))
        info_dialog.connect(info_dialog.closeButton, SIGNAL("clicked()"), info_dialog.accept)
        info_dialog.show()

    def system_tray_activated(self, reason):
        if reason == QtGui.QSystemTrayIcon.Trigger:
            if self.isMinimized():
                self.showNormal()
                self.activateWindow()
            elif not self.isActiveWindow():
                self.activateWindow()
            else:
                self.showMinimized()

    def update_statistics_on_map(self, data):
        if not self.statisticsButton.isChecked():
            return
        if data["result"] == "ok":
            self.dotlan.add_system_statistics(data["statistics"])
        elif data["result"] == "error":
            text = data["text"]
            self.trayIcon.showMessage("Loading statstics failed", text, 3)
            logging.error("update_statistics_on_map, error: %s" % text)

    def update_map_view(self):
        logging.debug("Updating map start")
        self.set_map_content(self.dotlan.svg)
        logging.debug("Updating map complete")

    def zoom_map_in(self):
        self.mapView.setZoomFactor(self.mapView.zoomFactor() + 0.1)

    def zoom_map_out(self):
        self.mapView.setZoomFactor(self.mapView.zoomFactor() - 0.1)

    def log_file_changed(self, path):
        messages = self.chatparser.file_modified(path)
        for message in messages:
            # If players location has changed
            if message.status == states.LOCATION:
                self.knownPlayerNames.add(message.user)
                self.set_location(message.user, message.systems[0])
            elif message.status == states.KOS_STATUS_REQUEST:
                # Do not accept KOS requests from any but monitored intel channels
                # as we don't want to encourage the use of xxx in those channels.
                if not message.room in self.roomnames:
                    text = message.message[4:]
                    text = text.replace("  ", ",")
                    parts = (name.strip() for name in text.split(","))
                    self.trayIcon.setIcon(self.taskbarIconWorking)
                    self.kosRequestThread.addRequest(parts, "xxx", False)
            # Otherwise consider it a 'normal' chat message
            elif message.user not in ("EVE-System", "EVE System") and message.status != states.IGNORE:
                self.add_message_to_intel_chat(message)
                # For each system that was mentioned in the message, check for alarm distance to the current system
                # and alarm if within alarm distance.
                system_list = self.dotlan.systems
                if message.systems:
                    for system in message.systems:
                        systemname = system.name
                        system_list[systemname].set_status(message.status)
                        if message.status in (states.REQUEST, states.ALARM) and message.user not in self.knownPlayerNames:
                            alarm_distance = self.alarmDistance if message.status == states.ALARM else 0
                            for nSystem, data in system.get_neighbours(alarm_distance).items():
                                distance = data["distance"]
                                chars = nSystem.get_located_characters()
                                if len(chars) > 0 and message.user not in chars:
                                    self.trayIcon.show_notification(message, system.name, ", ".join(chars), distance)
                self.set_map_content(self.dotlan.svg)


class ChatroomsChooser(QtGui.QDialog):
    def __init__(self, parent):
        QtGui.QDialog.__init__(self, parent)
        uic.loadUi(resourcePath("vi/ui/ChatroomsChooser.ui"), self)
        self.connect(self.defaultButton, SIGNAL("clicked()"), self.set_defaults)
        self.connect(self.cancelButton, SIGNAL("clicked()"), self.accept)
        self.connect(self.saveButton, SIGNAL("clicked()"), self.save_clicked)
        cache = Cache()
        roomnames = cache.get_fromcache("room_names")
        if not roomnames:
            roomnames = u"TheCitadel,North Provi Intel,North Catch Intel,North Querious Intel"
        self.roomnamesField.setPlainText(roomnames)

    def save_clicked(self):
        text = six.text_type(self.roomnamesField.toPlainText())
        rooms = [six.text_type(name.strip()) for name in text.split(",")]
        self.accept()
        self.emit(SIGNAL("rooms_changed"), rooms)

    def set_defaults(self):
        self.roomnamesField.setPlainText(u"TheCitadel,North Provi Intel,North Catch Intel,North Querious Intel")


class RegionChooser(QtGui.QDialog):
    def __init__(self, parent):
        QtGui.QDialog.__init__(self, parent)
        uic.loadUi(resourcePath("vi/ui/RegionChooser.ui"), self)
        self.connect(self.cancelButton, SIGNAL("clicked()"), self.accept)
        self.connect(self.saveButton, SIGNAL("clicked()"), self.save_clicked)
        cache = Cache()
        region_name = cache.get_fromcache("region_name")
        if not region_name:
            region_name = u"Providence"
        self.regionNameField.setPlainText(region_name)

    def save_clicked(self):
        text = six.text_type(self.regionNameField.toPlainText())
        text = dotlan.convert_region_name(text)
        self.regionNameField.setPlainText(text)
        correct = False
        try:
            url = dotlan.Map.DOTLAN_BASIC_URL.format(text)
            content = requests.get(url).text
            if u"not found" in content:
                correct = False
                # Fallback -> ships vintel with this map?
                try:
                    with open(resourcePath("vi/ui/res/mapdata/{0}.svg".format(text))) as _:
                        correct = True
                except Exception as e:
                    logging.error(e)
                    correct = False
                if not correct:
                    QMessageBox.warning(self, u"No such region!", u"I can't find a region called '{0}'".format(text))
            else:
                correct = True
        except Exception as e:
            QMessageBox.critical(self, u"Something went wrong!", u"Error while testing existing '{0}'".format(str(e)))
            logging.error(e)
            correct = False
        if correct:
            Cache().put_into_cache("region_name", text, 60 * 60 * 24 * 365)
            self.accept()
            self.emit(SIGNAL("new_region_chosen"))


class SystemChat(QtGui.QDialog):
    SYSTEM = 0

    def __init__(self, parent, chat_type, selector, chat_entries, known_player_names):
        QtGui.QDialog.__init__(self, parent)
        uic.loadUi(resourcePath("vi/ui/SystemChat.ui"), self)
        self.parent = parent
        self.chatType = 0
        self.selector = selector
        self.chatEntries = []
        for entry in chat_entries:
            self.add_chat_entry(entry)
        title_name = ""
        if self.chatType == SystemChat.SYSTEM:
            title_name = self.selector.name
            self.system = selector
        for name in known_player_names:
            self.playerNamesBox.addItem(name)
        self.setWindowTitle("Chat for {0}".format(title_name))
        self.connect(self.closeButton, SIGNAL("clicked()"), self.close_dialog)
        self.connect(self.alarmButton, SIGNAL("clicked()"), self.set_system_alarm)
        self.connect(self.clearButton, SIGNAL("clicked()"), self.set_system_clear)
        self.connect(self.locationButton, SIGNAL("clicked()"), self.location_set)

    def _add_message_to_chat(self, message, avatar_pixmap):
        scroll_to_bottom = False
        if self.chat.verticalScrollBar().value() == self.chat.verticalScrollBar().maximum():
            scroll_to_bottom = True
        entry = ChatEntryWidget(message)
        list_widget_item = QtGui.QListWidgetItem(self.chat)
        list_widget_item.setSizeHint(entry.sizeHint())
        self.chat.addItem(list_widget_item)
        self.chat.setItemWidget(list_widget_item, entry)
        self.chatEntries.append(entry)
        self.connect(entry, SIGNAL("mark_system"), self.parent.mark_system_on_map)
        if scroll_to_bottom:
            self.chat.scrollToBottom()

    def add_chat_entry(self, entry):
        if self.chatType == SystemChat.SYSTEM:
            message = entry.message
            avatar_pixmap = entry.avatarLabel.pixmap()
            if self.selector in message.systems:
                self._add_message_to_chat(message, avatar_pixmap)

    def location_set(self):
        char = six.text_type(self.playerNamesBox.currentText())
        self.emit(SIGNAL("location_set"), char, self.system.name)

    def set_system_alarm(self):
        self.system.set_status(states.ALARM)
        self.parent.update_map_view()

    def set_system_clear(self):
        self.system.set_status(states.CLEAR)
        self.parent.update_map_view()

    def close_dialog(self):
        self.accept()


class ChatEntryWidget(QtGui.QWidget):
    TEXT_SIZE = 11
    SHOW_AVATAR = True
    questionMarkPixmap = None

    def __init__(self, message):
        QtGui.QWidget.__init__(self)
        if not self.questionMarkPixmap:
            self.questionMarkPixmap = QtGui.QPixmap(resourcePath("vi/ui/res/qmark.png")).scaledToHeight(32)
        uic.loadUi(resourcePath("vi/ui/ChatEntry.ui"), self)
        self.avatarLabel.setPixmap(self.questionMarkPixmap)
        self.message = message
        self.update_text()
        self.connect(self.textLabel, SIGNAL("linkActivated(QString)"), self.link_clicked)
        if sys.platform.startswith("win32") or sys.platform.startswith("cygwin"):
            ChatEntryWidget.TEXT_SIZE = 8
        self.change_font_size(self.TEXT_SIZE)
        if not ChatEntryWidget.SHOW_AVATAR:
            self.avatarLabel.setVisible(False)

    def link_clicked(self, link):
        link = six.text_type(link)
        function, parameter = link.split("/", 1)
        if function == "mark_system":
            self.emit(SIGNAL("mark_system"), parameter)
        elif function == "link":
            webbrowser.open(parameter)

    def update_text(self):
        time = datetime.datetime.strftime(self.message.timestamp, "%H:%M:%S")
        text = u"<small>{time} - <b>{user}</b> - <i>{room}</i></small><br>{text}".format(user=self.message.user,
                                                                                         room=self.message.room,
                                                                                         time=time,
                                                                                         text=self.message.message)
        self.textLabel.setText(text)

    def change_font_size(self, new_size):
        font = self.textLabel.font()
        font.setPointSize(new_size)
        self.textLabel.setFont(font)
