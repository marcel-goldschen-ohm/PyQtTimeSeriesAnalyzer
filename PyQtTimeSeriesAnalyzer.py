"""
PyQtTimeSeriesAnalyzer.py

Very much still a work in progress.

TODO:
- reimplement measurements in ViewBox
- reimplement curve fitting in ViewBox
- fix delete series group error ???
- zero, interpolate, mask
- link ROIs across plots
- edit x, y data in new popup table view
- add series, attr via table view
- hidden series (or just episodes)?
- series tags, tag filter
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


class QtTimeSeriesAnalyzer(QWidget):
    """ Viewer/Analyzer for a collection of time (ar any x,y) series. """

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)

        self.data = []

        self.initUI()
        self.updateUI()
    
    def sizeHint(self):
        return QSize(800, 600)
    
    def clear(self):
        self.data = []
        self.updateUI()
    
    def save(self, filepath=None):
        if filepath is None:
            filepath, _ = QFileDialog.getSaveFileName(self, "Save Data", "", "MATLAB Data Files (*.mat)")
        if not filepath:
            return
        savemat(filepath, {"data": self.data})

    def open(self, filepath=None, clear=True):
        if filepath is None:
            filepath, _ = QFileDialog.getOpenFileName(self, "Open Data", "", "MATLAB Data Files (*.mat)")
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
                    try:
                        N = len(series['y'])
                    except:
                        if isinstance(series['y'], int) or isinstance(series['y'], float):
                            N = 1
                        else:
                            N = 0
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
            # elif attr == 'style':
            #     value = {}
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
    
    def visibleEpisodes(self) -> list:
        episodes = self.seriesEpisodes()
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
        episodes = self.seriesEpisodes()
        if not episodes:
            self._visibleEpisodesEdit.setText('')
            self._updateGroupPlots()
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
        self._updateGroupPlots()
    
    def visibleGroups(self) -> list:
        groups = self.seriesGroups()
        if not groups:
            return []
        visibleGroupIndexes = [index.row() for index in self._visibleGroupsListWidget.selectedIndexes()]
        visibleGroups = [groups[i] for i in visibleGroupIndexes if i < len(groups)]
        return visibleGroups if visibleGroups else groups
    
    def setVisibleGroups(self, visibleGroups: list):
        self._updateVisibleGroupsListView()
        groups = self.seriesGroups()
        listWidget = self._visibleGroupsListWidget
        listWidget.itemSelectionChanged.disconnect()
        for item in listWidget.items():
            item.setSelected(False)
        for group in visibleGroups:
            if group in groups:
                listWidget.item(groups.index(group)).setSelected(True)
        listWidget.itemSelectionChanged.connect(self._onVisibleGroupsChanged)
        self._onVisibleGroupsChanged()
    
    def visibleNames(self) -> list:
        names = self.seriesNames()
        if not names:
            return []
        selectedIndexes = [index.row() for index in self._visibleNamesListWidget.selectedIndexes()]
        visibleNames = [names[i] for i in selectedIndexes if i < len(names)]
        return visibleNames if visibleNames else names
    
    def setVisibleNames(self, visibleNames: list):
        self._updateVisibleNamesListView()
        names = self.seriesNames()
        listWidget = self._visibleNamesListWidget
        listWidget.itemSelectionChanged.disconnect()
        for item in listWidget.items():
            item.setSelected(False)
        for name in visibleNames:
            if name in names:
                listWidget.item(names.index(name)).setSelected(True)
        listWidget.itemSelectionChanged.connect(self._onVisibleNamesChanged)
        self._onVisibleNamesChanged()
    
    def initUI(self):
        # episode traversal
        self._visibleEpisodesEdit = QLineEdit("0")
        self._visibleEpisodesEdit.setMinimumWidth(64)
        self._visibleEpisodesEdit.setMaximumWidth(128)
        self._visibleEpisodesEdit.setToolTip("Visible Episodes")
        self._visibleEpisodesEdit.textEdited.connect(self._updateGroupPlots)

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

        # data table model/view
        self._dataTableModel = None
        self._dataTableView = None

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
        self._fileMenu.addAction("Import HEKA", self.importHEKA)
        self._fileMenu.addSection(" ")
        self._fileMenu.addAction("&Save", self.save)

        self._groupsMenu = QMenu("Groups")
        action = QWidgetAction(self._groupsMenu)
        action.setDefaultWidget(self._visibleGroupsListWidget)
        self._groupsMenu.addAction(action)

        self._namesMenu = QMenu("Names")
        action = QWidgetAction(self._namesMenu)
        action.setDefaultWidget(self._visibleNamesListWidget)
        self._namesMenu.addAction(action)

        self._mainMenu = QMenu()
        self._mainMenu.addMenu(self._fileMenu)
        self._mainMenu.addSection(" ")
        self._mainMenu.addMenu(self._groupsMenu)
        self._mainMenu.addMenu(self._namesMenu)
        self._mainMenu.addSection(" ")
        action = self._makeAction(self._mainMenu, "Data Table", self.showDataTable, "fa.table")
        self._mainMenu.addAction(action)
        if self._console is not None:
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

        # top toolbar
        self._toolbar = QToolBar()
        self._mainMenuButtonAction = self._toolbar.addWidget(self._mainMenuButton)
        self._visibleEpisodesEditAction = self._toolbar.addWidget(self._visibleEpisodesEdit)
        self._prevEpisodeButtonAction = self._toolbar.addWidget(self._prevEpisodeButton)
        self._nextEpisodeButtonAction = self._toolbar.addWidget(self._nextEpisodeButton)
        
        # plots layout
        self._groupPlotsLayout = QVBoxLayout()
        self._groupPlotsLayout.setContentsMargins(0, 0, 0, 0)
        self._groupPlotsLayout.setSpacing(0)

        # main layout
        self._mainLayout = QVBoxLayout(self)
        self._mainLayout.setContentsMargins(3, 3, 3, 3)
        self._mainLayout.setSpacing(0)
        self._mainLayout.addWidget(self._toolbar)
        self._mainLayout.addLayout(self._groupPlotsLayout)
    
    def updateUI(self):
        # update visible groups and names
        self._updateVisibleGroupsListView()
        self._updateVisibleNamesListView()

        # update plots
        self._updateGroupPlots()

        # update toolbar
        showEpisodeControls = len(self.seriesEpisodes()) > 1
        self._visibleEpisodesEditAction.setVisible(showEpisodeControls)
        self._prevEpisodeButtonAction.setVisible(showEpisodeControls)
        self._nextEpisodeButtonAction.setVisible(showEpisodeControls)

        # update table model/view
        if self._dataTableView is not None and self._dataTableView.isVisible():
            self.showDataTable()
    
    def _updateGroupPlots(self):
        visibleEpisodes = self.visibleEpisodes()
        visibleGroups = self.visibleGroups()
        visibleNames = self.visibleNames()
        groups = self.seriesGroups()
        plots = self.groupPlots()

        for i, group in enumerate(groups):
            # group plot
            if len(plots) > i:
                plot = plots[i]
            else:
                plot = PlotWidget()
                self._groupPlotsLayout.addWidget(plot, stretch=1)
                plots.append(plot)
            
            # plot series
            indexes = self.seriesIndexes(groups=[group], episodes=visibleEpisodes, names=visibleNames)
            plotDataItems = [item for item in plot.listDataItems() if isinstance(item, PlotDataItem)]
            textItems = [item for item in plot.getViewBox().allChildren() if isinstance(item, TextItem)]
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
                    plotDataItem = PlotDataItem(x, y)
                    plot.addItem(plotDataItem)
                    plotDataItems.append(plotDataItem)
                plotDataItem.seriesDict = series
                
                # style
                style = self.seriesAttr('style', series)
                if style is None:
                    style = {}
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
                            textItem = TextItem()
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
        plots = [widget for widget in widgets if isinstance(widget, PlotWidget)]
        return plots
    
    def nextEpisode(self):
        episodes = self.seriesEpisodes()
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
        episodes = self.seriesEpisodes()
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
    
    def _updateVisibleGroupsListView(self):
        groups = self.seriesGroups()
        groupNames = self.groupNames()
        listWidget = self._visibleGroupsListWidget
        selectedIndexes = [index.row() for index in listWidget.selectedIndexes()]
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
        for i in selectedIndexes:
            if i < len(groups):
                listWidget.item(i).setSelected(True)
        listWidget.itemSelectionChanged.connect(self._onVisibleGroupsChanged)
    
    def _onVisibleGroupsChanged(self):
        groups = self.seriesGroups()
        visibleGroups = self.visibleGroups()
        for i, plot in enumerate(self.groupPlots()):
            if i < len(groups) and groups[i] in visibleGroups:
                plot.show()
            else:
                plot.hide()

    def _updateVisibleNamesListView(self):
        names = self.seriesNames()
        listWidget = self._visibleNamesListWidget
        selectedIndexes = [index.row() for index in listWidget.selectedIndexes()]
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
        for i in selectedIndexes:
            if i < len(names):
                listWidget.item(i).setSelected(True)
        listWidget.itemSelectionChanged.connect(self._onVisibleNamesChanged)
    
    def _onVisibleNamesChanged(self):
        self._updateGroupPlots()
    
    def showDataTable(self):
        if self._dataTableModel is not None:
            self._dataTableModel.deleteLater()
        self._dataTableModel = DataTableModel(self)

        if self._dataTableView is None:
            self._dataTableView = QTableView()
        self._dataTableView.setModel(self._dataTableModel)
        self._dataTableView.show()
        self._dataTableView.resizeColumnsToContents()
    
    def showCosole(self):
        if self._console is None:
            return
        self._console.show()
    
    def _makeAction(self, parent, text, func, qta_icon=None) -> QAction:
        action = QAction(parent)
        action.setText(text)
        if qta_icon is not None and qta is not None:
            icon = qta.icon(qta_icon)
            action.setIcon(icon)
        action.triggered.connect(func)
        return action
    

class PlotWidget(pg.PlotWidget):
    """ pg.PlotWidget with custom view box. """

    def __init__(self,  *args, **kwargs):
        kwargs['viewBox'] = ViewBox()
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


class ViewBox(pg.ViewBox):
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
                    self._roi = LinearRegionItem(orientation=self._roiOrientation, values=limits)
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
            if isinstance(item, LinearRegionItem):
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
            if isinstance(item, LinearRegionItem):
                item.setVisible(False)
    
    def showROIs(self):
        for item in self.allChildren():
            if isinstance(item, LinearRegionItem):
                item.setVisible(True)
    
    def deleteROIs(self):
        for item in self.allChildren():
            if isinstance(item, LinearRegionItem):
                self.removeItem(item)
                item.deleteLater()


class PlotDataItem(pg.PlotDataItem):
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
        textItem = TextItem()
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


class LinearRegionItem(pg.LinearRegionItem):
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


class TextItem(pg.TextItem):
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
                value = self._tsa.seriesAttr(attr, seriesIndex)
            else:
                value = None
            if value is None:
                if attr == 'style':
                    return '{}'
                elif attr == 'labels':
                    return '[]'
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
                elif isinstance(value, int) or isinstance(value, float):
                    pass
                else:
                    return False
                applyChange = QMessageBox.question(self._tsa, 'Confirm', 'Are you sure you want to change the series data?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if applyChange == QMessageBox.No:
                    return False
                if isinstance(value, np.ndarray) and isinstance(self._data[seriesIndex][attr], np.ndarray):
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
    tsa = QtTimeSeriesAnalyzer()

    # testing
    # tsa.importHEKA('heka.dat')
    tsa.data = []
    tsa.addSeries(y=np.random.random(10), xlabel="Time, s", ylabel="Current, pA", group=0, labels=[{'text': 'testing 1', 'x': 3, 'y': 0.5}])
    tsa.addSeries(y=np.random.random(10) * 1000, xlabel="Time, s", ylabel="Voltage, mV", group=1)
    tsa.addSeries(y=np.random.random(10), xlabel="Time, s", ylabel="Current, pA", group=0, labels=[{'text': 'testing 2', 'x': 6, 'y': 0.5}])
    tsa.addSeries(y=np.random.random(10) * 1000, xlabel="Time, s", ylabel="Voltage, mV", group=1)
    tsa.addSeries(y=np.random.random(10), xlabel="Time, s", ylabel="Current, pA", group=0, episode=1, name='fit')
    tsa.updateUI()

    # tsa.open()


    # Show widget and run application
    tsa.show()
    status = app.exec()
    sys.exit(status)