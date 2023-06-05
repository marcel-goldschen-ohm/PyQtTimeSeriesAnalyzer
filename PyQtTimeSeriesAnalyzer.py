"""
PyQtTimeSeriesAnalyzer.py

Very much still a work in progress.

TODO:
- fix delete series group error
- zero, interpolate, mask
- link ROIs across plots
- edit x, y data in new popup table view
- add series, attr via table view
- hidden series (or just episodes)?
- series tags, tag filter
- dropdown menus for styles... (e.g., line, symbol, etc.)
- refactor for generic series selection and analysis (fits, measures)
- import pCLAMP, LabView data files
- allow 2D or 3D series data?
- requirements.txt
- detailed instructions in the associated README.md file
- package for pip/conda install
"""


__author__ = "Marcel P. Goldschen-Ohm"
__author_email__ = "goldschen-ohm@utexas.edu, marcel.goldschen@gmail.com"


import sys, os, re, ast, copy
import numpy as np
import scipy as sp
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import pyqtgraph as pg

# OPTIONAL: For some nice icons. Highly recommended.
try:
    # https://github.com/spyder-ide/qtawesome
    import qtawesome as qta
except ImportError:
    qta = None

# OPTIONAL: Only needed for fitting custom curve equations.
try:
    import lmfit
except ImportError:
    lmfit = None

# OPTIONAL: Interactive python console for the UI.
# !!! The run() function in this module will probably provide a better console experience alongside the UI than pyqtconsole.
try:
    # https://github.com/pyqtconsole/pyqtconsole
    from pyqtconsole.console import PythonConsole
except ImportError:
    PythonConsole = None

# OPTIONAL: For importing HEKA data files.
try:
    # https://github.com/campagnola/heka_reader
    # e.g., Just put heka_reader.py in the same directory as this file.
    import heka_reader
except ImportError:
    heka_reader = None


pg.setConfigOption('background', (200, 200, 200))  # Default background for plots.
pg.setConfigOption('foreground', (0, 0, 0))   # Default foreground color for text, lines, axes, etc.


class QtTimeSeriesAnalyzer2(QWidget):
    """ Viewer/Analyzer for a collection of time (ar any x,y) series. """

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)

        self.data = []

        self.initUI()
        self.updateUI()
    
    def sizeHint(self):
        return QSize(800, 600)
    
    def addSeries(self, **kwargs):
        seriesDict = kwargs
        self.data.append(seriesDict)
        self.updateUI()
    
    def seriesAttr(self, attr, seriesDictOrIndexOrListThereof=None):
        if seriesDictOrIndexOrListThereof is None:
            # default to list of all series indexes
            seriesDictOrIndexOrListThereof = list(range(len(self.data)))

        if isinstance(seriesDictOrIndexOrListThereof, int):
            index = seriesDictOrIndexOrListThereof
            series = self.data[index]
        elif isinstance(seriesDictOrIndexOrListThereof, dict):
            index = None
            series = seriesDictOrIndexOrListThereof
        elif isinstance(seriesDictOrIndexOrListThereof, list):
            seriesDictOrIndexList = seriesDictOrIndexOrListThereof
            values = [self.seriesAttr(attr, seriesDictOrIndex) for seriesDictOrIndex in seriesDictOrIndexList]
            return values
        else:
            raise TypeError('Input must be either a series index or a series dict or a list thereof.')
        
        value = series[attr] if attr in series else None

        if value is None:
            # default values
            if attr == 'x':
                if 'y' in series:
                    N = len(series['y'])
                    value = np.arange(N)
            elif attr in ['xlabel', 'ylabel']:
                value = ''
            elif attr == 'episode':
                # assign episode based on index of series within all series having the same group and name
                if index is None:
                    index = self.data.index(series)
                group = self.seriesAttr('group', series)
                name = self.seriesAttr('name', series)
                indexes = self.seriesIndexes(groups=[group], names=[name])
                value = indexes.index(index)
            elif attr == 'group':
                value = 0
            # elif attr == 'name':
            #     value = ''
            elif attr == 'style':
                value = {}
            # elif attr == 'labels':
            #     value = []
            # elif attr == 'xlink':
            #     value = 0
        elif attr == 'x':
            # convert sample interval to 1D array?
            if isinstance(value, float) or isinstance(value, int):
                if 'y' in series:
                    N = len(series['y'])
                    if N > 1:
                        value = np.arange(N) * value
        
        return value
    
    def setSeriesAttr(self, attr, value, seriesDictOrIndexOrListThereof=None):
        if seriesDictOrIndexOrListThereof is None:
            # default to list of all series indexes
            seriesDictOrIndexOrListThereof = list(range(len(self.data)))

        if isinstance(seriesDictOrIndexOrListThereof, int):
            index = seriesDictOrIndexOrListThereof
            series = self.data[index]
        elif isinstance(seriesDictOrIndexOrListThereof, dict):
            index = None
            series = seriesDictOrIndexOrListThereof
        elif isinstance(seriesDictOrIndexOrListThereof, list):
            seriesDictOrIndexList = seriesDictOrIndexOrListThereof
            for seriesDictOrIndex in seriesDictOrIndexList:
                self.setSeriesAttr(attr, value, seriesDictOrIndex)
            return
        else:
            raise TypeError('Input must be either a series index or a series dict or a list thereof.')
        
        if value is None:
            if attr in series:
                del series[attr]
            return
        
        series[attr] = value
    
    def styleAttr(self, style: dict, attr):
        attr = attr.lower()
        value = style[attr] if attr in style else None
        if value is not None:
            return value
        
        # search for an associated attr
        attrGroups = [
            ['color', 'c'],
            ['linestyle', 'ls'],
            ['linewidth', 'lw'],
            ['marker', 'm'],
            ['markersize', 'ms'],
            ['markeredgewidth', 'mew'],
            ['markeredgecolor', 'mec'],
            ['markerfacecolor', 'mfc']
        ]
        for attrGroup in attrGroups:
            if attr in attrGroup:
                for key in attrGroup:
                    if key in style:
                        return style[key]
                return None
        
        return None
    
    def setStyleAttr(self, style: dict, attr, value):
        # if attr in ['color', 'c']:
        #     # transparent color => None
        #     if len(value) == 4 and value[3] == 0:
        #         value = None
        
        attr = attr.lower()
        if attr in style:
            if value is None:
                del style[attr]
            else:
                style[attr] = value
            return

        # search for an associated attr
        attrGroups = [
            ['color', 'c'],
            ['linestyle', 'ls'],
            ['linewidth', 'lw'],
            ['marker', 'm'],
            ['markersize', 'ms'],
            ['markeredgewidth', 'mew'],
            ['markeredgecolor', 'mec'],
            ['markerfacecolor', 'mfc']
        ]
        for attrGroup in attrGroups:
            if attr in attrGroup:
                for key in attrGroup:
                    if key in style:
                        if value is None:
                            del style[key]
                        else:
                            style[key] = value
                        return
        
        if value is not None:
            style[attr] = value
    
    def seriesIndexes(self, episodes=None, groups=None, names=None) -> list:
        indexes = []
        for i in range(len(self.data)):
            if episodes is None or self.seriesAttr('episode', i) in episodes:
                if groups is None or self.seriesAttr('group', i) in groups:
                    if names is None or self.seriesAttr('name', i) in names:
                        indexes.append(i)
        return indexes
    
    def seriesEpisodes(self, seriesIndexes=None) -> list:
        return np.unique(self.seriesAttr('episode', seriesIndexes)).tolist()
    
    def seriesGroups(self, seriesIndexes=None) -> list:
        if isinstance(seriesIndexes, int):
            seriesIndexes = [seriesIndexes]
        groups = []
        for group in self.seriesAttr('group', seriesIndexes):
            if group not in groups:
                groups.append(group)
        if groups and np.all([isinstance(group, int) for group in groups]):
            groups = sorted(groups)
        return groups
    
    def seriesNames(self, seriesIndexes=None) -> list:
        if isinstance(seriesIndexes, int):
            seriesIndexes = [seriesIndexes]
        names = []
        for name in self.seriesAttr('name', seriesIndexes):
            if name not in names:
                names.append(name)
        return names
    
    def groupNames(self, groups=None) -> list:
        if groups is None:
            groups = self.seriesGroups()
        names = []
        for group in groups:
            name = group if isinstance(group, str) else str(group)
            if isinstance(group, int):
                # name -> int: ylabel
                indexes = self.seriesIndexes(groups=[group])
                for index in indexes:
                    ylabel = self.seriesAttr('ylabel', index)
                    if ylabel != "":
                        name += ": " + ylabel
                        break
            names.append(name)
        return names
    
    def visibleSeriesEpisodes(self) -> list:
        return self.seriesEpisodes() # TODO
    
    def setVisibleSeriesEpisodes(self, episodes: list):
        pass # TODO
    
    def visibleSeriesGroups(self) -> list:
        return self.seriesGroups() # TODO
    
    def setVisibleSeriesGroups(self, groups: list):
        pass # TODO
    
    def visibleSeriesNames(self) -> list:
        return self.seriesNames() # TODO
    
    def setVisibleSeriesNames(self, names: list):
        pass # TODO
    
    def initUI(self):
        self._toolbar = QToolBar()

        self._groupPlotsLayout = QVBoxLayout()

        self._mainLayout = QVBoxLayout(self)
        self._mainLayout.addWidget(self._toolbar)
        self._mainLayout.addLayout(self._groupPlotsLayout)
    
    def updateUI(self):
        self._updateGroupPlots()
    
    def _updateGroupPlots(self):
        visibleEpisodes = self.visibleSeriesEpisodes()
        visibleGroups = self.visibleSeriesGroups()
        visibleNames = self.visibleSeriesNames()
        groups = self.seriesGroups()
        plots = self.groupPlots()

        for i, group in enumerate(groups):
            # group plot
            if len(plots) > i:
                plot = plots[i]
            else:
                plot = PlotWidget2()
                self._groupPlotsLayout.addWidget(plot, stretch=1)
                plots.append(plot)
            
            # plot series
            indexes = self.seriesIndexes(groups=[group], episodes=visibleEpisodes, names=visibleNames)
            plotDataItems = [item for item in plot.listDataItems() if isinstance(item, PlotDataItem2)]
            textItems = [item for item in plot.getViewBox().allChildren() if isinstance(item, TextItem2)]
            plotDataItemCount = 0
            textItemCount = 0
            colorIndex = 0
            for index in indexes:
                series = self.data[index]
                x = self.seriesAttr('x', series)
                y = self.seriesAttr('y', series)
                if x is None or y is None:
                    continue
                
                if len(plotDataItems) > plotDataItemCount:
                    # update existing plot data item
                    plotDataItem = plotDataItems[plotDataItemCount]
                    plotDataItem.setData(x, y)
                else:
                    # add new plot data item
                    plotDataItem = PlotDataItem2(x, y)
                    plot.addItem(plotDataItem)
                    plotDataItems.append(plotDataItem)
                plotDataItem.seriesDict = series
                
                # style
                style = self.seriesAttr('style', series)
                colorIndex = plotDataItem.setCustomStyle(style, colorIndex)
                
                # axis labels (based on first plot with axis labels)
                if plotDataItemCount == 0 or plot.getAxis('bottom').labelText == '':
                    xlabel = self.seriesAttr('xlabel', index)
                    plot.getAxis('bottom').setLabel(xlabel)
                if plotDataItemCount == 0 or plot.getAxis('left').labelText == '':
                    group = self.seriesAttr('group', index)
                    ylabel = self.seriesAttr('ylabel', index)
                    if isinstance(group, int):
                        ylabel = str(group) + ":" + ylabel
                    plot.getAxis('left').setLabel(ylabel)
                
                # text items
                if 'labels' in series:
                    for label in series['labels']:
                        if len(textItems) > textItemCount:
                            # update existing text item
                            textItem = textItems[textItemCount]
                        else:
                            # add new text item
                            textItem = TextItem2()
                            plot.getViewBox().addItem(textItem)
                            textItems.append(textItem)
                        textItem.seriesDict = series
                        textItem.setLabelDict(label)
                        textItemCount += 1
                
                # next plot data item
                plotDataItemCount += 1
            
            # remove extra plot data items
            while len(plotDataItems) > plotDataItemCount:
                plotDataItem = plotDataItems.pop()
                plot.removeItem(plotDataItem)
                plotDataItem.deleteLater()
            
            # remove extra text items
            while len(textItems) > textItemCount:
                textItem = textItems.pop()
                plot.getViewBox().removeItem(textItem)
                textItem.deleteLater()
                
            # show/hide plot
            if group in visibleGroups:
                plot.show()
            else:
                plot.hide()
        
        # remove extra plots
        while len(plots) > len(groups):
            i = len(plots) - 1
            self._groupPlotsLayout.takeAt(i)
            plot = plots.pop(i)
            plot.deleteLater()

        # left align visible plot axes
        visiblePlots = [plot for plot in plots if plot.isVisible()]
        leftAxisWidths = [plot.getAxis('left').width() for plot in visiblePlots]
        for plot in visiblePlots:
            plot.getAxis('left').setWidth(max(leftAxisWidths))

        # link x-axis
        # TODO: link based on xlink attr?
        for i in range(1, len(plots)):
            plots[i].setXLink(plots[0])
    
    def groupPlots(self):
        widgets = [self._groupPlotsLayout.itemAt(i).widget() for i in range(self._groupPlotsLayout.count())]
        plots = [widget for widget in widgets if isinstance(widget, PlotWidget2)]
        return plots


class PlotWidget2(pg.PlotWidget):
    """ pg.PlotWidget with custom view box. """

    def __init__(self,  *args, **kwargs):
        kwargs['viewBox'] = ViewBox2()
        pg.PlotWidget.__init__(self, *args, **kwargs)

        # colormap (for default line colors)
        self.colormap = [
            [0, 113.9850, 188.9550],
            [216.7500, 82.8750, 24.9900],
            [236.8950, 176.9700, 31.8750],
            [125.9700, 46.9200, 141.7800],
            [118.8300, 171.8700, 47.9400],
            [76.7550, 189.9750, 237.9150],
            [161.9250, 19.8900, 46.9200]
        ]
        self.colorIndex = 0


