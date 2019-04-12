# -*- coding: utf-8 -*-

from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtGui import *
from qgis.core import *
from qgis.gui import *
import math
import numpy as np


## クリックで選択、選択解除
## 選択はレイヤの上から優先
## ドラッグすると、選択リセット後、ドラッグと交差するものを選択

class FeatureSelectionTool(QgsMapTool):

    def __init__(self, canvas,iface):
        QgsMapTool.__init__(self, canvas)
        self.canvas = canvas
        self.iface = iface
        self.shift = False # no use now
        self.rubberBand = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.rubberBand.setColor(QColor(255, 0, 0, 100))
        self.rubberBand.setWidth(1)
        self.reset()

    def reset(self):
        self.startPoint = self.endPoint = None
        self.isEmittingPoint = False
        self.rubberBand.reset(QgsWkbTypes.PolygonGeometry)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Shift:
            self.shift = True

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Shift:
            self.shift = False

    def canvasPressEvent(self, event):
        point = self.toMapCoordinates(event.pos())

        self.endPoint = self.startPoint = point
        self.isEmittingPoint = True
        self.showRect(self.startPoint, self.endPoint)

    def canvasMoveEvent(self, event):
        if not self.isEmittingPoint:
            return

        self.endPoint = self.toMapCoordinates(event.pos())
        self.showRect(self.startPoint, self.endPoint)

    def canvasReleaseEvent(self, event):
        point = self.toMapCoordinates(event.pos())
        self.isEmittingPoint = False
        r = self.rectangle()
        if r is not None:
            self.reset()
            self.selectFeatures(point,r)
        else:
            self.selectFeatures(point)

    def selectFeatures(self,point,rect=None):
        #layers = QgsMapLayerRegistry.instance().mapLayers().values()
        layers = QgsProject.instance().layerTreeRoot().findLayers()
        for layer in layers:
            #self.log("{}".format(layer.name().encode('utf-8')))
            if layer.layer().type() != QgsMapLayer.VectorLayer:
                continue
            near = self.selectNearFeature(layer.layer(), point, rect)
            if near and rect is None:
                break

    def showRect(self, startPoint, endPoint):
        self.rubberBand.reset(QgsWkbTypes.PolygonGeometry)
        if startPoint.x() == endPoint.x() or startPoint.y() == endPoint.y():
            return

        point1 = QgsPointXY(startPoint.x(), startPoint.y())
        point2 = QgsPointXY(startPoint.x(), endPoint.y())
        point3 = QgsPointXY(endPoint.x(), endPoint.y())
        point4 = QgsPointXY(endPoint.x(), startPoint.y())

        self.rubberBand.addPoint(point1, False)
        self.rubberBand.addPoint(point2, False)
        self.rubberBand.addPoint(point3, False)
        self.rubberBand.addPoint(point4, True)  # true to update canvas
        self.rubberBand.show()

    def rectangle(self):
        if self.startPoint is None or self.endPoint is None:
            return None
        elif self.startPoint.x() == self.endPoint.x() or self.startPoint.y() == self.endPoint.y():
            return None

        return QgsRectangle(self.startPoint, self.endPoint)

    def getNearFeatures(self, layer, point, rect=None):
        if rect is None:
            d = self.canvas.mapUnitsPerPixel() * 4
            rect = QgsRectangle((point.x() - d), (point.y() - d), (point.x() + d), (point.y() + d))
        self.check_crs()
        if self.layerCRS.srsid() != self.projectCRS.srsid():
            rectGeom = QgsGeometry.fromRect(rect)
            rectGeom.transform(QgsCoordinateTransform(self.projectCRS, self.layerCRS, QgsProject.instance()))
            rect = rectGeom.boundingBox()
        request = QgsFeatureRequest()
        #request.setLimit(1)
        request.setFilterRect(rect)
        f = [feat for feat in layer.getFeatures(request)]
        if len(f) == 0:
            return False, None
        else:
            return True, f

    def selectNearFeature(self,layer,pnt,rect=None):
        if rect is not None:
            layer.removeSelection()
        near, features = self.getNearFeatures(layer,pnt,rect)
        if near:
            fids = [f.id() for f in features]
            if rect is not None:
                layer.selectByIds(fids)
            else:
                for fid in fids:
                    if self.IsSelected(layer,fid):
                        layer.deselect(fid)
                    else:
                        layer.select(fid)
        return near

    def IsSelected(self,layer,fid):
        for sid in layer.selectedFeatureIds():
            if sid == fid:
                return True
        return False

    def check_crs(self):
        layer = self.canvas.currentLayer()
        renderer = self.canvas.mapSettings()
        self.layerCRS = layer.crs()
        self.projectCRS = renderer.destinationCrs()
    def showSettingsWarning(self):
        pass
    def activate(self):
        self.cursor = QCursor()
        self.cursor.setShape(Qt.ArrowCursor)
        self.canvas.setCursor(self.cursor)
        self.alt = False

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
