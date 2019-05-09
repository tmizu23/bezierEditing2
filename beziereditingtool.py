# -*- coding: utf-8 -*-
from __future__ import absolute_import
from builtins import zip
from builtins import range
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtGui import *
from qgis.core import *
from qgis.gui import *
import math
import numpy as np
from .BezierGeometry import *
from .BezierMarker import *

class BezierEditingTool(QgsMapTool):
    def __init__(self, canvas,iface):
        QgsMapTool.__init__(self, canvas)
        self.iface = iface
        self.canvas = canvas

        # ペンツールのライン
        self.pen_rbl = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.pen_rbl.setColor(QColor(255, 0, 0, 150))
        self.pen_rbl.setWidth(2)
        # スナップのマーカー
        self.snap_mark = QgsVertexMarker(self.canvas)
        self.snap_mark.setColor(QColor(0, 0, 255))
        self.snap_mark.setPenWidth(2)
        self.snap_mark.setIconType(QgsVertexMarker.ICON_BOX)
        self.snap_mark.setIconSize(10)

        #　アイコン
        self.addanchor_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/anchor.svg'), 1, 1)
        self.insertanchor_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/anchor_add.svg'), 1, 1)
        self.deleteanchor_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/anchor_del.svg'), 1, 1)
        self.movehandle_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/handle.svg'), 1, 1)
        self.addhandle_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/handle_add.svg'), 1, 1)
        self.deletehandle_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/handle_del.svg'), 1, 1)
        self.drawline_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/drawline.svg'), 1, 1)
        self.split_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/mCrossHair.svg'), -1, -1)

       #　変数と初期設定
        self.mode = "bezier"  # bezier, pen , split
        self.mouse_state = "free" # free, add_anchor,move_anchor,move_handle,insert_anchor,draw_line
        self.editing = False #オブジェクト作成、修正中
        self.snapping = None #スナップが設定されているかどうか
        self.show_handle = False  # ベジエマーカーを表示するかどうか
        self.editing_feature_id = None # 編集オブジェクトのid
        self.selected_idx = None # 選択されたアンカーもしくはハンドルのインデックス. ドラッグ時の識別のために使用
        self.alt = False
        self.ctrl = False
        self.shift = False

        self.b = None #BezierGeometry #現時点では、1度に1つだけ
        self.m = None #BezierMarker
        #self.tolerance = 1


    ####### キー、キャンパスイベント
    def keyPressEvent(self, event):
        if self.mode == "bezier":
            if event.key() == Qt.Key_Alt:
                self.alt = True
            if event.key() == Qt.Key_Control:
                self.ctrl = True
            if event.key() == Qt.Key_Shift:
                self.shift = True

    def keyReleaseEvent(self, event):
        if self.mode == "bezier":
            if event.key() == Qt.Key_Alt:
                self.alt = False
            if event.key() == Qt.Key_Control:
                self.ctrl = False
            if event.key() == Qt.Key_Shift:
                self.shift = False

    def canvasPressEvent(self, event):
        layer = self.canvas.currentLayer()
        if not layer or layer.type() != QgsMapLayer.VectorLayer:
            return
        self.check_snapsetting()
        mouse_point, snapped, snap_point, snap_idx = self.getSnapPoint(event, layer)
        #self.log("{}".format(snapped))
        if self.mode == "bezier":
            # ベジエツールで右クリック
            if event.button() == Qt.RightButton:
                # 編集を確定する
                if self.editing:
                    self.finish_editing(layer)
                # ベジエに変換する
                else:
                    self.start_editing(layer,mouse_point)
            # ベジエで左クリック
            elif event.button() == Qt.LeftButton:
                # Ctrlを押しながら
                if self.ctrl:
                    # アンカーと重なっていてもアンカーを追加したいとき。ポリゴンを閉じたいときなど。
                    if snapped[1]:
                        self.mouse_state = "add_anchor"
                        self.selected_idx = self.b.anchorCount()
                        self.b.add_anchor(self.selected_idx, snap_point[1])
                        self.m.addAnchorMarker(self.selected_idx, snap_point[1])

                # Altを押しながら
                elif self.alt:
                    # アンカーからハンドルを引き出すとき
                    if snapped[2] and snapped[1]:
                        self.mouse_state = "move_handle"
                        self.selected_idx = snap_idx[2]
                    # アンカーを挿入するとき
                    elif snapped[3] and not snapped[1]:
                        self.mouse_state = "insert_anchor"
                        self.b.insert_anchor(snap_idx[3], snap_point[3])
                        self.m.showBezierLineMarkers()

                # Shiftを押しながら
                elif self.shift:
                    # アンカーを削除するとき
                    if snapped[1]:
                        self.b.delete_anchor(snap_idx[1],snap_point[1])
                        self.m.deleteAnchorMarker(snap_idx[1])
                    # ハンドルを削除するとき
                    elif snapped[2]:
                        self.b.delete_handle(snap_idx[2],snap_point[2])
                        pnt = self.b.getAnchor(int(snap_idx[2] / 2))
                        self.m.moveHandleMarker(snap_idx[2], pnt)
                else:

                    # 判定の順番が重要
                    # 「アンカーの移動」かどうか
                    if snapped[1]:
                        self.mouse_state = "move_anchor"
                        self.selected_idx = snap_idx[1]
                        self.b.move_anchor(snap_idx[1],snap_point[1])
                        self.m.moveAnchorMarker(snap_idx[1],snap_point[1])

                    # 「ハンドルの移動」かどうか
                    elif snapped[2]:
                        self.mouse_state="move_handle"
                        self.selected_idx = snap_idx[2]
                        self.b.move_handle(snap_idx[2],snap_point[2])
                        self.m.moveHandleMarker(snap_idx[2],snap_point[2])

                    else:
                    # 上のどれでもなければ「新規ポイント追加」
                        if not self.editing:
                            self.b = BezierGeometry()
                            self.m = BezierMarker(self.canvas,self.b)
                            self.editing = True
                        self.mouse_state = "add_anchor"
                        self.selected_idx = self.b.anchorCount()
                        self.b.add_anchor(self.selected_idx, snap_point[0])
                        self.m.addAnchorMarker(self.selected_idx, snap_point[0])

        elif self.mode == "pen":
            # 右クリックで確定
            if event.button() == Qt.RightButton:
                if self.editing:
                    self.finish_editing(layer)
                else:
                    if layer.geometryType() != QgsWkbTypes.LineGeometry:
                        QMessageBox.warning(None, "Warning", u"ライン以外はベジエに変換できません")
                        return
                    self.start_editing(layer,mouse_point)
            # 左クリック
            elif event.button() == Qt.LeftButton:
                # 新規作成
                if not self.editing:
                    self.b = BezierGeometry()
                    self.m = BezierMarker(self.canvas,self.b)
                    pnt = mouse_point
                    self.editing = True
                # 編集中でベジエ曲線に近いなら修正
                elif self.editing and snapped[3]:
                    pnt = snap_point[3]
                else:
                    return
                self.mouse_state = "draw_line"
                self.pen_rbl.reset(QgsWkbTypes.LineGeometry)
                self.pen_rbl.addPoint(pnt)

        elif self.mode == "split":
            # 右クリックで確定
            if event.button() == Qt.RightButton:
                if self.editing:
                    self.finish_editing(layer)
                else:
                    if layer.geometryType() != QgsWkbTypes.LineGeometry:
                        QMessageBox.warning(None, "Warning", u"ライン以外はベジエに変換できません")
                        return
                    self.start_editing(layer,mouse_point)
            # 左クリック
            elif event.button() == Qt.LeftButton:
                # 編集中で編集中のラバーバンドに近いなら
                if self.editing:
                    if self.editing_feature_id is None:
                        QMessageBox.warning(None, "Warning", u"フィーチャーがありません")
                        return
                    if snapped[1]:
                        lineA, lineB = self.b.split_line(snap_idx[1], snap_point[1],isAnchor=True)
                    elif snapped[3]:
                        lineA, lineB = self.b.split_line(snap_idx[3],snap_point[3],isAnchor=False)
                    else:
                        return
                    # 作成するオブジェクトをgeomに変換。修正するためのフィーチャーも取得
                    type = layer.geometryType()
                    if type == QgsWkbTypes.LineGeometry:
                        if layer.wkbType() == QgsWkbTypes.LineString:
                            geomA = QgsGeometry.fromPolylineXY(lineA)
                            geomB = QgsGeometry.fromPolylineXY(lineB)
                        elif layer.wkbType() == QgsWkbTypes.MultiLineString:
                            geomA = QgsGeometry.fromMultiPolylineXY([lineA])
                            geomB = QgsGeometry.fromMultiPolylineXY([lineB])
                    else:
                        QMessageBox.warning(None, "Warning", u"レイヤのタイプが違います")
                        self.resetPoints()
                        return

                    feature = self.getFeatureById(layer, self.editing_feature_id)
                    self.createFeature(geomB, feature, editmode=False,showdlg=False)
                    self.createFeature(geomA, feature, editmode=True,showdlg=False)
                    layer.select(feature.id())
                    self.resetPoints()

    def canvasMoveEvent(self, event):
        layer = self.canvas.currentLayer()
        if not layer or layer.type() != QgsMapLayer.VectorLayer:
            return
        mouse_point, snapped, snap_point, snap_idx = self.getSnapPoint(event, layer)
        if self.mode == "bezier":
            # 追加時のドラッグはハンドルの移動
            if self.mouse_state=="add_anchor":
                handle_idx, pb = self.b.move_handle2(self.selected_idx, mouse_point)
                self.m.moveHandleMarker(handle_idx, pb)
                self.m.moveHandleMarker(handle_idx + 1, mouse_point)
            elif self.mouse_state == "insert_anchor":
                pass
            elif self.alt and snapped[1] and snapped[2]:
                self.canvas.setCursor(self.addhandle_cursor)
            elif self.alt and snapped[3] and not snapped[1]:
                self.canvas.setCursor(self.insertanchor_cursor)
            elif self.ctrl and snapped[1]:
                self.canvas.setCursor(self.insertanchor_cursor)
            elif self.shift and snapped[1]:
                self.canvas.setCursor(self.deleteanchor_cursor)
            elif self.shift and snapped[2]:
                self.canvas.setCursor(self.deletehandle_cursor)
            # 選択されたハンドルの移動
            elif self.mouse_state=="move_handle":
                self.b.moveHandle(self.selected_idx, mouse_point)
                self.m.moveHandleMarker(self.selected_idx, mouse_point)
            # 選択されたアンカーの移動
            elif self.mouse_state=="move_anchor":
                pnt = snap_point[0]
                if snapped[1]:
                    pnt = snap_point[1]
                self.b.moveAnchor(self.selected_idx, pnt)
                self.m.moveAnchorMarker(self.selected_idx, pnt)
            else:
                if snapped[1]:
                    self.canvas.setCursor(self.movehandle_cursor)
                elif snapped[2]:
                    self.canvas.setCursor(self.movehandle_cursor)
                else:
                    self.canvas.setCursor(self.addanchor_cursor)
        elif self.mode == "pen":
            self.canvas.setCursor(self.drawline_cursor)
            if self.mouse_state == "draw_line":
                pnt = mouse_point
                # スタートポイントとスナップしてるなら
                if snapped[4]:
                    pnt = snap_point[4]
                self.pen_rbl.addPoint(pnt)
        elif self.mode == "split":
            self.canvas.setCursor(self.split_cursor)

    def canvasReleaseEvent(self, event):
        layer = self.canvas.currentLayer()
        if not layer or layer.type() != QgsMapLayer.VectorLayer:
            return
        mouse_point, snapped, snap_point, _ = self.getSnapPoint(event, layer)
        if self.mode == "bezier":
            self.selected_idx = None
            self.mouse_state="free"
        elif self.mode == "pen":
            # ドロー終了
            if self.mouse_state != "free":
                self.convert_draw_line(snapped[4])
                self.mouse_state = "free"
        elif self.mode == "split":
            self.selected_idx = None
            self.mouse_state = "free"

        self.m.showHandle(self.show_handle)

    ####### イベント処理からの呼び出し
    # ベジエ関係
    def start_editing(self,layer,mouse_point):
        # 編集開始
        near, f = self.getNearFeature(layer, mouse_point)
        if near:
            ret = self.convertFeatureToBezier(f)
            if ret:
                self.editing_feature_id = f.id()
                self.editing = True

    def finish_editing(self,layer):
        num_anchor = self.b.anchorCount()
        #self.log("{}".format(num_anchor))
        # 作成するオブジェクトをgeomに変換。修正するためのフィーチャーも取得
        type = layer.geometryType()
        if type == QgsWkbTypes.PointGeometry and num_anchor == 1:
            geom = QgsGeometry.fromPointXY(self.b.points[0])
        elif type == QgsWkbTypes.LineGeometry and num_anchor >= 2:
            if layer.wkbType() == QgsWkbTypes.LineString:
                geom = QgsGeometry.fromPolylineXY(self.b.points)
            elif layer.wkbType() == QgsWkbTypes.MultiLineString:
                geom = QgsGeometry.fromMultiPolylineXY([self.b.points])
        elif type == QgsWkbTypes.PolygonGeometry and num_anchor >= 3:
            geom = QgsGeometry.fromPolygonXY([self.b.points])
        else:
            QMessageBox.warning(None, "Warning", u"レイヤのタイプが違います")
            return

        if  self.editing_feature_id is not None:
            feature = self.getFeatureById(layer, self.editing_feature_id)
            if feature is None:
                QMessageBox.warning(None, "Warning", u"レイヤを確かめてください")
                self.resetPoints()
                return
            continueFlag = self.createFeature(geom, feature, editmode=True)
        else:
            continueFlag = self.createFeature(geom, None, editmode=False)

        if continueFlag is False:
            self.resetPoints()

        self.canvas.refresh()

    # ペン関係
    def convert_draw_line(self,snap_to_start):
        if self.pen_rbl.numberOfVertices() <= 2:
            self.pen_rbl.reset(QgsWkbTypes.LineGeometry)
            return
        geom = self.pen_rbl.asGeometry()
        d = self.canvas.mapUnitsPerPixel() * 10
        self.b.modified_by_geometry(geom, d, snap_to_start)  # 編集箇所の次のハンドル以降を削除
        self.m.showBezierLineMarkers()
        self.pen_rbl.reset()

    # ポイント、ハンドルの配列、マーカー、ラインとベジエライン、履歴を初期化
    def resetPoints(self):
        self.m.removeBezierLineMarkers()
        self.b.reset()
        self.editing_feature_id = None
        self.editing = False

    # フィーチャをベジエ曲線のハンドルに変換
    def convertFeatureToBezier(self, f):
        geom = QgsGeometry(f.geometry())
        self.check_crs()
        if self.layerCRS.srsid() != self.projectCRS.srsid():
            geom.transform(QgsCoordinateTransform(self.layerCRS, self.projectCRS, QgsProject.instance()))

        if geom.type() == QgsWkbTypes.PointGeometry:
            point = geom.asPoint()

            self.b = BezierGeometry.convertPointToBezier(point)
            self.m = BezierMarker(self.canvas, self.b)
            self.m.addAnchorMarker(0, point)
            return True
        elif geom.type() == QgsWkbTypes.LineGeometry:
            if geom.wkbType() == QgsWkbTypes.MultiLineString:
                polyline = geom.asMultiPolyline()[0]
            elif geom.wkbType() == QgsWkbTypes.LineString:
                polyline = geom.asPolyline()

            if len(polyline) % 10 != 1:
                # 他のツールで編集されているのでベジエに変換できない。
                # 編集されていても偶然、あまりが1になる場合は、変換してしまう。
                QMessageBox.warning(None, "Warning", u"他のツールで編集されたオブジェクトはベジエに変換できません")
                return False


            self.b = BezierGeometry.convertLineToBezier(polyline)
            self.m = BezierMarker(self.canvas, self.b)
            self.m.showBezierLineMarkers(self.show_handle)

            return True
        else:
            QMessageBox.warning(None, "Warning", u"ベジエに変換できないレイヤタイプです")
            return False


    def createFeature(self, geom, feat, editmode=True,showdlg=True):
        continueFlag = False
        layer = self.canvas.currentLayer()
        self.check_crs()
        if self.layerCRS.srsid() != self.projectCRS.srsid():
            geom.transform(QgsCoordinateTransform(self.projectCRS, self.layerCRS, QgsProject.instance()))

        if not editmode:
            f = QgsFeature()
            fields = layer.fields()
            f.setFields(fields)
            f.setGeometry(geom)
            # add attribute fields to feature

            if feat is not None:
                for i in range(fields.count()):
                    f.setAttribute(i, feat.attributes()[i])
        else:
            f = feat

        settings = QSettings()
        disable_attributes = settings.value("/qgis/digitizing/disable_enter_attribute_values_dialog", False, type=bool)
        if disable_attributes or showdlg is False:
            if not editmode:
                layer.beginEditCommand("Feature added")
                layer.addFeature(f)
            else:
                layer.beginEditCommand("Feature edited")
                layer.changeGeometry(feat.id(), geom)
            layer.endEditCommand()
        else:

            if not editmode:
                layer.beginEditCommand("Feature added")
                dlg = QgsAttributeDialog(layer, f, True)
                dlg.setAttribute(QtCore.Qt.WA_DeleteOnClose)
                dlg.setMode(QgsAttributeEditorContext.AddFeatureMode)
            else:
                layer.beginEditCommand("Feature edited")
                dlg = QgsAttributeDialog(layer, f, True)

            ret = dlg.exec_()
            if ret:
                if editmode:
                    layer.changeGeometry(f.id(), geom)
                layer.endEditCommand()
            else:
                reply = QMessageBox.question(None, "Question", u"編集を続けますか？", QMessageBox.Yes,
                                             QMessageBox.No)
                if reply == QMessageBox.Yes:
                    continueFlag = True

                layer.destroyEditCommand()

        return continueFlag


    def checkSnapToPoint(self,point,layer):
        snapped = False
        snap_point = self.toMapCoordinates(point)
        if self.snapping:
            snapper = self.canvas.snappingUtils()
            snapMatch = snapper.snapToMap(point)
            if snapMatch.hasVertex():
                snppoint = snapMatch.point()
                #ここのpointはQgsPointになっているので、layerが必要
                snap_point = self.toMapCoordinates(layer,snppoint)
                snapped = True
        return snapped, snap_point



    # マウスがベジエのハンドルのどこにスナップしたか確認
    def getSnapPoint(self,event,layer):
        # どこにスナップしたか？のリスト、スナップしたポイント、線上にスナップした場合のポイントのidを返す
        snap_idx=["","","","",""]
        snapped = [False,False,False,False,False]
        snap_point = [None,None,None,None,None]

        self.snap_mark.hide()
        # snapしていない場合
        mouse_point = self.toMapCoordinates(event.pos())
        snapped[0], snap_point[0] = self.checkSnapToPoint(event.pos(), layer)
        if self.editing:
            point = self.toMapCoordinates(event.pos())
            d = self.canvas.mapUnitsPerPixel() * 4
            snapped[1], snap_point[1], snap_idx[1] = self.b.checkSnapToAnchor(point,self.selected_idx,d)
            if self.show_handle and self.mode == "bezier":
                snapped[2], snap_point[2], snap_idx[2] = self.b.checkSnapToHandle(point,d)
            snapped[3], snap_point[3], snap_idx[3] = self.b.checkSnapToLine(point,d)
            snapped[4], snap_point[4], snap_idx[4] = self.b.checkSnapToStart(point,d)

        # スナップマーカーの表示. ラインへのスナップは表示しない
        for i in [0,1,2,4]:
            if snapped[i]:
                self.snap_mark.setCenter(snap_point[i])
                self.snap_mark.show()
                break

        return mouse_point,snapped,snap_point,snap_idx

    # フィーチャーIDからフィーチャを返す
    def getFeatureById(self,layer,featid):
        features = [f for f in layer.getFeatures(QgsFeatureRequest().setFilterFids([featid]))]
        if len(features) != 1:
            return None
        else:
            return features[0]

    # ポイントから近いフィーチャを返す
    def getNearFeature(self, layer, point):
        d = self.canvas.mapUnitsPerPixel() * 4
        rect = QgsRectangle((point.x() - d), (point.y() - d), (point.x() + d), (point.y() + d))
        self.check_crs()
        if self.layerCRS.srsid() != self.projectCRS.srsid():
            rectGeom = QgsGeometry.fromRect(rect)
            rectGeom.transform(QgsCoordinateTransform(self.projectCRS, self.layerCRS, QgsProject.instance()))
            rect = rectGeom.boundingBox()
        request = QgsFeatureRequest()
        request.setLimit(1)
        request.setFilterRect(rect)
        f = [feat for feat in layer.getFeatures(request)]  # only one because of setlimit(1)
        if len(f)==0:
            return False,None
        else:
            return True,f[0]



    # アンドゥ処理
    def undo(self):
        history_length = self.b.undo()
        self.m.showBezierLineMarkers(self.show_handle)
        if history_length==0:
            self.resetPoints()

    def showHandle(self,checked):
        self.show_handle = checked
        self.m.showHandle(checked)

    def check_snapsetting(self):
        snap_cfg = self.iface.mapCanvas().snappingUtils().config()
        if snap_cfg.enabled():
            self.snapping = True
        else:
            self.snapping = False
        QgsMessageLog.logMessage("snapping:{}".format(self.snapping), 'MyPlugin')

    def check_crs(self):
        self.layerCRS = self.canvas.currentLayer().crs()
        self.projectCRS = self.canvas.mapSettings().destinationCrs()
        if self.projectCRS.projectionAcronym() == "longlat":
            QMessageBox.warning(None, "Warning", u"プロジェクトの投影法を緯度経度から変更してください")

    def activate(self):
        self.canvas.setCursor(self.addanchor_cursor)
        self.check_snapsetting()
        self.check_crs()
        self.snap_mark.hide()

    def deactivate(self):
        pass
    def isZoomTool(self):
        return False
    def isTransient(self):
        return False
    def isEditTool(self):
        return True
    def showSettingsWarning(self):
        pass
    def log(self, msg):
        QgsMessageLog.logMessage(msg, 'MyPlugin', Qgis.Info)
