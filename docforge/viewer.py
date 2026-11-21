"""Окно просмотра документа: QtWebEngine показывает тот же HTML, что и Android-версия, а страница связана с программой мостом."""
from __future__ import annotations

import json
import urllib.parse

from PyQt6.QtCore import QBuffer, QByteArray, QFile, QIODevice, QObject, QPoint, Qt, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import (
    QWebEnginePage, QWebEngineProfile, QWebEngineScript, QWebEngineSettings, QWebEngineUrlRequestJob,
    QWebEngineUrlScheme, QWebEngineUrlSchemeHandler,
)
from PyQt6.QtWidgets import QMenu
from PyQt6.QtWebEngineWidgets import QWebEngineView

from .document import LoadedDoc, image_mime

SCHEME = b"docforge"
BASE = "docforge://local/"
ANDROID_BASE = "https://docforge.local/"  # так движки пишут адреса картинок и в политике безопасности страницы


def register_scheme() -> None:
    """Нужно вызвать до создания QApplication."""
    scheme = QWebEngineUrlScheme(SCHEME)
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    scheme.setFlags(QWebEngineUrlScheme.Flag.SecureScheme)
    QWebEngineUrlScheme.registerScheme(scheme)


# window.Android — тот же мост, что в Android-версии (edit, page, presRect); вызовы ждут, пока откроется канал
_SHIM = r"""
(function () {
  var queue = [], bridge = null;
  function call(name, args) { if (bridge) { bridge[name].apply(bridge, args); } else { queue.push([name, args]); } }
  window.Android = {
    edit: function (id) { call('edit', [String(id)]); },
    page: function (c, t) { call('page', [c | 0, t | 0]); },
    presRect: function (i, x, y, w, h, vw) { call('presRect', [i | 0, +x, +y, +w, +h, +vw]); }
  };
  new QWebChannel(qt.webChannelTransport, function (channel) {
    bridge = channel.objects.bridge;
    queue.forEach(function (q) { bridge[q[0]].apply(bridge, q[1]); });
    queue = [];
  });
})();
"""


def _read_qwebchannel_js() -> str:
    f = QFile(":/qtwebchannel/qwebchannel.js")
    if not f.open(QIODevice.OpenModeFlag.ReadOnly):
        return ""
    return bytes(f.readAll()).decode("utf-8")


class Bridge(QObject):
    """Страница -> программа."""

    editRequested = pyqtSignal(str)
    pageReported = pyqtSignal(int, int)
    presRectReported = pyqtSignal(int, float, float, float, float, float)

    @pyqtSlot(str)
    def edit(self, element_id: str) -> None:
        self.editRequested.emit(element_id)

    @pyqtSlot(int, int)
    def page(self, current: int, total: int) -> None:
        self.pageReported.emit(current, total)

    @pyqtSlot(int, float, float, float, float, float)
    def presRect(self, index: int, x: float, y: float, w: float, h: float, vw: float) -> None:
        self.presRectReported.emit(index, x, y, w, h, vw)


class DocSchemeHandler(QWebEngineUrlSchemeHandler):
    """Отдаёт странице сам документ (/doc), картинки пакета (/m/…) и страницы PDF (/pdf/N). Всё остальное блокируется."""

    def __init__(self, view: "DocView"):
        super().__init__(view)
        self._view = view

    def requestStarted(self, job: QWebEngineUrlRequestJob) -> None:
        doc = self._view.doc
        path = job.requestUrl().path()
        data, mime = None, ""
        if doc is not None:
            if path.startswith("/doc"):
                data, mime = self._view.page_html.encode("utf-8"), "text/html"
            elif path.startswith("/m/"):
                name = urllib.parse.unquote(path[3:])
                data, mime = doc.media(name), image_mime(name) or ""
            elif path.startswith("/pdf/") and doc.pdf is not None:
                try:
                    index = int(path[5:])
                except ValueError:
                    index = -1
                data, mime = doc.pdf.render_jpeg(index, self._view.pdf_width()), "image/jpeg"
        if not data or not mime:
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
            return
        buf = QBuffer(job)
        buf.setData(QByteArray(data))
        buf.open(QIODevice.OpenModeFlag.ReadOnly)
        job.reply(mime.encode("ascii"), buf)


class DocPage(QWebEnginePage):
    def acceptNavigationRequest(self, url: QUrl, nav_type, is_main_frame: bool) -> bool:
        # ссылки внутри документа не открываем: страница — это только отображение файла
        return nav_type != QWebEnginePage.NavigationType.NavigationTypeLinkClicked

    def javaScriptConsoleMessage(self, level, message, line, source) -> None:
        pass


