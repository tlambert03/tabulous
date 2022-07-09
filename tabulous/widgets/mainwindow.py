from __future__ import annotations
from functools import partial
from pathlib import Path
import weakref
from typing import TYPE_CHECKING, Any, Callable, Union
from psygnal import Signal, SignalGroup

from .table import TableLayer
from .tablelist import TableList
from .keybindings import register_shortcut

from ..types import WidgetType
from .._qt import QMainWindow, QMainWidget, get_app

if TYPE_CHECKING:
    from .._qt._dockwidget import QtDockWidget
    from .._qt._mainwindow import _QtMainWidgetBase
    from qtpy.QtWidgets import QWidget
    from magicgui.widgets import Widget

PathLike = Union[str, Path, bytes]


class TableViewerSignal(SignalGroup):
    current_index = Signal(int)


class _TableViewerBase:
    events: TableViewerSignal
    _qwidget_class: type[_QtMainWidgetBase]
    
    def __init__(
        self,
        *, 
        widget_type: WidgetType | str = WidgetType.list,
        show: bool = True
    ):
        app = get_app()
        self._qwidget = self._qwidget_class(widget_type=widget_type)
        self._qwidget._table_viewer = self
        self._tablist = TableList(parent=self)
        self._link_events()
        
        self.events = TableViewerSignal()
        
        if show:
            self.show()

    def reset_choices(self, *_):
        pass
    
    def _move_pytable(self, src: int, dst: int):
        """Move evented list when list is moved in GUI."""
        with self._tablist.events.blocked():
            if dst > src:
                dst += 1
            self._tablist.move(src, dst)
    
    def _move_qtable(self, src: int, dst: int):
        """Move backend tab list widget when programmatically moved."""
        with self._tablist.events.blocked():
            self._qwidget._tablist.moveTable(src, dst)

    def _rename_pytable(self, index: int, name: str):
        with self._tablist.events.blocked():
            self._tablist.rename(index, name)

    def _remove_pytable(self, index: int):
        with self._tablist.events.blocked():
            del self._tablist[index]

    @property
    def tables(self) -> TableList:
        """Return the table list object."""
        return self._tablist
    
    @property
    def current_table(self) -> TableLayer:
        """Return the currently visible table."""
        return self.tables[self.current_index]
    
    @property
    def current_index(self) -> int:
        """Return the index of currently visible table."""
        return self._qwidget._tablist.currentIndex()
    
    @current_index.setter
    def current_index(self, index: int | str):
        if isinstance(index, str):
            index = self.tables.index(index)
        elif index < 0:
            index += len(self.tables)
        return self._qwidget._tablist.setCurrentIndex(index)
    
    def bind_key(self, *seq) -> Callable[[TableViewer], Any | None]:
        def register(f):
            register_shortcut(seq, self._qwidget, partial(f, self))
        return register
    
    def show(self):
        """Show the widget."""
        self._qwidget.show()
    
    def add_table(self, data, *, name: str = None, editable: bool = False) -> TableLayer:
        table = TableLayer(data, name=name, editable=editable)
        return self.add_layer(table)
    
    def add_layer(self, layer):
        self.tables.append(layer)
        self.current_index = -1  # activate the last table
        return layer
    
    def read_csv(self, path, *args, **kwargs):
        import pandas as pd
        df = pd.read_csv(path, *args, **kwargs)
        name = Path(path).stem
        self.add_table(df, name=name)
        return df
    
    def read_excel(self, path, *args, **kwargs):
        import pandas as pd
        df_dict = pd.read_excel(path, *args, **kwargs)
        
        for sheet_name, df in df_dict.items():
            self.add_table(df, name=sheet_name)
        return df_dict

    def open(self, path: PathLike) -> None:
        path = Path(path)
        suf = path.suffix
        if suf in (".csv", ".txt", ".dat"):
            self.read_csv(path)
        elif suf in (".xlsx", ".xls", "xml"):
            self.read_excel(path)
        else:
            raise ValueError(f"Extension {suf} not supported.")
    
    def save(self, path: PathLike) -> None:
        path = Path(path)
        suf = path.suffix
        df = self.current_table.data
        if suf in (".csv", ".txt", ".dat"):
            df.to_csv(path)
        elif suf in (".xlsx", ".xls", "xml"):
            df.to_excel(path)
        else:
            raise ValueError(f"Extension {suf} not supported.")

    def _link_events(self):
        _tablist = self._tablist
        _qtablist = self._qwidget._tablist
        
        @_tablist.events.inserted.connect
        def _insert_qtable(i: int):
            table = _tablist[i]
            _qtablist.addTable(table._qwidget, table.name)
        
        @_tablist.events.removed.connect
        def _remove_qtable(index: int, table: TableLayer):
            with _tablist.events.blocked():
                _qtablist.takeTable(index)
        
        @_tablist.events.moved.connect
        def _move_qtable(src: int, dst: int):
            with _tablist.events.blocked():
                _qtablist.moveTable(src, dst)
        
        @_tablist.events.renamed.connect
        def _rename_qtable(index: int, name: str):
            with _tablist.events.blocked():
                _qtablist.renameTable(index, name)

        @_qtablist.itemMoved.connect
        def _move_pytable(src: int, dst: int):
            """Move evented list when list is moved in GUI."""
            with self._tablist.events.blocked():
                if dst > src:
                    dst += 1
                self._tablist.move(src, dst)
        
        @_qtablist.tableRenamed.connect
        def _rename_pytable(index: int, name: str):
            with self._tablist.events.blocked():
                self._tablist.rename(index, name)
        
        @_qtablist.tableRemoved.connect
        def _remove_pytable(index: int):
            with self._tablist.events.blocked():
                del self._tablist[index]    
        
        _qtablist.itemDropped.connect(self.open)
        
        # reset choices when something changed in python table list
        _tablist.events.inserted.connect(self.reset_choices)
        _tablist.events.removed.connect(self.reset_choices)
        _tablist.events.moved.connect(self.reset_choices)
        _tablist.events.changed.connect(self.reset_choices)
        _tablist.events.renamed.connect(self.reset_choices)


