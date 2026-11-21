"""Главное окно DocForge для ПК."""
from __future__ import annotations

import os
import zipfile

from PyQt6.QtCore import QSize, Qt, QUrl, QTimer
from PyQt6.QtGui import QAction, QActionGroup, QDragEnterEvent, QDropEvent, QIcon, QKeySequence, QShortcut
from PyQt6.QtPdf import QPdfSearchModel
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox,
    QPushButton, QStackedWidget, QStyle, QToolBar, QVBoxLayout, QWidget,
)

from . import APP_NAME, AUTHOR, __version__
from .config import Settings
from .document import OPEN_FILTER, LoadedDoc
from .engine import DocError, EngineClient
from .paths import resource
from .printdialog import PrintDialog
from .printjob import PrintController
from .viewer import DocView

ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 50, 300, 10


class MainWindow(QMainWindow):
    def __init__(self, engine: EngineClient, settings: Settings):
        super().__init__()
        self.engine = engine
        self.settings = settings
        self.doc: LoadedDoc | None = None
        self.edit_mode = False
        self.night = bool(settings["night_documents"])
        self.zoom = int(settings["text_scale"])
        self.cur_page, self.page_total = 1, 0
        self.presenting = False
        self._print: PrintController | None = None
        self._pdf_hits: list[int] = []
        self._pdf_pos = -1
        self._find_text = ""

        self.setWindowTitle(APP_NAME)
        icon = resource("icon.png")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1100, 800)
        self.setAcceptDrops(True)

        self.view = DocView(self)
        self.view.bridge.editRequested.connect(self._edit)
        self.view.bridge.pageReported.connect(self._on_page)
        self.view.loaded.connect(self._on_loaded)
        self.view.imageRequested.connect(self._save_image)
        self.view.wheelZoom.connect(lambda d: self._zoom_by(ZOOM_STEP * d))
        self.view.presentationClick.connect(lambda d: self.view.pres_go(d))

        self._build_welcome()
        self._build_search_bar()
        doc_page = QWidget()
        lay = QVBoxLayout(doc_page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.search_bar)
        lay.addWidget(self.view, 1)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.welcome)
        self.stack.addWidget(doc_page)
        self.setCentralWidget(self.stack)

        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_statusbar()
        self._build_presentation_shortcuts()
        self._update_state()

    # ------------------------------------------------------------------ построение интерфейса

    def _build_welcome(self) -> None:
        self.welcome = QWidget()
        lay = QVBoxLayout(self.welcome)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel(f"<h1>{APP_NAME}</h1><p>Просмотр и правка DOCX, XLSX, PPTX, ODT, ODS, ODP и просмотр PDF.<br>"
                       "Всё работает локально, без интернета.</p>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        button = QPushButton("Открыть файл…")
        button.setMinimumHeight(40)
        button.clicked.connect(self.open_dialog)
        lay.addWidget(button, 0, Qt.AlignmentFlag.AlignCenter)
        self.recent_list = QListWidget()
        self.recent_list.setMaximumWidth(620)
        self.recent_list.setMaximumHeight(260)
        self.recent_list.itemActivated.connect(lambda item: self.open_path(item.data(Qt.ItemDataRole.UserRole)))
        self.recent_label = QLabel("Недавние файлы")
        self.recent_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.recent_label)
        lay.addWidget(self.recent_list, 0, Qt.AlignmentFlag.AlignCenter)
        hint = QLabel("Файл можно перетащить в окно. Ctrl+O — открыть, Ctrl+P — печать.")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: gray;")
        lay.addWidget(hint)
        self._fill_recent()

    def _fill_recent(self) -> None:
        self.recent_list.clear()
        from PyQt6.QtWidgets import QListWidgetItem

        items = self.settings.recent()
        for path in items:
            it = QListWidgetItem(f"{os.path.basename(path)}    —    {os.path.dirname(path)}")
            it.setData(Qt.ItemDataRole.UserRole, path)
            self.recent_list.addItem(it)
        self.recent_list.setVisible(bool(items))
        self.recent_label.setVisible(bool(items))

    def _build_search_bar(self) -> None:
        self.search_bar = QWidget()
        lay = QHBoxLayout(self.search_bar)
        lay.setContentsMargins(6, 4, 6, 4)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._search_changed)
        self.search_edit.returnPressed.connect(lambda: self._search_step(False))
        self.search_count = QLabel("")
        self.search_count.setMinimumWidth(110)
        prev = QPushButton("▲")
        nxt = QPushButton("▼")
        close = QPushButton("✕")
        for b in (prev, nxt, close):
            b.setFixedWidth(34)
        prev.clicked.connect(lambda: self._search_step(True))
        nxt.clicked.connect(lambda: self._search_step(False))
        close.clicked.connect(self.close_search)
        lay.addWidget(self.search_edit, 1)
        lay.addWidget(self.search_count)
        lay.addWidget(prev)
        lay.addWidget(nxt)
        lay.addWidget(close)
        self.search_bar.hide()
        for keys, slot in (("Shift+Return", lambda: self._search_step(True)), ("Esc", self.close_search)):
            shortcut = QShortcut(QKeySequence(keys), self.search_edit, activated=slot)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)  # только в поле поиска: Esc нужен ещё и презентации

    def _act(self, text, slot, shortcut=None, icon=None, checkable=False) -> QAction:
        a = QAction(text, self)
        if icon is not None:
            a.setIcon(self.style().standardIcon(icon))
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.setCheckable(checkable)
        if checkable:
            a.toggled.connect(slot)
        else:
            a.triggered.connect(lambda checked=False: slot())
        self.addAction(a)
        return a

    def _build_actions(self) -> None:
        S = QStyle.StandardPixmap
        self.a_open = self._act("Открыть…", self.open_dialog, "Ctrl+O", S.SP_DialogOpenButton)
        self.a_save = self._act("Сохранить", self.save, "Ctrl+S", S.SP_DialogSaveButton)
        self.a_save_as = self._act("Сохранить как…", self.save_as, "Ctrl+Shift+S")
        self.a_export_pdf = self._act("Экспорт в PDF…", self.export_pdf)
        self.a_print = self._act("Печать…", self.print_doc, "Ctrl+P")
        self.a_all_images = self._act("Сохранить все картинки (ZIP)…", self.save_all_images)
        self.a_page_image = self._act("Сохранить страницу PDF как изображение…", self.save_pdf_page)
        self.a_close = self._act("Закрыть документ", self.close_document, "Ctrl+W")
        self.a_quit = self._act("Выход", self.close, "Ctrl+Q")
        self.a_edit = self._act("Режим правки", self.set_edit_mode, "Ctrl+E", S.SP_FileDialogDetailedView, checkable=True)
        self.a_find = self._act("Найти…", self.show_search, "Ctrl+F", S.SP_FileDialogContentsView)
        self.a_goto = self._act("Перейти на страницу…", self.goto_dialog, "Ctrl+G")
        self.a_zoom_in = self._act("Увеличить", lambda: self._zoom_by(ZOOM_STEP), "Ctrl+=")
        self.a_zoom_in2 = self._act("Увеличить", lambda: self._zoom_by(ZOOM_STEP), "Ctrl++")
        self.a_zoom_out = self._act("Уменьшить", lambda: self._zoom_by(-ZOOM_STEP), "Ctrl+-")
        self.a_zoom_reset = self._act("Масштаб 100%", lambda: self._set_zoom(100), "Ctrl+0")
        self.a_night = self._act("Тёмная тема документа", self.set_night, "Ctrl+D", checkable=True)
        self.a_night.setChecked(self.night)
        self.a_present = self._act("Режим презентации", lambda: self.start_presentation(False), "F5", S.SP_MediaPlay)
        self.a_present_here = self._act("Презентация с текущей страницы", lambda: self.start_presentation(True), "Shift+F5")
        self.a_fullscreen = self._act("Во весь экран", self.toggle_fullscreen, "F11")
        self.a_about = self._act("О программе", self.about)
        self.a_clear_recent = self._act("Очистить список", self._clear_recent)

    def _build_menus(self) -> None:
        m = self.menuBar()
        f = m.addMenu("&Файл")
        f.addAction(self.a_open)
        self.recent_menu = f.addMenu("Недавние")
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        f.addSeparator()
        for a in (self.a_save, self.a_save_as, self.a_export_pdf):
            f.addAction(a)
        f.addSeparator()
        f.addAction(self.a_print)
        f.addSeparator()
        f.addAction(self.a_all_images)
        f.addAction(self.a_page_image)
        f.addSeparator()
        f.addAction(self.a_close)
        f.addAction(self.a_quit)

        e = m.addMenu("&Правка")
        e.addAction(self.a_edit)
        e.addAction(self.a_find)

        v = m.addMenu("&Вид")
        for a in (self.a_zoom_in, self.a_zoom_out, self.a_zoom_reset):
            v.addAction(a)
        v.addSeparator()
        v.addAction(self.a_goto)
        v.addAction(self.a_night)
        theme = v.addMenu("Оформление окна")
        group = QActionGroup(self)
        for label, key in (("Как в системе", "system"), ("Светлое", "light"), ("Тёмное", "dark")):
            a = QAction(label, self, checkable=True)
            a.setChecked(self.settings["theme"] == key)
            a.triggered.connect(lambda checked, k=key: self._set_theme(k))
            group.addAction(a)
            theme.addAction(a)
        v.addSeparator()
        v.addAction(self.a_present)
        v.addAction(self.a_present_here)
        v.addAction(self.a_fullscreen)

        h = m.addMenu("&Справка")
        h.addAction(self.a_about)

    def _build_toolbar(self) -> None:
        self.toolbar = QToolBar("Основное")
        self.toolbar.setMovable(False)
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toolbar.setIconSize(QSize(20, 20))
        for a in (self.a_open, self.a_save, self.a_print):
            self.toolbar.addAction(a)
        self.toolbar.addSeparator()
        for a in (self.a_find, self.a_edit, self.a_present):
            self.toolbar.addAction(a)
        self.addToolBar(self.toolbar)

    def _build_statusbar(self) -> None:
        self.page_button = QPushButton("")
        self.page_button.setFlat(True)
        self.page_button.setToolTip("Перейти на страницу")
        self.page_button.clicked.connect(self.goto_dialog)
        self.statusBar().addPermanentWidget(self.page_button)
        self.zoom_label = QLabel("")
        self.statusBar().addPermanentWidget(self.zoom_label)

    def _build_presentation_shortcuts(self) -> None:
        self._pres_shortcuts: list[QShortcut] = []

        def add(keys, slot):
            for k in keys:
                s = QShortcut(QKeySequence(k), self, activated=slot)
                s.setEnabled(False)
                self._pres_shortcuts.append(s)

        add(("Right", "Down", "PgDown", "Space", "Return"), lambda: self.view.pres_go(1))
        add(("Left", "Up", "PgUp", "Backspace"), lambda: self.view.pres_go(-1))
        add(("Home",), lambda: self.view.pres_go(-100000))
        add(("End",), lambda: self.view.pres_go(100000))
        add(("Esc",), self.stop_presentation)

    # ------------------------------------------------------------------ состояние

    def _update_state(self) -> None:
        has = self.doc is not None
        kind = self.doc.kind if has else ""
        self.a_save.setEnabled(has and self.doc.editable and self.doc.dirty)
        self.a_save_as.setEnabled(has and self.doc.editable)
        self.a_export_pdf.setEnabled(has and kind != "pdf")
        self.a_print.setEnabled(has)
        self.a_all_images.setEnabled(has and kind != "pdf")
        self.a_page_image.setEnabled(has and kind == "pdf")
        self.a_close.setEnabled(has)
        self.a_edit.setEnabled(has and self.doc.editable)
        self.a_find.setEnabled(has)
        self.a_goto.setEnabled(has and self.doc.has_pages)
        for a in (self.a_zoom_in, self.a_zoom_in2, self.a_zoom_out, self.a_zoom_reset, self.a_night):
            a.setEnabled(has)
        self.a_present.setEnabled(has and self.doc.has_pages)
        self.a_present_here.setEnabled(has and self.doc.has_pages)
        self.page_button.setVisible(has and self.doc.has_pages and self.page_total > 0)
        self.page_button.setText(f"{self.cur_page} / {self.page_total}")
        self.zoom_label.setText(f"{self.zoom}%" if has else "")
        self._update_title()

    def _update_title(self) -> None:
        if self.doc is None:
            self.setWindowTitle(APP_NAME)
        else:
            self.setWindowTitle(f"{self.doc.name}{' *' if self.doc.dirty else ''} — {APP_NAME}")
        self.a_save.setEnabled(self.doc is not None and self.doc.editable and self.doc.dirty)

    # ------------------------------------------------------------------ открытие и закрытие

    def open_dialog(self) -> None:
        if not self._confirm_discard():
            return
        start = os.path.dirname(self.doc.source_path) if self.doc else ""
        path, _ = QFileDialog.getOpenFileName(self, "Открыть документ", start, OPEN_FILTER)
        if path:
            self.open_path(path, confirmed=True)

    def open_path(self, path: str, confirmed: bool = False) -> None:
        if not confirmed and not self._confirm_discard():
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            doc = LoadedDoc(self.engine, path)
        except DocError as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, APP_NAME, str(e))
            return
        except FileNotFoundError as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, APP_NAME, f"Не удалось запустить движок документов:\n{e}")
            return
        except OSError as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, APP_NAME, f"Не удалось открыть файл: {e.strerror or e}")
            return
        QApplication.restoreOverrideCursor()
        self._drop_document()
        self.doc = doc
        self.edit_mode = False
        self.a_edit.blockSignals(True)
        self.a_edit.setChecked(False)
        self.a_edit.blockSignals(False)
        self.cur_page, self.page_total = 1, 0
        self.close_search()
        self.settings.add_recent(os.path.abspath(path))
        self.view.show_document(doc)
        self.stack.setCurrentIndex(1)
        self._update_state()
        self.statusBar().showMessage(f"{doc.title}", 4000)

    def _drop_document(self) -> None:
        if self.presenting:
            self.stop_presentation()
        self._reset_pdf_model()
        old, self.doc = self.doc, None
        self.view.doc = None
        if old is not None:
            old.close()

    def close_document(self) -> None:
        if not self._confirm_discard():
            return
        self._drop_document()
        self.view.show_document(None)
        self.stack.setCurrentIndex(0)
        self.cur_page, self.page_total = 1, 0
        self._fill_recent()
        self._update_state()

    def _confirm_discard(self) -> bool:
        if self.doc is None or not self.doc.dirty:
            return True
        box = QMessageBox(QMessageBox.Icon.Question, APP_NAME, f"Сохранить изменения в «{self.doc.name}»?", parent=self)
        save = box.addButton("Сохранить", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Не сохранять", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save:
            return self.save()
        return clicked is discard

    def closeEvent(self, event) -> None:
        if not self._confirm_discard():
            event.ignore()
            return
        self._drop_document()
        self.engine.close()
        event.accept()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.open_path(url.toLocalFile())
                break

    def _fill_recent_menu(self) -> None:
        self.recent_menu.clear()
        items = self.settings.recent()
        for path in items:
            a = self.recent_menu.addAction(os.path.basename(path))
            a.setToolTip(path)
            a.triggered.connect(lambda checked=False, p=path: self.open_path(p))
        if items:
            self.recent_menu.addSeparator()
            self.recent_menu.addAction(self.a_clear_recent)
        else:
            self.recent_menu.addAction("Пока пусто").setEnabled(False)

    def _clear_recent(self) -> None:
        self.settings.clear_recent()
        self._fill_recent()

    # ------------------------------------------------------------------ сохранение

    def save(self) -> bool:
        if self.doc is None or not self.doc.editable:
            return True
        try:
            self.doc.save()
        except DocError:
            return self.save_as()  # исходный файл недоступен для записи — предлагаем другое место
        self._update_state()
        self.statusBar().showMessage("Сохранено", 3000)
        return True

    def save_as(self) -> bool:
        if self.doc is None:
            return False
        ext = os.path.splitext(self.doc.name)[1] or "." + self.doc.format.lower()
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить как", self.doc.source_path, f"{self.doc.title} (*{ext})")
        if not path:
            return False
        if not os.path.splitext(path)[1]:
            path += ext
        try:
            self.doc.save(path)
        except DocError as e:
            QMessageBox.critical(self, APP_NAME, str(e))
            return False
        self.settings.add_recent(os.path.abspath(path))
        self._update_state()
        return True

    def export_pdf(self) -> None:
        if self.doc is None or self.doc.kind == "pdf":
            return
        base = os.path.splitext(self.doc.source_path)[0] + ".pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт в PDF", base, "PDF (*.pdf)")
        if not path:
            return
        page = self.view.page()

        def done(file_path: str, ok: bool) -> None:
            page.pdfPrintingFinished.disconnect(done)
            self.view.set_night(self.night)
            self.statusBar().showMessage("PDF сохранён" if ok else "Не удалось создать PDF", 4000)

        page.pdfPrintingFinished.connect(done)
        self.view.set_night(False)
        page.printToPdf(path)

    # ------------------------------------------------------------------ вид

    def _on_loaded(self) -> None:
        self.view.set_night(self.night)
        self.view.set_editing(self.edit_mode)
        self.view.setZoomFactor(self.zoom / 100)

    def _on_page(self, current: int, total: int) -> None:
        self.cur_page, self.page_total = current, total
        self.page_button.setText(f"{current} / {total}")
        self.page_button.setVisible(self.doc is not None and self.doc.has_pages and total > 0)
        self.a_goto.setEnabled(self.doc is not None and self.doc.has_pages)

    def _zoom_by(self, delta: int) -> None:
        self._set_zoom(self.zoom + delta)

    def _set_zoom(self, value: int) -> None:
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, value))
        self.view.setZoomFactor(self.zoom / 100)
        self.zoom_label.setText(f"{self.zoom}%")
        self.settings["text_scale"] = self.zoom

    def set_night(self, on: bool) -> None:
        self.night = bool(on)
        self.settings["night_documents"] = self.night
        self.view.set_night(self.night)

    def _set_theme(self, key: str) -> None:
        from .app import apply_theme

        self.settings["theme"] = key
        apply_theme(QApplication.instance(), key)

    def toggle_fullscreen(self) -> None:
        if self.presenting:
            return
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def goto_dialog(self) -> None:
        if self.doc is None or not self.doc.has_pages or self.page_total < 1:
            return
        n, ok = QInputDialog.getInt(self, "Перейти на страницу", f"Страница (1–{self.page_total}):", self.cur_page, 1, self.page_total)
        if ok:
            self.view.goto_page(n)

    # ------------------------------------------------------------------ правка

    def set_edit_mode(self, on: bool) -> None:
        self.edit_mode = bool(on)
        self.view.set_editing(self.edit_mode)
        self.statusBar().showMessage("Нажмите на абзац, ячейку или текст слайда, чтобы изменить" if on else "", 4000)

    def _edit(self, element_id: str) -> None:
        if not self.edit_mode or self.doc is None or not self.doc.editable:
            return
        try:
            text = self.doc.text_at(element_id)
        except DocError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        new, ok = QInputDialog.getMultiLineText(self, "Правка", "Текст элемента:", text)
        if not ok or new == text:
            return
        try:
            self.doc.edit(element_id, new)
            shown = self.doc.display_at(element_id)
        except DocError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        self.view.set_text(element_id, shown)
        self._update_state()

    # ------------------------------------------------------------------ поиск

    def show_search(self) -> None:
        if self.doc is None:
            return
        self.search_bar.show()
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def close_search(self) -> None:
        self.search_bar.hide()
        self.search_count.setText("")
        self._find_text = ""
        self._pdf_hits, self._pdf_pos = [], -1
        if self.doc is not None and self.doc.kind != "pdf":
            self.view.findText("")
        self.view.setFocus()

    def _search_changed(self, text: str) -> None:
        self._find_text = text
        if self.doc is None:
            return
        if self.doc.kind == "pdf":
            self._pdf_search(text)
        else:
            if not text:
                self.view.findText("")
                self.search_count.setText("")
                return
            self.view.findText(text, QWebEnginePage.FindFlag(0), self._on_find_result)

    def _search_step(self, backwards: bool) -> None:
        if self.doc is None or not self._find_text:
            return
        if self.doc.kind == "pdf":
            if not self._pdf_hits:
                return
            self._pdf_pos = (self._pdf_pos + (-1 if backwards else 1)) % len(self._pdf_hits)
            self._show_pdf_hit()
        else:
            flags = QWebEnginePage.FindFlag.FindBackward if backwards else QWebEnginePage.FindFlag(0)
            self.view.findText(self._find_text, flags, self._on_find_result)

    def _on_find_result(self, result) -> None:
        total = result.numberOfMatches()
        self.search_count.setText("Не найдено" if total == 0 else f"{result.activeMatchOrdinal()} из {total}")

    def _pdf_search(self, text: str) -> None:
        if not hasattr(self, "_pdf_model") or self._pdf_model_doc is not self.doc:
            self._reset_pdf_model()
            self._pdf_model = QPdfSearchModel(self)
            self._pdf_model.setDocument(self.doc.pdf.doc)
            self._pdf_model_doc = self.doc
            self._pdf_model.rowsInserted.connect(self._pdf_results)
            self._pdf_model.modelReset.connect(self._pdf_results)
        self._pdf_hits, self._pdf_pos = [], -1
        self._pdf_model.setSearchString(text)
        if not text:
            self.search_count.setText("")

    def _reset_pdf_model(self) -> None:
        model = getattr(self, "_pdf_model", None)
        if model is not None:
            model.setSearchString("")
            model.setDocument(None)
            model.deleteLater()
            del self._pdf_model
        self._pdf_model_doc = None
        self._pdf_hits, self._pdf_pos = [], -1

    def _pdf_results(self, *args) -> None:
        model = self._pdf_model
        role = QPdfSearchModel.Role.Page.value
        self._pdf_hits = [int(model.data(model.index(i, 0), role)) + 1 for i in range(model.rowCount())]
        if not self._find_text:
            self.search_count.setText("")
        elif not self._pdf_hits:
            self.search_count.setText("Не найдено (у сканов нет текста)")
        else:
            if self._pdf_pos < 0:
                self._pdf_pos = 0
                self._show_pdf_hit(first=True)
            self.search_count.setText(f"{self._pdf_pos + 1} из {len(self._pdf_hits)}")

    def _show_pdf_hit(self, first: bool = False) -> None:
        if not self._pdf_hits:
            return
        self.view.goto_page(self._pdf_hits[self._pdf_pos])
        self.search_count.setText(f"{self._pdf_pos + 1} из {len(self._pdf_hits)}")

    # ------------------------------------------------------------------ картинки

    def _save_image(self, url: str, pos) -> None:
        if self.doc is None:
            return
        path = QUrl(url).path()
        if path.startswith("/m/"):
            import urllib.parse

            name = urllib.parse.unquote(path[3:])
            data = self.doc.media(name)
            if data is None:
                return
            target, _ = QFileDialog.getSaveFileName(self, "Сохранить картинку", os.path.basename(name))
            if target:
                with open(target, "wb") as f:
                    f.write(data)
        elif path.startswith("/pdf/"):
            self._save_pdf_page(int(path[5:]) + 1)

    def save_pdf_page(self) -> None:
        self._save_pdf_page(self.cur_page)

    def _save_pdf_page(self, number: int) -> None:
        if self.doc is None or self.doc.pdf is None:
            return
        target, _ = QFileDialog.getSaveFileName(self, "Сохранить страницу как изображение", f"страница-{number}.png", "PNG (*.png);;JPEG (*.jpg)")
        if not target:
            return
        image = self.doc.pdf.render_image(number - 1, 2480)
        if image is None or not image.save(target):
            QMessageBox.warning(self, APP_NAME, "Не удалось сохранить изображение.")

    def save_all_images(self) -> None:
        if self.doc is None:
            return
        parts = self.doc.image_parts()
        if not parts:
            QMessageBox.information(self, APP_NAME, "В документе нет картинок.")
            return
        base = os.path.splitext(self.doc.source_path)[0] + "-картинки.zip"
        target, _ = QFileDialog.getSaveFileName(self, "Сохранить все картинки", base, "ZIP (*.zip)")
        if not target:
            return
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
            for name in parts:
                data = self.doc.media(name)
                if data is not None:
                    z.writestr(os.path.basename(name), data)
        self.statusBar().showMessage(f"Сохранено картинок: {len(parts)}", 4000)

    # ------------------------------------------------------------------ печать

    def print_doc(self) -> None:
        if self.doc is None:
            return
        if self._print is not None:
            QMessageBox.information(self, APP_NAME, "Печать уже идёт.")
            return
        dialog = PrintDialog(self, self.settings, can_current=self.doc.has_pages, doc_is_pdf=self.doc.kind == "pdf")
        if dialog.exec() != PrintDialog.DialogCode.Accepted or dialog.request is None:
            return
        self._print = PrintController(self, self.view, self.doc, dialog.request, self.cur_page, lambda: self.view.set_night(self.night))
        self._print.finished.connect(lambda: setattr(self, "_print", None))
        self._print.start()

    # ------------------------------------------------------------------ презентация

    def start_presentation(self, from_current: bool) -> None:
        if self.doc is None or not self.doc.has_pages or self.presenting:
            return
        self.close_search()
        self.presenting = True
        self.view.presenting = True
        self._was_maximized = self.isMaximized()
        self.menuBar().hide()
        self.toolbar.hide()
        self.statusBar().hide()
        for s in self._pres_shortcuts:
            s.setEnabled(True)
        self.showFullScreen()
        first = self.cur_page if from_current and self.page_total > 0 else 1
        QTimer.singleShot(150, lambda: self.view.pres_start(first))

    def stop_presentation(self) -> None:
        if not self.presenting:
            return
        self.presenting = False
        self.view.presenting = False
        for s in self._pres_shortcuts:
            s.setEnabled(False)
        self.view.pres_stop()
        self.menuBar().show()
        self.toolbar.show()
        self.statusBar().show()
        self.showMaximized() if self._was_maximized else self.showNormal()

    # ------------------------------------------------------------------ прочее

    def about(self) -> None:
        QMessageBox.about(
            self, f"О программе {APP_NAME}",
            f"<h3>{APP_NAME} {__version__}</h3>"
            "<p>Просмотр и правка DOCX, XLSX, PPTX, ODT, ODS, ODP, просмотр PDF. Работает локально.</p>"
            "<p>Движки документов — те же, что в Android-версии. Печать: системная или встроенная "
            "(PCL 5, PostScript, PDF, foo2zjs и родственные драйверы).</p>"
            f"<p>Автор: {AUTHOR}. Лицензия GPLv3.</p>",
        )
