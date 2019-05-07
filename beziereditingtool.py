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
        self.pen_rbl.setColor(QColor(255, 255, 0, 150))
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
        self.moveFlag = False  # クリックかドラッグかの判定（リリース時）
        self.mouse_state = "free" # free, add_anchor,move_anchor,move_handle,insert_anchor,draw_newline,draw_updateline
        self.editing = False #オブジェクト作成、修正中
        self.modify = False #オブジェクトの修正かどうか（すでに属性が入っている）
        self.snapping = None #スナップが設定されているかどうか
        self.show_handle = False  # ベジエマーカーを表示するかどうか
        self.featid = None # 編集オブジェクトのid
        self.selected_point_idx = None # 選択されたアンカーもしくはハンドルのインデックス. ドラッグ時の識別のために使用
        self.history = [] # undo履歴
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
        orgpoint, snaptype, point, snapidx = self.getSnapPoint(event, layer)
        #self.log("{}".format(snaptype))
        if self.mode == "bezier":
            self.moveFlag = False
            # ベジエツールで右クリック
            if event.button() == Qt.RightButton:
                # 編集を確定する
                if self.editing:
                    self.finish_drawing(layer)
                # ベジエに変換する
                else:
                    self.start_modify(layer,orgpoint)
            # ベジエで左クリック
            elif event.button() == Qt.LeftButton:
                # Ctrlを押しながら
                if self.ctrl:
                    # アンカーと重なっていてもアンカーを追加したいとき。ポリゴンを閉じたいときなど。
                    if snaptype[1]:
                        self.mouse_state = "add_anchor"
                        self.selected_point_idx = self.b.anchorCount()
                        self.history.append({"state": "add_anchor", "pointidx": self.selected_point_idx})
                        self.b.addAnchor(-1, point[1])
                        self.m.addAnchorMarker(-1, point[1])

                # Altを押しながら
                elif self.alt:
                    # アンカーからハンドルを引き出すとき
                    if snaptype[2] and snaptype[1]:
                        self.mouse_state = "move_handle"
                        self.selected_point_idx = snapidx[2]
                    # アンカーを挿入するとき
                    # invert_bezierを利用してハンドルを再計算できる。
                    elif snaptype[3] and not snaptype[1]:
                        self.mouse_state = "insert_anchor"
                        anchor_idx = self.b.AnchorIdx(snapidx[3])
                        self.selected_point_idx = anchor_idx
                        self.history.append(
                            {"state": "insert_anchor",
                             "pointidx": anchor_idx,
                             "ctrlpoint0": self.b.getHandle((anchor_idx - 1) * 2 + 1),
                             "ctrlpoint1": self.b.getHandle((anchor_idx - 1) * 2 + 2)
                             }
                        )
                        self.b.insertAnchorPointToBezier(snapidx[3], point[3])
                        self.m.showBezierLineMarkers()

                # Shiftを押しながら
                elif self.shift:
                    # アンカーを削除するとき
                    if snaptype[1]:
                        idx = snapidx[1]
                        self.history.append(
                            {"state": "delete_anchor",
                             "pointidx": idx,
                             "point": point[1],
                             "ctrlpoint0": self.b.getHandle(idx * 2),
                             "ctrlpoint1": self.b.getHandle(idx * 2 + 1)
                            }
                        )
                        self.b.deleteAnchor(idx)
                        self.m.deleteAnchorMarker(idx)
                    # ハンドルを削除するとき
                    elif snaptype[2]:
                        self.history.append(
                            {"state": "delete_handle",
                             "pointidx": snapidx[2],
                             "point": point[2],
                            }
                        )
                        idx = snapidx[2]
                        pnt = self.b.getAnchor(int(idx / 2))
                        self.b.moveHandle(idx, pnt)
                        self.m.moveHandleMarker(idx, pnt)
                else:
                    # a. ハンドルの移動
                    # b. ポイントの移動
                    # c. 新規ポイントの追加
                    # 判定の順番が重要

                    # 「ポイントの移動」かどうか
                    if snaptype[1]:
                        self.mouse_state = "move_anchor"
                        self.selected_point_idx = snapidx[1]
                        self.history.append({"state": "move_anchor", "pointidx": self.selected_point_idx,"point":point[1]})
                    # 「ハンドルの移動」かどうか
                    elif snaptype[2]:
                        self.mouse_state="move_handle"
                        self.selected_point_idx = snapidx[2]
                        self.history.append({"state": "move_handle", "pointidx": self.selected_point_idx, "point": point[2]})
                    else:
                    # 上のどれでもなければ「新規ポイント追加」
                        if not self.editing:
                            self.b = BezierGeometry()
                            self.m = BezierMarker(self.canvas, self.b)
                            self.editing = True
                        self.mouse_state = "add_anchor"
                        self.selected_point_idx = self.b.anchorCount()
                        self.history.append({"state": "add_anchor", "pointidx": self.selected_point_idx})
                        self.b.addAnchor(-1, point[0])
                        self.m.addAnchorMarker(-1, point[0])

        elif self.mode == "pen":
            # 右クリックで確定
            if event.button() == Qt.RightButton:
                if self.editing:
                    self.finish_drawing(layer)
                else:
                    if layer.geometryType() != QgsWkbTypes.LineGeometry:
                        QMessageBox.warning(None, "Warning", u"ライン以外はベジエに変換できません")
                        return
                    self.start_modify(layer,orgpoint)
            # 左クリック
            elif event.button() == Qt.LeftButton:
                if self.editing and snaptype[3]:
                    #編集中で編集中のラバーバンドに近いなら
                    self.editing = True
                    self.mouse_state = "draw_updateline"
                    self.pen_rbl.reset(QgsWkbTypes.LineGeometry)
                    self.pen_rbl.addPoint(point[3])
                elif not self.editing:
                    #新規作成なら
                    self.b = BezierGeometry()
                    self.m = BezierMarker(self.canvas, self.b)
                    self.editing = True
                    self.mouse_state = "draw_newline"
                    self.m.bezier_rbl.reset(QgsWkbTypes.LineGeometry)  # ベイジライン
                    self.m.bezier_rbl.addPoint(orgpoint)  # 最初のポイントは同じ点が2つ追加される仕様？
        elif self.mode == "split":
            # 右クリックで確定
            if event.button() == Qt.RightButton:
                if self.editing:
                    self.finish_drawing(layer)
                else:
                    if layer.geometryType() != QgsWkbTypes.LineGeometry:
                        QMessageBox.warning(None, "Warning", u"ライン以外はベジエに変換できません")
                        return
                    self.start_modify(layer,orgpoint)
            # 左クリック
            elif event.button() == Qt.LeftButton:
                # 編集中で編集中のラバーバンドに近いなら
                if self.editing and snaptype[3] and not snaptype[1]:
                    if self.featid is None:
                        QMessageBox.warning(None, "Warning", u"フィーチャーがありません")
                        return

                    lineA, lineB = self.b.splitLine(snapidx[3],point[3])

                    feature = self.getFeatureById(layer, self.featid)
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
                        self.featid = None
                        self.editing = False
                        self.modify = False
                        return

                    self.createFeature(geomB, feature)
                    self.editFeature(geomA, feature, False)
                    layer.select(feature.id())

                    self.resetPoints()
                    self.featid = None
                    self.editing = False
                    self.modify = False


    def canvasMoveEvent(self, event):
        layer = self.canvas.currentLayer()
        if not layer or layer.type() != QgsMapLayer.VectorLayer:
            return
        orgpoint, snaptype, point, snapidx = self.getSnapPoint(event, layer)
        if self.mode == "bezier":
            #self.log("{}".format(self.mouse_state))
            self.moveFlag = True
            # 追加時のドラッグはハンドルの移動
            if self.mouse_state=="add_anchor" or self.mouse_state=="insert_anchor":
                self.updateHandle(point[0])
            elif self.alt and snaptype[1] and snaptype[2]:
                self.canvas.setCursor(self.addhandle_cursor)
            elif self.alt and snaptype[3] and not snaptype[1]:
                self.canvas.setCursor(self.insertanchor_cursor)
            elif self.ctrl and snaptype[1]:
                self.canvas.setCursor(self.insertanchor_cursor)
            elif self.shift and snaptype[1]:
                self.canvas.setCursor(self.deleteanchor_cursor)
            elif self.shift and snaptype[2]:
                self.canvas.setCursor(self.deletehandle_cursor)
            # 選択されたハンドルの移動
            elif self.mouse_state=="move_handle":
                self.b.moveHandle(self.selected_point_idx, orgpoint)
                self.m.moveHandleMarker(self.selected_point_idx, orgpoint)
            # 選択されたポイントの移動
            elif self.mouse_state=="move_anchor":
                pnt = point[0]
                #ポイントとスナップしたら
                if snaptype[1]:
                    pnt = point[1]
                self.b.moveAnchor(self.selected_point_idx, pnt)
                self.m.moveAnchorMarker(self.selected_point_idx, pnt)
            else:
                if snaptype[1]:
                    self.canvas.setCursor(self.movehandle_cursor)
                elif snaptype[2]:
                    self.canvas.setCursor(self.movehandle_cursor)
                else:
                    self.canvas.setCursor(self.addanchor_cursor)
        elif self.mode == "pen":
            self.canvas.setCursor(self.drawline_cursor)
            pnt = orgpoint
            # スタートポイントとスナップしてるなら
            if snaptype[4]:
                pnt = point[4]
            if self.mouse_state == "draw_newline":
                self.m.bezier_rbl.addPoint(pnt)
            elif self.mouse_state == "draw_updateline":
                self.pen_rbl.addPoint(pnt)
        elif self.mode == "split":
            self.canvas.setCursor(self.split_cursor)

    def canvasReleaseEvent(self, event):
        layer = self.canvas.currentLayer()
        if not layer or layer.type() != QgsMapLayer.VectorLayer:
            return
        orgpoint, snaptype, point, _ = self.getSnapPoint(event, layer)
        if self.mode == "bezier":
            self.selected_point_idx = None
            self.mouse_state="free"
            self.moveFlag=False
        elif self.mode == "pen":
            # ドロー終了
            if self.mouse_state != "free":
                if self.mouse_state == "draw_updateline":
                    self.draw_updateline(snaptype)
                elif self.mouse_state == "draw_newline":
                    self.draw_newline(snaptype)
                self.mouse_state = "free"
        elif self.mode == "split":
            self.selected_point_idx = None
            self.mouse_state = "free"
            self.moveFlag = False

        self.m.showHandle(self.show_handle)
            
    ####### イベント処理からの呼び出し
    # ベジエ関係
    def start_modify(self,layer,orgpoint):
        # 編集開始
        near, f = self.getNearFeature(layer, orgpoint)
        if near:
            self.featid = f.id()
            ret = self.convertFeatureToBezier(f)
            if ret:
                # self.log("edit start")
                self.editing = True
                self.modify = True

    def finish_drawing(self,layer):
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
            self.resetPoints()
            self.featid = None
            self.editing = False
            self.modify = False
            return

        if self.modify:
            feature = self.getFeatureById(layer, self.featid)
            if feature is None:
                QMessageBox.warning(None, "Warning", u"レイヤを確かめてください")
                self.resetPoints()
                self.featid = None
                self.editing = False
                self.modify = False
                return
            continueFlag = self.editFeature(geom, feature)
        else:
            continueFlag = self.createFeature(geom)

        if continueFlag is False:
            self.resetPoints()
            self.featid = None
            self.editing = False
            self.modify = False

        self.canvas.refresh()

    # ジオメトリのペンでの修正
    def modify_bezier(self, update_geom, org_geom):
        update_line = update_geom.asPolyline()
        org_line = org_geom.asPolyline()

        startpnt = update_line[0]
        lastpnt = update_line[-1]
        startpnt_is_near, start_anchoridx, start_vertexidx = self.closestAnchorOfGeometry(startpnt, org_geom)
        lastpnt_is_near, last_anchoridx, last_vertexidx = self.closestAnchorOfGeometry(lastpnt, org_geom)
        # self.log("{},{}".format(len(points),len(org_line)))
        # org_lineとupdate_lineの交差する周辺のベクトルの内積を計算。正なら順方向、不なら逆方向
        v1 = np.array(org_line[start_vertexidx]) - np.array(org_line[start_vertexidx - 1])
        v2 = np.array(update_line[1]) - np.array(update_line[0])
        direction = np.dot(v1, v2)
        self.history.append({"state": "start_pen"})
        # 逆方向ならorg_lineとベジエを定義しているのアンカー、ハンドル関連のリストを逆順にする
        if direction < 0:
            org_line.reverse()
            reversed_geom = QgsGeometry.fromPolylineXY(org_line)
            startpnt_is_near, start_anchoridx, start_vertexidx = self.closestAnchorOfGeometry(startpnt, reversed_geom)
            lastpnt_is_near, last_anchoridx, last_vertexidx = self.closestAnchorOfGeometry(lastpnt, reversed_geom)
            self.b.flipBezierLine()
        # 編集箇所の前のハンドルから今のところまでをくっつける
        # ベジエ区間ごとのポイントリスト　を作成
        point_list = self.b.pointList(org_line)
        # A 部分の修正. startpnt_is_nearは修正開始の時点で確定している.
        if lastpnt_is_near and last_vertexidx > start_vertexidx and last_anchoridx <= len(point_list):
            polyline = point_list[start_anchoridx - 1][0:self.b.pointListIdx(start_vertexidx)] + \
                       update_line + \
                       point_list[last_anchoridx - 1][self.b.pointListIdx(last_vertexidx):]
            geom = self.convertLineToSimpleGeom(polyline)

            for i in range(start_anchoridx, last_anchoridx):
                self.history.append(
                    {"state": "delete_anchor",
                     "pointidx": start_anchoridx,
                     "point": self.b.getAnchor(start_anchoridx),
                     "ctrlpoint0": self.b.getHandle(start_anchoridx * 2),
                     "ctrlpoint1": self.b.getHandle(start_anchoridx * 2 + 1)
                     }
                )
                self.b.deleteAnchor(start_anchoridx)

            pointnum, cp_first, cp_last = self.b.insertGeomToBezier(start_anchoridx, geom, last=False)
            self.history.append({"state": "insert_geom", "pointidx": start_anchoridx, "pointnum": pointnum, "cp_first": cp_first, "cp_last": cp_last})

            self.m.showBezierLineMarkers()
            # self.history.append({"state": "end_pen"})
        # B 終点が離れる場合。終点が線上でも逆方向に戻っている場合、始点に閉じる場合、最終点に近い場合。
        elif not lastpnt_is_near or (lastpnt_is_near and last_vertexidx <= start_vertexidx) or last_anchoridx > len(
                point_list):
            if start_anchoridx == self.b.anchorCount():  # 右端の場合はそのまま。
                polyline = update_line
            else:  # ベジエ区間の中の何個目のポイントからか調べて、くっつける
                polyline = point_list[start_anchoridx - 1][0:self.b.pointListIdx(start_vertexidx)] + update_line
            geom = self.convertLineToSimpleGeom(polyline)

            for i in range(start_anchoridx, self.b.anchorCount()):
                self.history.append(
                    {"state": "delete_anchor",
                     "pointidx": start_anchoridx,
                     "point": self.b.getAnchor(start_anchoridx),
                     "ctrlpoint0": self.b.getHandle(start_anchoridx * 2),
                     "ctrlpoint1": self.b.getHandle(start_anchoridx * 2 + 1)
                     }
                )
                self.b.deleteAnchor(start_anchoridx)

            pointnum, cp_first,_ = self.b.insertGeomToBezier(start_anchoridx, geom, last=True)
            self.history.append(
                {"state": "insert_geom", "pointidx": start_anchoridx, "pointnum": pointnum, "cp_first": cp_first,
                 "cp_last": None})
            self.m.showBezierLineMarkers()
        self.history.append({"state": "end_pen", "direction": "forward"})
        # ベジエの方向を元に戻す
        if direction < 0:
            self.b.flipBezierLine()
            self.history[-1]["direction"] = "reverse"

    def updateHandle(self, point):
        # ハンドルを更新
        p = self.b.getAnchor(self.selected_point_idx)
        pb = QgsPointXY(p[0] - (point[0] - p[0]), p[1] - (point[1] - p[1]))
        idx = self.selected_point_idx * 2
        self.b.moveHandle(idx, pb)
        self.b.moveHandle(idx + 1, point)
        self.m.moveHandleMarker(idx, pb)
        self.m.moveHandleMarker(idx + 1, point)

    # ペン関係
    def draw_newline(self,snaptype):
        # スムーズ処理してrbを付け替える
        if self.m.bezier_rbl.numberOfVertices() <= 2: #クリックいた場合は無視
            self.m.bezier_rbl.reset(QgsWkbTypes.LineGeometry)
            self.editing = False
            return
        rbgeom = self.m.bezier_rbl.asGeometry()
        rbline = rbgeom.asPolyline()
        geom = self.convertLineToSimpleGeom(rbline)
        self.history.append({"state": "start_pen"})
        pointnum,_,_ = self.b.insertGeomToBezier(0,geom,last=True)
        self.history.append(
            {"state": "insert_geom", "pointidx": 0, "pointnum": pointnum, "cp_first": None,
             "cp_last": None})
        self.history.append({"state": "end_pen","direction":"forward"})
        # スタートポイントにスナップしていたらスムーズ処理でずれた最後の点を最初のポイントに動かす
        if snaptype[4]:
            self.b.moveAnchor(self.b.anchorCount() - 1, self.b.getAnchor(0))
        self.m.showBezierLineMarkers()

    def draw_updateline(self,snaptype):
        if self.pen_rbl.numberOfVertices() <= 2:
            self.pen_rbl.reset(QgsWkbTypes.LineGeometry)
            return
        org_geom = self.m.bezier_rbl.asGeometry()
        update_geom = self.pen_rbl.asGeometry()
        self.modify_bezier(update_geom, org_geom)  # 編集箇所の次のハンドル以降を削除
        # スタートポイントにスナップしていたらスムーズ処理でずれた最後の点を最初のポイントに動かす
        if snaptype[4]:
            self.b.moveAnchor(self.b.anchorCount() - 1, self.b.getAnchor(0))
            self.m.moveAnchorMarker(self.b.anchorCount() - 1, self.b.getAnchor(0))
        self.pen_rbl.reset()
        
 
    # アンドゥ処理
    def undo(self):
        if len(self.history)>0:
            act = self.history.pop()
            if act["state"]=="add_anchor":
                self.b.deleteAnchor(act["pointidx"])
            elif act["state"]=="move_anchor":
                self.b.moveAnchor(act["pointidx"],act["point"])
            elif act["state"]=="move_handle":
                self.b.moveHandle(act["pointidx"],act["point"])
            elif act["state"]=="insert_anchor":
                self.b.deleteAnchor(act["pointidx"])
                self.b.moveHandle((act["pointidx"]-1) * 2 + 1, act["ctrlpoint0"])
                self.b.moveHandle((act["pointidx"]-1) * 2 + 2, act["ctrlpoint1"])
            elif act["state"]=="delete_anchor":
                self.b.addAnchor(act["pointidx"],act["point"])
                self.b.moveHandle(act["pointidx"] * 2, act["ctrlpoint0"])
                self.b.moveHandle(act["pointidx"] * 2+1, act["ctrlpoint1"])
            elif act["state"] == "delete_handle":
                self.b.moveHandle(act["pointidx"], act["point"])
            elif act["state"]=="end_pen":
                direction = act["direction"]
                if direction=="reverse":
                    self.b.flipBezierLine()
                act = self.history.pop()
                while act["state"] !="start_pen":
                    if act["state"] == "insert_geom":
                        for i in range(act["pointnum"]):
                            self.b.deleteAnchor(act["pointidx"])
                        if act["cp_first"] is not None:
                            self.b.moveHandle(act["pointidx"] * 2 - 1, act["cp_first"])
                        if act["cp_last"] is not None:
                            self.b.moveHandle(act["pointidx"] * 2, act["cp_last"])
                    elif act["state"]=="delete_anchor":
                        self.b.addAnchor(act["pointidx"], act["point"])
                        self.b.moveHandle(act["pointidx"] * 2, act["ctrlpoint0"])
                        self.b.moveHandle(act["pointidx"] * 2 + 1, act["ctrlpoint1"])
                    act = self.history.pop()
                if direction=="reverse":
                    self.b.flipBezierLine()
            self.m.showBezierLineMarkers(self.show_handle)

        if len(self.history)==0:
            self.resetPoints()
            self.featid = None
            self.editing = False
            self.modify = False

    # ポイント、ハンドルの配列、マーカー、ラインとベジエライン、履歴を初期化
    def resetPoints(self):
        self.m.removeBezierLineMarkers()
        self.b.reset()
        self.history = []
        self.alt = False
        self.ctrl = False

    # フィーチャをベジエ曲線のハンドルに変換
    def convertFeatureToBezier(self, f):
        geom = QgsGeometry(f.geometry())
        self.check_crs()
        if self.layerCRS.srsid() != self.projectCRS.srsid():
            geom.transform(QgsCoordinateTransform(self.layerCRS, self.projectCRS, QgsProject.instance()))

        if geom.type() == QgsWkbTypes.PointGeometry:
            point = geom.asPoint()
            self.b = BezierGeometry.converPointToBezier(point)
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



    ########ジオメトリ、フィーチャー　ツール
    # ポイントに近いジオメトリ上のポイントを返す
    def closestPointOfGeometry(self,point,geom):
        #フィーチャとの距離が近いかどうかを確認
        near = False
        (dist, minDistPoint, afterVertex,leftOf)=geom.closestSegmentWithContext(point)
        d = self.canvas.mapUnitsPerPixel() * 10
        if math.sqrt(dist) < d:
            near = True
        return near,minDistPoint,afterVertex
    # 描画の開始ポイントとのスナップを調べる
    def getSelfSnapPoint(self,p,point):
        d = self.canvas.mapUnitsPerPixel() * 4
        if (p.x() - d <= point.x() <= p.x() + d) and (p.y() - d <= point.y() <= p.y() + d):
            return True,p
        return False,None
    # ポインタの次のアンカーのidとvertexのidを返す。アンカーとスナップしている場合は、次のIDを返す。右端のアンカーの処理は注意
    def closestAnchorOfGeometry(self,point,geom):
        near = False
        (dist, minDistPoint, vertexidx, leftOf) = geom.closestSegmentWithContext(point)
        anchoridx = self.b.AnchorIdx(vertexidx)
        d = self.canvas.mapUnitsPerPixel() * 10
        if math.sqrt(dist) < d:
            near = True
        return near, anchoridx, vertexidx

    def createFeature(self, geom, feat=None):
        continueFlag = False
        layer = self.canvas.currentLayer()
        provider = layer.dataProvider()
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
        if disable_attributes or feat is not None:
            layer.beginEditCommand("Feature added")
            layer.addFeature(f)
            layer.endEditCommand()
        else:
            dlg = QgsAttributeDialog(layer, f, True)
            dlg.setAttribute(QtCore.Qt.WA_DeleteOnClose)
            dlg.setMode(QgsAttributeEditorContext.AddFeatureMode)
            dlg.setEditCommandMessage("Feature added")
            if dlg.exec_():
                pass
            else:
                reply = QMessageBox.question(None, "Question", u"編集を続けますか？", QMessageBox.Yes,
                                             QMessageBox.No)
                if reply == QMessageBox.Yes:
                    continueFlag = True
        return continueFlag

    def editFeature(self,geom,feat,showdlg=True):
        continueFlag = False
        layer = self.canvas.currentLayer()
        self.check_crs()
        if self.layerCRS.srsid() != self.projectCRS.srsid():
            geom.transform(QgsCoordinateTransform(self.projectCRS, self.layerCRS, QgsProject.instance()))
        layer.beginEditCommand("Feature edited")
        settings = QSettings()
        disable_attributes = settings.value("/qgis/digitizing/disable_enter_attribute_values_dialog", False, type=bool)
        if disable_attributes or showdlg is False:
            layer.changeGeometry(feat.id(), geom)
            layer.endEditCommand()
        else:
            dlg = self.iface.getFeatureForm(layer, feat)
            if dlg.exec_():
                layer.changeGeometry(feat.id(), geom)
                layer.endEditCommand()
            else:
                reply = QMessageBox.question(None, "Question", u"編集を続けますか？", QMessageBox.Yes,
                                             QMessageBox.No)
                if reply == QMessageBox.Yes:
                    continueFlag = True
        return continueFlag
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
    # マウスがベジエのハンドルのどこにスナップしたか確認
    def getSnapPoint(self,event,layer):
        # どこにスナップしたか？のリスト、スナップしたポイント、線上にスナップした場合のポイントのidを返す
        idx=["","","","",""]
        snaptype = [False,False,False,False,False]
        pnt = [None,None,None,None,None]
        self.snap_mark.hide()
        point = event.pos()
        # snapしていない場合
        orgpoint = self.toMapCoordinates(point)
        pnt[0] = orgpoint
        if self.snapping:
            snapper = self.canvas.snappingUtils()
            snapMatch = snapper.snapToMap(point)
            if snapMatch.hasVertex():
                snppoint = snapMatch.point()
                self.snap_mark.setCenter(snppoint)
                self.snap_mark.show()
                #ここのpointはQgsPointになっているので、layerが必要
                pnt[0] = self.toMapCoordinates(layer,snppoint)
                snaptype[0]=True
        point = self.toMapCoordinates(point)

        if self.editing:
            # 「アンカーと近い」かどうか.
            for i, p in reversed(list(enumerate(self.b.anchor))):
                snapped, snppoint = self.getSelfSnapPoint(p, point)
                # freeの時にマウス位置がポイントかどうか調べたい場合
                if self.selected_point_idx is None:
                    if snapped:
                        snaptype[1] = True
                        idx[1] = i
                        pnt[1] = snppoint
                        self.snap_mark.setCenter(snppoint)
                        self.snap_mark.show()
                        break
                # ドラッグしているポイントが他のポイントと近いかどうかを調べたい場合
                elif self.selected_point_idx != i:
                    if snapped:
                        snaptype[1] = True
                        idx[1] = i
                        pnt[1] = snppoint
                        break
            # 「ハンドルと近い」かどうか
            for i, p in reversed(list(enumerate(self.b.handle))):
                snapped,snppoint = self.getSelfSnapPoint(p,point)
                if snapped and self.show_handle and self.mode=="bezier":
                    snaptype[2]=True
                    idx[2]=i
                    pnt[2] = snppoint
                    self.snap_mark.setCenter(snppoint)
                    self.snap_mark.show()
                    break
            # 「線上かどうか for pen」
            if self.m.bezier_rbl.numberOfVertices() > 0:
                p=[]
                for i in range(self.m.bezier_rbl.numberOfVertices()):
                    p.append(self.m.bezier_rbl.getPoint(0,i))
                geom = QgsGeometry.fromPolylineXY(p)
                (dist, minDistPoint, afterVertex, leftOf) = geom.closestSegmentWithContext(point)
                d = self.canvas.mapUnitsPerPixel() * 10
                if math.sqrt(dist) < d:
                    snaptype[3] = True
                    idx[3] = afterVertex
                    pnt[3] = minDistPoint
            # 「スタートポイントかどうか for pen」
                p=self.m.bezier_rbl.getPoint(0, 0)
                snapped, snppoint = self.getSelfSnapPoint(p, point)
                if snapped:
                    snaptype[4]=True
                    idx[4]=0
                    pnt[4] = snppoint
                    self.snap_mark.setCenter(snppoint)
                    self.snap_mark.show()
        return orgpoint,snaptype,pnt,idx

    ########ツール（基礎的な関数）
    #移動平均でスムージング
    def smoothing(self,polyline):
        poly=np.reshape(polyline,(-1,2)).T
        num = 8
        b = np.ones(num) / float(num)
        x_pad = np.pad(poly[0], (num-1, 0), 'edge')
        y_pad = np.pad(poly[1], (num-1, 0), 'edge')
        x_smooth = np.convolve(x_pad, b, mode='valid')
        y_smooth = np.convolve(y_pad, b, mode='valid')
        poly_smooth = [QgsPointXY(x, y) for x,y in zip(x_smooth,y_smooth)]
        return poly_smooth
    #ポイント間の距離
    def distance(self,p1, p2):
        dx = p1[0] - p2[0]
        dy = p1[1] - p2[1]
        return math.sqrt(dx * dx + dy * dy)

    def convertLineToSimpleGeom(self,polyline):
        polyline = self.smoothing(polyline)
        geom = QgsGeometry.fromPolylineXY(polyline)
        #simplifyするとベジエ化でおかしくなる場合がある。端の点が移動するため？

        # d = self.canvas.mapUnitsPerPixel()
        # geom = geom.simplify(self.tolerance * d)
        # self.test2_rbl.reset(QgsWkbTypes.LineGeometry)
        # for point in geom.asPolyline():
        #     self.test2_rbl.addPoint(point)
        return geom

    def showHandle(self,checked):
        self.show_handle = checked
        self.m.showHandle(checked)


    def check_snapsetting(self):
        snap_cfg = self.iface.mapCanvas().snappingUtils().config()
        if snap_cfg.enabled():
            self.snapping = True
        else:
            self.snapping = False
        #QgsMessageLog.logMessage("snapping:{}".format(self.snapping), 'MyPlugin')

    def check_crs(self):
        self.layerCRS = self.canvas.currentLayer().crs()
        self.projectCRS = self.canvas.mapSettings().destinationCrs()
        if self.projectCRS.projectionAcronym() == "longlat":
            QMessageBox.warning(None, "Warning", u"プロジェクトの投影法を緯度経度から変更してください")

    def activate(self):
        self.canvas.setCursor(self.addanchor_cursor)
        self.alt = False
        self.ctrl = False
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
