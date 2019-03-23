# -*- coding: utf-8 -*-

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *
import math
import numpy as np

class SplitPolygonTool(QgsMapTool):

    def __init__(self, canvas,iface):
        QgsMapTool.__init__(self, canvas)
        self.canvas = canvas
        self.iface = iface
        self.alt = False # no use now

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Alt:
            self.alt = True

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Alt:
            self.alt = False

    def runSplit(self):

        #選択フィーチャからポリゴンレイヤー取得

        polygon_layer_num, polygon_layer, polygons = self.selectedPolygonFeatures()
        line_layer_num, line_layer, lines = self.selectedLineFeatures()
        if polygon_layer_num != 1:
            QMessageBox.warning(None, "Warning", u"2つ以上のレイヤに選択されたポリゴンがあります。")
            return
        if len(polygons) < 1:
            QMessageBox.warning(None, "Warning", u"ポリゴンレイヤが選択されていません。")
            return
        if len(lines) < 1:
            QMessageBox.warning(None, "Warning", u"ラインレイヤが選択されていません。")
            return

        polygon_layer.invertSelection()
        invert_selection_ids = polygon_layer.selectedFeaturesIds()
        polygon_layer.invertSelection()

        for line in lines:
            self.splitSelectedPolygonByLine(line)
            polygon_layer.selectByIds(invert_selection_ids)
            polygon_layer.invertSelection()
        polygon_layer.removeSelection()
        line_layer.removeSelection()

    def splitSelectedPolygonByLine(self,line):
        polygon_layer_num, polygon_layer, polygons = self.selectedPolygonFeatures()
        line_geom = QgsGeometry(line.geometry())
        polygon_layer.beginEditCommand(QtCore.QCoreApplication.translate("editcommand", "Features split"))
        for i, polygon in enumerate(polygons):
            polygon_geom = QgsGeometry(polygon.geometry())
            result, newGeometries, topoTestPoints = polygon_geom.splitGeometry(line_geom.asPolyline(), False)
            if result == 0:
                newFeatures = self.makeFeaturesFromGeometries(polygon_layer, polygon, newGeometries)
                polygons[i].setGeometry(polygon_geom)
                polygon_layer.updateFeature(polygons[i])
                polygon_layer.addFeatures(newFeatures, False)
        polygon_layer.endEditCommand()


    def dtGetFeatureForId(self,layer, fid):
        '''Function that returns the QgsFeature with FeatureId *fid* in QgsVectorLayer *layer*'''
        feat = QgsFeature()

        if layer.getFeatures(QgsFeatureRequest().setFilterFid(fid)).nextFeature(feat):
            return feat
        else:
            return None

    def dtCreateFeature(self,layer):
        '''Create an empty feature for the *layer*'''
        if isinstance(layer, QgsVectorLayer):
            newFeature = QgsFeature()
            provider = layer.dataProvider()
            fields = layer.pendingFields()

            newFeature.initAttributes(fields.count())

            for i in range(fields.count()):
                newFeature.setAttribute(i, provider.defaultValue(i))

            return newFeature
        else:
            return None

    def dtCopyFeature(self, layer, srcFeature=None, srcFid=None):
        '''Copy the QgsFeature with FeatureId *srcFid* in *layer* and return it. Alternatively the
        source Feature can be given as paramter. The feature is not added to the layer!'''
        if srcFid != None:
            srcFeature = self.dtGetFeatureForId(layer, srcFid)

        if srcFeature:
            newFeature = self.dtCreateFeature(layer)

            # # copy the attribute values#
            # pkFields = layer.dataProvider().pkAttributeIndexes()
            # fields = layer.pendingFields()
            # for i in range(fields.count()):
            #     # do not copy the PK value if there is a PK field
            #     if i in pkFields:
            #         continue
            #     else:
            #         newFeature.setAttribute(i, srcFeature[i])

            return newFeature
        else:
            return None

    def makeFeaturesFromGeometries(self, layer, srcFeat, geometries):
        '''create new features from geometries and copy attributes from srcFeat'''
        newFeatures = []

        for aGeom in geometries:
            newFeat = self.dtCopyFeature(layer, srcFeat)
            newFeat.setGeometry(aGeom)
            newFeatures.append(newFeat)

        return newFeatures

    def createFeature(self,layer,geom):
        continueFlag = False
        provider = layer.dataProvider()
        fields = layer.pendingFields()
        f = QgsFeature(fields)

        self.check_crs()
        if self.layerCRSSrsid != self.projectCRSSrsid:
            geom.transform(QgsCoordinateTransform(self.projectCRSSrsid, self.layerCRSSrsid))
        f.setGeometry(geom)

        ## Add attributefields to feature.
        for field in fields.toList():
            ix = fields.indexFromName(field.name())
            f[field.name()] = provider.defaultValue(ix)

        layer.beginEditCommand("Feature added")

        settings = QSettings()
        disable_attributes = settings.value("/qgis/digitizing/disable_enter_attribute_values_dialog", False, type=bool)
        if disable_attributes:
            layer.addFeature(f)
            layer.endEditCommand()
        else:
            dlg = self.iface.getFeatureForm(layer, f)
            if dlg.exec_():
                layer.endEditCommand()
            else:
                layer.destroyEditCommand()
                reply = QMessageBox.question(None, "Question", u"編集を続けますか？", QMessageBox.Yes,
                                             QMessageBox.No)
                if reply == QMessageBox.Yes:
                    continueFlag = True
        return continueFlag

    def selectedPolygonFeatures(self):
        layers = QgsMapLayerRegistry.instance().mapLayers().values()
        layer_num = 0
        layer = None
        features = []
        for l in layers:
            if l.type() == QgsMapLayer.VectorLayer and l.geometryType() == QGis.Polygon:
                fids = l.selectedFeaturesIds()
                features = [self.getFeatureById(l,fid) for fid in fids]
                layer = l
                layer_num = layer_num + 1
        return layer_num, layer, features

    def selectedLineFeatures(self):
        layers = QgsMapLayerRegistry.instance().mapLayers().values()
        layer_num = 0
        layer = None
        features = []
        for l in layers:
            if l.type() == QgsMapLayer.VectorLayer and l.geometryType() == QGis.Line:
                fids = l.selectedFeaturesIds()
                features = [self.getFeatureById(l,fid) for fid in fids]
                layer = l
                layer_num = layer_num + 1
        return layer_num, layer, features

    def getFeatureById(self,layer,featid):
        features = [f for f in layer.getFeatures(QgsFeatureRequest().setFilterFids([featid]))]
        if len(features) != 1:
            return None
        else:
            return features[0]

    def check_crs(self):
        layer = self.canvas.currentLayer()
        renderer = self.canvas.mapSettings()
        self.layerCRSSrsid = layer.crs().srsid()
        self.projectCRSSrsid = renderer.destinationCrs().srsid()
    def showSettingsWarning(self):
        pass
    def activate(self):
        self.cursor = QCursor()
        self.cursor.setShape(Qt.ArrowCursor)
        self.canvas.setCursor(self.cursor)
        self.alt = False
        self.runSplit()

    def deactivate(self):
        pass
    def isZoomTool(self):
        return False
    def isTransient(self):
        return False
    def isEditTool(self):
        return True
    def log(self,msg):
        QgsMessageLog.logMessage(msg, 'MyPlugin',QgsMessageLog.INFO)