class ViewBox2(pg.ViewBox):
    """ pg.ViewBox with custom context menu for measuring and curve fitting. """

    def __init__(self,  *args, **kwargs):
        pg.ViewBox.__init__(self, *args, **kwargs)

        self._initContextMenu()

        self._isDrawingROIs = False

        self.sigTransformChanged.connect(self._onViewChanged)
        self.sigResized.connect(self._onViewChanged)
    
    def getPlotItem(self):
        return self.parentWidget()
    
    def getPlotWidget(self):
        return self.getViewWidget()
    
    def mousePressEvent(self, event):
        if self._isDrawingROIs:
            if event.button() == Qt.LeftButton:
                posInAxes = self.mapSceneToView(self.mapToScene(event.pos()))
                if self._roiOrientation == "vertical":
                    posAlongAxis = posInAxes.x()
                elif self._roiOrientation == "horizontal":
                    posAlongAxis = posInAxes.y()
                self._roiStartPos = posAlongAxis
            else:
                self.stopDrawingROIs()
            event.accept()
            return
        pg.ViewBox.mousePressEvent(self, event)
    
    def mouseReleaseEvent(self, event):
        if self._isDrawingROIs:
            if event.button() == Qt.LeftButton:
                self._roi = None
                event.accept()
                return
        pg.ViewBox.mouseReleaseEvent(self, event)
    
    def mouseMoveEvent(self, event):
        if self._isDrawingROIs:
            if event.buttons() & Qt.LeftButton:
                posInAxes = self.mapSceneToView(self.mapToScene(event.pos()))
                if self._roiOrientation == "vertical":
                    posAlongAxis = posInAxes.x()
                elif self._roiOrientation == "horizontal":
                    posAlongAxis = posInAxes.y()
                limits = sorted([self._roiStartPos, posAlongAxis])
                if self._roi is None:
                    self._roi = LinearRegionItem2(orientation=self._roiOrientation, values=limits)
                    self.addItem(self._roi)
                else:
                    self._roi.setRegion(limits)
                event.accept()
                return
        pg.ViewBox.mouseMoveEvent(self, event)
    
    def _initContextMenu(self):
        self._roiMenu = QMenu("ROIs")
        self._roiMenu.addAction("Draw X-Axis ROIs", lambda: self.startDrawingROIs(orientation="vertical"))
        self._roiMenu.addSection(" ")
        self._roiMenu.addAction("Hide All", self.hideROIs)
        self._roiMenu.addAction("Show All", self.showROIs)
        self._roiMenu.addSection(" ")
        self._roiMenu.addAction("Delete All", self.deleteROIs)

        self._measureMenu = QMenu("Measure")
        self._measureMenu.addAction("Mean", lambda: self.measure(measurementType="mean"))
        self._measureMenu.addAction("Median", lambda: self.measure(measurementType="median"))
        self._measureMenu.addAction("Min", lambda: self.measure(measurementType="min"))
        self._measureMenu.addAction("Max", lambda: self.measure(measurementType="max"))
        self._measureMenu.addAction("AbsMax", lambda: self.measure(measurementType="absmax"))
        self._measureMenu.addAction("Variance", lambda: self.measure(measurementType="var"))
        self._measureMenu.addAction("Standard Deviation", lambda: self.measure(measurementType="std"))

        self._curveFitMenu = QMenu("Curve Fit")
        self._curveFitMenu.addAction("Mean", lambda: self.curveFit(fitType="mean"))
        self._curveFitMenu.addAction("Line", lambda: self.curveFit(fitType="line"))
        self._curveFitMenu.addAction("Polynomial", lambda: self.curveFit(fitType="polynomial"))
        self._curveFitMenu.addAction("Spline", lambda: self.curveFit(fitType="spline"))
        self._curveFitMenu.addAction("Custom", lambda method="custom": self.curveFit(fitType=method))

        # append to default context menu
        self.menu.addSection(" ")
        self.menu.addMenu(self._roiMenu)
        self.menu.addSection(" ")
        self.menu.addMenu(self._measureMenu)
        self.menu.addMenu(self._curveFitMenu)
        self.menu.addSection(" ")
    
    def _onViewChanged(self):
        for item in self.allChildren():
            if isinstance(item, LinearRegionItem2):
                # reposition ROI label
                item.updateLabelPos()
    
    def startDrawingROIs(self, orientation="vertical"):
        self._isDrawingROIs = True
        self._roiOrientation = orientation
        self._roi = None

    def stopDrawingROIs(self):
        self._isDrawingROIs = False
        self._roi = None
    
    def hideROIs(self):
        for item in self.allChildren():
            if isinstance(item, LinearRegionItem2):
                item.setVisible(False)
    
    def showROIs(self):
        for item in self.allChildren():
            if isinstance(item, LinearRegionItem2):
                item.setVisible(True)
    
    def deleteROIs(self):
        for item in self.allChildren():
            if isinstance(item, LinearRegionItem2):
                self.removeItem(item)
                item.deleteLater()


class PlotDataItem2(pg.PlotDataItem):
    """ Clickable pg.PlotDataItem with context menu. """

    def __init__(self, *args, **kwargs):
        pg.PlotDataItem.__init__(self, *args, **kwargs)

        self.seriesDict = None

        self.menu = None
    
    def _delete(self):
        self.getViewBox().removeItem(self)
        self.deleteLater()

    def shape(self):
        return self.curve.shape()

    def boundingRect(self):
        return self.shape().boundingRect()
    
    def setName(self, name):
        self.opts['name'] = name
    
    def setCustomStyle(self, style: dict, colorIndex=0):
        plot = self.getViewBox().getPlotWidget()
        tsa = plot.parentWidget()

        # color
        color = tsa.styleAttr(style, 'color')
        if color is not None:
            color = str2color(color)
        if color is None or (len(color) == 4 and color[3] == 0):
            colormap = plot.colormap
            color = colormap[colorIndex % len(colormap)]
            color = [int(c) for c in color]
            if len(color) == 3:
                color.append(255)
            color = tuple(color)
            colorIndex += 1

        # line
        lineStyle = tsa.styleAttr(style, 'linestyle')
        if not isinstance(lineStyle, int):
            lineStyles = {
                '-': Qt.SolidLine, '--': Qt.DashLine, ':': Qt.DotLine, '-.': Qt.DashDotLine, 
                'none': None, '': None, None: Qt.SolidLine
            }
            lineStyle = lineStyles[lineStyle]

        lineWidth = tsa.styleAttr(style, 'linewidth')
        if lineWidth is None:
            lineWidth = 2
        else:
            lineWidth = float(lineWidth)
        
        if lineStyle is None:
            linePen = None
        else:
            linePen = pg.mkPen(color=color, width=lineWidth, style=lineStyle)
        self.setPen(linePen)

        # symbol
        symbol = tsa.styleAttr(style, 'marker')
        self.setSymbol(symbol)
        
        symbolSize = tsa.styleAttr(style, 'markersize')
        if symbolSize is None:
            symbolSize = 10
        else:
            symbolSize = float(symbolSize)
        self.setSymbolSize(symbolSize)

        symbolEdgeWidth = tsa.styleAttr(style, 'markeredgewidth')
        if symbolEdgeWidth is None:
            symbolEdgeWidth = lineWidth
        else:
            symbolEdgeWidth = float(symbolEdgeWidth)
        
        symbolEdgeColor = tsa.styleAttr(style, 'markeredgecolor')
        if symbolEdgeColor is None:
            symbolEdgeColor = color
        else:
            symbolEdgeColor = str2color(symbolEdgeColor)
        
        symbolPen = pg.mkPen(color=symbolEdgeColor, width=symbolEdgeWidth)
        self.setSymbolPen(symbolPen)

        symbolFaceColor = tsa.styleAttr(style, 'markerfacecolor')
        if symbolFaceColor is None:
            symbolFaceColor = symbolEdgeColor[:3] + (0,)
        else:
            symbolFaceColor = str2color(symbolFaceColor)
        self.setSymbolBrush(symbolFaceColor)
        
        return colorIndex
    
    def mouseClickEvent(self, event):
        if event.button() == Qt.RightButton:
            if self.curve.mouseShape().contains(event.pos()):
                if self.raiseContextMenu(event):
                    self._lastClickPos = self.mapToView(event.pos())
                    event.accept()
    
    def raiseContextMenu(self, event):
        menu = self.getContextMenus()
        
        # Let the scene add on to the end of our context menu (this is optional)
        menu = self.scene().addParentContextMenus(self, menu, event)
        
        pos = event.screenPos()
        menu.popup(QPoint(int(pos.x()), int(pos.y())))
        return True
    
    def getContextMenus(self, event=None):
        name = self.name()
        if name is None:
            name = "Data Series"
        self._dataMenu = QMenu(name)
        self._dataMenu.addAction("Rename", self.editNameDialog)
        self._dataMenu.addAction("Edit Style", self.editStyleDialog)
        self._dataMenu.addSection(" ")
        self._dataMenu.addAction("Add Label", self.addTextItem)
        self._dataMenu.addSection(" ")
        self._dataMenu.addAction("Delete", self._delete)

        self.menu = QMenu()
        self.menu.addMenu(self._dataMenu)
        self.menu.addSection(" ")
        return self.menu
    
    def editNameDialog(self):
        name = self.name()
        if name is None:
            name = ''
        name, ok = QInputDialog.getText(self.getViewBox().getPlotWidget(), "Series Name", "Name:", text=name)
        if not ok:
            return
        name = name.strip()
        if name == '':
            name = None

        # update this widget
        self.setName(name)

        # update series dict
        if self.seriesDict is not None:
            if name is None:
                if 'name' in self.seriesDict:
                    del self.seriesDict['name']
                else:
                    self.seriesDict['name'] = name
    
    def editStyleDialog(self):
        try:
            tsa = self.getViewBox().getPlotWidget().parentWidget()
        except:
            tsa = None
        if (tsa is not None) and (self.seriesDict is not None):
            style = tsa.seriesAttr('style', self.seriesDict)
            if style is None:
                style = {}
        else:
            style = None
        
        dlg = QDialog()
        form = QFormLayout(dlg)

        # QPen, QBrush
        pen = pg.mkPen(self.opts['pen'])
        symbolPen = pg.mkPen(self.opts['symbolPen'])
        symbolBrush = pg.mkBrush(self.opts['symbolBrush'])

        # Qt.PenStyle.NoPen = 0
        # Qt.PenStyle.SolidLine = 1
        # Qt.PenStyle.DashLine = 2
        # Qt.PenStyle.DotLine = 3
        # Qt.PenStyle.DashDotLine = 4
        lineStyleComboBox = QComboBox()
        lineStyleComboBox.addItems(['No Line', 'Solid Line', 'Dash Line', 'Dot Line', 'Dash Dot Line'])
        lineStyleComboBox.setCurrentIndex(pen.style())  # Set via a Qt.PenStyle enum value.
        form.addRow('Line Style', lineStyleComboBox)

        lineWidthSpinBox = QDoubleSpinBox()
        lineWidthSpinBox.setMinimum(0)
        lineWidthSpinBox.setValue(pen.widthF())
        form.addRow('Line Width', lineWidthSpinBox)

        if style is not None:
            color = tsa.styleAttr(style, 'color')
            if color is None:
                color = QColor('transparent')
            else:
                color = QColor(*color)
        else:
            color = pen.color()
        colorButton = ColorButton(color)
        defaultColorButton = QPushButton('Default')
        defaultColorButton.setToolTip('Use current color in colormap')
        defaultColorButton.clicked.connect(lambda: colorButton.setColor(QColor('transparent')))
        colorLayout = QHBoxLayout()
        colorLayout.setContentsMargins(0, 0, 0, 0)
        colorLayout.setSpacing(5)
        colorLayout.addWidget(colorButton)
        colorLayout.addWidget(defaultColorButton)
        form.addRow('Color', colorLayout)

        markerComboBox = QComboBox()
        markers = [None, 'o', 't', 't1', 't2', 't3', 's', 'p', 'h', 'star', '+', 'd', 'x']
        markerComboBox.addItems([
            'None', 'Circle', 'Triangle Down', 'Triangle Up', 'Triangle Right', 'Triangle Left', 'Square', 
            'Pentagon', 'Hexagon', 'Star', 'Plus', 'Prism', 'Cross'])
        markerComboBox.setCurrentIndex(markers.index(self.opts['symbol']))
        form.addRow('Marker', markerComboBox)

        markerSizeSpinBox = QDoubleSpinBox()
        markerSizeSpinBox.setMinimum(0)
        markerSizeSpinBox.setValue(self.opts['symbolSize'])
        form.addRow('Marker Size', markerSizeSpinBox)

        markerEdgeWidthSpinBox = QDoubleSpinBox()
        markerEdgeWidthSpinBox.setMinimum(0)
        markerEdgeWidthSpinBox.setValue(symbolPen.widthF())
        form.addRow('Marker Edge Width', markerEdgeWidthSpinBox)

        if style is not None:
            markerEdgeColor = tsa.styleAttr(style, 'markeredgecolor')
            if markerEdgeColor is None:
                markerEdgeColor = QColor('transparent')
            else:
                markerEdgeColor = QColor(*markerEdgeColor)
        else:
            markerEdgeColor = symbolPen.color()
        markerEdgeColorButton = ColorButton(markerEdgeColor)
        defaultMarkerEdgeColorButton = QPushButton('Default')
        defaultMarkerEdgeColorButton.setToolTip('Same as color')
        defaultMarkerEdgeColorButton.clicked.connect(lambda: markerEdgeColorButton.setColor(QColor('transparent')))
        markerEdgeColorLayout = QHBoxLayout()
        markerEdgeColorLayout.setContentsMargins(0, 0, 0, 0)
        markerEdgeColorLayout.setSpacing(5)
        markerEdgeColorLayout.addWidget(markerEdgeColorButton)
        markerEdgeColorLayout.addWidget(defaultMarkerEdgeColorButton)
        form.addRow('Marker Edge Color', markerEdgeColorLayout)

        if style is not None:
            markerFaceColor = tsa.styleAttr(style, 'markerfacecolor')
            if markerFaceColor is None:
                markerFaceColor = QColor('transparent')
            else:
                markerFaceColor = QColor(*markerFaceColor)
        else:
            markerFaceColor = symbolBrush.color()
        markerFaceColorButton = ColorButton(markerFaceColor)
        defaultMarkerFaceColorButton = QPushButton('Default')
        defaultMarkerFaceColorButton.setToolTip('Transparent')
        defaultMarkerFaceColorButton.clicked.connect(lambda: markerFaceColorButton.setColor(QColor('transparent')))
        markerFaceColorLayout = QHBoxLayout()
        markerFaceColorLayout.setContentsMargins(0, 0, 0, 0)
        markerFaceColorLayout.setSpacing(5)
        markerFaceColorLayout.addWidget(markerFaceColorButton)
        markerFaceColorLayout.addWidget(defaultMarkerFaceColorButton)
        form.addRow('Marker Edge Color', markerFaceColorLayout)

        btns = QDialogButtonBox()
        btns.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        dlg.setWindowModality(Qt.ApplicationModal)
        if dlg.exec_() != QDialog.Accepted:
            return
        
        # apply style
        linestyle = lineStyleComboBox.currentIndex()
        lineWidth = lineWidthSpinBox.value()
        color = colorButton.color()
        if color == QColor('transparent'):
            color = None
        marker = markers[markerComboBox.currentIndex()]
        markerSize = markerSizeSpinBox.value()
        markerEdgeWidth = markerEdgeWidthSpinBox.value()
        markerEdgeColor = markerEdgeColorButton.color()
        if markerEdgeColor == QColor('transparent'):
            markerEdgeColor = None
        markerFaceColor = markerFaceColorButton.color()
        if markerFaceColor == QColor('transparent'):
            markerFaceColor = None

        pen.setStyle(linestyle)
        pen.setWidthF(lineWidth)
        if color is not None:
            pen.setColor(color)
        self.setPen(pen)

        self.setSymbol(marker)
        self.setSymbolSize(markerSize)

        symbolPen.setWidthF(markerEdgeWidth)
        if markerEdgeColor is not None:
            symbolPen.setColor(markerEdgeColor)
        else:
            symbolPen.setColor(pen.color())
        self.setSymbolPen(symbolPen)

        if markerFaceColor is not None:
            symbolBrush.setColor(markerFaceColor)
        else:
            r = symbolPen.color().red()
            g = symbolPen.color().green()
            b = symbolPen.color().blue()
            symbolBrush.setColor(QColor(r, g, b, 0))
        self.setSymbolBrush(symbolBrush)

        # update style dict
        if style is None:
            return

        lineStyles = ['none', '-', '--', ':', '-.']
        tsa.setStyleAttr(style, 'linestyle', lineStyles[linestyle])
        tsa.setStyleAttr(style, 'linewidth', lineWidth)
        if colorButton.colorWasPicked():
            if color:
                color = color.red(), color.green(), color.blue(), color.alpha()
            tsa.setStyleAttr(style, 'color', color)
        tsa.setStyleAttr(style, 'marker', marker)
        tsa.setStyleAttr(style, 'markersize', markerSize)
        tsa.setStyleAttr(style, 'markeredgewidth', markerEdgeWidth)
        if markerEdgeColorButton.colorWasPicked():
            if markerEdgeColor:
                markerEdgeColor = markerEdgeColor.red(), markerEdgeColor.green(), markerEdgeColor.blue(), markerEdgeColor.alpha()
            tsa.setStyleAttr(style, 'markeredgecolor', markerEdgeColor)
        if markerFaceColorButton.colorWasPicked():
            if markerFaceColor:
                markerFaceColor = markerFaceColor.red(), markerFaceColor.green(), markerFaceColor.blue(), markerFaceColor.alpha()
            tsa.setStyleAttr(style, 'markerfacecolor', markerFaceColor)
        tsa.setSeriesAttr('style', style, self.seriesDict)
    
    def addTextItem(self):
        if self.seriesDict is None:
            return
        textItem = TextItem2()
        self.getViewBox().addItem(textItem)
        textItem.seriesDict = self.seriesDict
        x = self._lastClickPos.x()
        y = self._lastClickPos.y()
        labelDict = {'x': x, 'y': y, 'text': ''}
        if 'labels' not in self.seriesDict:
            self.seriesDict['labels'] = [labelDict]
        else:
            self.seriesDict['labels'].append(labelDict)
        textItem.setLabelDict(labelDict)
        textItem.editDialog()
        print(self.seriesDict)


