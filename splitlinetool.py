# -*- coding: utf-8 -*-

from builtins import range
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtGui import *
from qgis.core import *
from qgis.gui import *
import math
import numpy as np

class SplitLineTool(QgsMapTool):

    def __init__(self, canvas,iface):
        QgsMapTool.__init__(self, canvas)
        self.canvas = canvas
        self.iface = iface


    def canvasPressEvent(self, event):
        layer = self.canvas.currentLayer()
        if not layer or layer.type() != QgsMapLayer.VectorLayer or layer.geometryType() != QgsWkbTypes.LineGeometry:
            return
        button_type = event.button()
        pnt = self.toMapCoordinates(event.pos())

        # 右クリック
        if button_type == 2:
            # 近い地物を選択
            selected, f = self.getSelectedNearFeature(layer, pnt)
            # 属性ポップアップ
            if selected:
                layer.beginEditCommand("edit attribute")
                dlg = self.iface.getFeatureForm(layer, f)
                if dlg.exec_():
                    layer.endEditCommand()
                else:
                    layer.destroyEditCommand()
                layer.removeSelection()
            # 選択
            else:
                layer.removeSelection()
                self.selectNearFeature(layer, pnt)
        #左クリック
        if button_type == 1:
            selected, f = self.getSelectedNearFeature(layer, pnt)
            if selected:
                geom = QgsGeometry(f.geometry())
                self.check_crs()
                if self.layerCRSSrsid != self.projectCRSSrsid:
                    geom.transform(QgsCoordinateTransform(self.layerCRSSrsid, self.projectCRSSrsid))
                near, minDistPoint, afterVertex = self.closestPointOfGeometry(pnt, geom)
                polyline = geom.asPolyline()
                line1 = polyline[0:afterVertex]
                line1.append(minDistPoint)
                line2 = polyline[afterVertex:]
                line2.insert(0, minDistPoint)
                self.createFeature(QgsGeometry.fromPolylineXY(line2), f)
                self.editFeature(QgsGeometry.fromPolylineXY(line1), f, True)
                self.canvas.currentLayer().removeSelection()

    def createFeature(self, geom, feat):
        continueFlag = False
        layer = self.canvas.currentLayer()
        provider = layer.dataProvider()

        self.check_crs()
        if self.layerCRSSrsid != self.projectCRSSrsid:
            geom.transform(QgsCoordinateTransform(self.projectCRSSrsid, self.layerCRSSrsid))

        # validate geometry
        f = QgsFeature()
        f.setGeometry(geom)

        # add attribute fields to feature
        fields = layer.fields()
        f.initAttributes(fields.count())

        if feat is None:
            for i in range(fields.count()):
                if provider.defaultValue(i):
                    f.setAttribute(i, provider.defaultValue(i))
        else:
            for i in range(fields.count()):
                    f.setAttribute(i, feat.attributes()[i])

        layer.beginEditCommand("Feature added")

        settings = QSettings()
        disable_attributes = settings.value("/qgis/digitizing/disable_enter_attribute_values_dialog", False, type=bool)
        if disable_attributes or feat is not None:
            if layer.geometryType() == QgsWkbTypes.LineGeometry:
                layer.addFeature(f)
                layer.endEditCommand()
            else:
                QMessageBox.warning(None, "Warning", "Select Line layer!")
        else:
            dlg = self.iface.getFeatureForm(layer, f)
            if dlg.exec_():
                if layer.geometryType() == QgsWkbTypes.LineGeometry:
                    layer.addFeature(f)
                    layer.endEditCommand()
                else:
                    QMessageBox.warning(None, "Warning", "Select Line layer!")
                    layer.destroyEditCommand()
                    continueFlag = True
            else:
                layer.destroyEditCommand()
                reply = QMessageBox.question(None, "Question", "continue?", QMessageBox.Yes,
                                             QMessageBox.No)
                if reply == QMessageBox.Yes:
                    continueFlag = True
            return continueFlag
    def editFeature(self, geom, f, hidedlg):
        layer = self.canvas.currentLayer()
        self.check_crs()
        if self.layerCRSSrsid != self.projectCRSSrsid:
            geom.transform(QgsCoordinateTransform(self.projectCRSSrsid, self.layerCRSSrsid))
        layer.beginEditCommand("Feature edited")
        settings = QSettings()
        disable_attributes = settings.value("/qgis/digitizing/disable_enter_attribute_values_dialog", False, type=bool)
        if disable_attributes or hidedlg:
            layer.changeGeometry(f.id(), geom)
            layer.endEditCommand()
        else:
            dlg = self.iface.getFeatureForm(layer, f)
            if dlg.exec_():
                layer.changeGeometry(f.id(), geom)
                layer.endEditCommand()
            else:
                layer.destroyEditCommand()

    def closestPointOfGeometry(self,point,geom):
        #フィーチャとの距離が近いかどうかを確認
        near = False
        (dist, minDistPoint, afterVertex, leftOf) = geom.closestSegmentWithContext(point)
        d = self.canvas.mapUnitsPerPixel() * 8
        if math.sqrt(dist) < d:
            near = True
        return near,minDistPoint,afterVertex
    def getNearFeature(self, layer,point):
        d = self.canvas.mapUnitsPerPixel() * 4
        rect = QgsRectangle((point.x() - d), (point.y() - d), (point.x() + d), (point.y() + d))
        self.check_crs()
        if self.layerCRSSrsid != self.projectCRSSrsid:
            rectGeom = QgsGeometry.fromRect(rect)
            rectGeom.transform(QgsCoordinateTransform(self.projectCRSSrsid, self.layerCRSSrsid))
            rect = rectGeom.boundingBox()
        request = QgsFeatureRequest()
        request.setLimit(1)
        request.setFilterRect(rect)
        f = [feat for feat in layer.getFeatures(request)]  # only one because of setlimit(1)
        if len(f)==0:
            return False,None
        else:
            return True,f[0]

    def check_selection(self,layer):
        featid_list = layer.selectedFeatureIds()
        if len(featid_list) > 0:
            return True,featid_list
        else:
            return False,featid_list

    def getSelectedNearFeature(self,layer,pnt):
        selected, featids = self.check_selection(layer)
        near, f = self.getNearFeature(layer,pnt)
        if selected and near and featids[0]==f.id():
            return True,f
        else:
            return False,None

    def selectNearFeature(self,layer,pnt):
        #近い地物を選択
        layer.removeSelection()
        near, f = self.getNearFeature(layer,pnt)
        if near:
            layer.select(f.id())
            return True,f
        else:
            return False,None

    def check_crs(self):
        layer = self.canvas.currentLayer()
        renderer = self.canvas.mapSettings()
        self.layerCRSSrsid = layer.crs().srsid()
        self.projectCRSSrsid = renderer.destinationCrs().srsid()

    def showSettingsWarning(self):
        pass
    def activate(self):
        cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/mCrossHair.svg'), -1, -1)
        #cursor = QCursor()
        #cursor.setShape(Qt.ArrowCursor)
        self.canvas.setCursor(cursor)

    def deactivate(self):
        pass
    def isZoomTool(self):
        return False
    def isTransient(self):
        return False
    def isEditTool(self):
        return True
    def log(self,msg):
        QgsMessageLog.logMessage(msg, 'MyPlugin',Qgis.Info)
