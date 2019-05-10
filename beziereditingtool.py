# -*- coding: utf-8 -*-
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

        # unsplitでの矩形選択
        self.rubberBand = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.rubberBand.setColor(QColor(255, 0, 0, 100))
        self.rubberBand.setWidth(1)

        #　アイコン
        self.addanchor_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/anchor.svg'), 1, 1)
        self.insertanchor_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/anchor_add.svg'), 1, 1)
        self.deleteanchor_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/anchor_del.svg'), 1, 1)
        self.movehandle_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/handle.svg'), 1, 1)
        self.addhandle_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/handle_add.svg'), 1, 1)
        self.deletehandle_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/handle_del.svg'), 1, 1)
        self.drawline_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/drawline.svg'), 1, 1)
        self.split_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/mCrossHair.svg'), -1, -1)
        self.unsplit_cursor = QCursor(Qt.ArrowCursor)

       #　変数と初期設定
        self.mode = "bezier"  # bezier, pen , split, unsplit
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
                if self.editing:
                    # 逆向きにする
                    if snapped[4]:
                        self.b.flip_line()
                        self.m.showBezierLineMarkers(self.show_handle)
                    # 編集を確定する
                    else:
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
                    self.b.add_anchor(0,pnt,undo=False)
                    self.editing = True
                # 編集中でベジエ曲線かアンカーに近いなら修正
                elif self.editing and (snapped[1] or snapped[3]):
                    if snapped[1]:
                        pnt = snap_point[1]
                    elif snapped[3]:
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
                if self.editing and self.editing_feature_id:
                    # 作成するオブジェクトをgeomに変換。修正するためのフィーチャーも取得
                    type = layer.geometryType()
                    if type == QgsWkbTypes.LineGeometry:
                        if snapped[1]:
                            lineA, lineB = self.b.split_line(snap_idx[1], snap_point[1], isAnchor=True)
                        elif snapped[3]:
                            lineA, lineB = self.b.split_line(snap_idx[3], snap_point[3], isAnchor=False)
                        else:
                            return

                        if layer.wkbType() == QgsWkbTypes.LineString:
                            geomA = QgsGeometry.fromPolylineXY(lineA)
                            geomB = QgsGeometry.fromPolylineXY(lineB)
                        elif layer.wkbType() == QgsWkbTypes.MultiLineString:
                            geomA = QgsGeometry.fromMultiPolylineXY([lineA])
                            geomB = QgsGeometry.fromMultiPolylineXY([lineB])

                        feature = self.getFeatureById(layer, self.editing_feature_id)
                        _, _ = self.createFeature(geomB, feature, editmode=False, showdlg=False)
                        f, _ = self.createFeature(geomA, feature, editmode=True, showdlg=False)
                        layer.removeSelection()
                        layer.select(f.id())
                        self.resetPoints()

                    else:
                        QMessageBox.warning(None, "Warning", u"レイヤのタイプが違います")
                        #self.resetPoints()
                else:
                    QMessageBox.warning(None, "Warning", u"切断できるフィーチャーがありません")
        elif self.mode == "unsplit":
            # 右クリックで確定
            if event.button() == Qt.RightButton:
                #結合処理
                self.unsplit()
            # 左クリック
            elif event.button() == Qt.LeftButton:
                #選択処理
                self.endPoint = self.startPoint = mouse_point
                self.isEmittingPoint = True
                self.showRect(self.startPoint, self.endPoint)

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
                self.b.move_handle(self.selected_idx, mouse_point,undo=False)
                self.m.moveHandleMarker(self.selected_idx, mouse_point)
            # 選択されたアンカーの移動
            elif self.mouse_state=="move_anchor":
                pnt = snap_point[0]
                if snapped[1]:
                    pnt = snap_point[1]
                self.b.move_anchor(self.selected_idx, pnt, undo=False)
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
        elif self.mode == "unsplit":
            self.canvas.setCursor(self.unsplit_cursor)
            if not self.isEmittingPoint:
                return
            self.endPoint = mouse_point
            self.showRect(self.startPoint, self.endPoint)

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
        elif self.mode == "unsplit":
            self.isEmittingPoint = False
            r = self.rectangle()
            if r is not None:
                self.reset_unsplit()
                self.selectFeatures(mouse_point, r)
            else:
                self.selectFeatures(mouse_point)

        self.m.showHandle(self.show_handle)

    ####### イベント処理からの呼び出し
    # ベジエ関係
    def start_editing(self,layer,mouse_point):
        # 編集開始
        near, f = self.getNearFeatures(layer, mouse_point)
        if near:
            ret = self.convertFeatureToBezier(f[0])
            if ret:
                self.editing_feature_id = f[0].id()
                self.editing = True

    def finish_editing(self,layer):

        #self.log("{}".format(num_anchor))
        # 作成するオブジェクトをgeomに変換。修正するためのフィーチャーも取得
        layer_type = layer.geometryType()
        layer_wkbtype = layer.wkbType()
        result,geom = self.b.asGeometry(layer_type,layer_wkbtype)
        if result is None:
            self.resetPoints()
        elif result is False:
            QMessageBox.warning(None, "Warning", u"レイヤのタイプが違います")
        else:
            # 新規
            if  self.editing_feature_id is None:
                f, continueFlag = self.createFeature(geom, None, editmode=False)
            # 修正
            else:
                feature = self.getFeatureById(layer, self.editing_feature_id)
                if feature is None:
                    QMessageBox.warning(None, "Warning", u"レイヤを確かめてください")
                    self.resetPoints()
                else:
                    f,continueFlag = self.createFeature(geom, feature, editmode=True)
            if continueFlag is False:
                self.resetPoints()
        self.canvas.refresh()

    # ペン関係
    def convert_draw_line(self,snap_to_start):
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

        f = QgsFeature()
        fields = layer.fields()
        f.setFields(fields)
        f.setGeometry(geom)
        # add attribute fields to feature

        if feat is not None:
            for i in range(fields.count()):
                f.setAttribute(i, feat.attributes()[i])

        settings = QSettings()
        disable_attributes = settings.value("/qgis/digitizing/disable_enter_attribute_values_dialog", False, type=bool)
        if disable_attributes or showdlg is False:
            if not editmode:
                layer.beginEditCommand("Bezier added")
                layer.addFeature(f)
            else:
                #changeGeometryが上手く動かないため追加して、削除
                layer.beginEditCommand("Bezier edited")
                layer.addFeature(f)
                layer.deleteFeature(feat.id())
            layer.endEditCommand()
        else:
            if not editmode:
                dlg = QgsAttributeDialog(layer, f, True)
                dlg.setAttribute(QtCore.Qt.WA_DeleteOnClose)
                dlg.setMode(QgsAttributeEditorContext.AddFeatureMode)
                dlg.setEditCommandMessage("Bezier added")
                ok = dlg.exec_()
                if not ok:
                    reply = QMessageBox.question(None, "Question", u"編集を続けますか？", QMessageBox.Yes,
                                                 QMessageBox.No)
                    if reply == QMessageBox.Yes:
                        continueFlag = True
            else:
                layer.beginEditCommand("Bezier edited")
                f=feat
                dlg = self.iface.getFeatureForm(layer, f)
                ok = dlg.exec_()
                if ok:
                    layer.changeGeometry(f.id(), geom)
                    layer.endEditCommand()
                else:
                    layer.destroyEditCommand()
                    reply = QMessageBox.question(None, "Question", u"編集を続けますか？", QMessageBox.Yes,
                                                 QMessageBox.No)
                    if reply == QMessageBox.Yes:
                        continueFlag = True
        return f, continueFlag

    def checkSnapToPoint(self,point,layer):
        snapped = False
        snap_point = self.toMapCoordinates(point)
        if self.snapping:
            snapper = self.canvas.snappingUtils()
            snapMatch = snapper.snapToMap(point)
            if snapMatch.hasVertex():
                snap_point = snapMatch.point()
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

    # ポイントまたは矩形から近いフィーチャを返す
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

    def check_crs(self):
        self.layerCRS = self.canvas.currentLayer().crs()
        self.projectCRS = self.canvas.mapSettings().destinationCrs()
        if self.projectCRS.projectionAcronym() == "longlat":
            QMessageBox.warning(None, "Warning", u"プロジェクトの投影法を緯度経度から変更してください")

    # unsplit 関係
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
            elif not near:
                layer.layer().removeSelection()

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

    def reset_unsplit(self):
        self.startPoint = self.endPoint = None
        self.isEmittingPoint = False
        self.rubberBand.reset(QgsWkbTypes.PolygonGeometry)

    def distance(self, p1, p2):
        dx = p1[0] - p2[0]
        dy = p1[1] - p2[1]
        return math.sqrt(dx * dx + dy * dy)

    def unsplit(self):
        layer = self.canvas.currentLayer()
        if layer.geometryType() == QgsWkbTypes.LineGeometry:
            selected_features = layer.selectedFeatures()
            if len(selected_features) == 2:
                f0 = selected_features[0]
                f1 = selected_features[1]
                geom0 = f0.geometry()
                geom0.convertToSingleType()
                geom1 = f1.geometry()
                geom1.convertToSingleType()
                line0 = geom0.asPolyline()
                line1 = geom1.asPolyline()
                #端点のすべての組み合わせから距離が最小の点と点をくっつける
                dist = [self.distance(li0, li1) for li0, li1 in
                        [(line0[-1], line1[0]), (line0[0], line1[-1]), (line0[0], line1[0]), (line0[-1], line1[-1])]]
                type = dist.index(min(dist))
                if type == 0:
                    pass
                elif type == 1:
                    line0.reverse()
                    line1.reverse()
                elif type == 2:
                    line0.reverse()
                elif type == 3:
                    line1.reverse()
                # 端点が同じ位置なら
                if line0[-1] == line1[0]:
                    line = line0 + line1[1:]
                # 端点が離れている場合は、間を直線のベジエで補間
                else:
                    b = BezierGeometry()
                    b.add_anchor(0, line0[-1], undo=False)
                    b.add_anchor(1, line1[0], undo=False)
                    interporate_line = b.asPolyline()
                    line = line0 + interporate_line[1:] + line1[1:]

                if layer.wkbType()== QgsWkbTypes.LineString:
                    geom = QgsGeometry.fromPolylineXY(line)
                elif layer.wkbType()== QgsWkbTypes.MultiLineString:
                    geom = QgsGeometry.fromMultiPolylineXY([line])

                layer.beginEditCommand("Bezier unsplit")
                settings = QSettings()
                disable_attributes = settings.value("/qgis/digitizing/disable_enter_attribute_values_dialog", False,
                                                    type=bool)
                if disable_attributes:
                    layer.changeGeometry(f0.id(), geom)
                    layer.deleteFeature(f1.id())
                    layer.endEditCommand()
                else:
                    dlg = self.iface.getFeatureForm(layer, f0)
                    if dlg.exec_():
                        layer.changeGeometry(f0.id(), geom)
                        layer.deleteFeature(f1.id())
                        layer.endEditCommand()
                    else:
                        layer.destroyEditCommand()
                self.canvas.refresh()
            else:
                QMessageBox.warning(None, "Warning", u"2本のラインを選択してください")
                #self.iface.messageBar().pushWarning("Warning", "Select two feature!")
        else:
            QMessageBox.warning(None, "Warning", u"ラインレイヤを選択してください")
            #self.iface.messageBar().pushWarning("Warning", "Only Support LineString")



    def activate(self):
        self.canvas.setCursor(self.addanchor_cursor)
        self.check_snapsetting()
        self.check_crs()
        self.snap_mark.hide()
        self.reset_unsplit()

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