class LinearRegionItem2(pg.LinearRegionItem):
    """ pg.LinearRegionItem with optional label in upper left corner and context menu for editing. """

    def __init__(self, *args, **kwargs):
        pg.LinearRegionItem.__init__(self, *args, **kwargs)

        # self._labelItem = None
        self.menu = None

        # self.sigRegionChanged.connect(self._onRegionChanged)
    
    def _delete(self):
        # self.removeLabel()
        self.getViewBox().removeItem(self)
        self.deleteLater()
    
    def _setVisible(self, isVisible: bool):
        self.setVisible(isVisible)
        # if self._labelItem:
        #     self._labelItem.setVisible(isVisible)
    
    # def _onRegionChanged(self):
    #     self.updateLabelPos()
    
    def mouseClickEvent(self, event):
        if event.button() == Qt.RightButton:
            if self.boundingRect().contains(event.pos()):
                if self.raiseContextMenu(event):
                    event.accept()
    
    def raiseContextMenu(self, event):
        menu = self.getContextMenus()
        
        # Let the scene add on to the end of our context menu (this is optional)
        menu = self.scene().addParentContextMenus(self, menu, event)
        
        pos = event.screenPos()
        menu.popup(QPoint(int(pos.x()), int(pos.y())))
        return True
    
    def getContextMenus(self, event=None):
        self._roiMenu = QMenu("ROI")
        self._roiMenu.addAction("Set Limits", self.editDialog)
        self._roiMenu.addSection(" ")
        self._roiMenu.addAction("Hide", lambda: self._setVisible(False))
        self._roiMenu.addSection(" ")
        self._roiMenu.addAction("Delete", self._delete)

        self.menu = QMenu()
        self.menu.addMenu(self._roiMenu)
        self.menu.addSection(" ")
        return self.menu
    
    # def labelText(self):
    #     try:
    #         return self._labelItem.text
    #     except:
    #         return ''
    
    # def setLabelText(self, text):
    #     if text == '':
    #         self.removeLabel()
    #         return
    #     if self._labelItem is None:
    #         self._labelItem = pg.LabelItem(text=text, size="8pt", color=(0,0,0,128))
    #         self._labelItem.setParentItem(self.getViewBox())
    #         self.updateLabelPos()
    #     else:
    #         self._labelItem.setText(text)
    
    # def removeLabel(self):
    #     if self._labelItem is not None:
    #         self.getViewBox().removeItem(self._labelItem)
    #         self._labelItem = None
    
    # def updateLabelPos(self):
    #     """ place label in upper left of visible portion of region """
    #     if self._labelItem is None:
    #         return
    #     viewBox = self.getViewBox()
    #     if self.orientation == 'vertical':
    #         xViewMin, xViewMax = viewBox.viewRange()[0]
    #         xRegionMin, xRegionMax = self.getRegion()
    #         if xRegionMin >= xViewMax or xRegionMax <= xViewMin:
    #             # hide the label if the region is not visible
    #             self._labelItem.setVisible(False)
    #             return
    #         xFraction = (max(xRegionMin, xViewMin) - xViewMin) / (xViewMax - xViewMin)
    #         # itemPos=(0,0) => anchor top left of label
    #         # parentPos=(x,0) => place label anchor at top left of portion of region in view
    #         # offset=(2,2) => offset label 2 pixels right and 2 pixels down
    #         self._labelItem.anchor(itemPos=(0,0), parentPos=(xFraction,0), offset=(2,2))
    #         self._labelItem.setVisible(True)
    #     elif self.orientation == 'horizontal':
    #         yViewMin, yViewMax = viewBox.viewRange()[1]
    #         yRegionMin, yRegionMax = self.getRegion()
    #         if yRegionMin >= yViewMax or yRegionMax <= yViewMin:
    #             # hide the label if the region is not visible
    #             self._labelItem.setVisible(False)
    #             return
    #         yFraction = (yViewMax - min(yRegionMax, yViewMax)) / (yViewMax - yViewMin)
    #         # itemPos=(0,0) => anchor top left of label
    #         # parentPos=(0,y) => place label anchor at top left of portion of region in view
    #         # offset=(2,2) => offset label 2 pixels right and 2 pixels down
    #         self._labelItem.anchor(itemPos=(0,0), parentPos=(0,yFraction), offset=(2,2))
    #         self._labelItem.setVisible(True)
    
    def editDialog(self):
        dlg = QDialog()
        form = QFormLayout(dlg)

        limits = self.getRegion()
        form.addRow('Limits', QLineEdit(str(limits[0])+", "+str(limits[1])))
        # form.addRow('Label', QLineEdit(self.labelText()))

        btns = QDialogButtonBox()
        btns.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        dlg.setWindowModality(Qt.ApplicationModal)
        if dlg.exec_() == QDialog.Accepted:
            limits = [float(value) for value in form.itemAt(0, 1).widget().text().split(',')]
            self.setRegion(sorted(limits))
            # text = form.itemAt(1, 1).widget().text()
            # self.setLabelText(text)


class TextItem2(pg.TextItem):
    """ Draggable pg.TextItem with context menu for editing text, color, etc. """

    def __init__(self, *args, **kwargs):
        pg.TextItem.__init__(self, *args, **kwargs)

        self.seriesDict = None
        self.labelDict = None
        
        self.menu = None

        self.setColor((0,0,0,255))
    
    def _delete(self):
        if self.seriesDict is not None:
            if self.labelDict is not None:
                self.seriesDict['labels'].remove(self.labelDict)
        self.getViewBox().removeItem(self)
        self.deleteLater()
    
    def setLabelDict(self, labelDict: dict):
        self.labelDict = labelDict

        self.setPlainText(labelDict['text'])

        x = labelDict.get('x', self.pos().x())
        y = labelDict.get('y', self.pos().y())
        self.setPos(x, y)

        if 'anchor' in labelDict:
            try:
                halign, valign = labelDict['anchor']
                self.setAnchorAlignment(halign, valign)
            except:
                pass

        if 'color' in labelDict:
            self.setColor(labelDict['color'])

        if 'angle' in labelDict:
            self.setAngle(labelDict['angle'])

        if 'font-size' in labelDict:
            self.textItem.font().setPointSize(labelDict['font-size'])
    
    def mouseClickEvent(self, event):
        if event.button() == Qt.RightButton:
            if self.boundingRect().contains(event.pos()):
                if self.raiseContextMenu(event):
                    event.accept()
    
    def mouseDragEvent(self, event):
        if event.button() == Qt.LeftButton:
            if event.isStart():
                self._dragOffset = self.pos() - self.getViewBox().mapSceneToView(self.mapToScene(event.buttonDownPos()))
            elif event.isFinish():
                self._dragOffset = None
                return
            if self._dragOffset is not None:
                self.setPos(self.getViewBox().mapSceneToView(self.mapToScene(event.pos())) + self._dragOffset)
                event.accept()
    
    def raiseContextMenu(self, event):
        menu = self.getContextMenus()
        
        # Let the scene add on to the end of our context menu (this is optional)
        menu = self.scene().addParentContextMenus(self, menu, event)
        
        pos = event.screenPos()
        menu.popup(QPoint(int(pos.x()), int(pos.y())))
        return True
    
    def getContextMenus(self, event=None):
        self._labelMenu = QMenu("Label")
        self._labelMenu.addAction("Edit", self.editDialog)
        self._labelMenu.addSection(" ")
        self._labelMenu.addAction("Delete", self._delete)

        self.menu = QMenu()
        self.menu.addMenu(self._labelMenu)
        self.menu.addSection(" ")

        return self.menu
    
    def setAnchorAlignment(self, halign, valign):
        if halign == 'left':
            halign = 0
        elif halign == 'right':
            halign = 1
        elif halign == 'center':
            halign = 0.5
        
        if valign == 'top':
            valign = 0
        elif valign == 'bottom':
            valign = 1
        elif valign == 'middle':
            valign = 0.5
        
        self.anchor[0] = halign
        self.anchor[1] = valign
    
    def editDialog(self):
        dlg = QDialog()
        form = QFormLayout(dlg)

        text = self.toPlainText()
        textEdit = QTextEdit()
        textEdit.setPlainText(text)
        form.addRow('Text', textEdit)

        xStr = f'{self.pos().x():.6f}'.rstrip('0').rstrip('.')
        yStr = f'{self.pos().y():.6f}'.rstrip('0').rstrip('.')
        form.addRow('Position', QLineEdit(xStr + ', ' + yStr))

        leftAlignBtn = QRadioButton()
        centerAlignBtn = QRadioButton()
        rightAlignBtn = QRadioButton()
        topAlignBtn = QRadioButton()
        middleAlignBtn = QRadioButton()
        bottomAlignBtn = QRadioButton()
        if self.anchor[0] == 0:
            leftAlignBtn.setChecked(True)
        elif self.anchor[0] == 0.5:
            centerAlignBtn.setChecked(True)
        elif self.anchor[0] == 1:
            rightAlignBtn.setChecked(True)
        if self.anchor[1] == 0:
            topAlignBtn.setChecked(True)
        elif self.anchor[1] == 0.5:
            middleAlignBtn.setChecked(True)
        elif self.anchor[1] == 1:
            bottomAlignBtn.setChecked(True)
        if qta is not None:
            leftAlignBtn.setIcon(qta.icon('mdi.format-horizontal-align-left'))
            centerAlignBtn.setIcon(qta.icon('mdi.format-horizontal-align-center'))
            rightAlignBtn.setIcon(qta.icon('mdi.format-horizontal-align-right'))
            topAlignBtn.setIcon(qta.icon('mdi.format-vertical-align-top'))
            middleAlignBtn.setIcon(qta.icon('mdi.format-vertical-align-center'))
            bottomAlignBtn.setIcon(qta.icon('mdi.format-vertical-align-bottom'))
        else:
            leftAlignBtn.setText('Left')
            centerAlignBtn.setText('Center')
            rightAlignBtn.setText('Right')
            topAlignBtn.setText('Top')
            middleAlignBtn.setText('Middle')
            bottomAlignBtn.setText('Bottom')
        halignBtnGroup = QButtonGroup()
        halignBtnGroup.setExclusive(True)
        halignBtnGroup.addButton(leftAlignBtn)
        halignBtnGroup.addButton(centerAlignBtn)
        halignBtnGroup.addButton(rightAlignBtn)
        valignBtnGroup = QButtonGroup()
        valignBtnGroup.setExclusive(True)
        valignBtnGroup.addButton(topAlignBtn)
        valignBtnGroup.addButton(middleAlignBtn)
        valignBtnGroup.addButton(bottomAlignBtn)
        halignBtnLayout = QHBoxLayout()
        halignBtnLayout.addWidget(leftAlignBtn)
        halignBtnLayout.addWidget(centerAlignBtn)
        halignBtnLayout.addWidget(rightAlignBtn)
        halignBtnLayout.addStretch()
        valignBtnLayout = QHBoxLayout()
        valignBtnLayout.addWidget(topAlignBtn)
        valignBtnLayout.addWidget(middleAlignBtn)
        valignBtnLayout.addWidget(bottomAlignBtn)
        valignBtnLayout.addStretch()
        form.addRow('Horizontal Anchor', halignBtnLayout)
        form.addRow('Vertical Anchor', valignBtnLayout)

        form.addRow('Color', ColorButton(self.color))

        angleSpinBox = QSpinBox()
        angleSpinBox.setValue(self.angle)
        angleSpinBox.setMinimum(-90)
        angleSpinBox.setMaximum(90)
        angleSpinBox.setSuffix(' degrees')
        form.addRow('Rotation', angleSpinBox)

        ptSizeSpinBox = QSpinBox()
        ptSizeSpinBox.setValue(self.textItem.font().pointSize())
        ptSizeSpinBox.setMinimum(1)
        ptSizeSpinBox.setSuffix(' pt')
        form.addRow('Font Size', ptSizeSpinBox)

        btns = QDialogButtonBox()
        btns.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        dlg.setWindowModality(Qt.ApplicationModal)
        if dlg.exec_() != QDialog.Accepted:
            if text == '':
                self._delete()
            return
        
        text = form.itemAt(0, 1).widget().toPlainText()
        if text == '':
            self._delete()
            return
        self.setPlainText(text)

        x, y = [float(value) for value in form.itemAt(1, 1).widget().text().split(',')]
        self.setPos(x, y)

        if halignBtnGroup.checkedButton() is leftAlignBtn:
            self.anchor[0] = 0
            halign = 'left'
        elif halignBtnGroup.checkedButton() is centerAlignBtn:
            self.anchor[0] = 0.5
            halign = 'center'
        elif halignBtnGroup.checkedButton() is rightAlignBtn:
            self.anchor[0] = 1
            halign = 'right'
        if valignBtnGroup.checkedButton() is topAlignBtn:
            self.anchor[1] = 0
            valign = 'top'
        elif valignBtnGroup.checkedButton() is middleAlignBtn:
            self.anchor[1] = 0.5
            valign = 'middle'
        elif valignBtnGroup.checkedButton() is bottomAlignBtn:
            self.anchor[1] = 1
            valign = 'bottom'

        color = form.itemAt(4, 1).widget().color()
        self.setColor(color)

        angle = form.itemAt(5, 1).widget().value()
        self.setAngle(angle)

        fontPointSize = form.itemAt(6, 1).widget().value()
        self.textItem.font().setPointSize(fontPointSize)

        if self.labelDict is None:
            return
        
        self.labelDict['text'] = text
        self.labelDict['x'] = x
        self.labelDict['y'] = y
        self.labelDict['anchor'] = (halign, valign)
        self.labelDict['color'] = (color.red(), color.green(), color.blue(), color.alpha())
        self.labelDict['angle'] = angle
        self.labelDict['font-size'] = fontPointSize








