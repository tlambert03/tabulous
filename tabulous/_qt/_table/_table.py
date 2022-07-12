from __future__ import annotations
from typing import Any
from io import StringIO
import numpy as np
import pandas as pd

from ._table_base import QTableLayerBase
from ._model import DataFrameModel, SpreadSheetModel


class QTableLayer(QTableLayerBase):

    def getDataFrame(self) -> pd.DataFrame:
        return self._data_raw

    def setDataFrame(self, data: pd.DataFrame) -> None:
        self._data_raw = data
        self.model().df = data
        self._filter_slice = None  # filter should be reset
        self.viewport().update()
        return

    def createModel(self) -> DataFrameModel:
        return DataFrameModel(self)
    
    def convertValue(self, r: int, c: int, value: Any) -> Any:
        """Convert value to the type of the table."""
        kind = self._data_raw.dtypes[c].kind
        return _DTYPE_CONVERTER[kind](value)

def _bool_converter(val: Any):
    if isinstance(val, str):
        if val in ("True", "1", "true"):
            return True
        elif val in ("False", "0", "false"):
            return False
        else:
            raise ValueError(f"Cannot convert {val} to bool.")
    else:
        return bool(val)
    
_DTYPE_CONVERTER = {
    "i": int,
    "f": float,
    "u": int,
    "b": _bool_converter,
    "U": str,
    "O": lambda e: e,
    "c": complex,
    "M": pd.to_datetime,
    "m": pd.to_timedelta,
}

class QSpreadSheet(QTableLayerBase):
    """
    A table layer class that works similar to Excel sheet.
    
    Unlike ``QTableLayer``, this class does not have dtype. The dtype will be 
    determined every time table data is converted into DataFrame. Table data
    is (almost) unbounded.
    """
    def __init__(self, parent = None, data: pd.DataFrame | None = None):
        super().__init__(parent, data)
        self._data_cache = None

    def getDataFrame(self) -> pd.DataFrame:
        if self._data_cache is not None:
            return self._data_cache
        # Convert table data into a DataFrame with the optimal dtypes
        buf = StringIO(self._data_raw.to_string())
        out = pd.read_csv(buf, sep="\s+")
        self._data_cache = out
        return out
    
    def setDataFrame(self, data: pd.DataFrame) -> None:
        self._data_raw = data.astype("string")
        self._data_cache = None
        self.model().df = data
        self._filter_slice = None  # filter should be reset
        self.update()
        return
    
    def createModel(self) -> SpreadSheetModel:
        return SpreadSheetModel(self)
    
    def convertValue(self, r: int, c: int, value: Any) -> Any:
        """Convert value to the type of the table."""
        return value
    
    def readClipBoard(self):
        return pd.read_clipboard(header=None).astype("string")
    
    def setDataFrameValue(self, r: int | slice, c: int | slice, value: Any) -> None:
        if isinstance(value, str) and value == "":
            return

        nr, nc = self._data_raw.shape
        rmax = _get_limit(r)
        cmax = _get_limit(c)
        if nr <= rmax or nc <= cmax:
            if nr <= rmax:
                self.expandRows(rmax - nr + 1)
            if self._data_raw.shape[1] <= cmax:  # NOTE: DataFrame shape is updated
                self.expandColumns(cmax - nc + 1)
            new_shape = self._data_raw.shape
            self.model().setShape(new_shape[0] + 10, new_shape[1] + 10)    
        
        self._data_cache = None
        super().setDataFrameValue(r, c, value)
        
        self.setFilter(self._filter_slice)
        return None
    
    def expandRows(self, n_expand: int):
        if self._data_raw.size == 0:
            self._data_raw = pd.DataFrame(
                np.full((n_expand,  1), np.nan),
                index=range(n_expand),
                dtype="string",
            )
            return
        nr, nc = self._data_raw.shape
        ext = pd.DataFrame(
            np.full((n_expand, nc), np.nan),
            index=range(nr, n_expand + nr),
            columns=self._data_raw.columns,
            dtype="string",
        )
        self._data_raw = pd.concat([self._data_raw, ext], axis=0)
        return None
    
    def expandColumns(self, n_expand: int):
        if self._data_raw.size == 0:
            self._data_raw = pd.DataFrame(
                np.full((1, n_expand), np.nan),
                columns=range(n_expand),
                dtype="string",
            )
            return
        nr, nc = self._data_raw.shape
        ext = pd.DataFrame(
            np.full((nr, n_expand), np.nan),
            index=self._data_raw.index,
            columns=range(nc, n_expand + nc),
            dtype="string",
        )
        self._data_raw = pd.concat([self._data_raw, ext], axis=1)
        return None
    
    def setVerticalHeaderValue(self, index: int, value: Any) -> None:
        """Set value of the table vertical header and DataFrame at the index."""
        nrows = self._data_raw.shape[0]
        if index >= nrows:
            self.expandRows(index - nrows + 1)
            self.setFilter(self._filter_slice)

        new_shape = self._data_raw.shape
        self._data_cache = None
        self.setFilter(self._filter_slice)
        self.model().setShape(new_shape[0] + 10, new_shape[1] + 10)
        
        return super().setVerticalHeaderValue(index, value)
    
    def setHorizontalHeaderValue(self, index: int, value: Any) -> None:
        """Set value of the table horizontal header and DataFrame at the index."""
        ncols = self._data_raw.shape[1]
        if index >= ncols:
            self.expandColumns(index - ncols + 1)
            self.setFilter(self._filter_slice)
        
        new_shape = self._data_raw.shape
        self._data_cache = None
        self.setFilter(self._filter_slice)
        self.model().setShape(new_shape[0] + 10, new_shape[1] + 10)
        
        return super().setHorizontalHeaderValue(index, value)

def _get_limit(a) -> int:
    if isinstance(a, int):
        amax = a
    elif isinstance(a, slice):
        amax = a.stop - 1
    else:
        raise TypeError(f"Cannot infer limit of type {type(a)}")
    return amax
