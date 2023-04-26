"""
PyQtTimeSeriesAnalyzer.py

Very much still a work in progress.

TODO:
- edit plot styles
- zero, interpolate, mask
- series math
- ROI measurements
- hidden series (or just episodes)?
- series tags
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
        self.ROIs = []

        # ROI context menu
        self._roiMenu = QMenu("ROI")
        self._roiMenu.addAction("Add X axis ROI", lambda: self.addROI(orientation="vertical"))
        self._roiMenu.addAction("Add Y axis ROI", lambda: self.addROI(orientation="horizontal"))
        self._roiMenu.addSeparator()
        self._roiMenu.addAction("Show ROIs", self.showROIs)
        self._roiMenu.addAction("Hide ROIs", self.hideROIs)
        self._roiMenu.addSeparator()
        self._roiMenu.addAction("Remove Last ROI", self.removeLastROI)
        self._roiMenu.addAction("Clear ROIs", self.clearROIs)

        # Curve fit context menu
        self._fitMenu = QMenu("Curve Fit")
        self._fitMenu.addAction("Mean", lambda: self.curveFit(fitType="mean", restrictOptimizationToROIs=True, restrictOutputToROIs=False))
        self._fitMenu.addAction("Line", lambda: self.curveFit(fitType="line", restrictOptimizationToROIs=True, restrictOutputToROIs=False))
        self._fitMenu.addAction("Polynomial", lambda: self.curveFit(fitType="polynomial", restrictOptimizationToROIs=True, restrictOutputToROIs=False))
        self._fitMenu.addAction("Spline", lambda: self.curveFit(fitType="spline", restrictOptimizationToROIs=True, restrictOutputToROIs=False))
        self._fitMenu.addAction("Custom", lambda: self.curveFit(fitType="custom", restrictOptimizationToROIs=True, restrictOutputToROIs=False))

        # Context menu (added on to default context menu)
        self._customMenuBeginningSeparatorAction = self.menu.addSeparator()
        self.menu.addMenu(self._roiMenu)
        self.menu.addMenu(self._fitMenu)
        self._customMenuEndingSeparatorAction = self.menu.addSeparator()
    
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
    
    def removeLastROI(self):
        if self.ROIs:
            roi = self.ROIs.pop()
            self.removeItem(roi)
            roi.deleteLater()
    
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
    
    def curveFit(self, curveDataItems=None, fitType="mean", fitParams=None, 
                restrictOptimizationToROIs=True, outputXValues=None, restrictOutputToROIs=False):
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
        fits = []
        if curveDataItems is None:
            curveDataItems = self.listDataItems()
        elif not isinstance(curveDataItems, list):
            curveDataItems = [curveDataItems]
        for dataItem in curveDataItems:
            seriesIndex = dataItem.seriesIndex
            data = self.tsa.data[seriesIndex]
            x = self.tsa._seriesAttr(seriesIndex, 'x')
            y = self.tsa._seriesAttr(seriesIndex, 'y')
            
            # optimize fit based on (fx, fy)
            if restrictOptimizationToROIs and len(self.ROIs):
                inROIs = np.zeros(len(x), dtype=bool)
                for roi in self.ROIs:
                    roiXMin, roiXMax = roi.getRegion()
                    inROIs = inROIs | ((x >= roiXMin) & (x <= roiXMax))
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
                tck = sp.interpolate.splrep(fx, fy, s=fitParams['smoothing'])
                yfit = sp.interpolate.splev(xfit, tck, der=0)
            elif fitType == "custom":
                pass

            # fit series data
            fit = {'x': xfit, 'y': yfit}
            for key in ['xlabel', 'ylabel', 'episode', 'group']:
                fit[key] = self.tsa._seriesAttr(seriesIndex, key)
            fits.append(fit)

            # add fit to plot
            fitItem = CustomPlotDataItem(x=xfit, y=yfit, pen=pg.mkPen(color=(255, 0, 0), width=3))
            self.plotWidget.addItem(fitItem)
        
        # keep fits?
        if not fits:
            return
        keepFits = QMessageBox.question(self.parentWidget().parentWidget(), "Keep Fits?", "Keep fits?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if keepFits == QMessageBox.No:
            self.tsa.updateUI()
            return

        # name fits
        fitName, ok = QInputDialog.getText(self.parentWidget().parentWidget(), "Fit Name", "Fit name:", text=fitType)
        if not ok:
            self.tsa.updateUI()
            return
        fitName = fitName.strip()
        for i in range(len(fits)):
            fits[i]['name'] = fitName
        
        # overwrite existing (episode,group,name) series?
        fitNameAlreadyExists = False
        for fit in fits:
            seriesIndexes = self.tsa._seriesIndexes(episodes=[fit['episode']], groups=[fit['group']])
            names = self.tsa.names(seriesIndexes)
            if fit['name'] in names:
                fitNameAlreadyExists = True
                break
        if fitNameAlreadyExists:
            overwrite = QMessageBox.question(self.parentWidget().parentWidget(), "Overwrite?", "Overwrite existing series with same name?", QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Cancel)
            if overwrite == QMessageBox.Cancel:
                self.tsa.updateUI()
                return
        else:
            overwrite = QMessageBox.No
        
        # store fits
        if overwrite == QMessageBox.Yes:
            for fit in fits:
                seriesIndexes = self.tsa._seriesIndexes(episodes=[fit['episode']], groups=[fit['group']], names=[fit['name']])
                self.tsa.data[seriesIndexes[-1]] = fit
        elif overwrite == QMessageBox.No:
            self.tsa.data.extend(fits)
        
        # make sure fits are visible
        visibleNames = self.tsa.visibleNames()
        for fit in fits:
            if fit['name'] not in visibleNames:
                visibleNames.append(fit['name'])
        self.tsa.setVisibleNames(visibleNames)

        # update UI
        self.tsa.updateUI()


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
        if self.menu is None:
            # defer menu creation until needed
            self.menu = QMenu()

            viewBox = self.parentWidget()
            tsa = viewBox.tsa
            name = tsa._seriesAttr(self.seriesIndex, 'name')
            if name is None or name == "":
                name = f"Series {self.seriesIndex}"
            self._contextMenu = QMenu(name)

            # self._baselineMenu = QMenu("Baseline")
            # self._baselineMenu.addAction("Mean", lambda: viewBox.curveFit(self, fitType="mean", fitBaseline=True))
            # self._baselineMenu.addAction("Line", lambda: viewBox.curveFit(self, fitType="line", fitBaseline=True))
            # self._baselineMenu.addAction("Polynomial", lambda: viewBox.curveFit(self, fitType="polynomial", fitBaseline=True))
            # self._baselineMenu.addAction("Spline", lambda: viewBox.curveFit(self, fitType="spline", fitBaseline=True))
            # self._baselineMenu.addAction("Custom", lambda: viewBox.curveFit(self, fitType="custom", fitBaseline=True))
            # self._baselineMenu.addSeparator()
            # self._baselineMenu.addAction("Clear")
            # self._contextMenu.addMenu(self._baselineMenu)

            self.menu.addMenu(self._contextMenu)
            self.menu.addSeparator()

        return self.menu


class QtTimeSeriesAnalyzer(QWidget):
    def __init__(self):
        QWidget.__init__(self)

        # list of data series dictionaries
        self.data = []

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
        self._visibleGroupsButton.setText("Groups")  # u"\U0001F441"
        self._visibleGroupsButton.setToolTip("Visible groups")
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
        self._visibleNamesButton.setToolTip("Visible names")
        self._visibleNamesButton.setPopupMode(QToolButton.InstantPopup)
        self._visibleNamesButton.setMenu(QMenu(self._visibleNamesButton))
        action = QWidgetAction(self._visibleNamesButton)
        action.setDefaultWidget(self._visibleNamesListWidget)
        self._visibleNamesButton.menu().addAction(action)

        # episode traversal
        self._visibleEpisodesEdit = QLineEdit()
        self._visibleEpisodesEdit.setMinimumWidth(64)
        self._visibleEpisodesEdit.setMaximumWidth(128)
        self._visibleEpisodesEdit.setToolTip("Visible episodes")
        self._visibleEpisodesEdit.textEdited.connect(self.updatePlots)

        self._prevEpisodeButton = QPushButton("<")
        self._prevEpisodeButton.setMaximumWidth(32)
        self._prevEpisodeButton.setToolTip("Previous episode")
        self._prevEpisodeButton.clicked.connect(self.prevEpisode)

        self._nextEpisodeButton = QPushButton(">")
        self._nextEpisodeButton.setMaximumWidth(32)
        self._nextEpisodeButton.setToolTip("Next episode")
        self._nextEpisodeButton.clicked.connect(self.nextEpisode)

        # data table model/view
        self._tableModel = None
        self._tableView = None
        self._tableModelViewButton = QToolButton()
        self._tableModelViewButton.setText("Table")
        self._tableModelViewButton.setToolTip("Data table")
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

        # tags

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
        # self._showBaselineButtonAction = self._topToolbar.addWidget(self._showBaselineButton)
        # self._applyBaselineButtonAction = self._topToolbar.addWidget(self._applyBaselineButton)
        # self._applyScaleButtonAction = self._topToolbar.addWidget(self._applyScaleButton)
        self._mainGridLayout.addWidget(self._topToolbar, 0, 0)

        self._groupPlotsVBoxLayout = QVBoxLayout()
        self._groupPlotsVBoxLayout.setContentsMargins(3, 3, 3, 3)
        self._groupPlotsVBoxLayout.setSpacing(3)
        self._mainGridLayout.addLayout(self._groupPlotsVBoxLayout, 1, 0)
    
    def numSeries(self) -> int:
        return len(self.data)
    
    def addSeries(self, **kwargs):
        seriesDict = kwargs
        self.data.append(seriesDict)
        self.updateUI()
    
    def addListOfSeries(self, listOfSeriesDicts: list):
        self.data.extend(listOfSeriesDicts)
        self.updateUI()
    
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
            
            # get data for this group
            dataItems = plot.listCustomDataItems()
            colormap = self.styles['lines']['colormap']
            seriesIndexes = self._seriesIndexes(groups=[group], episodes=visibleEpisodes, names=visibleNames)
            for j, index in enumerate(seriesIndexes):
                # data to plot
                series = self.data[index]
                x = self._seriesAttr(index, 'x')
                y = self._seriesAttr(index, 'y')
                color = colormap[j % len(colormap)]
                lineWidth = self.styles['lines']['width']
                linePen = pg.mkPen(color, width=lineWidth)
                
                if len(dataItems) > j:
                    # update existing plot data
                    dataItems[j].setData(x, y)
                    dataItems[j].setPen(linePen)
                    dataItems[j].seriesIndex = index
                else:
                    # add new plot data
                    # dataItem = plot.plot(x, y, pen=linePen)
                    dataItem = CustomPlotDataItem(x, y, pen=linePen)
                    dataItem.seriesIndex = index
                    plot.addItem(dataItem)
                
                # axis labels (based on first plot)
                if j == 0:
                    xlabel = self._seriesAttr(index, 'xlabel')
                    ylabel = self._seriesAttr(index, 'ylabel')
                    plot.getAxis('bottom').setLabel(xlabel)
                    plot.getAxis('left').setLabel(ylabel)
                
                # show/hide plot
                if group in visibleGroups:
                    plot.show()
                else:
                    plot.hide()
            
            # remove extra plot items
            dataItems = plot.listCustomDataItems()
            while len(dataItems) > len(seriesIndexes):
                dataItem = dataItems.pop()
                plot.removeItem(dataItem)
                dataItem.deleteLater()
        
        # remove extra plots
        while self._groupPlotsVBoxLayout.count() > len(groups):
            self._groupPlotsVBoxLayout.takeAt(len(groups) - 1).deleteLater()
        
        # link x-axis
        if self._groupPlotsVBoxLayout.count() > 1:
            firstPlot = self._groupPlotsVBoxLayout.itemAt(0).widget()
            for i in range(1, self._groupPlotsVBoxLayout.count()):
                plot = self._groupPlotsVBoxLayout.itemAt(i).widget()
                plot.setXLink(firstPlot)
    
    def updateUI(self):
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


class DataTableModel(QAbstractTableModel):
    def __init__(self, tsa):
        QAbstractTableModel.__init__(self)
        self._tsa = tsa
        self._data = tsa.data
        self._requiredColumns = ['episode', 'group', 'name', 'x', 'y', 'xlabel', 'ylabel']
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
                    elif len(values) == 1:
                        value = values[0]
                    else:
                        value = np.array(values)
                elif not (isinstance(value, int) or isinstance(value, float)):
                    return False
                applyChange = QMessageBox.question(self._tsa, 'Confirm', 'Are you sure you want to change the series data?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if applyChange == QMessageBox.No:
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


if __name__ == '__main__':
    # Create the application
    app = QApplication(sys.argv)

    # style theme
    app.setStyle('Fusion')

    # Create widget
    widget = QtTimeSeriesAnalyzer()

    # testing
    for i in range(10):
        widget.addSeries(y=np.random.random(10000), xlabel="Time, s", ylabel="Current, pA", group="I", episode=2*i, test=None)
        widget.addSeries(y=np.random.random(10000), xlabel="Time, s", ylabel="Voltage, mV", group="V", episode=2*i)

    # Show widget and run application
    widget.show()
    exitStatus = app.exec()
    sys.exit(exitStatus)