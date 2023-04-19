"""
PyQtTimeSeriesAnalyzer.py

Very much still a work in progress.

TODO:
- add fit lines to data set
- UI to edit data table
- load/save data in Matlab format
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

import sys
import re
import numpy as np
import scipy as sp
import pyqtgraph as pg


pg.setConfigOption('foreground', 'k')   # Default foreground color for text, lines, axes, etc.
pg.setConfigOption('background', None)  # Default background for GraphicsView.
# pg.setConfigOptions(antialias=True)     # Draw lines with smooth edges at the cost of reduced performance. !!! HUGE COST


class CustomViewBox(pg.ViewBox):
    def __init__(self, parent=None, tsa=None):
        pg.ViewBox.__init__(self, parent)

        # Time Series Analyzer
        self.tsa = tsa

        # Regions of Interest
        self.ROIs = []

        self._roiMenu = QMenu("ROI")
        self._roiMenu.addAction("Add X axis ROI", lambda: self.addROI(orientation="vertical"))
        self._roiMenu.addAction("Add Y axis ROI", lambda: self.addROI(orientation="horizontal"))
        self._roiMenu.addSeparator()
        self._roiMenu.addAction("Show ROIs", self.showROIs)
        self._roiMenu.addAction("Hide ROIs", self.hideROIs)
        self._roiMenu.addSeparator()
        self._roiMenu.addAction("Clear ROIs", self.clearROIs)

        self._fitMenu = QMenu("Curve Fit")
        self._fitMenu.addAction("Mean", lambda: self.curveFit(fitType="mean"))
        self._fitMenu.addAction("Line", lambda: self.curveFit(fitType="line"))
        self._fitMenu.addAction("Polynomial", lambda: self.curveFit(fitType="polynomial"))
        self._fitMenu.addAction("Spline", lambda: self.curveFit(fitType="spline"))
        self._fitMenu.addAction("Custom", lambda: self.curveFit(fitType="custom"))

        self.menu.addSeparator()
        self.menu.addMenu(self._roiMenu)
        self.menu.addMenu(self._fitMenu)
        self.menu.addSeparator()
    
    def group(self):
        groups = self.tsa.groups()
        for i, plot in enumerate(self.tsa._groupPlots()):
            if self is plot.getPlotItem().getViewBox():
                return groups[i]
    
    def addROI(self, orientation="vertical", limits=None):
        if limits is None:
            # place ROI in the middle of the view range
            if orientation == "vertical":
                # X axis range
                min_, max_ = self.state['viewRange'][0]
            elif orientation == "horizontal":
                # Y axis range
                min_, max_ = self.state['viewRange'][1]
            range_ = max_ - min_
            mid = (min_ + max_) / 2
            limits = (mid - 0.05 * range_, mid + 0.05 * range_)
        roi = pg.LinearRegionItem(values=limits, orientation=orientation)
        self.addItem(roi)
        self.ROIs.append(roi)
    
    def showROIs(self):
        for roi in self.ROIs:
            roi.show()
    
    def hideROIs(self):
        for roi in self.ROIs:
            roi.hide()
    
    def clearROIs(self):
        for roi in self.ROIs:
            self.removeItem(roi)
            roi.deleteLater()
        self.ROIs = []
    
    def listDataItems(self) -> list:
        return [item for item in self.allChildren() if isinstance(item, pg.PlotDataItem)]
    
    def curveFit(self, fitType="mean", fitParams=None, restrictOptimizationToROIs=True, restrictOutputToROIs=False):
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
            if 'smoothing' not in fitParams:
                try:
                    x, y = self.listDataItems()[0].getData()
                    s = len(x)
                except:
                    s = 100
                fitParams['smoothing'], ok = QInputDialog.getInt(
                    self.parentWidget().parentWidget(), "Spline Fit", "Smoothing 0-inf (# samples often works well):", s, 0, int(1e9), 1)
                if not ok:
                    return

        # fit each data item
        dataItems = self.listDataItems()
        fits = []
        group = self.group()
        for dataItem in dataItems:
            x, y = dataItem.getData()  # ??? x, y = dataItem.getOriginalData() ???
            
            # optimize fit based on (fx, fy)
            if restrictOptimizationToROIs and len(self.ROIs):
                inROIs = np.zeros(len(x), dtype=bool)
                for roi in self.ROIs:
                    inROIs = inROIs | roi.getRegion().contains(x)
                fx, fy = x[inROIs], y[inROIs]
            else:
                fx, fy = x, y
            
            # fit = (xfit, yfit)
            if restrictOutputToROIs:
                xfit = fx
            else:
                xfit = x
            
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
                tck = sp.interpolate.splrep(fx, fy, s=fitParams['smoothing'])
                yfit = sp.interpolate.splev(xfit, tck, der=0)
            elif fitType == "custom":
                pass

            # fit series data
            fits.append({'x': xfit, 'y': yfit, 'group': group})

            # add fit to plot
            fitItem = pg.PlotDataItem(x=xfit, y=yfit, pen=pg.mkPen(color=(255, 0, 0), width=3))
            self.addItem(fitItem)
        
        # keep fits?
        keepFits = QMessageBox.question(self.parentWidget().parentWidget(), "Keep Fits?", "Keep fits?", QMessageBox.Yes | QMessageBox.No)
        if keepFits == QMessageBox.Yes:
            self.tsa.dataSeries.extend(fits)
        
        self.tsa.updatePlots()


class CustomPlotWidget(pg.PlotWidget):
    def __init__(self, parent=None, tsa=None):
        pg.PlotWidget.__init__(self, parent, viewBox=CustomViewBox(tsa=tsa))

        # Time Series Analyzer
        self.tsa = tsa


class QtTimeSeriesAnalyzer(QWidget):
    def __init__(self):
        QWidget.__init__(self)

        # list of time series dictionaries
        self.dataSeries = []

        # plot styles
        self.styles = {}
        self.styles['figure'] = {}
        self.styles['figure']['background-color'] = None
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

        # widget background color
        # pal = self.palette()
        # pal.setColor(pal.Window, QColor(*self.styles['figure']['background-color']))
        # self.setPalette(pal)

        # visible group selection
        self._visibleGroupsListWidget = QListWidget()
        self._visibleGroupsListWidget.setSelectionMode(QAbstractItemView.MultiSelection)
        self._visibleGroupsListWidget.itemSelectionChanged.connect(self._onVisibleGroupsChanged)

        self._visibleGroupsButton = QToolButton()
        self._visibleGroupsButton.setText(u"\U0001F441")
        # self._visibleGroupsButton.setMaximumWidth(35)
        self._visibleGroupsButton.setToolTip("Select visible groups")
        self._visibleGroupsButton.setPopupMode(QToolButton.InstantPopup)
        self._visibleGroupsButton.setMenu(QMenu(self._visibleGroupsButton))
        action = QWidgetAction(self._visibleGroupsButton)
        action.setDefaultWidget(self._visibleGroupsListWidget)
        self._visibleGroupsButton.menu().addAction(action)

        # traversal over time series within each group (i.e., sweeps)
        self._visibleSweepsIndexEdit = QLineEdit()
        self._visibleSweepsIndexEdit.setMinimumWidth(50)
        self._visibleSweepsIndexEdit.setMaximumWidth(150)
        self._visibleSweepsIndexEdit.setToolTip("Current series")
        self._visibleSweepsIndexEdit.textEdited.connect(self.updatePlots)

        self._prevSweepButton = QPushButton("<")
        self._prevSweepButton.setMaximumWidth(35)
        self._prevSweepButton.setToolTip("Previous series")
        self._prevSweepButton.clicked.connect(self.prevSweep)

        self._nextSweepButton = QPushButton(">")
        self._nextSweepButton.setMaximumWidth(35)
        self._nextSweepButton.setToolTip("Next series")
        self._nextSweepButton.clicked.connect(self.nextSweep)

        # layout
        self._mainGridLayout = QGridLayout(self)
        self._mainGridLayout.setContentsMargins(3, 3, 3, 3)
        self._mainGridLayout.setSpacing(0)

        self._topToolbar = QToolBar()
        self._visibleGroupsButtonAction = self._topToolbar.addWidget(self._visibleGroupsButton)
        self._seriesIndexEditAction = self._topToolbar.addWidget(self._visibleSweepsIndexEdit)
        self._prevSeriesButtonAction = self._topToolbar.addWidget(self._prevSweepButton)
        self._nextSeriesButtonAction = self._topToolbar.addWidget(self._nextSweepButton)
        self._mainGridLayout.addWidget(self._topToolbar, 0, 0)

        self._groupPlotsVBoxLayout = QVBoxLayout()
        self._groupPlotsVBoxLayout.setContentsMargins(3, 3, 3, 3)
        self._groupPlotsVBoxLayout.setSpacing(3)
        self._mainGridLayout.addLayout(self._groupPlotsVBoxLayout, 1, 0)
    
    def numSeries(self) -> int:
        return len(self.dataSeries)
    
    def addSeries(self, **kwargs):
        seriesDict = kwargs
        self.dataSeries.append(seriesDict)
        self.updateUI()
    
    def addListOfSeries(self, dataSeries: list):
        self.dataSeries.extend(dataSeries)
        self.updateUI()
    
    def _seriesAttr(self, series: dict, attr):
        if attr == 'x':
            if 'x' in series:
                x = series['x']
                if len(x) == 1 and 'y' in series:
                    n = len(series['y'])
                    if n > 1:
                        x = np.arange(n) * x
                return x
            elif 'y' in series:
                return np.arange(len(series['y']))
        elif attr == 'group':
            return series[attr] if attr in series else ''
        elif attr == 'xlabel':
            return series[attr] if attr in series else ''
        elif attr == 'ylabel':
            return series[attr] if attr in series else ''
    
    def groups(self) -> list:
        groups = []
        for series in self.dataSeries:
            group = self._seriesAttr(series, 'group')
            if group not in groups:
                groups.append(group)
        return groups
    
    def _groupedSeriesIndexes(self, groups=None) -> dict:
        if groups is None:
            groups = self.groups()
        allSeriesGroups = np.array([
            self._seriesAttr(series, 'group')
            for series in self.dataSeries
            ])
        groupedSeriesIndexes = {}
        for group in groups:
            groupedSeriesIndexes[group] = np.where(allSeriesGroups == group)[0]
        return groupedSeriesIndexes
    
    def _withinGroupSweepIndex(self, seriesIndex: int) -> int:
        seriesGroup = self._seriesAttr(self.dataSeries[seriesIndex], 'group')
        groupedSeriesIndexes = self._groupedSeriesIndexes([seriesGroup])
        return np.where(groupedSeriesIndexes[seriesGroup] == seriesIndex)[0][0]
    
    def visibleGroups(self) -> list:
        groups = self.groups()
        visibleGroupIndexes = [index.row() for index in self._visibleGroupsListWidget.selectedIndexes()]
        visibleGroups = [groups[i] for i in visibleGroupIndexes if i < len(groups)]
        if len(visibleGroups) == 0:
            visibleGroups = groups
        return visibleGroups
    
    def setVisibleGroups(self, visibleGroups):
        groups = self.groups()
        self._visibleGroupsListWidget.itemSelectionChanged.disconnect()
        self._visibleGroupsListWidget.clear()
        self._visibleGroupsListWidget.addItems([str(group) for group in groups])
        for group in visibleGroups:
            if group in groups:
                self._visibleGroupsListWidget.item(groups.index(group)).setSelected(True)
        self._visibleGroupsListWidget.itemSelectionChanged.connect(self._onVisibleGroupsChanged)
        self._onVisibleGroupsChanged()
    
    def _updateVisibleGroupsListView(self):
        visibleGroupIndexes = [index.row() for index in self._visibleGroupsListWidget.selectedIndexes()]
        self._visibleGroupsListWidget.itemSelectionChanged.disconnect()
        self._visibleGroupsListWidget.clear()
        self._visibleGroupsListWidget.addItems([str(group) for group in self.groups()])
        for i in visibleGroupIndexes:
            if i < len(self.groups()):
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
        return [self._groupPlotsVBoxLayout.itemAt(i).widget() for i in range(self._groupPlotsVBoxLayout.count())]
    
    def visibleSweepIndexes(self) -> list:
        if self.numSeries() == 0:
            return []
        numSweepsMax = self._numVisibleSweepsMax()
        visibleSweepsText = self._visibleSweepsIndexEdit.text().strip()
        if visibleSweepsText == '':
            return list(range(numSweepsMax))
        visibleSweepsFields = re.split('[,\s]+', visibleSweepsText)
        indexes = []
        for field in visibleSweepsFields:
            if field == '':
                continue
            if ':' in field:
                sliceArgs = [int(arg) if len(arg.strip()) else None for arg in field.split(':')]
                sliceObj = slice(*sliceArgs)
                sliceIndexes = list(range(*sliceObj.indices(numSweepsMax)))
                indexes.extend(sliceIndexes)
            elif '-' in field:
                start, end = field.split('-')
                indexes.extend(list(range(int(start), int(end)+1)))
            else:
                indexes.append(int(field))
        indexes = np.unique(indexes)
        indexes = indexes[indexes >= 0]
        return list(indexes)
    
    def setVisibleSweepIndexes(self, sweepIndexes):
        self._visibleSweepsIndexEdit.setText(' '.join([str(i) for i in sweepIndexes]))
        self.updatePlots()
    
    def nextSweep(self):
        indexes = self.visibleSweepIndexes()
        if len(indexes) == 0:
            nextIndex = 0
        else:
            nextIndex = min(indexes[-1] + 1, self._numVisibleSweepsMax() - 1)
        self.setVisibleSweepIndexes([nextIndex])
    
    def prevSweep(self):
        indexes = self.visibleSweepIndexes()
        if len(indexes) == 0:
            prevIndex = self._numVisibleSweepsMax() - 1
        else:
            prevIndex = max(0, indexes[0] - 1)
        self.setVisibleSweepIndexes([prevIndex])
    
    def _numVisibleSweepsMax(self) -> int:
        visibleGroupSeriesIndexes = self._groupedSeriesIndexes(self.visibleGroups())
        return np.max([len(indexes) for indexes in visibleGroupSeriesIndexes.values()])

    def updatePlots(self):
        # one plot per group, arranged vertically
        groups = self.groups()
        n_groups = len(groups)
        visibleGroups = self.visibleGroups()
        groupedSeriesIndexes = self._groupedSeriesIndexes()
        visibleSweepIndexes = self.visibleSweepIndexes()
        for i, group in enumerate(groups):
            if self._groupPlotsVBoxLayout.count() > i:
                # use existing plot
                plot = self._groupPlotsVBoxLayout.itemAt(i).widget()
            else:
                # append new plot
                plot = self.newPlot()
                self._groupPlotsVBoxLayout.addWidget(plot, stretch=1)
            
            # get data for this group
            dataItems = plot.listDataItems()
            colormap = self.styles['lines']['colormap']
            seriesIndexes = [groupedSeriesIndexes[group][i] for i in visibleSweepIndexes if i < len(groupedSeriesIndexes[group])]
            for j, index in enumerate(seriesIndexes):
                # data to plot
                series = self.dataSeries[index]
                x = self._seriesAttr(series, 'x')
                y = series['y']
                xlabel = self._seriesAttr(series, 'xlabel')
                ylabel = self._seriesAttr(series, 'ylabel')
                color = colormap[j % len(colormap)]
                lineWidth = self.styles['lines']['width']
                linePen = pg.mkPen(color, width=lineWidth)
                
                if len(dataItems) > j:
                    # update existing plot data
                    dataItems[j].setData(x, y)
                    dataItems[j].setPen(linePen)
                else:
                    # add new plot data
                    plot.plot(x, y, pen=linePen)
                
                # axis labels
                plot.getAxis('bottom').setLabel(xlabel)
                if j == 0:
                    plot.getAxis('left').setLabel(ylabel)
                
                # show/hide plot
                if group in visibleGroups:
                    plot.show()
                else:
                    plot.hide()
            
            # remove extra plot items
            dataItems = plot.listDataItems()
            for j in range(len(seriesIndexes), len(dataItems)):
                plot.removeItem(dataItems[j])
                dataItems[j].deleteLater()
        
        # remove extra plots
        while self._groupPlotsVBoxLayout.count() > n_groups:
            self._groupPlotsVBoxLayout.takeAt(n_groups).deleteLater()
        
        # link x-axis
        if self._groupPlotsVBoxLayout.count() > 0:
            firstItem = self._groupPlotsVBoxLayout.itemAt(0)
            firstPlot = self._groupPlotsVBoxLayout.itemAt(0).widget()
            for i in range(1, self._groupPlotsVBoxLayout.count()):
                plot = self._groupPlotsVBoxLayout.itemAt(i).widget()
                plot.setXLink(firstPlot)
    
    def updateUI(self):
        # update plots
        self.updatePlots()
        
        # show/hide group plots
        self._updateVisibleGroupsListView()
        self._onVisibleGroupsChanged()

        # visible group selection controls
        if len(self.groups()) > 1:
            self._visibleGroupsButtonAction.setVisible(True)
        else:
            self._visibleGroupsButtonAction.setVisible(False)
        
        # series traversal controls
        if self._numVisibleSweepsMax() > 1:
            self._seriesIndexEditAction.setVisible(True)
            self._prevSeriesButtonAction.setVisible(True)
            self._nextSeriesButtonAction.setVisible(True)
        else:
            self._seriesIndexEditAction.setVisible(False)
            self._prevSeriesButtonAction.setVisible(False)
            self._nextSeriesButtonAction.setVisible(False)
    
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


if __name__ == '__main__':
    # Create the application
    app = QApplication(sys.argv)

    # style theme
    app.setStyle('Fusion') 

    # Create widget
    widget = QtTimeSeriesAnalyzer()

    # testing
    widget.addSeries(x=np.arange(100), y=np.random.random(100), xlabel="Time, s", ylabel="Current, pA", group="Current")
    widget.addSeries(x=np.arange(100), y=np.random.random(100), xlabel="Time, s", ylabel="Voltage, mV", group="Voltage")
    widget.addSeries(x=np.arange(100), y=np.random.random(100), xlabel="Time, s", ylabel="Current, pA", group="Current")
    widget.addSeries(x=np.arange(100), y=np.random.random(100), xlabel="Time, s", ylabel="Voltage, mV", group="Voltage")

    # Show widget and run application
    widget.show()
    exitStatus = app.exec()
    sys.exit(exitStatus)