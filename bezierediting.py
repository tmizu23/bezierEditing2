# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtGui import *
from qgis.core import *
from qgis.gui import *
from .beziereditingtool import BezierEditingTool
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

        # Create split action
        self.split = QAction(QIcon(":/plugins/bezierEditing2/icon/spliticon.svg"),"Bezier_Split", self.iface.mainWindow())
        self.split.setObjectName("BezierEditing_split")
        self.split.setEnabled(False)
        self.split.setCheckable(True)
        self.split.triggered.connect(self.spliting)
        self.toolbar.addAction(self.split)

        # Create show anchor option
        self.show_handle = QAction(QIcon(":/plugins/bezierEditing2/icon/showhandleicon.svg"),"Bezier_Show Anchor", self.iface.mainWindow())
        self.show_handle.setObjectName("BezierEditing_show_handle")
        self.show_handle.setCheckable(True)
        self.show_handle.setEnabled(False)
        self.show_handle.toggled.connect(self.showhandle)
        self.toolbar.addAction(self.show_handle)

        # Create undo option
        self.undo = QAction(QIcon(":/plugins/bezierEditing2/icon/undoicon.svg"),"Bezier_Undo", self.iface.mainWindow())
        self.undo.setObjectName("BezierEditing_undo")
        self.undo.setEnabled(False)
        self.undo.triggered.connect(self.beziertool.undo)
        self.toolbar.addAction(self.undo)

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

    def spliting(self):
        self.canvas.setMapTool(self.beziertool)
        self.split.setChecked(True)
        self.beziertool.mode = "split"

    def showhandle(self,checked):
        self.beziertool.showHandle(checked)

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
            self.split.setEnabled(True)
            self.show_handle.setEnabled(True)
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
            self.split.setEnabled(False)
            self.show_handle.setEnabled(False)
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
        self.split.setChecked(False)

        #self.active = False

    def unload(self):
        self.toolbar.removeAction(self.bezier_edit)
        self.toolbar.removeAction(self.pen_edit)
        self.toolbar.removeAction(self.split)
        self.toolbar.removeAction(self.show_handle)
        self.toolbar.removeAction(self.undo)
        del self.toolbar

    def log(self, msg):
        QgsMessageLog.logMessage(msg, 'MyPlugin', Qgis.Info)
