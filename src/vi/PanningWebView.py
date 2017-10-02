from PyQt4 import QtCore
from PyQt4.QtCore import QEvent
from PyQt4.QtCore import QPoint
from PyQt4.QtCore import QString
from PyQt4.QtGui import *
from PyQt4.QtWebKit import QWebView


class PanningWebView(QWebView):
    def __init__(self, parent=None):
        super(PanningWebView, self).__init__()
        self.pressed = False
        self.scrolling = False
        self.ignored = []
        self.position = None
        self.offset = 0
        self.handIsClosed = False
        self.clickedInScrollBar = False

    def mousePressEvent(self, mouse_event):
        pos = mouse_event.pos()

        if self.point_in_scroller(pos, QtCore.Qt.Vertical) or self.point_in_scroller(pos, QtCore.Qt.Horizontal):
            self.clickedInScrollBar = True
        else:
            if self.ignored.count(mouse_event):
                self.ignored.remove(mouse_event)
                return QWebView.mousePressEvent(self, mouse_event)

            if not self.pressed and not self.scrolling and mouse_event.modifiers() == QtCore.Qt.NoModifier:
                if mouse_event.buttons() == QtCore.Qt.LeftButton:
                    self.pressed = True
                    self.scrolling = False
                    self.handIsClosed = False
                    QApplication.setOverrideCursor(QtCore.Qt.OpenHandCursor)

                    self.position = mouse_event.pos()
                    frame = self.page().mainFrame()
                    x_tuple = frame.evaluateJavaScript("window.scrollX").toInt()
                    y_tuple = frame.evaluateJavaScript("window.scrollY").toInt()
                    self.offset = QPoint(x_tuple[0], y_tuple[0])
                    return

        return QWebView.mousePressEvent(self, mouse_event)

    def mouseReleaseEvent(self, mouse_event):
        if self.clickedInScrollBar:
            self.clickedInScrollBar = False
        else:
            if self.ignored.count(mouse_event):
                self.ignored.remove(mouse_event)
                return QWebView.mousePressEvent(self, mouse_event)

            if self.scrolling:
                self.pressed = False
                self.scrolling = False
                self.handIsClosed = False
                QApplication.restoreOverrideCursor()
                return

            if self.pressed:
                self.pressed = False
                self.scrolling = False
                self.handIsClosed = False
                QApplication.restoreOverrideCursor()

                event1 = QMouseEvent(QEvent.MouseButtonPress, self.position, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton,
                                     QtCore.Qt.NoModifier)
                event2 = QMouseEvent(mouse_event)
                self.ignored.append(event1)
                self.ignored.append(event2)
                QApplication.postEvent(self, event1)
                QApplication.postEvent(self, event2)
                return
        return QWebView.mouseReleaseEvent(self, mouse_event)

    def mouseMoveEvent(self, mouse_event):
        if not self.clickedInScrollBar:
            if self.scrolling:
                if not self.handIsClosed:
                    QApplication.restoreOverrideCursor()
                    QApplication.setOverrideCursor(QtCore.Qt.ClosedHandCursor)
                    self.handIsClosed = True
                delta = mouse_event.pos() - self.position
                p = self.offset - delta
                frame = self.page().mainFrame()
                frame.evaluateJavaScript(QString("window.scrollTo(%1, %2);").arg(p.x()).arg(p.y()))
                return

            if self.pressed:
                self.pressed = False
                self.scrolling = True
                return
        return QWebView.mouseMoveEvent(self, mouse_event)

    def point_in_scroller(self, position, orientation):
        rect = self.page().mainFrame().scrollBarGeometry(orientation)
        left_top = self.mapToGlobal(QtCore.QPoint(rect.left(), rect.top()))
        right_bottom = self.mapToGlobal(QtCore.QPoint(rect.right(), rect.bottom()))
        global_rect = QtCore.QRect(left_top.x(), left_top.y(), right_bottom.x(), right_bottom.y())
        return global_rect.contains(self.mapToGlobal(position))