class QtTimeSeriesAnalyzer(QWidget):
    """ Viewer/Analyzer for a collection of time (ar any x,y) series sharing the same x-axis units.
    
    (x,y) data series
    -----------------
    Each series is stored in a dictionary such as { x=..., y=..., xlabel=..., ylabel=..., etc. } for maximum flexibility.
    Multiple series are stored in a list of such dictionaries.
    !!! Currently all series are expected to share the same x-axis units. As such, the x-axis of all plots in the UI are linked.

    Each series dictionary can have any number of attributes for maximum flexibility.
    Currently, the following series attributes are used by the UI:
          x: [OPTIONAL] 1D array of x-axis values -OR- sample interval. Defaults to sample indexes if not specified.
          y: [REQUIRED] 1D array of y-axis values.
     xlabel: [OPTIONAL] x-axis label. !!! Should be the same for all series within each group.
     ylabel: [OPTIONAL] y-axis label. !!! Should be the same for all series within each group.
    episode: [OPTIONAL] Index for, e.g., serial or in-parallel series from the same recording channel.
                        Defaults to index of series within all series having the same group and name.
      group: [OPTIONAL] ID for different types of series (can have different y units).
                        Each group will be displayed in a separate plot vertically stacked for easy comparison across groups along the x-axis.
                        e.g., channel ID for simultaneous recording channels.
                        Defaults to 0 (i.e., all series where group is not specified are in the same group).
       name: [OPTIONAL] String label for further differentiating between multiple series in the same episode and group.
                        e.g., 'original data', 'fit', 'baseline', 'baseline subtracted', 'filtered'
                        Defaults to '' (i.e., all series where name is not specified have the same name).
      style: [OPTIONAL] Dictionary of optional plot style attributes such as { 'color': (255, 0, 0), 'linewidth': 2, 'ls': '--', etc. }
                        Defaults to {} (i.e., use default styles specified in self.state).
                        Currently, the following style attributes are used by the UI:
                                  color   (c): RGB or RGBA tuple (0-255) for line color. Defaults to current color in self.state['line']['colormap'].
                              linestyle  (ls): '-' (solid), '--' (dashed), '-.' (dash-dot), ':' (dotted), 'none' (none). Defaults to solid.
                              linewidth  (lw): Line width in pixels. Defaults to self.state['line']['width'].
                                 marker   (m): '' (none), 'o' (circle), 's' (square), '^' (triangle), etc. Defaults to none.
                             markersize  (ms): Marker size in pixels. Defaults to self.state['marker']['size'].
                        markeredgewidth (mew): Marker edge width in pixels. Defaults to linewidth.
                        markeredgecolor (mec): RGB or RGBA tuple (0-255) for marker edge color. Defaults to color.
                        markerfacecolor (mfc): RGB or RGBA tuple (0-255) for marker face color. Defaults to markeredgecolor.
    
    File I/O
    --------
    Load/Save all series and ROI data from/to a MATLAB .mat file (main menu -> File -> Open/Save).
    This allows simple interoperation with MATLAB (Python list of dicts <-> MATLAB struct array).
    
    User Interface (UI)
    -------------------
    Top toolbar includes main menu, episode traversal, and series visibility controls.
    The UI organizes multiple series by (episode, group, name).
    The UI includes a plot for each visible group stacked vertically.
    Visible groups can be quickly toggled on/off from a dropdown menu.
    Each of the group plots displays all of the series in that group whose episode and name are visible.
    Visible episodes can be entered into a text box as indexes or index ranges and prev/next buttons enable quick traversal across episodes.
    Visible names can be quickly toggled on/off from a dropdown menu.

    Data Series Table View
    ----------------------
    All of the series data can be explored in an editable table view in the UI (main menu -> Data Table).

    Python Console
    --------------
    Optionally, a python console can be spawned (main menu -> Python Console) for interactive analysis of the series data.
    The console uses pyqtconsole which is a full-featured python interpreter with tab-completion, syntax highlighting, etc.
    The console has access to the instance of this class via the variable `self` and thus the series data via `self.data`.
    Note that after manual changes to self.data, you must call self.updateUI() to update the UI.
    !!! The run() function in this module will probably provide a better console experience alongside the UI than pyqtconsole.
    """

    def __init__(self):
        QWidget.__init__(self)

        # List of data series dictionaries { x=..., y=..., xlabel=..., ylabel=..., episode=0, group=2, name=..., style=..., etc. }
        # If you change this manually, call updateUI() to update the UI.
        # !!! Currently only handles 1D series data.
        self.data = []

        # List of region of interest (ROI) dictionaries { xlim=(xmin, xmax), name=... }
        # If you change this manually, call updateUI() to update the UI.
        # !!! Currently only handles x-axis ranges (i.e., ylim is assumed to be (-inf, inf)).
        self.ROIs = []

        # Dictionary of default colors, fonts, etc.
        # !!! The default UI theme may not be appropriate for you. Feel free to edit the colors and fonts in defaultState().
        # TODO: Autodetect system default theme colors and fonts?
        self.state = self.defaultState()

        # UI
        self.initUI()
        self.updateUI()
    
    def defaultState(self):
        state = {}
        state['figure'] = {}
        state['figure']['background-color'] = None  # None ==> use system default
        state['axes'] = {}
        state['axes']['background-color'] = [220, 220, 220]
        state['axes']['foreground-color'] = [128, 128, 128]
        state['axes']['label-font-name'] = 'Helvetica'
        state['axes']['label-font-size'] = 14
        state['axes']['label-font-weight'] = QFont.Normal
        state['axes']['tick-font-name'] = 'Helvetica'
        state['axes']['tick-font-size'] = 10
        state['axes']['tick-font-weight'] = QFont.Thin
        state['line'] = {}
        state['line']['width'] = 2
        state['line']['colormap'] = [
            [0, 113.9850, 188.9550],
            [216.7500, 82.8750, 24.9900],
            [236.8950, 176.9700, 31.8750],
            [125.9700, 46.9200, 141.7800],
            [118.8300, 171.8700, 47.9400],
            [76.7550, 189.9750, 237.9150],
            [161.9250, 19.8900, 46.9200]
        ]
        state['marker'] = {}
        state['marker']['size'] = 10
        return state
    
    # I/O
    
    def clear(self):
        self.data = [{}]
        self.ROIs = {}
        self.updateUI()
    
    def save(self, filepath=None):
        if filepath is None:
            filepath, _ = QFileDialog.getSaveFileName(self, "Save Data", "", "MATLAB Data Files (*.mat)")
        if not filepath:
            return
        savemat(filepath, {"data": self.data})

    def open(self, filepath=None, clear=True):
        print(filepath)
        if filepath is None:
            filepath, _ = QFileDialog.getOpenFileName(self, "Open Data", "", "MATLAB Data Files (*.mat)")
        print(filepath)
        if not filepath or not os.path.isfile(filepath):
            return
        data = loadmat(filepath)
        if clear:
            self.data = data
        else:
            self.data.extend(data)
        self.updateUI()
    
    def importHEKA(self, filepath=None, clear=True):
        """
        Import HEKA data file.

        HEKA format:
        ------------
        Group (Experiment)
            Series (Recording)
                Sweep (Episode)
                    Trace (Data Series for Channel A)
                    Trace (Data Series for Channel B)
        """
        if heka_reader is None:
            return
        if filepath is None:
            filepath, _ = QFileDialog.getOpenFileName(self, "Open HEKA File", "", "HEKA Data Files (*.dat)")
        if not filepath or not os.path.isfile(filepath):
            return
        bundle = heka_reader.Bundle(filepath)
        numHekaGroups = len(bundle.pul)
        if numHekaGroups == 0:
            return
        elif numHekaGroups == 1:
            hekaGroupIndex = 0
        elif numHekaGroups > 1:
            # choose a group (experiment) to load
            hekaGroupNames = [bundle.pul[i].Label for i in range(numHekaGroups)]
            hekaGroupNamesListWidget = QListWidget()
            hekaGroupNamesListWidget.addItems(hekaGroupNames)
            hekaGroupNamesListWidget.setSelectionMode(QAbstractItemView.SingleSelection)
            hekaGroupNamesListWidget.setSelected(hekaGroupNamesListWidget.item(0), True)
            dlg = QDialog()
            dlg.setWindowTitle("Choose Recording")
            buttonBox = QDialogButtonBox()
            buttonBox.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
            buttonBox.accepted.connect(dlg.accept)
            buttonBox.rejected.connect(dlg.reject)
            dlg.setWindowModality(Qt.ApplicationModal)
            if dlg.exec_():
                hekaGroupIndex = hekaGroupNamesListWidget.selectedIndexes()[0].row()
            else:
                return
        data = []
        numHekaSeries = len(bundle.pul[hekaGroupIndex])
        for hekaSeriesIndex in range(numHekaSeries):
            numHekaSweeps = len(bundle.pul[hekaGroupIndex][hekaSeriesIndex])
            for hekaSweepIndex in range(numHekaSweeps):
                episode = hekaSweepIndex
                numHekaTraces = len(bundle.pul[hekaGroupIndex][hekaSeriesIndex][hekaSweepIndex])
                for hekaTraceIndex in range(numHekaTraces):
                    group = hekaTraceIndex
                    trace = bundle.pul[hekaGroupIndex][hekaSeriesIndex][hekaSweepIndex][hekaTraceIndex]
                    x = trace.XInterval + trace.XStart
                    y = bundle.data[(hekaGroupIndex, hekaSeriesIndex, hekaSweepIndex, hekaTraceIndex)] + trace.YOffset
                    xlabel = 'Time, ' + trace.XUnit
                    ylabel = trace.Label + ', ' + trace.YUnit
                    data.append({'x': x, 'y': y, 'xlabel': xlabel, 'ylabel': ylabel, 'episode': episode, 'group': group})
        if not data:
            return
        if clear:
            self.data = data
        else:
            self.data.extend(data)
        self.updateUI()
    
    def numSeries(self) -> int:
        return len(self.data)
    
    def addSeries(self, **kwargs):
        seriesDict = kwargs
        self.data.append(seriesDict)
    
    def addData(self, data, copyData=False):
        """ data = series dict or list of series dicts """
        if copyData:
            data = copy.deepcopy(data)
        if isinstance(data, dict):
            self.data.append(data)
        elif isinstance(data, list):
            for series in data:
                if isinstance(series, dict):
                    self.data.append(series)
                else:
                    raise TypeError('Input list must contain series dicts.')
        else:
            raise TypeError('Input must be either a series dict or a list of series dicts.')
    
    # Series attributes
    
    def _seriesAttr(self, attr, seriesOrSeriesIndexOrListThereof=None):
        if seriesOrSeriesIndexOrListThereof is None:
            seriesOrSeriesIndexOrListThereof = list(range(len(self.data)))  # list of all series indexes

        if isinstance(seriesOrSeriesIndexOrListThereof, int):
            seriesIndex = seriesOrSeriesIndexOrListThereof
            series = self.data[seriesIndex]
        elif isinstance(seriesOrSeriesIndexOrListThereof, dict):
            seriesIndex = None
            series = seriesOrSeriesIndexOrListThereof
        elif isinstance(seriesOrSeriesIndexOrListThereof, list):
            seriesOrSeriesIndexList = seriesOrSeriesIndexOrListThereof
            values = [self._seriesAttr(attr, seriesOrSeriesIndex) for seriesOrSeriesIndex in seriesOrSeriesIndexList]
            return values
        else:
            raise TypeError('Input must be either a series index or a series dict.')
        
        value = series[attr] if attr in series else None

        if value is None:
            # default values
            if attr == 'x':
                if 'y' in series:
                    # n = series['y'].shape[-1]
                    n = len(series['y'])
                    value = np.arange(n)
            elif attr == 'episode':
                # assign episode based on index of series within all series having the same group and name
                if seriesIndex is None:
                    seriesIndex = self.data.index(series)
                group = self._seriesAttr('group', series)
                name = self._seriesAttr('name', series)
                seriesIndexes = self._seriesIndexes(groups=[group], names=[name])
                value = seriesIndexes.index(seriesIndex)
            elif attr == 'group':
                value = 0
            elif attr == 'name':
                value = ''
            elif attr in ['xlabel', 'ylabel']:
                value = ''
            elif attr == 'style':
                value = {}
        elif attr == 'x':
            # convert sample interval to 1D array?
            if isinstance(value, float) or isinstance(value, int):
                if 'y' in series:
                    try:
                        # n = series['y'].shape[-1]
                        n = len(series['y'])
                        if n > 1:
                            value = np.arange(n) * value
                    except:
                        pass
        return value
    
    # Series plot styles
    
    def _styleAttr(self, style: dict, attr):
        attr = attr.lower()
        value = style[attr] if attr in style else None
        if value is not None:
            return value
        attrGroups = [
            ['color', 'c'],
            ['linestyle', 'ls'],
            ['linewidth', 'lw'],
            ['marker', 'm'],
            ['markersize', 'ms'],
            ['markeredgewidth', 'mew'],
            ['markeredgecolor', 'mec'],
            ['markerfacecolor', 'mfc']
        ]
        for attrGroup in attrGroups:
            if attr in attrGroup:
                for key in attrGroup:
                    if key in style:
                        return style[key]
                return None
        return None
    
    def _setStyleAttr(self, style: dict, attr, value):
        attr = attr.lower()
        if attr in style:
            if value is None:
                del style[attr]
            else:
                style[attr] = value
            return
        attrGroups = [
            ['color', 'c'],
            ['linestyle', 'ls'],
            ['linewidth', 'lw'],
            ['marker', 'm'],
            ['markersize', 'ms'],
            ['markeredgewidth', 'mew'],
            ['markeredgecolor', 'mec'],
            ['markerfacecolor', 'mfc']
        ]
        for attrGroup in attrGroups:
            if attr in attrGroup:
                for key in attrGroup:
                    if key in style:
                        if value is None:
                            del style[key]
                        else:
                            style[key] = value
                        return
        if value is not None:
            style[attr] = value
    
    def styleDialog(self, style: dict):
        dlg = QDialog(self)
        dlg.setWindowTitle("Style")
        form = QFormLayout(dlg)
        widgets = {}
        for key in ['linestyle', 'linewidth', 'color', 'marker', 'markersize', 'markeredgewidth', 'markeredgecolor', 'markerfacecolor']:
            value = self._styleAttr(style, key)
            if 'color' in key:
                if value is None:
                    color = QColor('transparent')
                else:
                    color = str2qcolor(value)
                widgets[key] = ColorButton(color)
            else:
                if value is None:
                    value = ''
                widgets[key] = QLineEdit(str(value))
            form.addRow(key, widgets[key])
        buttonBox = QDialogButtonBox()
        buttonBox.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttonBox.accepted.connect(dlg.accept)
        buttonBox.rejected.connect(dlg.reject)
        form.addRow(buttonBox)
        dlg.setWindowModality(Qt.ApplicationModal)
        if dlg.exec_() == QDialog.Accepted:
            for key, widget in widgets.items():
                if isinstance(widget, ColorButton):
                    value = widget.color()
                    if value == QColor('transparent'):
                        value = None
                    else:
                        value = qcolor2str(value)
                elif isinstance(widget, QLineEdit):
                    value = widget.text().strip()
                    if value == '':
                        value = None
                self._setStyleAttr(style, key, value)
            return True
        return False
    
    # Series organization by episode, group, and name
    
    def _seriesIndexes(self, episodes=None, groups=None, names=None) -> list:
        indexes = []
        for i in range(len(self.data)):
            if episodes is None or self._seriesAttr('episode', i) in episodes:
                if groups is None or self._seriesAttr('group', i) in groups:
                    if names is None or self._seriesAttr('name', i) in names:
                        indexes.append(i)
        return indexes
    
    def episodes(self, seriesIndexes=None) -> list:
        return np.unique(self._seriesAttr('episode', seriesIndexes)).tolist()
    
    def groups(self, seriesIndexes=None) -> list:
        if isinstance(seriesIndexes, int):
            seriesIndexes = [seriesIndexes]
        groups = []
        for group in self._seriesAttr('group', seriesIndexes):
            if group not in groups:
                groups.append(group)
        if np.all([isinstance(group, int) for group in groups]):
            groups = np.sort(groups).tolist()
        return groups
    
    def names(self, seriesIndexes=None) -> list:
        if isinstance(seriesIndexes, int):
            seriesIndexes = [seriesIndexes]
        names = []
        for name in self._seriesAttr('name', seriesIndexes):
            if name not in names:
                names.append(name)
        return names
    
    def groupNames(self, groups=None) -> list:
        if groups is None:
            groups = self.groups()
        names = []
        for group in groups:
            name = group if isinstance(group, str) else str(group)
            if isinstance(group, int):
                # name -> name: ylabel
                indexes = self._seriesIndexes(groups=[group])
                if indexes:
                    ylabel = self._seriesAttr('ylabel', indexes[0])
                    name += ": " + ylabel
            names.append(name)
        return names
    
    # Visible series

    def visibleEpisodes(self) -> list:
        episodes = self.episodes()
        if not episodes:
            return []
        visibleEpisodesText = self._visibleEpisodesEdit.text().strip()
        if visibleEpisodesText == '':
            return episodes
        visibleEpisodesFields = re.split('[,\s]+', visibleEpisodesText)
        visibleEpisodes = []
        for field in visibleEpisodesFields:
            if field == '':
                continue
            if ':' in field:
                sliceArgs = [int(arg) if len(arg.strip()) else None for arg in field.split(':')]
                sliceObj = slice(*sliceArgs)
                sliceIndexes = list(range(*sliceObj.indices(max(episodes) + 1)))
                visibleEpisodes.extend(sliceIndexes)
            elif '-' in field:
                start, end = field.split('-')
                visibleEpisodes.extend(list(range(int(start), int(end)+1)))
            else:
                visibleEpisodes.append(int(field))
        visibleEpisodes = np.unique(visibleEpisodes)
        return [episode for episode in visibleEpisodes if episode in episodes]
    
    def setVisibleEpisodes(self, visibleEpisodes: list):
        episodes = self.episodes()
        if not episodes:
            self._visibleEpisodesEdit.setText('')
            self.updatePlots()
            return
        visibleEpisodes = [episode for episode in visibleEpisodes if episode in episodes]
        visibleEpisodesText = []
        i = 0
        while i < len(visibleEpisodes):
            j = i
            while j + 1 < len(visibleEpisodes) and  visibleEpisodes[j+1] == visibleEpisodes[j] + 1:
                j += 1
            if i == j:
                visibleEpisodesText.append(str(visibleEpisodes[i]))
            else:
                visibleEpisodesText.append(str(visibleEpisodes[i]) + '-' + str(visibleEpisodes[j]))
            i = j + 1
        self._visibleEpisodesEdit.setText(' '.join(visibleEpisodesText))
        self.updatePlots()
    
    def nextEpisode(self):
        episodes = self.episodes()
        if not episodes:
            return
        if self._visibleEpisodesEdit.text().strip() == '':
            self.setVisibleEpisodes([episodes[0]])
            return
        visibleEpisodes = self.visibleEpisodes()
        if not visibleEpisodes:
            self.setVisibleEpisodes([episodes[0]])
            return
        index = episodes.index(visibleEpisodes[-1])
        index = min(index + 1, len(episodes) - 1)
        self.setVisibleEpisodes([episodes[index]])
    
    def prevEpisode(self):
        episodes = self.episodes()
        if not episodes:
            return
        if self._visibleEpisodesEdit.text().strip() == '':
            self.setVisibleEpisodes([episodes[-1]])
            return
        visibleEpisodes = self.visibleEpisodes()
        if not visibleEpisodes:
            self.setVisibleEpisodes([episodes[-1]])
            return
        index = episodes.index(visibleEpisodes[0])
        index = max(0, index - 1)
        self.setVisibleEpisodes([episodes[index]])
    
    def visibleGroups(self) -> list:
        groups = self.groups()
        if not groups:
            return []
        visibleGroupIndexes = [index.row() for index in self._visibleGroupsListWidget.selectedIndexes()]
        visibleGroups = [groups[i] for i in visibleGroupIndexes if i < len(groups)]
        return visibleGroups if visibleGroups else groups
    
    def setVisibleGroups(self, visibleGroups: list):
        self._updateVisibleGroupsListView()
        groups = self.groups()
        listWidget = self._visibleGroupsListWidget
        listWidget.itemSelectionChanged.disconnect()
        for item in listWidget.items():
            item.setSelected(False)
        for group in visibleGroups:
            if group in groups:
                listWidget.item(groups.index(group)).setSelected(True)
        listWidget.itemSelectionChanged.connect(self._onVisibleGroupsChanged)
        self._onVisibleGroupsChanged()
    
    def _updateVisibleGroupsListView(self):
        groups = self.groups()
        groupNames = self.groupNames()
        listWidget = self._visibleGroupsListWidget
        visibleGroupIndexes = [index.row() for index in listWidget.selectedIndexes()]
        listWidget.itemSelectionChanged.disconnect()
        listWidget.clear()
        if qta is not None:
            for name in groupNames:
                item = QListWidgetItem(name)
                item.setIcon(qta.icon('mdi.circle-small'))
                listWidget.addItem(item)
            listWidget.setIconSize(QSize(16, 16))
        else:
            listWidget.addItems(groupNames)
        for i in visibleGroupIndexes:
            if i < len(groups):
                listWidget.item(i).setSelected(True)
        listWidget.itemSelectionChanged.connect(self._onVisibleGroupsChanged)
    
    def _onVisibleGroupsChanged(self):
        groups = self.groups()
        visibleGroups = self.visibleGroups()
        for i, plot in enumerate(self._groupPlots()):
            if i < len(groups) and groups[i] in visibleGroups:
                plot.show()
            else:
                plot.hide()
    
    def visibleNames(self) -> list:
        names = self.names()
        if not names:
            return []
        visibleNameIndexes = [index.row() for index in self._visibleNamesListWidget.selectedIndexes()]
        visibleNames = [names[i] for i in visibleNameIndexes if i < len(names)]
        if not visibleNames:
            visibleNames = names
        return visibleNames
    
    def setVisibleNames(self, visibleNames: list):
        self._updateVisibleNamesListView()
        names = self.names()
        listWidget = self._visibleNamesListWidget
        listWidget.itemSelectionChanged.disconnect()
        for item in listWidget.items():
            item.setSelected(False)
        for name in visibleNames:
            if name in names:
                listWidget.item(names.index(name)).setSelected(True)
        listWidget.itemSelectionChanged.connect(self._onVisibleNamesChanged)
        self._onVisibleNamesChanged()
    
    def _updateVisibleNamesListView(self):
        names = self.names()
        listWidget = self._visibleNamesListWidget
        visibleNameIndexes = [index.row() for index in listWidget.selectedIndexes()]
        listWidget.itemSelectionChanged.disconnect()
        listWidget.clear()
        if qta is not None:
            for name in names:
                item = QListWidgetItem(name)
                item.setIcon(qta.icon('mdi.circle-small'))
                listWidget.addItem(item)
            listWidget.setIconSize(QSize(16, 16))
        else:
            listWidget.addItems(names)
        for i in visibleNameIndexes:
            if i < len(names):
                listWidget.item(i).setSelected(True)
        listWidget.itemSelectionChanged.connect(self._onVisibleNamesChanged)
    
    def _onVisibleNamesChanged(self):
        self.updatePlots()
    
    def numSelectedVisibleNames(self) -> int:
        visibleNameIndexes = [index.row() for index in self._visibleNamesListWidget.selectedIndexes()]
        return len(visibleNameIndexes)
    
    # ROIs

    def rois(self, names=None) -> list:
        if names is None:
            return self.ROIs
        rois = []
        for roi in self.ROIs:
            name = roi['name'] if 'name' in roi else ''
            if names is None or name in names:
                rois.append(roi)
        return rois
    
    def roiNames(self) -> list:
        names = []
        for roi in self.ROIs:
            name = roi['name'] if 'name' in roi else ''
            if name not in names:
                names.append(name)
        return names
    
    def startDrawingROIs(self):
        self.state['is-drawing-rois'] = True
    
    def stopDrawingROIs(self):
        if 'is-drawing-rois' in self.state:
            del self.state['is-drawing-rois']
    
    def isDrawingROIs(self) -> bool:
        return ('is-drawing-rois' in self.state) and self.state['is-drawing-rois']
    
    def showROIs(self):
        for plot in self._groupPlots():
            plot.getViewBox().showROIs()
    
    def hideROIs(self):
        for plot in self._groupPlots():
            plot.getViewBox().hideROIs()

    def clearROIs(self):
        self.ROIs = []
        self._updateROIs()
    
    # Visible ROIs (grouped by name)

    def visibleROINames(self) -> list:
        roiNames = self.roiNames()
        if not roiNames:
            return []
        visibleIndexes = [index.row() for index in self._visibleROINamesListWidget.selectedIndexes()]
        visibleROINames = [roiNames[i] for i in visibleIndexes if i < len(roiNames)]
        return visibleROINames if visibleROINames else roiNames
    
    def setVisibleROINames(self, visibleROINames: list):
        self._updateVisibleROINamesListView()
        roiNames = self.roiNames()
        listWidget = self._visibleROINamesListWidget
        listWidget.itemSelectionChanged.disconnect()
        for item in listWidget.items():
            item.setSelected(False)
        for roiName in visibleROINames:
            if roiName in roiNames:
                listWidget.item(roiNames.index(roiName)).setSelected(True)
        listWidget.itemSelectionChanged.connect(self._onVisibleROINamesChanged)
        self._onVisibleROINamesChanged()
    
    def _updateVisibleROINamesListView(self):
        roiNames = self.roiNames()
        listWidget = self._visibleROINamesListWidget
        visibleIndexes = [index.row() for index in listWidget.selectedIndexes()]
        listWidget.itemSelectionChanged.disconnect()
        listWidget.clear()
        if qta is not None:
            for name in roiNames:
                item = QListWidgetItem(name)
                item.setIcon(qta.icon('mdi.circle-small'))
                listWidget.addItem(item)
            listWidget.setIconSize(QSize(16, 16))
        else:
            listWidget.addItems(roiNames)
        for i in visibleIndexes:
            if i < len(roiNames):
                listWidget.item(i).setSelected(True)
        listWidget.itemSelectionChanged.connect(self._onVisibleROINamesChanged)
    
    def _onVisibleROINamesChanged(self):
        self.updatePlots()
    
    # UI
    
    def sizeHint(self):
        return QSize(800, 600)
    
    def initUI(self):
        # widget background color
        if self.state['figure']['background-color'] is not None:
            pal = self.palette()
            pal.setColor(pal.Window, QColor(*self.state['figure']['background-color']))
            self.setPalette(pal)

        # episode traversal
        self._visibleEpisodesEdit = QLineEdit("0")
        self._visibleEpisodesEdit.setMinimumWidth(64)
        self._visibleEpisodesEdit.setMaximumWidth(128)
        self._visibleEpisodesEdit.setToolTip("Visible Episodes")
        self._visibleEpisodesEdit.textEdited.connect(self.updatePlots)

        self._prevEpisodeButton = QPushButton()
        if qta is not None:
            icon = qta.icon("fa.step-backward")
            self._prevEpisodeButton.setIcon(icon)
        else:
            self._prevEpisodeButton.setText("<")
            self._prevEpisodeButton.setMaximumWidth(32)
        self._prevEpisodeButton.setToolTip("Previous Episode")
        self._prevEpisodeButton.clicked.connect(self.prevEpisode)

        self._nextEpisodeButton = QPushButton()
        if qta is not None:
            icon = qta.icon("fa.step-forward")
            self._nextEpisodeButton.setIcon(icon)
        else:
            self._nextEpisodeButton.setText(">")
            self._nextEpisodeButton.setMaximumWidth(32)
        self._nextEpisodeButton.setToolTip("Next Episode")
        self._nextEpisodeButton.clicked.connect(self.nextEpisode)

        # visible group selection
        self._visibleGroupsListWidget = QListWidget()
        self._visibleGroupsListWidget.setSelectionMode(QAbstractItemView.MultiSelection)
        self._visibleGroupsListWidget.itemSelectionChanged.connect(self._onVisibleGroupsChanged)

        # visible name selection
        self._visibleNamesListWidget = QListWidget()
        self._visibleNamesListWidget.setSelectionMode(QAbstractItemView.MultiSelection)
        self._visibleNamesListWidget.itemSelectionChanged.connect(self._onVisibleNamesChanged)

        # visible ROI selection
        self._visibleROINamesListWidget = QListWidget()
        self._visibleROINamesListWidget.setSelectionMode(QAbstractItemView.MultiSelection)
        self._visibleROINamesListWidget.itemSelectionChanged.connect(self._onVisibleROINamesChanged)

        # data table model/view
        self._tableModel = None
        self._tableView = None

        # Python interactive console
        if PythonConsole is not None:
            self._console = PythonConsole()
            # In the console the variable `self` provides access to this instance.
            self._console.push_local_ns('self', self)
            self._console.eval_queued()

            # TODO: Use better console colors. The default colors suck.
            pal = self._console.palette()
            pal.setColor(pal.Base, QColor(82, 82, 82))
            self._console.setPalette(pal)
        else:
            self._console = None
        
        # main menu
        self._fileMenu = QMenu("&File")
        self._fileMenu.addAction("&Open", self.open)
        self._fileMenu.addSection(" ")
        self._fileMenu.addAction("&Save", self.save)
        self._fileMenu.addSection(" ")
        self._fileMenu.addAction("Import HEKA", self.importHEKA)

        self._groupsMenu = QMenu("Groups")
        action = QWidgetAction(self._groupsMenu)
        action.setDefaultWidget(self._visibleGroupsListWidget)
        self._groupsMenu.addAction(action)

        self._namesMenu = QMenu("Names")
        action = QWidgetAction(self._namesMenu)
        action.setDefaultWidget(self._visibleNamesListWidget)
        self._namesMenu.addAction(action)

        self._roisMenu = QMenu("ROIs")
        self._roisMenu.addAction("Draw X-axis ROIs", self.startDrawingROIs)
        self._roisMenu.addAction("Hide ROIs", self.hideROIs)
        self._roisMenu.addAction("Clear ROIs", self.clearROIs)
        self._roisMenu.addSection(" ")
        action = QWidgetAction(self._roisMenu)
        action.setDefaultWidget(self._visibleROINamesListWidget)
        self._roisMenu.addAction(action)

        self._mainMenu = QMenu()
        self._mainMenu.addMenu(self._fileMenu)
        self._mainMenu.addSection(" ")
        self._mainMenu.addMenu(self._groupsMenu)
        self._mainMenu.addMenu(self._namesMenu)
        self._mainMenu.addMenu(self._roisMenu)
        self._mainMenu.addSection(" ")
        action = self._makeAction(self._mainMenu, "Data Table", self.showDataTable, "fa.table")
        self._mainMenu.addAction(action)
        if PythonConsole is not None:
            action = self._makeAction(self._mainMenu, "Python Console", self.showCosole, "fa.terminal")
            self._mainMenu.addAction(action)

        self._mainMenuButton = QToolButton()
        self._mainMenuButton.setPopupMode(QToolButton.InstantPopup)
        self._mainMenuButton.setMenu(self._mainMenu)
        if qta is not None:
            icon = qta.icon("fa.bars")
            self._mainMenuButton.setIcon(icon)
        else:
            self._mainMenuButton.setText("Menu")

        # layout
        self._mainGridLayout = QGridLayout(self)
        self._mainGridLayout.setContentsMargins(3, 3, 3, 3)
        self._mainGridLayout.setSpacing(0)

        self._topToolbar = QToolBar()
        self._mainMenuButtonAction = self._topToolbar.addWidget(self._mainMenuButton)
        self._visibleEpisodesEditAction = self._topToolbar.addWidget(self._visibleEpisodesEdit)
        self._prevEpisodeButtonAction = self._topToolbar.addWidget(self._prevEpisodeButton)
        self._nextEpisodeButtonAction = self._topToolbar.addWidget(self._nextEpisodeButton)
        self._mainGridLayout.addWidget(self._topToolbar, 0, 0)

        self._groupPlotsVBoxLayout = QVBoxLayout()
        self._groupPlotsVBoxLayout.setContentsMargins(3, 3, 3, 3)
        self._groupPlotsVBoxLayout.setSpacing(3)
        self._mainGridLayout.addLayout(self._groupPlotsVBoxLayout, 1, 0)
        self.setFocus()
    
    def updateUI(self):
        # update visible groups and names
        self._updateVisibleGroupsListView()
        self._updateVisibleNamesListView()

        # update plots
        self.updatePlots()

        # update fonts
        labelFont = QFont(self.state['axes']['label-font-name'])
        labelFont.setPointSize(self.state['axes']['label-font-size'])
        labelFont.setWeight(self.state['axes']['label-font-weight'])
        tickFont = QFont(self.state['axes']['tick-font-name'])
        tickFont.setPointSize(self.state['axes']['tick-font-size'])
        tickFont.setWeight(self.state['axes']['tick-font-weight'])
        for plot in self._groupPlots():
            for key in ['left', 'right', 'top', 'bottom']:
                plot.getAxis(key).setPen(self.state['axes']['foreground-color'])
                plot.getAxis(key).setTextPen(self.state['axes']['foreground-color'])
                plot.getAxis(key).label.setFont(labelFont)
                plot.getAxis(key).setTickFont(tickFont)

        # update toolbar
        showEpisodeControls = len(self.episodes()) > 1
        self._visibleEpisodesEditAction.setVisible(showEpisodeControls)
        self._prevEpisodeButtonAction.setVisible(showEpisodeControls)
        self._nextEpisodeButtonAction.setVisible(showEpisodeControls)

        # update table model/view
        if self._tableView is not None and self._tableView.isVisible():
            self.showDataTable()
    
    def updatePlots(self):
        # one plot per group, arranged vertically
        visibleEpisodes = self.visibleEpisodes()
        visibleGroups = self.visibleGroups()
        visibleNames = self.visibleNames()
        visibleROINames = self.visibleROINames()
        groups = self.groups()
        plots = self._groupPlots()
        for i, group in enumerate(groups):
            # group plot
            if len(plots) > i:
                plot = plots[i]
            else:
                plot = self._appendGroupPlot()
                plots.append(plot)
            
            # get data for this group
            dataItems = [item for item in plot.listDataItems() if isinstance(item, PlotDataItem)]
            colormap = self.state['line']['colormap']
            colorIndex = 0
            seriesIndexes = self._seriesIndexes(groups=[group], episodes=visibleEpisodes, names=visibleNames)
            j = 0
            for index in seriesIndexes:
                # data to plot
                series = self.data[index]
                x = self._seriesAttr('x', index)
                y = self._seriesAttr('y', index)
                if x is None or y is None:
                    continue
                style = self._seriesAttr('style', index)
                
                if len(dataItems) > j:
                    # update existing plot data
                    dataItems[j].setData(x, y)
                    colorIndex = self._updatePlotStyle(dataItems[j], style, colorIndex)
                    dataItems[j].seriesIndex = index
                else:
                    # add new plot data
                    dataItem = PlotDataItem(x, y)
                    colorIndex = self._updatePlotStyle(dataItem, style, colorIndex)
                    dataItem.seriesIndex = index
                    plot.addItem(dataItem)
                    dataItems.append(dataItem)
                
                # axis labels (based on first plot with axis labels)
                if j == 0 or plot.getAxis('bottom').labelText == '':
                    xlabel = self._seriesAttr('xlabel', index)
                    plot.getAxis('bottom').setLabel(xlabel)
                if j == 0 or plot.getAxis('left').labelText == '':
                    group = self._seriesAttr('group', index)
                    ylabel = self._seriesAttr('ylabel', index)
                    if (isinstance(group, str) and len(group) <= 1) or isinstance(group, int):
                        ylabel = str(group) + ":<br/>" + ylabel
                    opts = {'display': 'table', 'text-align': 'center'}
                    plot.getAxis('left').setLabel(ylabel, **opts)
                
                # next plot data item
                j += 1
            
            # remove extra plot items
            dataItems = [item for item in plot.listDataItems() if isinstance(item, PlotDataItem)]
            while len(dataItems) > j:
                dataItem = dataItems.pop()
                plot.removeItem(dataItem)
                dataItem.deleteLater()
            
            # TODO: get ROIs for this group

            # TODO: remove extra ROI items
                
            if j == 0:
                # empty plot axes
                plot.getAxis('bottom').setLabel('')
                plot.getAxis('left').setLabel('')
                
            # show/hide plot
            if group in visibleGroups:
                plot.show()
            else:
                plot.hide()
        
        # remove extra plots
        while len(plots) > len(groups):
            i = len(plots) - 1
            self._groupPlotsVBoxLayout.takeAt(i)
            plot = plots.pop(i)
            plot.deleteLater()

        # link x-axis
        if self._groupPlotsVBoxLayout.count() > 1:
            firstPlot = self._groupPlotsVBoxLayout.itemAt(0).widget()
            for i in range(1, self._groupPlotsVBoxLayout.count()):
                plot = self._groupPlotsVBoxLayout.itemAt(i).widget()
                plot.setXLink(firstPlot)
    
    def _updatePlotStyle(self, plotDataItem, style: dict, colorIndex=0, colormap=None):
        # color
        color = self._styleAttr(style, 'color')
        if color is not None:
            color = str2color(color)
        if color is None or (len(color) == 4 and color[3] == 0):
            if colormap is None:
                colormap = self.state['line']['colormap']
            color = colormap[colorIndex % len(colormap)]
            color = [int(c) for c in color]
            if len(color) == 3:
                color.append(255)
            color = tuple(color)
            colorIndex += 1

        # line
        lineStyle = self._styleAttr(style, 'linestyle')
        lineStyles = {
            '-': Qt.SolidLine, '--': Qt.DashLine, ':': Qt.DotLine, '-.': Qt.DashDotLine, 
            'none': None, '': Qt.SolidLine, None: Qt.SolidLine
        }
        lineStyle = lineStyles[lineStyle]

        lineWidth = self._styleAttr(style, 'linewidth')
        if lineWidth is None:
            lineWidth = self.state['line']['width']
        else:
            lineWidth = float(lineWidth)
        
        if lineStyle is None:
            linePen = None
        else:
            linePen = pg.mkPen(color=color, width=lineWidth, style=lineStyle)
        plotDataItem.setPen(linePen)

        # symbol
        symbol = self._styleAttr(style, 'marker')
        plotDataItem.setSymbol(symbol)
        
        if symbol is not None:
            symbolSize = self._styleAttr(style, 'markersize')
            if symbolSize is None:
                symbolSize = self.state['marker']['size']
            else:
                symbolSize = float(symbolSize)
            plotDataItem.setSymbolSize(symbolSize)

            symbolEdgeWidth = self._styleAttr(style, 'markeredgewidth')
            if symbolEdgeWidth is None:
                symbolEdgeWidth = lineWidth
            else:
                symbolEdgeWidth = float(symbolEdgeWidth)
            
            symbolEdgeColor = self._styleAttr(style, 'markeredgecolor')
            if symbolEdgeColor is None:
                symbolEdgeColor = color
            else:
                symbolEdgeColor = str2color(symbolEdgeColor)
            
            symbolPen = pg.mkPen(color=symbolEdgeColor, width=symbolEdgeWidth)
            plotDataItem.setSymbolPen(symbolPen)

            symbolFaceColor = self._styleAttr(style, 'markerfacecolor')
            if symbolFaceColor is None:
                symbolFaceColor = symbolEdgeColor[:3] + (0,)
            else:
                symbolFaceColor = str2color(symbolFaceColor)
            plotDataItem.setSymbolBrush(symbolFaceColor)
        
        return colorIndex
    
    def _groupPlots(self) -> list:
        groupPlotsVBoxWidgets = [self._groupPlotsVBoxLayout.itemAt(i).widget() for i in range(self._groupPlotsVBoxLayout.count())]
        return [widget for widget in groupPlotsVBoxWidgets if isinstance(widget, PlotWidget)]
    
    def _appendGroupPlot(self) -> pg.PlotWidget:
        plot = PlotWidget(tsa=self)
        # plot = self._newPlot()
        self._groupPlotsVBoxLayout.addWidget(plot, stretch=1)
        return plot
    
    def _makeAction(self, parent, text, func, qta_icon=None) -> QAction:
        action = QAction(parent)
        action.setText(text)
        if qta_icon is not None and qta is not None:
            icon = qta.icon(qta_icon)
            action.setIcon(icon)
        action.triggered.connect(func)
        return action
    
    def _updateROIs(self):
        for plot in self._groupPlots():
            viewBox = plot.getViewBox()
            roiWidgets = viewBox.getROIs()
            for i, roi in enumerate(self.ROIs):
                if len(roiWidgets) > i:
                    # update existing ROI widget
                    roiWidgets[i].setRegion(roi['xlim'])
                    roiWidgets[i].roiIndex = i
                    roiWidgets[i]._updateNameLabel()
                else:
                    # add new ROI widget
                    roiWidget = LinearRegionItem(viewBox=viewBox, values=roi['xlim'], orientation="vertical")
                    roiWidget.roiIndex = i
                    roiWidget._updateNameLabel()
                    roiWidgets.append(roiWidget)
            # remove extra ROI widgets
            while len(roiWidgets) > len(self.ROIs):
                roiWidget = roiWidgets.pop()
                roiWidget.deleteThis()
    
    def _updateROI(self, roiIndex: int):
        roi = self.ROIs[roiIndex]
        for plot in self._groupPlots():
            viewBox = plot.getViewBox()
            for roiWidget in viewBox.getROIs():
                if roiWidget.roiIndex == roiIndex:
                    roiWidget.setRegion(roi['xlim'])
                    roiWidget._updateNameLabel()
                    break
    
    # Table UI for all series
    
    def showDataTable(self):
        if self._tableModel is not None:
            self._tableModel.deleteLater()
        self._tableModel = DataTableModel(self)

        if self._tableView is None:
            self._tableView = QTableView()
            # self._tableView.horizontalHeader().setMinimumSectionSize(50)
        self._tableView.setModel(self._tableModel)
        self._tableView.show()
        self._tableView.resizeColumnsToContents()
    
    # Console UI
    
    def showCosole(self):
        if self._console is None:
            return
        self._console.show()
    
    # Other dialogs
    
    def traceMathDialog(self, episodes=None, groups=None):
        dlg = QDialog(self)
        dlg.setWindowTitle("Trace Math")
        grid = QGridLayout(dlg)

        result = QLineEdit('result')
        lhs = QLineEdit('data')
        rhs = QLineEdit()
        operations = QComboBox()
        operations.addItems(['+', '-', '*', '/'])

        grid.addWidget(QLabel('name'), 0, 0)
        grid.addWidget(result, 1, 0)

        grid.addWidget(QLabel('='), 1, 1)

        grid.addWidget(QLabel('name'), 0, 2)
        grid.addWidget(lhs, 1, 2)

        grid.addWidget(operations, 1, 3)

        grid.addWidget(QLabel('name or value'), 0, 4)
        grid.addWidget(rhs, 1, 4)

        grid.addWidget(QLabel(''), 2, 0)  # spacer

        buttonBox = QDialogButtonBox()
        buttonBox.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttonBox.accepted.connect(dlg.accept)
        buttonBox.rejected.connect(dlg.reject)
        grid.addWidget(buttonBox, 4, 0, 1, 4)
        dlg.setWindowModality(Qt.ApplicationModal)
        if dlg.exec_() == QDialog.Accepted:
            result = result.text().strip()
            lhs = lhs.text().strip()
            rhs = rhs.text().strip()
            try:
                rhs = float(rhs)
            except ValueError:
                pass
            op = operations.currentText()

            if episodes is None:
                episodes = self.visibleEpisodes()
            if groups is None:
                groups = self.visibleGroups()
            for episode in episodes:
                for group in groups:
                    seriesIndexes = self._seriesIndexes(episodes=[episode], groups=[group])
                    if not isinstance(seriesIndexes, list):
                        seriesIndexes = [seriesIndexes]
                    names = self._seriesAttr('name', seriesIndexes=seriesIndexes)
                    if lhs not in names:
                        continue
                    lhsIndex = seriesIndexes[names.index(lhs)]
                    lhsSeries = self.data[lhsIndex]
                    if isinstance(rhs, str):
                        if rhs not in names:
                            continue
                        rhsIndex = seriesIndexes[names.index(rhs)]
                        rhsSeries = self.data[rhsIndex]
                        rhsValue = rhsSeries['y']
                    else:
                        rhsValue = rhs
                    resultSeries = copy.deepcopy(lhsSeries)
                    resultSeries['name'] = result
                    if op == '+':
                        resultSeries['y'] += rhsValue
                    elif op == '-':
                        resultSeries['y'] -= rhsValue
                    elif op == '*':
                        resultSeries['y'] *= rhsValue
                    elif op == '/':
                        resultSeries['y'] /= rhsValue
                    resultSeries['episode'] = episode
                    resultSeries['group'] = group
                    self.data.append(resultSeries)
            self.updateUI()


