# -*- coding: utf-8 -*-
#-----------------------------------------------------------

# Import the PyQt and the QGIS libraries
from __future__ import absolute_import
from builtins import object
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtGui import *
from qgis.core import *
from qgis.gui import *

#Import own classes and tools
from .beziereditingtool import BezierEditingTool
from .featureselectiontool import FeatureSelectionTool
from .splitpolygontool import SplitPolygonTool
from .splitlinetool import SplitLineTool

# initialize Qt resources from file resources.py
from . import resources


class BezierEditing2(object):

    def __init__(self, iface):
      # Save reference to the QGIS interface
        self.iface = iface
        self.canvas = self.iface.mapCanvas()
        self.active = False

    def initGui(self):
        settings = QSettings()
        # create toolbar for this plugin
        self.toolbar = self.iface.addToolBar("BezierEditing")


        # Get the tool
        self.beziertool = BezierEditingTool(self.canvas,self.iface)
        self.featureselectiontool = FeatureSelectionTool(self.canvas, self.iface)
        self.polygonsplittool = SplitPolygonTool(self.canvas, self.iface)
        self.linesplittool = SplitLineTool(self.canvas, self.iface)

        # Create bezier action
        self.bezier_edit = QAction(QIcon(":/plugins/bezierEditing2/icon/beziericon.svg"),"Bezier_editing", self.iface.mainWindow())
        self.bezier_edit.setObjectName("BezierEditing_bezier_edit")
        self.bezier_edit.setEnabled(False)
        self.bezier_edit.setCheckable(True)
        self.bezier_edit.triggered.connect(self.bezierediting)
        self.toolbar.addAction(self.bezier_edit)

        # Create pen action
        self.pen_edit = QAction(QIcon(":/plugins/bezierEditing2/icon/penicon.svg"),"Bezier_Freehand editing", self.iface.mainWindow())
        self.pen_edit.setObjectName("BezierEditing_pen_edit")
        self.pen_edit.setEnabled(False)
        self.pen_edit.setCheckable(True)
        self.pen_edit.triggered.connect(self.penediting)
        self.toolbar.addAction(self.pen_edit)

        # Create show anchor option
        self.anchor_on = QAction(QIcon(":/plugins/bezierEditing2/icon/anchoronicon.svg"),"Bezier_Show Anchor", self.iface.mainWindow())
        self.anchor_on.setObjectName("BezierEditing_anchor_on")
        self.anchor_on.setCheckable(True)
        self.anchor_on.setEnabled(False)
        self.anchor_on.toggled.connect(self.anchoron)
        self.toolbar.addAction(self.anchor_on)

        # Create undo option
        self.undo = QAction(QIcon(":/plugins/bezierEditing2/icon/undoicon.svg"),"Bezier_Undo", self.iface.mainWindow())
        self.undo.setObjectName("BezierEditing_undo")
        self.undo.setEnabled(False)
        self.undo.triggered.connect(self.beziertool.undo)
        self.toolbar.addAction(self.undo)

        # Create selection action
        self.feature_selection = QAction(QIcon(":/plugins/bezierEditing2/icon/featureselectionicon.svg"),"Bezier_Selection", self.iface.mainWindow())
        self.feature_selection.setObjectName("BezierEditing_feature_selection")
        self.feature_selection.setEnabled(False)
        self.feature_selection.setCheckable(True)
        self.feature_selection.triggered.connect(self.featureselection)
        self.toolbar.addAction(self.feature_selection)

        # Create polygon split action
        self.polygon_split = QAction(QIcon(":/plugins/bezierEditing2/icon/polygonspliticon.svg"),"Bezier_Polygon split", self.iface.mainWindow())
        self.polygon_split.setObjectName("BezierEditing_polygon_split")
        self.polygon_split.setEnabled(False)
        self.polygon_split.setCheckable(True)
        self.polygon_split.triggered.connect(self.polygonsplit)
        self.toolbar.addAction(self.polygon_split)

        # Create line split action
        self.line_split = QAction(QIcon(":/plugins/bezierEditing2/icon/linespliticon.svg"),"Bezier_Line Select and Split", self.iface.mainWindow())
        self.line_split.setObjectName("BezierEditing_line_split")
        self.line_split.setEnabled(False)
        self.line_split.setCheckable(True)
        self.line_split.triggered.connect(self.linesplit)
        self.toolbar.addAction(self.line_split)


        # Connect to signals for button behaviour
        self.iface.layerTreeView().currentLayerChanged.connect(self.toggle)
        self.canvas.mapToolSet.connect(self.deactivate)


    def bezierediting(self):
        self.canvas.setMapTool(self.beziertool)
        self.bezier_edit.setChecked(True)
        self.beziertool.mode = "bezier"

    def penediting(self):
        self.canvas.setMapTool(self.beziertool)
        self.pen_edit.setChecked(True)
        self.beziertool.mode = "pen"

    def featureselection(self):
        self.canvas.setMapTool(self.featureselectiontool)
        self.feature_selection.setChecked(True)

    def polygonsplit(self):
        self.canvas.setMapTool(self.polygonsplittool)
        self.polygon_split.setChecked(True)

    def linesplit(self):
        self.canvas.setMapTool(self.linesplittool)
        self.line_split.setChecked(True)

    def anchoron(self,checked):
        if checked:
            self.beziertool.showBezierMarker()
        else:
            self.beziertool.hideBezierMarker()


    def toggle(self):
        mc = self.canvas
        layer = mc.currentLayer()
        if layer is None:
            return

        #Decide whether the plugin button/menu is enabled or disabled
        if layer.isEditable() and layer.type() == QgsMapLayer.VectorLayer:
            ### add for tool
            self.bezier_edit.setEnabled(True)
            self.pen_edit.setEnabled(True)
            self.feature_selection.setEnabled(True)
            self.polygon_split.setEnabled(True)
            self.line_split.setEnabled(True)
            self.anchor_on.setEnabled(True)
            self.undo.setEnabled(True)

            try:  # remove any existing connection first
                layer.editingStopped.disconnect(self.toggle)
            except TypeError:  # missing connection
                pass
            layer.editingStopped.connect(self.toggle)
            try:
                layer.editingStarted.disconnect(self.toggle)
            except TypeError:  # missing connection
                pass
        else:
            ### add for tool
            self.bezier_edit.setEnabled(False)
            self.pen_edit.setEnabled(False)
            self.feature_selection.setEnabled(False)
            self.polygon_split.setEnabled(False)
            self.line_split.setEnabled(False)
            self.anchor_on.setEnabled(False)
            self.undo.setEnabled(False)

            if layer.type() == QgsMapLayer.VectorLayer:
                try:  # remove any existing connection first
                    layer.editingStarted.disconnect(self.toggle)
                except TypeError:  # missing connection
                    pass
                layer.editingStarted.connect(self.toggle)
                try:
                    layer.editingStopped.disconnect(self.toggle)
                except TypeError:  # missing connection
                    pass


    def deactivate(self):
        self.bezier_edit.setChecked(False)
        self.pen_edit.setChecked(False)
        self.feature_selection.setChecked(False)
        self.polygon_split.setChecked(False)
        self.line_split.setChecked(False)
        #self.active = False

    def unload(self):
        self.toolbar.removeAction(self.bezier_edit)
        self.toolbar.removeAction(self.pen_edit)
        self.toolbar.removeAction(self.feature_selection)
        self.toolbar.removeAction(self.polygon_split)
        self.toolbar.removeAction(self.line_split)
        self.toolbar.removeAction(self.anchor_on)
        self.toolbar.removeAction(self.undo)
        del self.toolbar

    def log(self, msg):
        QgsMessageLog.logMessage(msg, 'MyPlugin', Qgis.Info)