class TableViewerWidget(_TableViewerBase):
    """The non-main table viewer widget."""
    events: TableViewerSignal
    
    _qwidget_class = QMainWidget
    _qwidget: QMainWidget

    def add_widget(
        self, widget: Widget | QWidget, *, name: str = "",
    ):
        backend_widget, name = _normalize_widget(widget, name)
        backend_widget.setParent(self._qwidget, backend_widget.windowFlags())
        return backend_widget
    
class TableViewer(_TableViewerBase):
    """The main table viewer widget."""
    events: TableViewerSignal
    _dock_widgets: weakref.WeakValueDictionary[str, QtDockWidget]
    
    _qwidget_class = QMainWindow
    _qwidget: QMainWindow
    
    def __init__(self, *, widget_type: WidgetType | str = WidgetType.list, show=True):
        super().__init__(widget_type=widget_type, show=show)
        self._dock_widgets = weakref.WeakValueDictionary()
    
    # def register_action(self, location: str):
    #     return self._qwidget.registerAction(location)
    
    def add_dock_widget(
        self, 
        widget: Widget | QWidget,
        *,
        name: str = "",
        area: str = "right",
        allowed_areas: list[str] = None,
    ):
        backend_widget, name = _normalize_widget(widget, name)
            
        dock = self._qwidget.addDockWidget(
            backend_widget, name=name, area=area, allowed_areas=allowed_areas
        )
        dock.setSourceObject(widget)
        self._dock_widgets[name] = dock
        return dock
    
    def remove_dock_widget(self, name_or_widget):
        if isinstance(name_or_widget, str):
            name = name_or_widget
            dock = self._dock_widgets[name_or_widget]
        else:
            for k, v in self._dock_widgets.items():
                if v is name_or_widget:
                    name = k
                    dock = v
                    break
            else:
                raise ValueError(f"Widget {name_or_widget} not found.")
        self._qwidget.removeDockWidget(dock)
        self._dock_widgets.pop(name)
        return None
    
    def reset_choices(self, *_):
        for dock in self._dock_widgets.values():
            widget = dock.widget
            if hasattr(widget, "reset_choices"):
                widget.reset_choices()

def _normalize_widget(widget: Widget | QWidget, name: str) -> tuple[QWidget, str]:
    if hasattr(widget, "native"):
        backend_widget = widget.native
        if not name:
            name = widget.name
    else:
        backend_widget = widget
        if not name:
            name = backend_widget.objectName()
    
    return backend_widget, name