class PlotWidget(pg.PlotWidget):
    """ PlotWidget with a custom ViewBox for QtTimeSeriesAnalyzer. """

    def __init__(self, parent=None, tsa=None):
        pg.PlotWidget.__init__(self, parent, viewBox=ViewBox(tsa=tsa))
        self.getViewBox().plotWidget = self

        # # for alignment of vertically stacked plots
        # self.getAxis('left').setWidth(70)
        
        # # colors
        # if tsa is not None:
        #     self.getViewBox().setBackgroundColor(QColor(*tsa.state['axes']['background-color']))
        #     for key in ['left', 'right', 'top', 'bottom']:
        #         self.getAxis(key).setPen(tsa.state['axes']['foreground-color'])
        #         self.getAxis(key).setTextPen(tsa.state['axes']['foreground-color'])

        # # fonts
        # if tsa is not None:
        #     labelFont = QFont(tsa.state['axes']['label-font-name'])
        #     labelFont.setPointSize(tsa.state['axes']['label-font-size'])
        #     labelFont.setWeight(tsa.state['axes']['label-font-weight'])
        #     tickFont = QFont(tsa.state['axes']['tick-font-name'])
        #     tickFont.setPointSize(tsa.state['axes']['tick-font-size'])
        #     tickFont.setWeight(tsa.state['axes']['tick-font-weight'])
        #     for key in ['left', 'right', 'top', 'bottom']:
        #         self.getAxis(key).setPen(tsa.state['axes']['foreground-color'])
        #         self.getAxis(key).setTextPen(tsa.state['axes']['foreground-color'])
        #         self.getAxis(key).label.setFont(labelFont)
        #         self.getAxis(key).setTickFont(tickFont)

        # grid
        if False:
            self.showGrid(x=True, y=True, alpha=0.2)
            # hack to stop grid from clipping axis tick labels
            for key in ['left', 'bottom']:
                self.getAxis(key).setGrid(False)
            for key in ['right', 'top']:
                self.getAxis(key).setStyle(showValues=False)
                self.showAxis(key)
    
    # # Access to the ancestor QtTimeSeriesAnalyzer instance.
    # @property
    # def tsa(self):
    #     return self.getViewBox().tsa

    # @tsa.setter
    # def tsa(self, value):
    #     self.getViewBox().tsa = value


