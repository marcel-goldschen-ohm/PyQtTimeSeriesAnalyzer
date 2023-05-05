"""
PyQtTimeSeriesAnalyzer.py

Very much still a work in progress.

TODO:
- zero, interpolate, mask
- add attr via table view
- hidden series (or just episodes)?
- series tags
- data item context menu
- requirements.txt
- detailed instructions in the associated README.md file
"""


__author__ = "Marcel P. Goldschen-Ohm"
__author_email__ = "goldschen-ohm@utexas.edu, marcel.goldschen@gmail.com"


try:
    from PyQt5.QtCore import *
    from PyQt5.QtGui import *
    from PyQt5.QtWidgets import *
except ImportError:
    raise ImportError("Requires PyQt5")

import sys, os, re, ast, copy
import numpy as np
import scipy as sp
import pyqtgraph as pg

try:
    from pyqtconsole.console import PythonConsole
except ImportError:
    PythonConsole = None

try:
    # https://github.com/campagnola/heka_reader
    import heka_reader
except ImportError:
    heka_reader = None


pg.setConfigOption('foreground', 'k')   # Default foreground color for text, lines, axes, etc.
pg.setConfigOption('background', None)  # Default background for GraphicsView.
# pg.setConfigOptions(antialias=True)     # Draw lines with smooth edges at the cost of reduced performance. !!! HUGE COST


class CustomPlotWidget(pg.PlotWidget):
    def __init__(self, parent=None, tsa=None):
        pg.PlotWidget.__init__(self, parent, viewBox=CustomViewBox(tsa=tsa))

        self.getViewBox().plotWidget = self

        # Time Series Analyzer
        self.tsa = tsa

        # # handle mouse hover over items in scene
        # self.scene().sigMouseHover.connect(self.onMouseHover)

        # # handle mouse clicks
        # self.scene().sigMouseClicked.connect(self.onMouseClick)
    
    def listCustomDataItems(self):
        return [item for item in self.listDataItems() if isinstance(item, CustomPlotDataItem)]
    
    def listNonCustomDataItems(self):
        return [item for item in self.listDataItems() if not isinstance(item, CustomPlotDataItem)]
    
    # def onMouseHover(self, items):
    #     plotItem = items[0]
    #     dataItems = plotItem.listDataItems()
    #     mousePosInPlotWidget = self.mapFromGlobal(QCursor.pos())
    #     viewBox = self.getViewBox()
    #     mousePosInPlotAxes = viewBox.mapSceneToView(mousePosInPlotWidget)
    #     viewBox._selectedSeriesIndexes = []
    #     for item in reversed(dataItems):
    #         if item.curve.mouseShape().contains(mousePosInPlotAxes):
    #             if item.seriesIndex not in viewBox._selectedSeriesIndexes:
    #                 viewBox._selectedSeriesIndexes.append(item.seriesIndex)
    #     # topSeriesIndex = max(seriesIndexes)
    #     # self.getViewBox().updateSeriesMenu(topSeriesIndex)
    
    # def onMouseClick(self, event):
    #     print(f'clicked plot 0x{id(self):x}, event: {event}')
    #     if event.button() == Qt.RightButton:
    #         event.accept()
    #         # hide view box context menu
    #         self.getViewBox().menu.close()
    #         # show context menu
    #         menu = QMenu()
    #         menu.addAction("Test")
    #         x, y = event.scenePos().x(), event.scenePos().y()
    #         menu.exec_(self.mapToGlobal(QPoint(int(x), int(y))))
    #         # self.getPlotItem().setMenuEnabled(False)