class DocView(QWebEngineView):
    imageRequested = pyqtSignal(str, QPoint)  # адрес картинки, место
    wheelZoom = pyqtSignal(int)               # +1 / -1 при Ctrl+колесо
    presentationClick = pyqtSignal(int)       # -1 назад, +1 вперёд (в режиме презентации)
    loaded = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc: LoadedDoc | None = None
        self.page_html = ""
        self.presenting = False
        self._counter = 0
        self.bridge = Bridge(self)

        from PyQt6.QtWidgets import QApplication

        # отдельный профиль без хранения данных на диске; живёт дольше окна, чтобы страница удалялась раньше профиля
        profile = QWebEngineProfile(QApplication.instance())
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        self._handler = DocSchemeHandler(self)
        profile.installUrlSchemeHandler(SCHEME, self._handler)
        page = DocPage(profile, self)
        self.setPage(page)

        s = page.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)  # нужен только скрипту страницы
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.ErrorPageEnabled, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)

        channel = QWebChannel(page)
        channel.registerObject("bridge", self.bridge)
        page.setWebChannel(channel)
        script = QWebEngineScript()
        script.setName("docforge-bridge")
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        script.setSourceCode(_read_qwebchannel_js() + _SHIM)
        page.scripts().insert(script)

        page.loadFinished.connect(self._on_loaded)

    # ------------------------------------------------------------------ загрузка

    def pdf_width(self) -> int:
        return max(1080, min(2200, int(self.width() * self.devicePixelRatioF() * 1.5)))

    def show_document(self, doc: LoadedDoc | None) -> None:
        self.doc = doc
        if doc is None:
            self.setHtml("")
            return
        # адреса и политика безопасности страницы переписываются на нашу схему, остальное — как в Android-версии
        self.page_html = doc.html.replace(ANDROID_BASE, BASE)
        self._counter += 1
        self.load(QUrl(f"{BASE}doc?{self._counter}"))

    def _on_loaded(self, ok: bool) -> None:
        proxy = self.focusProxy()
        if proxy is not None:
            proxy.removeEventFilter(self)
            proxy.installEventFilter(self)
        self.loaded.emit()

    # ------------------------------------------------------------------ скрипты страницы

    def js(self, code: str, callback=None) -> None:
        if callback is None:
            self.page().runJavaScript(code)
        else:
            self.page().runJavaScript(code, callback)

    def set_night(self, on: bool) -> None:
        self.js(f"if(window.setNight){{setNight({json.dumps(bool(on))})}}")

    def set_editing(self, on: bool) -> None:
        self.js(f"if(window.setEditing){{setEditing({json.dumps(bool(on))})}}")

    def set_text(self, element_id: str, text: str) -> None:
        self.js(f"if(window.setText){{setText({json.dumps(element_id)},{json.dumps(text)})}}")

    def goto_page(self, n: int) -> None:
        self.js(f"if(window.gotoPage){{gotoPage({int(n)})}}")

    def pres_start(self, n: int) -> None:
        self.js(f"if(window.presStart){{presStart({int(n)})}}")

    def pres_stop(self) -> None:
        self.js("if(window.presStop){presStop()}")

    def pres_go(self, delta: int) -> None:
        self.js(f"if(window.presGo){{presGo({int(delta)})}}")

    # ------------------------------------------------------------------ события

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent

        t = event.type()
        if t == QEvent.Type.Wheel:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.wheelZoom.emit(1 if event.angleDelta().y() > 0 else -1)
                return True
            if self.presenting:
                self.presentationClick.emit(-1 if event.angleDelta().y() > 0 else 1)
                return True
        elif self.presenting and t == QEvent.Type.MouseButtonRelease:
            # слева — назад, остальное — вперёд; правая кнопка — назад
            if event.button() == Qt.MouseButton.RightButton:
                self.presentationClick.emit(-1)
            elif event.button() == Qt.MouseButton.LeftButton:
                self.presentationClick.emit(-1 if event.position().x() < self.width() / 3 else 1)
            return True
        elif self.presenting and t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            return True
        return super().eventFilter(obj, event)

    def contextMenuEvent(self, event) -> None:
        if self.presenting or self.doc is None:
            return
        request = self.lastContextMenuRequest()
        menu = QMenu(self)
        if request is not None and request.mediaType() == request.MediaType.MediaTypeImage and request.mediaUrl().isValid():
            url = request.mediaUrl().toString()
            act = QAction("Сохранить картинку…", menu)
            act.triggered.connect(lambda: self.imageRequested.emit(url, event.globalPos()))
            menu.addAction(act)
        copy = self.pageAction(QWebEnginePage.WebAction.Copy)
        if copy.isEnabled():
            menu.addAction(copy)
        if not menu.isEmpty():
            menu.exec(event.globalPos())