class ViewBox(pg.ViewBox):
    """ ViewBox with custom behavior for QtTimeSeriesAnalyzer. """

    def __init__(self, parent=None, tsa=None):
        pg.ViewBox.__init__(self, parent)

        # Access to the ancestor QtTimeSeriesAnalyzer instance.
        self.tsa = tsa

        # Measurement context menu
        self._measureMenu = QMenu("Measure")
        self._measureMenu.addAction("Mean", lambda: self.measure(measurementType="mean"))
        self._measureMenu.addAction("Median", lambda: self.measure(measurementType="median"))
        self._measureMenu.addAction("Min", lambda: self.measure(measurementType="min"))
        self._measureMenu.addAction("Max", lambda: self.measure(measurementType="max"))
        self._measureMenu.addAction("AbsMax", lambda: self.measure(measurementType="absmax"))
        self._measureMenu.addAction("Variance", lambda: self.measure(measurementType="var"))
        self._measureMenu.addAction("Standard Deviation", lambda: self.measure(measurementType="std"))

        # Curve fit context menu
        self._fitMenu = QMenu("Curve Fit")
        self._fitMenu.addAction("Mean", lambda: self.curveFit(fitType="mean"))
        self._fitMenu.addAction("Line", lambda: self.curveFit(fitType="line"))
        self._fitMenu.addAction("Polynomial", lambda: self.curveFit(fitType="polynomial"))
        self._fitMenu.addAction("Spline", lambda: self.curveFit(fitType="spline"))
        self._fitMenu.addAction("Custom", lambda method="custom": self.curveFit(fitType=method))

        # Context menu (added on to default context menu)
        self.menu.addSection(" ")
        # self.menu.addMenu(self._roiMenu)
        self.menu.addMenu(self._measureMenu)
        self.menu.addMenu(self._fitMenu)
        self.menu.addAction("Trace Math", self.traceMathDialog)
        self.menu.addSection(" ")

        # Handle view change events
        self.sigTransformChanged.connect(self.updateROINameLabels)
        self.sigResized.connect(self.updateROINameLabels)
    
    def getGroup(self):
        groups = self.tsa.groups()
        plots = self.tsa._groupPlots()
        for group, plot in zip(group, plots):
            if plot.getViewBox() == self:
                return group
        return None
    
    def getROIs(self):
        return [item for item in self.allChildren() if isinstance(item, LinearRegionItem)]
    
    def getXAxisROIs(self):
        return [item for item in self.allChildren() if isinstance(item, LinearRegionItem) and item.orientation == "vertical"]
    
    def getYAxisROIs(self):
        return [item for item in self.allChildren() if isinstance(item, LinearRegionItem) and item.orientation == "horizontal"]
    
    def mousePressEvent(self, event):
        if self.tsa is not None:
            if self.tsa.isDrawingROIs():
                if event.button() == Qt.LeftButton:
                    posInAxes = self.mapSceneToView(self.mapToScene(event.pos()))
                    self._roiStartPos = posInAxes
                    self._roiWidget = None
                    self._roiIndex = None
                else:
                    self.tsa.stopDrawingROIs()
                event.accept()
                return
        pg.ViewBox.mousePressEvent(self, event)
    
    def mouseReleaseEvent(self, event):
        if self.tsa is not None:
            if self.tsa.isDrawingROIs():
                self._roiStartPos = None
                self._roiWidget = None
                self._roiIndex = None
                event.accept()
                return
        pg.ViewBox.mouseReleaseEvent(self, event)
    
    def mouseMoveEvent(self, event):
        if self.tsa is not None:
            if self.tsa.isDrawingROIs():
                if event.buttons() & Qt.LeftButton:
                    posInAxes = self.mapSceneToView(self.mapToScene(event.pos()))
                    xlim = tuple(sorted([self._roiStartPos.x(), posInAxes.x()]))
                    if self._roiIndex is None or self._roiWidget is None:
                        self.tsa.ROIs.append({'xlim': xlim})
                        self._roiIndex = len(self.tsa.ROIs) - 1
                        self._roiWidget = LinearRegionItem(self, values=xlim, orientation="vertical")
                        self._roiWidget.roiIndex = self._roiIndex
                        self.tsa._updateROIs()
                    else:
                        self.tsa.ROIs[self._roiIndex]['xlim'] = xlim
                        self.tsa._updateROI(self._roiIndex)
                    event.accept()
                    return
        pg.ViewBox.mouseMoveEvent(self, event)
    
    def showROIs(self):
        for roi in self.getROIs():
            roi.show()
    
    def hideROIs(self):
        for roi in self.getROIs():
            roi.hide()
    
    def clearROIs(self):
        for roi in self.getROIs():
            roi.deleteThis()
    
    def updateROINameLabels(self):
        for roi in self.getROIs():
            roi._updateNameLabel()
    
    def getCurves(self) -> list:
        return [item for item in self.allChildren() if isinstance(item, pg.PlotDataItem)]
    
    def curveFit(self, curveDataItems=None, fitType="mean", fitParams=None, 
                restrictOptimizationToROIs=True, outputXValues=None, restrictOutputToROIs=False):
        # curve data items
        if curveDataItems is None:
            curveDataItems = [item for item in self.allChildren() if isinstance(item, pg.PlotDataItem)]
        elif not isinstance(curveDataItems, list):
            curveDataItems = [curveDataItems]
        # fit parameters
        if fitParams is None:
            fitParams = {}
        if fitType == "polynomial":
            if 'degree' not in fitParams:
                fitParams['degree'], ok = QInputDialog.getInt(
                    self.parentWidget().parentWidget(), "Polynomial Fit", "Degree:", 2, 1, 100, 1)
                if not ok:
                    return
        elif fitType == "spline":
            if 'num_segments' not in fitParams:
                fitParams['num_segments'], ok = QInputDialog.getInt(
                    self.parentWidget().parentWidget(), "Spline Fit", "# Segments:", 10, 1, int(1e9), 1)
                if not ok:
                    return
            # if 'smoothing' not in fitParams:
            #     fitParams['smoothing'], ok = QInputDialog.getDouble(
            #         self.parentWidget().parentWidget(), "Spline Fit", "Smoothing (0-inf):", 0, 0, float(1e9), 9)
            #     if not ok:
            #         return
        elif fitType == "custom":
            if lmfit is None:
                QMessageBox.warning(self.parentWidget().parentWidget(), "Custom Fit", "Install `lmfit` package to fit custom curve equations.")
                return
            if 'equation' not in fitParams:
                fitParams['equation'], ok = QInputDialog.getText(
                    self.parentWidget().parentWidget(), "Custom Fit", "Equation y(x):", QLineEdit.Normal, "a * x**2 + b * x + c")
                if not ok:
                    return
            fitModel = lmfit.models.ExpressionModel(fitParams['equation'], independent_vars=['x'])
            # initialize fit params
            fitParams['initial_values'] = {}
            fitParams['bounds'] = {}
            dlg = QDialog(self.tsa)
            dlg.setWindowTitle("Fit Parameters")
            grid = QGridLayout(dlg)
            grid.addWidget(QLabel(fitParams['equation']), 0, 0, 1, 4)
            grid.addWidget(QLabel(" "), 1, 0, 1, 4)
            grid.addWidget(QLabel("Min"), 2, 1)
            grid.addWidget(QLabel("Init"), 2, 2)
            grid.addWidget(QLabel("Max"), 2, 3)
            row = 3
            for param in fitModel.param_names:
                start, lbnd, ubnd = QLineEdit("1"), QLineEdit(), QLineEdit()
                fitParams['initial_values'][param] = start
                fitParams['bounds'][param] = [lbnd, ubnd]
                grid.addWidget(QLabel(param), row, 0)
                grid.addWidget(lbnd, row, 1)
                grid.addWidget(start, row, 2)
                grid.addWidget(ubnd, row, 3)
                row += 1
            buttonBox = QDialogButtonBox()
            buttonBox.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
            buttonBox.accepted.connect(dlg.accept)
            buttonBox.rejected.connect(dlg.reject)
            grid.addWidget(QLabel(" "), row, 0, 1, 4)
            grid.addWidget(buttonBox, row + 1, 0, 1, 4)
            dlg.setWindowModality(Qt.ApplicationModal)
            if dlg.exec_() != QDialog.Accepted:
                return
            for param in fitModel.param_names:
                start = float(fitParams['initial_values'][param].text())
                fitParams['initial_values'][param] = start
                hint = {}
                hint['value'] = start
                try:
                    lbnd = float(fitParams['bounds'][param][0].text())
                    hint['min'] = lbnd
                except ValueError:
                    lbnd = None
                try:
                    ubnd = float(fitParams['bounds'][param][1].text())
                    hint['max'] = ubnd
                except ValueError:
                    ubnd = None
                fitModel.set_param_hint(param, **hint)

        # fit each data item
        fits = []
        for dataItem in curveDataItems:
            seriesIndex = dataItem.seriesIndex
            data = self.tsa.data[seriesIndex]
            x = self.tsa._seriesAttr('x', seriesIndex)
            y = self.tsa._seriesAttr('y', seriesIndex)
            
            # optimize fit based on (fx, fy)
            xrois = [roi for roi in self.getXAxisROIs() if roi.isVisible()]
            if restrictOptimizationToROIs and len(xrois):
                inROIs = np.zeros(len(x), dtype=bool)
                for xroi in xrois:
                    xmin, xmax = xroi.getRegion()
                    inROIs = inROIs | ((x >= xmin) & (x <= xmax))
                fx, fy = x[inROIs], y[inROIs]
            else:
                fx, fy = x, y
            
            # fit = (xfit, yfit)
            if outputXValues is not None:
                xfit = outputXValues
            elif restrictOutputToROIs:
                xfit = fx
            else:
                xfit = x
            # make sure xfit is not a reference to some other data
            xfit = xfit.copy()
            
            if fitType == "mean":
                yfit = np.zeros(xfit.shape)
                yfit[:] = np.mean(fy)
            elif fitType == "line":
                m, b = np.polyfit(fx, fy, 1)
                yfit = m * xfit + b
            elif fitType == "polynomial":
                p = np.polyfit(fx, fy, fitParams['degree'])
                yfit = np.polyval(p, xfit)
            elif fitType == "spline":
                segment_length = max(1, int(len(fy) / fitParams['num_segments']))
                knots = fx[segment_length:-segment_length:segment_length]
                if len(knots) < 2:
                    knots = fx[[1, -2]]
                tck = sp.interpolate.splrep(fx, fy, t=knots)
                yfit = sp.interpolate.splev(xfit, tck, der=0)
            elif fitType == "custom":
                result = fitModel.fit(fy, x=fx, **fitParams['initial_values'])
                # print(result.fit_report())
                yfit = fitModel.eval(result.params, x=xfit)

            # fit series data
            fit = {'x': xfit, 'y': yfit}
            for key in ['xlabel', 'ylabel', 'episode', 'group']:
                fit[key] = self.tsa._seriesAttr(key, seriesIndex)
            fits.append(fit)

            # add fit to plot
            fitItem = PlotDataItem(x=xfit, y=yfit, pen=pg.mkPen(color=(255, 0, 0), width=3))
            self.plotWidget.addItem(fitItem)

        self.addSeries(fits, "Fit", fitType)
        self.tsa.updateUI()
    
    def measure(self, curveDataItems=None, measurementType="mean"):
        measurements = []
        if curveDataItems is None:
            curveDataItems = [item for item in self.allChildren() if isinstance(item, pg.PlotDataItem)]
        elif not isinstance(curveDataItems, list):
            curveDataItems = [curveDataItems]
        for dataItem in curveDataItems:
            seriesIndex = dataItem.seriesIndex
            data = self.tsa.data[seriesIndex]
            x = self.tsa._seriesAttr('x', seriesIndex)
            y = self.tsa._seriesAttr('y', seriesIndex)

            # measurement within each ROI (or whole curve if no ROIs)
            xrois = [roi for roi in self.getXAxisROIs() if roi.isVisible()]
            xranges = [xroi.getRegion() for xroi in xrois]
            if not xranges:
                xranges = [(x[0], x[-1])]
            
            xmeasure = []
            ymeasure = []
            for xrange in xranges:
                xmin, xmax = xrange
                xmid = (xmin + xmax) / 2
                xmask = (x >= xmin) & (x <= xmax)
                xroi = x[xmask]
                yroi = y[xmask]
                nroi = len(xroi)
                if measurementType == "mean":
                    xm = xmid
                    ym = np.mean(yroi)
                elif measurementType == "median":
                    xm = xmid
                    ym = np.median(yroi)
                elif measurementType == "min":
                    i = np.argmin(yroi)
                    xm = xroi[i]
                    ym = yroi[i]
                elif measurementType == "max":
                    i = np.argmax(yroi)
                    xm = xroi[i]
                    ym = yroi[i]
                elif measurementType == "absmax":
                    i = np.argmax(np.abs(yroi))
                    xm = xroi[i]
                    ym = yroi[i]
                elif measurementType == "var":
                    xm = xmid
                    ym = np.var(yroi)
                elif measurementType == "std":
                    xm = xmid
                    ym = np.std(yroi)
                xmeasure.append(xm)
                ymeasure.append(ym)
            if not ymeasure:
                continue
            else:
                xmeasure = np.array(xmeasure)
                ymeasure = np.array(ymeasure)

            # measurement series data
            measurement = {'x': xmeasure, 'y': ymeasure}
            for key in ['xlabel', 'ylabel', 'episode', 'group']:
                measurement[key] = self.tsa._seriesAttr(key, seriesIndex)
            measurement['style'] = {'marker': 'o'}
            measurements.append(measurement)

            # add measure to plot
            measurementItem = PlotDataItem(x=xmeasure, y=ymeasure, pen=pg.mkPen(color=(255, 0, 0), width=3), 
                symbol='o', symbolSize=10, symbolPen=pg.mkPen(color=(255, 0, 0), width=3), symbolBrush=(255, 0, 0, 0))
            self.plotWidget.addItem(measurementItem)

        self.addSeries(measurements, "Measurement", measurementType)
        self.tsa.updateUI()
    
    def addSeries(self, data, label="series", defaultName="", askToKeep=True, rename=True, checkForOverwrite=True):
        if not data:
            return False
        
        if askToKeep:
            keep = QMessageBox.question(self.parentWidget().parentWidget(), f"Keep {label}?", f"Keep {label}?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if keep == QMessageBox.No:
                return False

        if rename:
            name, ok = QInputDialog.getText(self.parentWidget().parentWidget(), f"{label} name", f"{label} name:", text=defaultName)
            if not ok:
                return False
            name = name.strip()
            for i in range(len(data)):
                data[i]['name'] = name
        
        overwrite = False
        if checkForOverwrite:
            nameAlreadyExists = False
            for series in data:
                seriesIndexes = self.tsa._seriesIndexes(episodes=[series['episode']], groups=[series['group']])
                names = self.tsa.names(seriesIndexes)
                if series['name'] in names:
                    nameAlreadyExists = True
                    break
            if nameAlreadyExists:
                overwrite = QMessageBox.question(self.parentWidget().parentWidget(), "Overwrite?", "Overwrite existing series with same name?", QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Cancel)
                if overwrite == QMessageBox.Cancel:
                    return False
                overwrite = True if overwrite == QMessageBox.Yes else False
        
        # store data
        if overwrite:
            for series in data:
                seriesIndexes = self.tsa._seriesIndexes(episodes=[series['episode']], groups=[series['group']], names=[series['name']])
                if seriesIndexes:
                    self.tsa.data[seriesIndexes[-1]] = series
                else:
                    self.tsa.data.append(series)
        else:
            self.tsa.data.extend(data)
        
        # make sure new data is visible
        if self.tsa.numSelectedVisibleNames() > 0:
            visibleNames = self.tsa.visibleNames()
            for series in data:
                if series['name'] not in visibleNames:
                    visibleNames.append(series['name'])
            self.tsa.setVisibleNames(visibleNames)

        return True
    
    def traceMathDialog(self):
        self.tsa.traceMathDialog(groups=[self.getGroup()])


class PlotDataItem(pg.PlotDataItem):
    def __init__(self, *args, **kwargs):
        pg.PlotDataItem.__init__(self, *args, **kwargs)

        # index of series in tsa.data
        self.seriesIndex = None

        # context menu
        self.menu = None

    def shape(self):
        return self.curve.shape()

    def boundingRect(self):
        return self.shape().boundingRect()

    def mouseClickEvent(self, event):
        if event.button() == Qt.RightButton:
            if self.curve.mouseShape().contains(event.pos()):
                if self.raiseContextMenu(event):
                    event.accept()

    def raiseContextMenu(self, event):
        menu = self.getContextMenus()
        
        # Let the scene add on to the end of our context menu (this is optional)
        menu = self.scene().addParentContextMenus(self, menu, event)
        
        pos = event.screenPos()
        menu.popup(QPoint(int(pos.x()), int(pos.y())))
        return True
    
    def getContextMenus(self, event=None):
        if self.menu is not None:
            self.menu.deleteLater()
        
        # defer menu creation until needed
        self.menu = QMenu()

        viewBox = self.parentWidget()
        tsa = viewBox.tsa

        name = tsa._seriesAttr('name', self.seriesIndex)
        if name is None or name == "":
            name = f"Series {self.seriesIndex}"
        else:
            name = f"Series {self.seriesIndex}: " + name
        
        self._seriesMenu = QMenu(name)

        self._seriesMenu.addAction("Rename", self.nameDialog)
        self._seriesMenu.addAction("Edit Style", self.styleDialog)
        self._seriesMenu.addSection(" ")
        self._seriesMenu.addAction("Delete Series", self.deleteThis)

        self.menu.addMenu(self._seriesMenu)
        self.menu.addSection(" ")

        return self.menu
    
    def nameDialog(self):
        viewBox = self.parentWidget()
        tsa = viewBox.tsa
        name, ok = QInputDialog.getText(tsa, "Series name", "Series name:", text=tsa._seriesAttr('name', self.seriesIndex))
        if ok:
            name = name.strip()
            if name == "":
                del tsa.data[self.seriesIndex]['name']
            else:
                tsa.data[self.seriesIndex]['name'] = name
            tsa.updateUI()
    
    def styleDialog(self):
        viewBox = self.parentWidget()
        tsa = viewBox.tsa
        style = tsa._seriesAttr('style', self.seriesIndex)
        if tsa.styleDialog(style):
            tsa.data[self.seriesIndex]['style'] = style
            tsa.updatePlots()
    
    def deleteThis(self):
        viewBox = self.parentWidget()
        tsa = viewBox.tsa
        del tsa.data[self.seriesIndex]
        tsa.updateUI()


class LinearRegionItem(pg.LinearRegionItem):
    def __init__(self, viewBox, *args, **kwargs):
        pg.LinearRegionItem.__init__(self, *args, **kwargs)

        viewBox.addItem(self)

        # index of ROI in tsa.ROIs
        self.roiIndex = None

        # region name label
        self.nameLabel = pg.LabelItem("", size="8pt", color=(0,0,0,128))
        plot = viewBox.getViewWidget()
        self.nameLabel.setParentItem(plot.getPlotItem())
        self._updateNameLabel()

        # context menu
        self.menu = None

        # handle region change events
        self.sigRegionChanged.connect(self._onRegionChanged)
    
    def __del__(self):
        try:
            viewBox = self.parentWidget()
            viewBox.removeItem(self)
            plot = viewBox.getViewWidget()
            plot.removeItem(self.nameLabel)
            self.nameLabel.deleteLater()
        except:
            pass
    
    def mouseClickEvent(self, event):
        if event.button() == Qt.RightButton:
            if self.boundingRect().contains(event.pos()):
                if self.raiseContextMenu(event):
                    event.accept()
    
    def raiseContextMenu(self, event):
        menu = self.getContextMenus()
        
        # Let the scene add on to the end of our context menu (this is optional)
        menu = self.scene().addParentContextMenus(self, menu, event)
        
        pos = event.screenPos()
        menu.popup(QPoint(int(pos.x()), int(pos.y())))
        return True
    
    def getContextMenus(self, event=None):
        if self.menu is not None:
            self.menu.deleteLater()

        # defer menu creation until needed
        self.menu = QMenu()

        self.menu.addAction("Rename ROI", self.nameDialog)
        self.menu.addSeparator()
        self.menu.addAction("Delete ROI", self.deleteThis)
        self.menu.addSeparator()

        return self.menu
    
    def nameDialog(self):
        viewBox = self.parentWidget()
        plot = viewBox.getViewWidget()
        name, ok = QInputDialog.getText(plot.tsa, "ROI name", "ROI name:", text=self.nameLabel.text)
        if ok:
            viewBox.tsa.ROIs[self.roiIndex]['name'] = name.strip()
            name = name.strip()
            self._updateNameLabel()
    
    def deleteThis(self):
        viewBox = self.parentWidget()
        plot = viewBox.getViewWidget()
        viewBox.removeItem(self)
        plot.removeItem(self.nameLabel)
        try:
            del viewBox.tsa.ROIs[self.roiIndex]
        except:
            pass
        self.nameLabel.deleteLater()
        self.deleteLater()
    
    def _onRegionChanged(self):
        viewBox = self.parentWidget()
        tsa = viewBox.tsa
        tsa.ROIs[self.roiIndex]['xlim'] = self.getRegion()
        tsa._updateROI(self.roiIndex)
    
    def updateROI(self):
        viewBox = self.parentWidget()
        tsa = viewBox.tsa
        self.setRegion(tsa.ROIs[self.roiIndex]['xlim'])
        self._updateNameLabel()
    
    def _updateNameLabel(self):
        viewBox = self.parentWidget()
        tsa = viewBox.tsa
        try:
            name = tsa.ROIs[self.roiIndex]['name'].strip()
        except:
            name = ''
        self.nameLabel.setText(name)
        if self.nameLabel.text == "":
            self.nameLabel.setVisible(False)
            return
        plot = viewBox.getViewWidget()
        roixmin, roixmax = self.getRegion()
        vbxmin, vbxmax = viewBox.viewRange()[0]
        if roixmin >= vbxmax or roixmax <= vbxmin:
            self.nameLabel.setVisible(False)
            return
        roixleft = max(vbxmin, roixmin)
        vbxfrac = (roixleft - vbxmin) / (vbxmax - vbxmin)
        x = (viewBox.pos().x() + vbxfrac * viewBox.width()) / plot.width()
        self.nameLabel.anchor(itemPos=(0,0), parentPos=(x,0), offset=(0,2))
        self.nameLabel.setVisible(True)


class DataTableModel(QAbstractTableModel):
    def __init__(self, tsa):
        QAbstractTableModel.__init__(self)
        self._tsa = tsa
        self._data = tsa.data
        self._requiredColumns = ['episode', 'group', 'name', 'x', 'y', 'xlabel', 'ylabel', 'style']
        self._columns = []
        self._updateColumns()

    def rowCount(self, index):
        return len(self._data)

    def columnCount(self, index):
        return len(self._columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole or role == Qt.EditRole:
            seriesIndex = index.row()
            attr = self._columns[index.column()]
            if attr in self._data[seriesIndex]:
                value = self._data[seriesIndex][attr]
                if role == Qt.DisplayRole and isinstance(value, np.ndarray):# and len(value) > 10:
                    if value.ndim == 1:
                        return f'x{len(value)} {value.dtype}'
                    else:
                        return 'x'.join([*value.shape]) + f' {value.dtype}'
            elif attr not in ['x', 'y']:
                value = self._tsa._seriesAttr(attr, seriesIndex)
            else:
                value = None
            if value is None:
                return ''
            return str(value)
        elif role == Qt.FontRole:
            seriesIndex = index.row()
            attr = self._columns[index.column()]
            if attr in self._data[seriesIndex]:
                value = self._data[seriesIndex][attr]
                if isinstance(value, np.ndarray):
                    font = QFont()
                    font.setItalic(True)
                    return font

    def setData(self, index, value, role):
        if not index.isValid():
            return False
        if role == Qt.EditRole:
            seriesIndex = index.row()
            attr = self._columns[index.column()]
            try:
                value = int(value)
            except ValueError:
                try:
                    value = float(value)
                except ValueError:
                    try:
                        value = str(value)
                    except ValueError:
                        return False
            if attr == 'episode':
                if not isinstance(value, int):
                    return False
                applyChange = QMessageBox.question(self._tsa, 'Confirm', 'Are you sure you want to change the episode number? This could invalidate your data structure.', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if applyChange == QMessageBox.No:
                    return False
            elif attr in ['x', 'y']:
                if isinstance(value, str):
                    value = value.strip()
                    if value.startswith('[') and value.endswith(']'):
                        value = value[1:-1]
                    fields = re.split('[,\s]+', value)
                    values = []
                    for field in fields:
                        field = field.strip()
                        if field == '':
                            continue
                        elif field == '...':
                            # the string rep of this array is too long to display
                            # if we were to update based on this string rep, we would lose data
                            return False
                        try:
                            field = int(field)
                        except ValueError:
                            try:
                                field = float(field)
                            except ValueError:
                                # non-numeric value
                                return False
                        values.append(field)
                    if not values:
                        value = None
                        if attr == 'y':
                            return False
                    elif attr == 'x' and len(values) == 1:
                        value = values[0]
                    else:
                        value = np.array(values)
                elif not (isinstance(value, int) or isinstance(value, float)):
                    return False
                applyChange = QMessageBox.question(self._tsa, 'Confirm', 'Are you sure you want to change the series data?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if applyChange == QMessageBox.No:
                    return False
                if len(value) == len(self._data[seriesIndex][attr]):
                    # mutate array in place
                    self._data[seriesIndex][attr][:] = value
                    self._tsa.updateUI()
                    return True
            elif attr == 'style':
                # should be a dictionary
                try:
                    value = ast.literal_eval(value)
                except:
                    return False
                if not isinstance(value, dict):
                    return False
            if value == '' and attr not in self._data[seriesIndex]:
                return False
            self._data[seriesIndex][attr] = value
            self._tsa.updateUI()
            return True
        return False

    def flags(self, index):
        # if index.isValid():
        #     seriesIndex = index.row()
        #     attr = self._columns[index.column()]
        #     if attr in self._data[seriesIndex]:
        #         value = self._data[seriesIndex][attr]
        #         if isinstance(value, np.ndarray):
        #             return Qt.ItemIsSelectable | Qt.ItemIsEnabled
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable
    
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self._columns[section]
            elif orientation == Qt.Vertical:
                return section
    
    def _updateColumns(self):
        self._columns = self._requiredColumns
        for series in self._data:
            for attr in series:
                if attr not in self._columns:
                    self._columns.append(attr)


class ColorButton(QGroupBox):
    def __init__(self, color=QColor('transparent')):
        QGroupBox.__init__(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        self.colorButton = QPushButton()
        self.colorButton.clicked.connect(self.pickColor)
        self._colorWasPicked = False
        layout.addWidget(self.colorButton)

        self.setColor(color)
    
    def color(self) -> QColor:
        pal = self.colorButton.palette()
        return pal.brush(QPalette.Button).color()

    def setColor(self, color):
        if isinstance(color, str):
            color = str2qcolor(color)
        pal = self.colorButton.palette()
        pal.setBrush(QPalette.Button, QBrush(color))
        self.colorButton.setPalette(pal)
        self.colorButton.setGraphicsEffect(QGraphicsOpacityEffect(opacity=color.alphaF()))
    
    def pickColor(self):
        color = QColorDialog.getColor(self.color(), None, "Select Color", options=QColorDialog.ShowAlphaChannel)
        if color.isValid():
            self.setColor(color)
            self._colorWasPicked = True
    
    def colorWasPicked(self) -> bool:
        return self._colorWasPicked
    

# I/O for QtTimeSeriesAnalyzer data

def savemat(filepath, data):
    sp.io.savemat(filepath, {"data": data})

def loadmat(filepath):
    mat = sp.io.loadmat(filepath)
    matdata = mat['data']
    matdata = np.squeeze(matdata)  # (1,N) -> (N,)
    data = []
    for i in range(matdata.size):
        keys = matdata[i].dtype.names
        series = {}
        for j, key in enumerate(keys):
            value = matdata[i][0][0][j]
            value = np.squeeze(value)
            if value.ndim == 0:
                for type_ in [int, float, str]:
                    if value.dtype.type == np.dtype(type_):
                        value = type_(value)
                        break
            series[key] = value
        data.append(series)
    return data


# Utilities

def str2color(colorStr):
    if (colorStr.startswith('(') and colorStr.endswith(')')) or (colorStr.startswith('[') and colorStr.endswith(']')):
        rgba = [int(c) for c in colorStr[1:-1].split(',')]
        if len(rgba) == 3:
            rgba.append(255)
        return tuple(rgba)
    elif colorStr in QColor.colorNames():
        qcolor = QColor(colorStr)
        return qcolor.red(), qcolor.green(), qcolor.blue(), qcolor.alpha()

def str2qcolor(colorStr):
    if (colorStr.startswith('(') and colorStr.endswith(')')) or (colorStr.startswith('[') and colorStr.endswith(']')):
        rgba = [int(c) for c in colorStr[1:-1].split(',')]
        return QColor(*rgba)
    elif colorStr in QColor.colorNames():
        return QColor(colorStr)
    else:
        return pg.mkColor(colorStr)  # ???

def qcolor2str(color):
    for name in QColor.colorNames():
        if QColor(name) == color:
            return name
    if color.alpha() == 255:
        return f'({color.red()},{color.green()},{color.blue()})'
    else:
        return f'({color.red()},{color.green()},{color.blue()},{color.alpha()})'


# Run UI from REPL without blocking the REPL.

def run():
    """
    Run the application from a REPL without blocking the REPL.
    
    e.g., in a REPL, run the following:

    ```
    import PyQtTimeSeriesAnalyzer
    app, tsa = PyQtTimeSeriesAnalyzer.run()
    ```

    This will launch the UI and allow you to continue using the REPL
    where you can access the QApplication object and QtTimeSeriesAnalyzer UI widget
    via the variables `app` and `tsa`, respectively.
    """

    # Create the application
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # Create, show and return widget
    tsa = QtTimeSeriesAnalyzer()
    tsa.show()
    tsa.raise_()  # bring UI window to front
    
    return app, tsa


# Running this file directly will launch the UI.

if __name__ == '__main__':
    # Create the application
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # Create widget
    tsa = QtTimeSeriesAnalyzer2()

    # testing
    # tsa.importHEKA('heka.dat')
    tsa.data = []
    tsa.addSeries(y=np.random.random(10), xlabel="Time, s", ylabel="Current, pA", group=0, labels=[{'text': 'testing 1', 'x': 3, 'y': 0.5}])
    tsa.addSeries(y=np.random.random(10), xlabel="Time, s", ylabel="Voltage, mV", group=1)
    tsa.addSeries(y=np.random.random(10), xlabel="Time, s", ylabel="Current, pA", group=0, labels=[{'text': 'testing 2', 'x': 6, 'y': 0.5}])
    tsa.addSeries(y=np.random.random(10), xlabel="Time, s", ylabel="Voltage, mV", group=1)
    tsa.addSeries(y=np.random.random(10), xlabel="Time, s", ylabel="Current, pA", group=0, episode=1, name='fit')
    tsa.updateUI()

    # tsa.open()


    # Show widget and run application
    tsa.show()
    status = app.exec()
    sys.exit(status)