class CustomViewBox(pg.ViewBox):
    def __init__(self, parent=None, tsa=None):
        pg.ViewBox.__init__(self, parent)

        # Time Series Analyzer
        self.tsa = tsa

        # Regions of Interest (ROIs)
        self._drawROIs = False
        self._drawROIsOrientation = "vertical"
        self._drawingROI = None
        self._drawingROIStartPos = None

        # Measurement context menu
        self._measureMenu = QMenu("Measure")
        self._measureMenu.addAction("Mean", lambda: self.measure(measurementType="mean"))
        self._measureMenu.addAction("Median", lambda: self.measure(measurementType="median"))
        self._measureMenu.addAction("Min", lambda: self.measure(measurementType="min"))
        self._measureMenu.addAction("Max", lambda: self.measure(measurementType="max"))
        self._measureMenu.addAction("AbsMax", lambda: self.measure(measurementType="absmax"))

        # ROI context menu
        self._roiMenu = QMenu("ROI")
        self._roiMenu.addAction("Draw X axis ROIs", lambda: self.startDrawingROIs(orientation="vertical"))
        self._roiMenu.addSeparator()
        self._roiMenu.addMenu(self._measureMenu)
        self._roiMenu.addSeparator()
        self._roiMenu.addAction("Show ROIs", self.showROIs)
        self._roiMenu.addAction("Hide ROIs", self.hideROIs)
        self._roiMenu.addSeparator()
        self._roiMenu.addAction("Clear ROIs", self.clearROIs)

        # Curve fit context menu
        self._fitMenu = QMenu("Curve Fit")
        self._fitMenu.addAction("Mean", lambda: self.curveFit(fitType="mean"))
        self._fitMenu.addAction("Line", lambda: self.curveFit(fitType="line"))
        self._fitMenu.addAction("Polynomial", lambda: self.curveFit(fitType="polynomial"))
        self._fitMenu.addAction("Spline", lambda: self.curveFit(fitType="spline"))
        self._fitMenu.addAction("Custom", lambda: self.curveFit(fitType="custom"))

        # Context menu (added on to default context menu)
        self.menu.addSeparator()
        self.menu.addMenu(self._roiMenu)
        self.menu.addMenu(self._fitMenu)
        self.menu.addAction("Trace Math", self.traceMathDialog)
        self.menu.addSeparator()
    
    def group(self):
        groups = self.tsa.groups()
        plots = self.tsa._groupPlots()
        for i, plot in enumerate(plots):
            if plot.getViewBox() == self:
                return groups[i]
        return None
    
    def getROIs(self):
        return [item for item in self.allChildren() if isinstance(item, CustomLinearRegionItem)]
    
    def getXAxisROIs(self):
        return [item for item in self.allChildren() if isinstance(item, CustomLinearRegionItem) and item.orientation == "vertical"]
    
    def getYAxisROIs(self):
        return [item for item in self.allChildren() if isinstance(item, CustomLinearRegionItem) and item.orientation == "horizontal"]
    
    def startDrawingROIs(self, orientation="vertical"):
        self._drawROIsOrientation = orientation
        self._drawROIs = True

    def stopDrawingROIs(self):
        self._drawROIs = False
    
    def mousePressEvent(self, event):
        if self._drawROIs:
            if event.button() == Qt.LeftButton:
                posInAxes = self.mapSceneToView(self.mapToScene(event.pos()))
                if self._drawROIsOrientation == "vertical":
                    posAlongAxis = posInAxes.x()
                elif self._drawROIsOrientation == "horizontal":
                    posAlongAxis = posInAxes.y()
                self._drawingROIStartPos = posAlongAxis
                event.accept()
                return
            self._drawROIs = False
        pg.ViewBox.mousePressEvent(self, event)
    
    def mouseReleaseEvent(self, event):
        if self._drawROIs:
            if event.button() == Qt.LeftButton:
                self._drawingROI = None
                event.accept()
                return
        pg.ViewBox.mouseReleaseEvent(self, event)
    
    def mouseMoveEvent(self, event):
        if self._drawROIs:
            if event.buttons() & Qt.LeftButton:
                posInAxes = self.mapSceneToView(self.mapToScene(event.pos()))
                if self._drawROIsOrientation == "vertical":
                    posAlongAxis = posInAxes.x()
                elif self._drawROIsOrientation == "horizontal":
                    posAlongAxis = posInAxes.y()
                limits = sorted([self._drawingROIStartPos, posAlongAxis])
                if self._drawingROI is None:
                    self._drawingROI = CustomLinearRegionItem(orientation=self._drawROIsOrientation, values=limits)
                    self.addItem(self._drawingROI)
                else:
                    self._drawingROI.setRegion(limits)
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
            self.removeItem(roi)
            roi.deleteLater()
    
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

        # fit each data item
        fits = []
        for dataItem in curveDataItems:
            seriesIndex = dataItem.seriesIndex
            data = self.tsa.data[seriesIndex]
            x = self.tsa._seriesAttr(seriesIndex, 'x')
            y = self.tsa._seriesAttr(seriesIndex, 'y')
            
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
                # TODO: implement custom fit
                pass

            # fit series data
            fit = {'x': xfit, 'y': yfit}
            for key in ['xlabel', 'ylabel', 'episode', 'group']:
                fit[key] = self.tsa._seriesAttr(seriesIndex, key)
            fits.append(fit)

            # add fit to plot
            fitItem = CustomPlotDataItem(x=xfit, y=yfit, pen=pg.mkPen(color=(255, 0, 0), width=3))
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
            x = self.tsa._seriesAttr(seriesIndex, 'x')
            y = self.tsa._seriesAttr(seriesIndex, 'y')

            # measurement within each ROI (or whole curve if no ROIs)
            xrois = [roi for roi in self.getXAxisROIs() if roi.isVisible()]
            xranges = [xroi.getRegion() for xroi in xrois]
            if not xranges:
                xranges = [(x[0], x[-1])]
            
            xmeasure = []
            ymeasure = []
            for xrange in xranges:
                xmin, xmax = xrange
                xmask = (x >= xmin) & (x <= xmax)
                xroi = x[xmask]
                yroi = y[xmask]
                nroi = len(xroi)
                if measurementType == "mean":
                    xm = xroi[int(nroi / 2)]
                    ym = np.mean(yroi)
                elif measurementType == "median":
                    xm = xroi[int(nroi / 2)]
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
                measurement[key] = self.tsa._seriesAttr(seriesIndex, key)
            measurement['style'] = {'marker': 'o'}
            measurements.append(measurement)

            # add measure to plot
            measurementItem = CustomPlotDataItem(x=xmeasure, y=ymeasure, pen=pg.mkPen(color=(255, 0, 0), width=3), 
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
        self.tsa.traceMathDialog(groups=[self.group()])


class CustomPlotDataItem(pg.PlotDataItem):
    def __init__(self, *args, **kwargs):
        pg.PlotDataItem.__init__(self, *args, **kwargs)

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
        # if self.menu is None:
        # defer menu creation until needed
        self.menu = QMenu()

        viewBox = self.parentWidget()
        tsa = viewBox.tsa
        name = tsa._seriesAttr(self.seriesIndex, 'name')
        if name is None or name == "":
            name = f"Series {self.seriesIndex}"
        else:
            name += f" [{self.seriesIndex}]"
        self._contextMenu = QMenu(name)

        self._contextMenu.addAction("Rename", self.nameDialog)
        self._contextMenu.addAction("Edit Style", self.styleDialog)
        self._contextMenu.addSeparator()
        self._contextMenu.addAction("Delete Series", self.removeSeries)

        self.menu.addMenu(self._contextMenu)
        self.menu.addSeparator()

        return self.menu
    
    def nameDialog(self):
        viewBox = self.parentWidget()
        tsa = viewBox.tsa
        name, ok = QInputDialog.getText(tsa, "Series name", "Series name:", text=tsa._seriesAttr(self.seriesIndex, 'name'))
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
        style = tsa._seriesAttr(self.seriesIndex, 'style')
        if tsa.styleDialog(style):
            tsa.data[self.seriesIndex]['style'] = style
            tsa.updatePlots()
    
    def removeSeries(self):
        viewBox = self.parentWidget()
        tsa = viewBox.tsa
        del tsa.data[self.seriesIndex]
        tsa.updateUI()


class CustomLinearRegionItem(pg.LinearRegionItem):
    def __init__(self, *args, **kwargs):
        pg.LinearRegionItem.__init__(self, *args, **kwargs)

        # context menu
        self.menu = None
    
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
        if self.menu is None:
            # defer menu creation until needed
            self.menu = QMenu()
            self.menu.addAction("Delete ROI", self.removeROI)
            self.menu.addSeparator()
        return self.menu
    
    def removeROI(self):
        viewBox = self.parentWidget()
        viewBox.removeItem(self)
        self.deleteLater()


class QtTimeSeriesAnalyzer(QWidget):
    def __init__(self):
        QWidget.__init__(self)

        # list of data series dictionaries
        self.data = [{}]

        # plot styles
        self.styles = {}
        self.styles['figure'] = {}
        self.styles['figure']['background-color'] = None  # None ==> use system default
        self.styles['axes'] = {}
        self.styles['axes']['background-color'] = [220, 220, 220]
        self.styles['axes']['foreground-color'] = [128, 128, 128]
        self.styles['axes']['label-font'] = QFont('Helvetica')
        self.styles['axes']['label-font'].setPointSize(14)
        self.styles['axes']['label-font'].setWeight(QFont.Normal)
        self.styles['axes']['tick-font'] = QFont('Helvetica')
        self.styles['axes']['tick-font'].setPointSize(10)
        self.styles['axes']['tick-font'].setWeight(QFont.Thin)
        self.styles['lines'] = {}
        self.styles['lines']['width'] = 2
        self.styles['lines']['colormap'] = [
            [0, 113.9850, 188.9550],
            [216.7500, 82.8750, 24.9900],
            [236.8950, 176.9700, 31.8750],
            [125.9700, 46.9200, 141.7800],
            [118.8300, 171.8700, 47.9400],
            [76.7550, 189.9750, 237.9150],
            [161.9250, 19.8900, 46.9200]
        ]
        self.styles['markers'] = {}
        self.styles['markers']['size'] = 10

        # Python interactive console
        if PythonConsole is not None:
            self._console = PythonConsole()
            self._console.push_local_ns('self', self)
            self._console.eval_queued()

            pal = self._console.palette()
            pal.setColor(pal.Base, QColor(82, 82, 82))
            self._console.setPalette(pal)

            self._consoleButton = QToolButton()
            self._consoleButton.setText("Console")
            self._consoleButton.setToolTip("Interactive Python Console")
            self._consoleButton.clicked.connect(self.showCosole)
        else:
            self._console = None

        # widget background color
        if self.styles['figure']['background-color'] is not None:
            pal = self.palette()
            pal.setColor(pal.Window, QColor(*self.styles['figure']['background-color']))
            self.setPalette(pal)

        # visible group selection
        self._visibleGroupsListWidget = QListWidget()
        self._visibleGroupsListWidget.setSelectionMode(QAbstractItemView.MultiSelection)
        self._visibleGroupsListWidget.itemSelectionChanged.connect(self._onVisibleGroupsChanged)

        self._visibleGroupsButton = QToolButton()
        self._visibleGroupsButton.setText("Groups")  # u"\U0001F441"
        self._visibleGroupsButton.setToolTip("Visible Groups")
        self._visibleGroupsButton.setPopupMode(QToolButton.InstantPopup)
        self._visibleGroupsButton.setMenu(QMenu(self._visibleGroupsButton))
        action = QWidgetAction(self._visibleGroupsButton)
        action.setDefaultWidget(self._visibleGroupsListWidget)
        self._visibleGroupsButton.menu().addAction(action)

        # visible name selection
        self._visibleNamesListWidget = QListWidget()
        self._visibleNamesListWidget.setSelectionMode(QAbstractItemView.MultiSelection)
        self._visibleNamesListWidget.itemSelectionChanged.connect(self._onVisibleNamesChanged)

        self._visibleNamesButton = QToolButton()
        self._visibleNamesButton.setText("Names")  # u"\U0001F441"
        self._visibleNamesButton.setToolTip("Visible Names")
        self._visibleNamesButton.setPopupMode(QToolButton.InstantPopup)
        self._visibleNamesButton.setMenu(QMenu(self._visibleNamesButton))
        action = QWidgetAction(self._visibleNamesButton)
        action.setDefaultWidget(self._visibleNamesListWidget)
        self._visibleNamesButton.menu().addAction(action)

        # episode traversal
        self._visibleEpisodesEdit = QLineEdit()
        self._visibleEpisodesEdit.setMinimumWidth(64)
        self._visibleEpisodesEdit.setMaximumWidth(128)
        self._visibleEpisodesEdit.setToolTip("Visible Episodes")
        self._visibleEpisodesEdit.textEdited.connect(self.updatePlots)

        self._prevEpisodeButton = QPushButton("<")
        self._prevEpisodeButton.setMaximumWidth(32)
        self._prevEpisodeButton.setToolTip("Previous Episode")
        self._prevEpisodeButton.clicked.connect(self.prevEpisode)

        self._nextEpisodeButton = QPushButton(">")
        self._nextEpisodeButton.setMaximumWidth(32)
        self._nextEpisodeButton.setToolTip("Next Episode")
        self._nextEpisodeButton.clicked.connect(self.nextEpisode)

        # data table model/view
        self._tableModel = None
        self._tableView = None
        self._tableModelViewButton = QToolButton()
        self._tableModelViewButton.setText("Table")
        self._tableModelViewButton.setToolTip("Data Table")
        self._tableModelViewButton.clicked.connect(self.editDataTable)

        # # baseline and scale toggles
        # self._showBaselineButton = QToolButton()
        # self._showBaselineButton.setText("SB")
        # self._showBaselineButton.setToolTip("Show baseline")

        # self._applyBaselineButton = QToolButton()
        # self._applyBaselineButton.setText("B")
        # self._applyBaselineButton.setToolTip("Apply baseline")

        # self._applyScaleButton = QToolButton()
        # self._applyScaleButton.setText("S")
        # self._applyScaleButton.setToolTip("Apply scale")

        # layout
        self._mainGridLayout = QGridLayout(self)
        self._mainGridLayout.setContentsMargins(3, 3, 3, 3)
        self._mainGridLayout.setSpacing(0)

        self._topToolbar = QToolBar()
        self._visibleEpisodesEditAction = self._topToolbar.addWidget(self._visibleEpisodesEdit)
        self._prevEpisodeButtonAction = self._topToolbar.addWidget(self._prevEpisodeButton)
        self._nextEpisodeButtonAction = self._topToolbar.addWidget(self._nextEpisodeButton)
        self._visibleGroupsButtonAction = self._topToolbar.addWidget(self._visibleGroupsButton)
        self._visibleNamesButtonAction = self._topToolbar.addWidget(self._visibleNamesButton)
        self._tableModelViewButtonAction = self._topToolbar.addWidget(self._tableModelViewButton)
        if PythonConsole is not None:
            self._consoleButtonAction = self._topToolbar.addWidget(self._consoleButton)
        # self._showBaselineButtonAction = self._topToolbar.addWidget(self._showBaselineButton)
        # self._applyBaselineButtonAction = self._topToolbar.addWidget(self._applyBaselineButton)
        # self._applyScaleButtonAction = self._topToolbar.addWidget(self._applyScaleButton)
        self._mainGridLayout.addWidget(self._topToolbar, 0, 0)

        self._groupPlotsVBoxLayout = QVBoxLayout()
        self._groupPlotsVBoxLayout.setContentsMargins(3, 3, 3, 3)
        self._groupPlotsVBoxLayout.setSpacing(3)
        self._mainGridLayout.addLayout(self._groupPlotsVBoxLayout, 1, 0)

        self.updateUI()
    
    def clear(self):
        self.data = [{}]
        self.updateUI()
    
    def save(self, filepath=None):
        if filepath is None:
            filepath, _ = QFileDialog.getSaveFileName(self, "Save Data", "", "MATLAB Data Files (*.mat)")
        if not filepath:
            return
        sp.io.savemat(filepath, {"data": self.data})

    def open(self, filepath=None):
        if filepath is None:
            filepath, _ = QFileDialog.getOpenFileName(self, "Open Data", "", "MATLAB Data Files (*.mat)")
        if not filepath or not os.path.isfile(filepath):
            return
        mat = sp.io.loadmat(filepath)
        data = mat['data']
        data = np.squeeze(data)  # (1,N) -> (N,)
        self.data = []
        for i in range(data.size):
            keys = data[i].dtype.names
            series = {}
            for j, key in enumerate(keys):
                value = data[i][0][0][j]
                value = np.squeeze(value)
                if value.ndim == 0:
                    for type_ in [int, float, str]:
                        if value.dtype.type == np.dtype(type_):
                            value = type_(value)
                            break
                series[key] = value
            self.data.append(series)
        self.updateUI()
    
    def importHEKA(self, filepath=None):
        """
        Import HEKA data file.

        HEKA format: Group (Experiment) -> Series (Recording) -> Sweep (Episode) -> Trace (Data Series)
        """
        if heka_reader is None:
            return
        if filepath is None:
            filepath, _ = QFileDialog.getOpenFileName(self, "Open Data", "", "MATLAB Data Files (*.mat)")
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
        if data:
            self.data = data
            self.updateUI()
    
    def numSeries(self) -> int:
        return len(self.data)
    
    def addSeries(self, **kwargs):
        seriesDict = kwargs
        self.data.append(seriesDict)
        self.updateUI()
    
    # def addData(self, data):
    #     if isinstance(data, np.ndarray):
    #         pass
    #     elif isinstance(data, dict):
    #         self.data.append(data)
    #     elif isinstance(data, list):
    #         for item in data:
    #             if isinstance(item, np.ndarray):
    #                 pass
    #             elif isinstance(item, dict):
    #                 self.data.append(item)
    #     self.updateUI()
    
    def _seriesAttr(self, seriesIndex: int, attr):
        series = self.data[seriesIndex]
        value = series[attr] if attr in series else None
        if value is None:
            if attr == 'x':
                if 'y' in series:
                    # n = series['y'].shape[-1]
                    n = len(series['y'])
                    value = np.arange(n)
            elif attr in ['xlabel', 'ylabel']:
                value = ''
            elif attr == 'name':
                value = 'data'
            elif attr in ['episode', 'group']:
                value = 0
            elif attr == 'style':
                value = {}
        elif attr == 'x':
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
    
    def _dataAttr(self, attr, seriesIndexes=None) -> list:
        if seriesIndexes is None:
            seriesIndexes = range(len(self.data))
        return [self._seriesAttr(i, attr) for i in seriesIndexes if 0 <= i < len(self.data)]
    
    def _styleAttr(self, style: dict, attr):
        attr = attr.lower()
        value = style[attr] if attr in style else None
        if value is not None:
            return value
        attrGroups = [
            ['color', 'c'],
            ['linestyle', 'ls'],
            ['linewidth', 'lw'],
            ['marker'],
            ['markersize', 'ms', 'size'],
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
            ['marker'],
            ['markersize', 'ms', 'size'],
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
    
    def _seriesIndexes(self, episodes=None, groups=None, names=None) -> list:
        indexes = []
        for i in range(len(self.data)):
            if episodes is None or self._seriesAttr(i, 'episode') in episodes:
                if groups is None or self._seriesAttr(i, 'group') in groups:
                    if names is None:
                        indexes.append(i)
                    else:
                        name = self._seriesAttr(i, 'name')
                        if name is None or name == '' or name in names:
                            indexes.append(i)
        return indexes
    
    def groups(self, seriesIndexes=None) -> list:
        groups = []
        for group in self._dataAttr('group', seriesIndexes):
            if group not in groups:
                groups.append(group)
        if np.all([isinstance(group, int) for group in groups]):
            groups = np.sort(groups).tolist()
        return groups
    
    def episodes(self, seriesIndexes=None) -> list:
        return np.unique(self._dataAttr('episode', seriesIndexes)).tolist()
    
    def names(self, seriesIndexes=None) -> list:
        names = []
        for name in self._dataAttr('name', seriesIndexes):
            if name not in names:
                names.append(name)
        return names
    
    def groupNames(self, groups=None) -> list:
        if groups is None:
            groups = self.groups()
        names = []
        for group in groups:
            if isinstance(group, str):
                names.append(group)
            else:
                indexes = self._seriesIndexes(groups=[group])
                if indexes:
                    ylabel = self._seriesAttr(indexes[0], 'ylabel')
                    names.append(str(group) + ": " + ylabel)
                else:
                    names.append(str(group))
        return names
    
    def visibleGroups(self) -> list:
        groups = self.groups()
        if not groups:
            return []
        visibleGroupIndexes = [index.row() for index in self._visibleGroupsListWidget.selectedIndexes()]
        visibleGroups = [groups[i] for i in visibleGroupIndexes if i < len(groups)]
        if len(visibleGroups) == 0:
            visibleGroups = groups
        return visibleGroups
    
    def setVisibleGroups(self, visibleGroups: list):
        groups = self.groups()
        self._visibleGroupsListWidget.itemSelectionChanged.disconnect()
        self._visibleGroupsListWidget.clear()
        self._visibleGroupsListWidget.addItems(self.groupNames())
        for group in visibleGroups:
            if group in groups:
                self._visibleGroupsListWidget.item(groups.index(group)).setSelected(True)
        self._visibleGroupsListWidget.itemSelectionChanged.connect(self._onVisibleGroupsChanged)
        self._onVisibleGroupsChanged()
    
    def _updateVisibleGroupsListView(self):
        groups = self.groups()
        visibleGroupIndexes = [index.row() for index in self._visibleGroupsListWidget.selectedIndexes()]
        self._visibleGroupsListWidget.itemSelectionChanged.disconnect()
        self._visibleGroupsListWidget.clear()
        self._visibleGroupsListWidget.addItems(self.groupNames())
        for i in visibleGroupIndexes:
            if i < len(groups):
                self._visibleGroupsListWidget.item(i).setSelected(True)
        self._visibleGroupsListWidget.itemSelectionChanged.connect(self._onVisibleGroupsChanged)
    
    def _onVisibleGroupsChanged(self):
        groups = self.groups()
        visibleGroups = self.visibleGroups()
        for i, plot in enumerate(self._groupPlots()):
            if i < len(groups) and groups[i] in visibleGroups:
                plot.show()
            else:
                plot.hide()
    
    def _groupPlots(self) -> list:
        groupPlotsVBoxWidgets = [self._groupPlotsVBoxLayout.itemAt(i).widget() for i in range(self._groupPlotsVBoxLayout.count())]
        return [widget for widget in groupPlotsVBoxWidgets if isinstance(widget, CustomPlotWidget)]
    
    def _appendGroupPlot(self) -> CustomPlotWidget:
        plot = self.newPlot()
        self._groupPlotsVBoxLayout.addWidget(plot, stretch=1)
        return plot
    
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
        names = self.names()
        self._visibleNamesListWidget.itemSelectionChanged.disconnect()
        self._visibleNamesListWidget.clear()
        self._visibleNamesListWidget.addItems(names)
        for name in visibleNames:
            if name in names:
                self._visibleNamesListWidget.item(names.index(name)).setSelected(True)
        self._visibleNamesListWidget.itemSelectionChanged.connect(self._onVisibleNamesChanged)
        self._onVisibleNamesChanged()
    
    def _updateVisibleNamesListView(self):
        names = self.names()
        visibleNameIndexes = [index.row() for index in self._visibleNamesListWidget.selectedIndexes()]
        self._visibleNamesListWidget.itemSelectionChanged.disconnect()
        self._visibleNamesListWidget.clear()
        self._visibleNamesListWidget.addItems(names)
        for i in visibleNameIndexes:
            if i < len(names):
                self._visibleNamesListWidget.item(i).setSelected(True)
        self._visibleNamesListWidget.itemSelectionChanged.connect(self._onVisibleNamesChanged)
    
    def _onVisibleNamesChanged(self):
        self.updatePlots()
    
    def numSelectedVisibleNames(self) -> int:
        visibleNameIndexes = [index.row() for index in self._visibleNamesListWidget.selectedIndexes()]
        return len(visibleNameIndexes)
    
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
    
    def updatePlots(self):
        # one plot per group, arranged vertically
        visibleGroups = self.visibleGroups()
        visibleEpisodes = self.visibleEpisodes()
        visibleNames = self.visibleNames()
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
            dataItems = plot.listCustomDataItems()
            colormap = self.styles['lines']['colormap']
            colorIndex = 0
            seriesIndexes = self._seriesIndexes(groups=[group], episodes=visibleEpisodes, names=visibleNames)
            j = 0
            for index in seriesIndexes:
                # data to plot
                series = self.data[index]
                x = self._seriesAttr(index, 'x')
                y = self._seriesAttr(index, 'y')
                if x is None or y is None:
                    continue
                style = self._seriesAttr(index, 'style')

                color = self._styleAttr(style, 'color')
                if color is None:
                    color = colormap[colorIndex % len(colormap)]
                    color = [int(c) for c in color]
                    color = QColor(*color)
                    colorIndex += 1
                else:
                    color = str2qcolor(color)

                lineStyle = self._styleAttr(style, 'linestyle')
                lineStyles = {
                    '-': Qt.SolidLine, '--': Qt.DashLine, ':': Qt.DotLine, '-.': Qt.DashDotLine, 
                    'none': None, '': Qt.SolidLine, None: Qt.SolidLine
                }
                lineStyle = lineStyles[lineStyle]

                lineWidth = self._styleAttr(style, 'linewidth')
                if lineWidth is None:
                    lineWidth = self.styles['lines']['width']
                else:
                    lineWidth = float(lineWidth)
                
                if lineStyle is None:
                    linePen = None
                else:
                    linePen = pg.mkPen(color=color, width=lineWidth, style=lineStyle)

                symbol = self._styleAttr(style, 'marker')
                if symbol is not None:
                    symbolSize = self._styleAttr(style, 'markersize')
                    if symbolSize is None:
                        symbolSize = self.styles['markers']['size']
                    else:
                        symbolSize = float(symbolSize)

                    symbolEdgeWidth = self._styleAttr(style, 'markeredgewidth')
                    if symbolEdgeWidth is None:
                        symbolEdgeWidth = lineWidth
                    else:
                        symbolEdgeWidth = float(symbolEdgeWidth)
                    
                    symbolEdgeColor = self._styleAttr(style, 'markeredgecolor')
                    if symbolEdgeColor is None:
                        symbolEdgeColor = color
                    else:
                        symbolEdgeColor = str2qcolor(symbolEdgeColor)

                    symbolFaceColor = self._styleAttr(style, 'markerfacecolor')
                    if symbolFaceColor is None:
                        symbolFaceColor = symbolEdgeColor
                        symbolFaceColor.setAlpha(0)
                    else:
                        symbolFaceColor = str2qcolor(symbolFaceColor)
                    
                    symbolPen = pg.mkPen(color=symbolEdgeColor, width=symbolEdgeWidth)
                    # symbolBrush = (symbolFaceColor.red(), symbolFaceColor.green(), symbolFaceColor.blue(), symbolFaceColor.alpha())
                
                if len(dataItems) > j:
                    # update existing plot data
                    dataItems[j].setData(x, y)
                    dataItems[j].setPen(linePen)
                    dataItems[j].setSymbol(symbol)
                    if symbol is not None:
                        dataItems[j].setSymbolSize(symbolSize)
                        dataItems[j].setSymbolPen(symbolPen)
                        dataItems[j].setSymbolBrush(symbolFaceColor)
                    dataItems[j].seriesIndex = index
                else:
                    # add new plot data
                    # dataItem = plot.plot(x, y, pen=linePen)
                    if symbol is None:
                        dataItem = CustomPlotDataItem(x, y, pen=linePen)
                    else:
                        dataItem = CustomPlotDataItem(x, y, pen=linePen, 
                            symbol=symbol, symbolSize=symbolSize, symbolPen=symbolPen, symbolBrush=symbolFaceColor)
                    dataItem.seriesIndex = index
                    plot.addItem(dataItem)
                
                # axis labels (based on first plot with axis labels)
                if j == 0 or plot.getAxis('bottom').labelText == '':
                    xlabel = self._seriesAttr(index, 'xlabel')
                    plot.getAxis('bottom').setLabel(xlabel)
                if j == 0 or plot.getAxis('left').labelText == '':
                    ylabel = self._seriesAttr(index, 'ylabel')
                    plot.getAxis('left').setLabel(ylabel)
                
                # next plot data item
                j += 1
            
            # remove extra plot items
            dataItems = plot.listCustomDataItems()
            while len(dataItems) > j:
                dataItem = dataItems.pop()
                plot.removeItem(dataItem)
                dataItem.deleteLater()
                
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
    
    def updateUI(self):
        # update data
        while len(self.data) > 1 and self.data[0] == {}:
            self.data.pop(0)

        # update widgets
        self._updateVisibleGroupsListView()
        self._updateVisibleNamesListView()

        # update plots
        self.updatePlots()

        # show/hide toolbar widgets
        showGroupControls = len(self.groups()) > 1
        self._visibleGroupsButtonAction.setVisible(showGroupControls)
        showNameControls = len(self.names()) > 1
        self._visibleNamesButtonAction.setVisible(showNameControls)
        showEpisodeControls = len(self.episodes()) > 1
        self._visibleEpisodesEditAction.setVisible(showEpisodeControls)
        self._prevEpisodeButtonAction.setVisible(showEpisodeControls)
        self._nextEpisodeButtonAction.setVisible(showEpisodeControls)

        # update table model/view
        if self._tableView is not None and self._tableView.isVisible():
            self.editDataTable()
    
    def newPlot(self) -> CustomPlotWidget:
        plot = CustomPlotWidget(tsa=self)

        # layout
        plot.getAxis('left').setWidth(70)

        # fonts
        for key in ['left', 'right', 'top', 'bottom']:
            plot.getAxis(key).setPen(self.styles['axes']['foreground-color'])
            plot.getAxis(key).setTextPen(self.styles['axes']['foreground-color'])
            plot.getAxis(key).label.setFont(self.styles['axes']['label-font'])
            plot.getAxis(key).setTickFont(self.styles['axes']['tick-font'])
        
        # colors
        plot.getViewBox().setBackgroundColor(QColor(*self.styles['axes']['background-color']))

        # grid
        if False:
            plot.showGrid(x=True, y=True, alpha=0.2)
            # hack to stop grid from clipping axis tick labels
            for key in ['left', 'bottom']:
                plot.getAxis(key).setGrid(False)
            for key in ['right', 'top']:
                plot.getAxis(key).setStyle(showValues=False)
                plot.showAxis(key)

        return plot
    
    def editDataTable(self):
        if self._tableModel is not None:
            self._tableModel.deleteLater()
        self._tableModel = DataTableModel(self)

        if self._tableView is None:
            self._tableView = QTableView()
            # self._tableView.horizontalHeader().setMinimumSectionSize(50)
        self._tableView.setModel(self._tableModel)
        self._tableView.show()
        self._tableView.resizeColumnsToContents()
    
    def styleDialog(self, style: dict):
        dlg = QDialog(self)
        dlg.setWindowTitle("Style")
        form = QFormLayout(dlg)
        widgets = {}
        for key in ['linestyle', 'linewidth', 'color', 'marker', 'markersize', 'markeredgewidth', 'markeredgecolor', 'markerfacecolor']:
            value = self._styleAttr(style, key)
            if 'color' in key:
                if value is None:
                    color = QColor(255, 255, 255, 0)
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
                    if value.alpha() == 0:
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
    
    def showCosole(self):
        if self._console is None:
            return
        self._console.show()
    
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
                    seriesIndexes = self._seriesIndexes(episodes=episodes, groups=groups)
                    names = self._dataAttr('name', seriesIndexes=seriesIndexes)
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
                    self.data.append(resultSeries)
            self.updateUI()


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
                value = self._tsa._seriesAttr(seriesIndex, attr)
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


class ColorButton(QPushButton):
    def __init__(self, color=Qt.white):
        QPushButton.__init__(self)
        # self.setAutoFillBackground(True)  # not needed ???
        self.setColor(color)
        self.clicked.connect(self.pickColor)
    
    def color(self):
        pal = self.palette()
        return pal.color(QPalette.Button)

    def setColor(self, color):
        pal = self.palette()
        pal.setColor(QPalette.Button, color)
        self.setPalette(pal)
        self.update()
    
    def pickColor(self):
        color = QColorDialog.getColor(self.color(), None, "Select Color", options=QColorDialog.ShowAlphaChannel)
        if color.isValid():
            self.setColor(color)
    

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


def run():
    """
    Run the application from a REPL without blocking the REPL.
    
    e.g., in a REPL, run the following:

    ```
    import PyQtTimeSeriesAnalyzer
    app, tsa = PyQtTimeSeriesAnalyzer.run()
    ```

    This will launch the application and allow you to continue using the REPL
    where you can access the QApplication object and QtTimeSeriesAnalyzer widget
    via the variables app and tsa, respectively.
    """

    # Create the application
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # Create, show and return widget
    tsa = QtTimeSeriesAnalyzer()
    tsa.show()
    tsa.raise_()  # bring window to front
    
    return app, tsa


if __name__ == '__main__':
    # Create the application
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # Create widget
    tsa = QtTimeSeriesAnalyzer()

    # testing
    tsa.importHEKA('heka.dat')
    # for i in range(10):
    #     tsa.addSeries(y=np.random.random(100), xlabel="Time, s", ylabel="Current, pA", group="I", episode=i)
    #     tsa.addSeries(y=np.random.random(100), xlabel="Time, s", ylabel="Voltage, mV", group="V", episode=i)

    # Show widget and run application
    tsa.show()
    sys.exit(app.exec())