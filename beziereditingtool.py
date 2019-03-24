# -*- coding: utf-8 -*-
from __future__ import absolute_import
from builtins import zip
from builtins import range
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtWidgets import *
from qgis.PyQt.QtGui import *
from qgis.core import *
from qgis.gui import *
from .fitCurves import *
import math
import numpy as np
from .fitCurves import *
class BezierEditingTool(QgsMapTool):
    def __init__(self, canvas,iface):
        QgsMapTool.__init__(self, canvas)
        self.iface = iface
        self.canvas = canvas
        self.rbcls = []  # コントロールポイントのライン
        self.points = []  # 補間点
        self.ppoints = []  # ポイント
        self.cpoints = []  # コントロールポイント
        self.pmarkers = []  # ポイントのマーカー
        self.cmarkers = []  # コントロールポイントのマーカー
        self.moveFlag = False # クリックかドラッグかの判定（リリース時）
        self.history = [] # undo履歴
        self.alt = False
        self.ctrl = False
        self.shift = False
        self.mouse_state = "free" # free, add_anchor,move_anchor,move_handle,insert_anchor,draw_newline,draw_updateline
        self.editing = False #オブジェクト作成、修正中
        self.modify = False #オブジェクトの修正かどうか（すでに属性が入っている）
        self.snapping = True
        self.snapavoidbool = True
        self.featid = None # 編集オブジェクトのid
        self.selected_point_idx = None
        self.rbl = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)  # 補間ライン
        color = QColor(255, 0, 0,150)
        self.rbl.setColor(color)
        self.rbl.setWidth(2)
        self.edit_rbl = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.edit_rbl.setColor(QColor(255, 255, 0, 150))
        self.edit_rbl.setWidth(2)
        self.snapmarker = QgsVertexMarker(self.canvas)
        self.snapmarker.setIconType(QgsVertexMarker.ICON_BOX)
        self.snapmarker.setColor(QColor(0, 0, 255))
        self.snapmarker.setPenWidth(2)
        self.snapmarker.setIconSize(10)
        self.show_anchor = False
        self.bezier_num = 10 # bezierを補間する数
        self.addanchor_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/anchor.svg'), 1, 1)
        self.insertanchor_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/anchor_add.svg'), 1, 1)
        self.deleteanchor_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/anchor_del.svg'), 1, 1)
        self.movehandle_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/handle.svg'), 1, 1)
        self.addhandle_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/handle_add.svg'), 1, 1)
        self.deletehandle_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/handle_del.svg'), 1, 1)
        self.drawline_cursor = QCursor(QPixmap(':/plugins/bezierEditing2/icon/drawline.svg'), 1, 1)
        self.tolerance = 1
        self.mode = "bezier"
        self.snapmarker.hide()
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
            if event.button() == Qt.RightButton:
                # 右クリックで確定
                if self.editing:
                    self.finish_drawing(layer)
                else:
                    if layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                        QMessageBox.warning(None, "Warning", u"ポリゴンはベジエに変換できません")
                        return
                    self.start_modify(layer,orgpoint)
            elif event.button() == Qt.LeftButton:
                # 左クリック
                if self.ctrl:
                    # アンカーと重なっていてもアンカーを追加したいとき。ポリゴンを閉じたいときなど。
                    if snaptype[1]:
                        self.mouse_state = "add_anchor"
                        #self.log("{}".format(self.mouse_state))
                        ret = self.insertNewPoint(len(self.ppoints), point[1])
                        if ret:
                            self.selected_point_idx = len(self.ppoints) - 1
                            self.history.append({"state": "add_anchor", "pointidx": self.selected_point_idx})
                            # if len(self.history) > 5:
                            #     del self.history[0]
                            self.updateControlPoint(point[1])  # ベジエを補完するため動いてなくても最初に呼び出す
                elif self.alt:
                    # アンカーからコントロールポイントを引き出すとき
                    if snaptype[2] and snaptype[1]:
                        self.mouse_state = "move_handle"
                        self.selected_point_idx = snapidx[2]
                    # アンカーを挿入するとき
                    elif snaptype[3] and not snaptype[1]:
                        self.mouse_state = "insert_anchor"
                        ret = self.insertNewPoint(snapidx[3], point[3])
                        if ret:
                            self.selected_point_idx = snapidx[3]
                            self.history.append({"state": "insert_anchor", "pointidx": self.selected_point_idx})
                            # if len(self.history) > 5:
                            #     del self.history[0]
                            self.updateControlPoint(point[3])
                elif self.shift:
                    # アンカーを削除するとき
                    if snaptype[1]:
                        idx = snapidx[1]
                        self.history.append(
                            {"state": "delete_anchor",
                             "pointidx": idx,
                             "point": point[1],
                             "ctrlpoint0": self.cpoints[idx * 2],
                             "ctrlpoint1": self.cpoints[idx * 2 + 1]
                            }
                        )
                        self.deletePoint(idx)
                    # ハンドルを削除するとき
                    elif snaptype[2]:
                        self.history.append(
                            {"state": "delete_handle",
                             "pointidx": snapidx[2],
                             "point": point[2],
                            }
                        )
                        idx = snapidx[2]
                        pnt = self.ppoints[int(idx / 2)]
                        self.cpoints[idx] = pnt
                        self.moveControlPoint(idx, pnt)
                else:
                    # a. コントロールポイントの移動
                    # b. ポイントの移動
                    # c. 新規ポイントの追加
                    # 判定の順番が重要
                    # 「ポイントの移動」かどうか
                    if snaptype[1]:
                        self.mouse_state = "move_anchor"
                        self.selected_point_idx = snapidx[1]
                        self.history.append({"state": "move_anchor", "pointidx": self.selected_point_idx,"point":point[1]})
                        # if len(self.history) > 5:
                        #     del self.history[0]
                    # 「コントロールポイントの移動」かどうか
                    elif snaptype[2]:
                        self.mouse_state="move_handle"
                        self.selected_point_idx = snapidx[2]
                        self.history.append({"state": "move_handle", "pointidx": self.selected_point_idx, "point": point[2]})
                        # if len(self.history) > 5:
                        #     del self.history[0]
                    else:
                    # 上のどれでもなければ「新規ポイント追加」
                        self.editing = True
                        self.mouse_state = "add_anchor"
                        ret = self.insertNewPoint(len(self.ppoints), point[0])
                        if ret:
                            self.selected_point_idx = len(self.ppoints)-1
                            self.history.append({"state": "add_anchor", "pointidx": self.selected_point_idx})
                            # if len(self.history) > 5:
                            #     del self.history[0]
                            self.updateControlPoint(point[0])#ベジエを補完するため動いてなくても最初に呼び出す
        elif self.mode == "pen":
            # 右クリックで確定
            if event.button() == Qt.RightButton:
                if self.editing:
                    self.finish_drawing(layer)
                else:
                    if layer.geometryType() == QgsWkbTypes.PolygonGeometry:
                        QMessageBox.warning(None, "Warning", u"ポリゴンはベジエに変換できません")
                        return
                    self.start_modify(layer,orgpoint)
            # 左クリック
            elif event.button() == Qt.LeftButton:
                if self.editing and snaptype[3]:
                    #編集中で編集中のラバーバンドに近いなら
                    self.editing = True
                    #self.modify = True
                    self.mouse_state = "draw_updateline"
                    self.edit_rbl.reset(QgsWkbTypes.LineGeometry)
                    self.edit_rbl.addPoint(point[3])
                elif not self.editing:
                    #新規作成なら
                    self.editing = True
                    self.mouse_state = "draw_newline"
                    self.rbl.reset(QgsWkbTypes.LineGeometry)  # ベイジライン
                    self.rbl.addPoint(orgpoint)  # 最初のポイントは同じ点が2つ追加される仕様？
    def canvasMoveEvent(self, event):
        layer = self.canvas.currentLayer()
        if not layer or layer.type() != QgsMapLayer.VectorLayer:
            return
        orgpoint, snaptype, point, snapidx = self.getSnapPoint(event, layer)
        if self.mode == "bezier":
            #self.log("{}".format(self.mouse_state))
            self.moveFlag = True
            # 追加時のドラッグはコントロールポイントの移動
            if self.mouse_state=="add_anchor" or self.mouse_state=="insert_anchor":
                self.updateControlPoint(point[0])
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
            # 選択されたコントロールポイントの移動
            elif self.mouse_state=="move_handle":
                self.moveControlPoint(self.selected_point_idx, orgpoint)
            # 選択されたポイントの移動
            elif self.mouse_state=="move_anchor":
                pnt = point[0]
                #ポイントとスナップしたら
                if snaptype[1]:
                    pnt = point[1]
                self.movePoint(self.selected_point_idx, pnt)
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
                self.rbl.addPoint(pnt)
            elif self.mouse_state == "draw_updateline":
                self.edit_rbl.addPoint(pnt)
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
                    #self.log("pointQ:{}".format(len(self.points)))
                    self.draw_updateline(snaptype)
                elif self.mouse_state == "draw_newline":
                    self.draw_newline(snaptype)
                self.mouse_state = "free"
        if self.show_anchor:
            self.showBezierMarker()
        else:
            self.hideBezierMarker()
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
            else:
                QMessageBox.warning(None, "Warning", u"他のツールで編集されたオブジェクトはベジエに変換できません")
    def finish_drawing(self,layer):
        if len(self.ppoints) >= 1:
            # 作成するオブジェクトをgeomに変換。修正するためのフィーチャーも取得
            type = layer.geometryType()
            if type == QgsWkbTypes.PolygonGeometry:
                geom = QgsGeometry.fromPolygonXY([self.points])
            else:
                geom = QgsGeometry.fromPolylineXY(self.points)

            if self.modify:
                feature = self.getFeatureById(layer, self.featid)
                if feature is None:
                    QMessageBox.warning(None, "Warning", u"レイヤを確かめてください")
                    return
                continueFlag = self.editFeature(geom, feature)
            else:
                continueFlag = self.createFeature(geom)
            if continueFlag is False:
                self.resetPoints()
                self.featid = None
                self.editing = False
                self.modify = False
        else:
            self.resetPoints()
            self.featid = None
            self.editing = False
            self.modify = False
        self.canvas.refresh()
    def updateControlPoint(self, point):
        # コントロールポイントを更新（ベジエも更新するために強制的に呼び出す）
        #self.log("update")
        p = self.ppoints[self.selected_point_idx]
        pb = QgsPointXY(p[0] - (point[0] - p[0]), p[1] - (point[1] - p[1]))
        idx = self.selected_point_idx * 2
        self.moveControlPoint(idx, pb)
        self.moveControlPoint(idx + 1, point)
    # ペン関係
    def draw_newline(self,snaptype):
        # スムーズ処理してrbを付け替える
        rbgeom = self.rbl.asGeometry()
        rbline = rbgeom.asPolyline()
        geom = self.convertLineToSimpleGeom(rbline)
        self.history.append({"state": "start_pen"})
        self.insertGeomToBezier(0,geom,last=True)
        self.history.append({"state": "end_pen","direction":"forward"})
        # スタートポイントにスナップしていたらスムーズ処理でずれた最後の点を最初のポイントに動かす
        if snaptype[4]:
            self.movePoint(len(self.ppoints) - 1, self.ppoints[0])
        if self.show_anchor:
            self.showBezierMarker()
        else:
            self.hideBezierMarker()
    def draw_updateline(self,snaptype):
        org_geom = self.rbl.asGeometry()
        update_geom = self.edit_rbl.asGeometry()
        self.modify_bezier(update_geom, org_geom)  # 編集箇所の次のコントロールポイント以降を削除
        # スタートポイントにスナップしていたらスムーズ処理でずれた最後の点を最初のポイントに動かす
        if snaptype[4]:
            self.movePoint(len(self.ppoints) - 1, self.ppoints[0])
        self.edit_rbl.reset()
        if self.show_anchor:
            self.showBezierMarker()
        else:
            self.hideBezierMarker()
            #self.log("update1")
    # アンドゥ処理
    def undo(self):
        if len(self.history)>0:
            act = self.history.pop()
            if act["state"]=="add_anchor":
                self.deletePoint(act["pointidx"])
            elif act["state"]=="move_anchor":
                self.movePoint(act["pointidx"],act["point"])
            elif act["state"]=="move_handle":
                self.moveControlPoint(act["pointidx"],act["point"])
            elif act["state"]=="insert_anchor":
                self.deletePoint(act["pointidx"])
            elif act["state"]=="delete_anchor":
                self.insertNewPoint(act["pointidx"],act["point"])
                self.moveControlPoint(act["pointidx"] * 2, act["ctrlpoint0"])
                self.moveControlPoint(act["pointidx"] * 2+1, act["ctrlpoint1"])
            elif act["state"] == "delete_handle":
                self.moveControlPoint(act["pointidx"], act["point"])
            elif act["state"]=="end_pen":
                direction = act["direction"]
                if direction=="reverse":
                    self.flipBezierLine()
                act = self.history.pop()
                while act["state"] !="start_pen":
                    if act["state"] == "add_anchor":
                        self.deletePoint(act["pointidx"])
                    elif act["state"]=="delete_anchor":
                        self.insertNewPoint(act["pointidx"], act["point"])
                        self.moveControlPoint(act["pointidx"] * 2, act["ctrlpoint0"])
                        self.moveControlPoint(act["pointidx"] * 2 + 1, act["ctrlpoint1"])
                    act = self.history.pop()
                if direction=="reverse":
                    self.flipBezierLine()
                if len(self.history)==0:
                    self.resetPoints()
                    self.featid = None
                    self.editing = False
                    self.modify = False
        if self.mode=="bezier" and len(self.history)==0:
            self.resetPoints()
            self.featid = None
            self.editing = False
            self.modify = False
        if self.show_anchor:
            self.showBezierMarker()
        else:
            self.hideBezierMarker()
    ########ベジエ操作
    # 新規ポイントを追加
    def insertNewPoint(self, idx, point):
        if len(self.ppoints) > 0 and self.ppoints[-1] == point:
        # 最後の点と同じ点は打てないようにする（スナップでの誤作業防止）
            return False
        self.ppoints.insert(idx, point)
        self.cpoints.insert(idx * 2, point)
        self.cpoints.insert(idx * 2, point)
        self.insertNewMarker(self.pmarkers, idx, point)
        self.insertNewMarker(self.cmarkers, 2 * idx , point,QColor(125,125,125))
        self.insertNewMarker(self.cmarkers, 2 * idx , point,QColor(125,125,125))
        # コントロールポイント用ラインの追加（両側）
        self.addNewRubberBand(self.rbcls, 2 * idx , point)
        self.addNewRubberBand(self.rbcls, 2 * idx , point)
        pointsA=[]
        pointsB=[]
        # 右側. idxが右端だったら右側はなし
        if idx < len(self.ppoints) - 1:
            p1 = self.ppoints[idx]
            p2 = self.ppoints[idx + 1]
            c1 = self.cpoints[idx * 2 + 1]
            c2 = self.cpoints[idx * 2 + 2]
            pointsA = self.bezier(p1, c1, p2, c2)
        # 左側. idxが0の場合は左側はなし
        if idx >= 1:
            p1 = self.ppoints[idx - 1]
            p2 = self.ppoints[idx]
            c1 = self.cpoints[idx * 2 - 1]
            c2 = self.cpoints[idx * 2]
            pointsB = self.bezier(p1, c1, p2, c2)
        #self.log("idx:{}".format(idx))
        #self.log("pointsA:{}".format(len(self.points)))
        if idx==0: #最初のアンカーは追加するだけなので、表示しない
            pass
        elif idx==1 and idx==len(self.ppoints)-1: #新規追加の2点目のとき。最初の表示
            self.points = pointsB
        elif idx >= 2 and idx==len(self.ppoints)-1: #2点目以降の追加とき
            self.points = self.points + pointsB[1:]
        else: # 両側のアンカーがすでにあって挿入のとき
            self.points[self.bezier_num * (idx - 1):self.bezier_num * idx + 1] = pointsB+pointsA[1:]
        #self.log("pointsB:{}".format(len(self.points)))
        self.setRubberBandPoints(self.points, self.rbl)
        return True
    # ポイント削除
    def deletePoint(self,idx):
        # 左端の削除
        if idx == 0:
            del self.points[0:self.bezier_num]
            self.setRubberBandPoints(self.points, self.rbl)
        # 右端の削除
        elif idx + 1 == len(self.ppoints):
            del self.points[self.bezier_num * (idx - 1) + 1:]
            self.setRubberBandPoints(self.points, self.rbl)
        # 中間の削除
        else:
            p1 = self.ppoints[idx - 1]
            p2 = self.ppoints[idx + 1]
            c1 = self.cpoints[(idx - 1) * 2 + 1]
            c2 = self.cpoints[(idx + 1) * 2]
            points = self.bezier(p1, c1, p2, c2)
            self.points[self.bezier_num * (idx - 1):self.bezier_num * (idx + 1) + 1] = points
            self.setRubberBandPoints(self.points, self.rbl)
        del self.cpoints[2 * idx]
        self.removeMarker(self.cmarkers, 2 * idx)
        self.removeRubberBand(self.rbcls, 2 * idx)
        del self.ppoints[idx]
        self.removeMarker(self.pmarkers, idx)
        del self.cpoints[2 * idx]
        self.removeMarker(self.cmarkers, 2 * idx)
        self.removeRubberBand(self.rbcls, 2 * idx)
        return
    # コントロールポイントのラインを移動
    def moveControlPoint(self, idx, point):
        #コントロールポイントのラインの終点を移動
        self.rbcls[idx].movePoint(1, point,0)
        # コントロールポイントのマーカーを移動
        self.cmarkers[idx].setCenter(point)
        self.cpoints[idx] = point
        # ベジエの更新
        # ポイント2点目以降なら更新
        if len(self.ppoints) > 1:
            #右側
            if idx % 2 == 1 and idx < len(self.cpoints)-1:
                idxP = idx // 2
                p1 = self.ppoints[idxP]
                p2 = self.ppoints[idxP + 1]
                c1 = self.cpoints[idx]
                c2 = self.cpoints[idx + 1]
            #左側
            elif idx % 2 == 0 and idx >= 1:
                idxP = (idx - 1) // 2
                p1 = self.ppoints[idxP]
                p2 = self.ppoints[idxP + 1]
                c1 = self.cpoints[idx - 1]
                c2 = self.cpoints[idx]
            #上記以外は何もしない
            else:
                return
            points = self.bezier(p1, c1, p2, c2)
            self.points[self.bezier_num * idxP:self.bezier_num * (idxP + 1) + 1] = points
            self.setRubberBandPoints(self.points, self.rbl)
    # 特定のポイントを移動してベジエを更新
    def movePoint(self, idx, point):
        diff = point - self.ppoints[idx]
        # コントロールポイントのラインを移動
        self.rbcls[idx * 2].movePoint(0, point,0)
        self.rbcls[idx * 2+1].movePoint(0, point,0)
        self.rbcls[idx * 2].movePoint(1, self.cpoints[idx * 2]+diff,0)
        self.rbcls[idx * 2+1].movePoint(1, self.cpoints[idx * 2+1]+diff,0)
        # ポイントを移動
        self.pmarkers[idx].setCenter(point)
        self.ppoints[idx] = point
        # コントロールポイントのマーカーを移動
        self.cmarkers[idx*2].setCenter(self.cpoints[idx * 2]+diff)
        self.cpoints[idx*2] = self.cpoints[idx * 2]+diff
        self.cmarkers[idx*2+1].setCenter(self.cpoints[idx * 2+1]+diff)
        self.cpoints[idx*2+1] = self.cpoints[idx * 2+1]+diff
        # ベジエを更新
        # 右側
        if idx < len(self.ppoints)-1:
            p1 = self.ppoints[idx]
            p2 = self.ppoints[idx + 1]
            c1 = self.cpoints[idx * 2+1]
            c2 = self.cpoints[idx * 2 + 2]
            points = self.bezier(p1, c1, p2, c2)
            self.points[self.bezier_num * idx:self.bezier_num * (idx + 1) + 1] = points
            self.setRubberBandPoints(self.points, self.rbl)
        # 左側
        if idx >= 1:
            p1 = self.ppoints[idx - 1]
            p2 = self.ppoints[idx]
            c1 = self.cpoints[idx * 2 - 1]
            c2 = self.cpoints[idx * 2]
            points = self.bezier(p1, c1, p2, c2)
            self.points[self.bezier_num * (idx - 1):self.bezier_num * idx + 1] = points
            self.setRubberBandPoints(self.points, self.rbl)
    # ポイント、コントロールポイントの配列、マーカー、ラインとベジエライン、履歴を初期化
    def resetPoints(self):
        self.removeAllMarker(self.pmarkers)  # ポイントマーカーの削除
        self.removeAllMarker(self.cmarkers)  # コントロールポイントマーカーの削除
        self.removeAllRubberBand(self.rbcls)  # コントロールポイントのラインの削除
        self.rbl.reset(QgsWkbTypes.LineGeometry)  # ベイジライン
        self.rbcls = []  # コントロールライン
        self.pmarkers=[]
        self.cmarkers=[]
        self.points = []  # 補間点
        self.ppoints = []  # ポイント
        self.cpoints = []  # コントロールポイント
        self.history = []
        self.alt = False
        self.ctrl = False
    # フィーチャをベジエ曲線のコントロールポイントに変換
    def convertFeatureToBezier(self, f):
        geom = QgsGeometry(f.geometry())
        self.check_crs()
        if self.layerCRSSrsid != self.projectCRSSrsid:
            geom.transform(QgsCoordinateTransform(self.layerCRSSrsid, self.projectCRSSrsid))
        polyline = geom.asPolyline()
        if len(polyline) % 10 != 1:
            # 他のツールで編集されているのでベジエに変換できない。
            # 編集されていても偶然、あまりが1になる場合は、変換してしまう。
            return False
        #51個ずつ取り出す。間の点は重複させる。最後の要素は余分なので取り除く。
        points = [polyline[i:i + self.bezier_num+1] for i in range(0, len(polyline), self.bezier_num)][:-1]
        #self.log("{}".format(points))
        for i, points_i in enumerate(points):
            ps, cs, pe, ce = self.invert_bezier(points_i)
            p0 = QgsPointXY(ps[0], ps[1])
            p1 = QgsPointXY(pe[0], pe[1])
            c0 = QgsPointXY(ps[0], ps[1])
            c1 = QgsPointXY(cs[0], cs[1])
            c2 = QgsPointXY(ce[0], ce[1])
            c3 = QgsPointXY(pe[0], pe[1])
            if i == 0:
                self.insertNewPoint(len(self.ppoints), p0)
                self.moveControlPoint(i * 2, c0)
                self.moveControlPoint(i * 2 + 1, c1)
                self.insertNewPoint(len(self.ppoints), p1)
                self.moveControlPoint((i + 1) * 2, c2)
                self.moveControlPoint((i + 1) * 2 + 1, c3)
            else:
                self.moveControlPoint(i * 2 + 1, c1)
                self.insertNewPoint(len(self.ppoints), p1)
                self.moveControlPoint((i + 1) * 2, c2)
                self.moveControlPoint((i + 1) * 2 + 1, c3)
        return True
    def insertGeomToBezier(self, offset, geom, last=True):
        # self.check_crs()
        # if self.layerCRSSrsid != self.projectCRSSrsid:
        #     geom.transform(QgsCoordinateTransform(self.layerCRSSrsid, self.projectCRSSrsid))
        polyline = geom.asPolyline()
        points = np.array(polyline)
        beziers = fitCurve(points, 10.0)
        #self.log("pointsA:{}".format(len(self.points)))
        for i, bezier in enumerate(beziers):
            if offset == 0:
                if i == 0:
                    p0 = QgsPointXY(bezier[0][0], bezier[0][1])
                    self.insertNewPoint(0, p0)
                    self.history.append({"state": "add_anchor", "pointidx":0})
                p1 = QgsPointXY(bezier[3][0], bezier[3][1])
                c1 = QgsPointXY(bezier[1][0], bezier[1][1])
                c2 = QgsPointXY(bezier[2][0], bezier[2][1])
                self.moveControlPoint(i * 2 + 1, c1)
                self.insertNewPoint(i + 1, p1)
                self.moveControlPoint((i + 1) * 2, c2)
                self.history.append({"state": "add_anchor", "pointidx": i+1})
            elif offset > 0:
                p1 = QgsPointXY(bezier[3][0], bezier[3][1])
                c1 = QgsPointXY(bezier[1][0], bezier[1][1])
                c2 = QgsPointXY(bezier[2][0], bezier[2][1])
                idx = (offset - 1) * 2 + i * 2 + 1
                self.history.append({"state": "move_handle", "pointidx": idx, "point": self.cpoints[idx]})
                self.moveControlPoint(idx, c1)
                if i != len(beziers)-1 or last:
                    self.insertNewPoint(offset + i, p1)
                    self.history.append({"state": "add_anchor", "pointidx": offset + i})
                self.moveControlPoint((offset - 1) * 2 + (i + 1) * 2, c2)
        #self.log("pointsB:{}".format(len(self.points)))
    def convertLineToSimpleGeom(self,polyline):
        polyline = self.smoothing(polyline)
        geom = QgsGeometry.fromPolylineXY(polyline)
        d = self.canvas.mapUnitsPerPixel()
        geom = geom.simplify(self.tolerance * d)
        return geom
    def flipBezierLine(self):
        self.ppoints.reverse()
        self.cpoints.reverse()
        self.points.reverse()
        self.pmarkers.reverse()
        self.cmarkers.reverse()
        self.rbcls.reverse()
        rbl_line = self.rbl.asGeometry().asPolyline()
        rbl_line.reverse()
        self.setRubberBandPoints(rbl_line, self.rbl)
    # ジオメトリのペンでの修正
    def modify_bezier(self, update_geom, org_geom):
        update_line = update_geom.asPolyline()
        org_line = org_geom.asPolyline()

        startpnt = update_line[0]
        lastpnt = update_line[-1]
        startpnt_is_near, start_anchoridx, start_vertexidx = self.closestPPointOfGeometry(startpnt, org_geom)
        lastpnt_is_near, last_anchoridx, last_vertexidx = self.closestPPointOfGeometry(lastpnt, org_geom)
        points = [org_line[i:i + self.bezier_num + 1] for i in range(0, len(org_line), self.bezier_num)][:-1]
        #self.log("{},{}".format(len(points),len(org_line)))
        # org_lineとupdate_lineの交差する周辺のベクトルの内積を計算。正なら順方向、不なら逆方向
        v1 = np.array(org_line[start_vertexidx])-np.array(org_line[start_vertexidx-1])
        v2 = np.array(update_line[1]) - np.array(update_line[0])
        direction = np.dot(v1,v2)
        self.history.append({"state": "start_pen"})
        # 逆方向ならorg_lineとベジエを定義しているのアンカー、ハンドル関連のリストを逆順にする
        if direction < 0:
            #self.log("reverse")
            org_line.reverse()
            self.flipBezierLine()
            reversed_geom = QgsGeometry.fromPolylineXY(org_line)
            startpnt_is_near, start_anchoridx, start_vertexidx = self.closestPPointOfGeometry(startpnt, reversed_geom)
            lastpnt_is_near, last_anchoridx, last_vertexidx = self.closestPPointOfGeometry(lastpnt, reversed_geom)
        # 編集箇所の前のコントロールポイントから今のところまでをくっつける
        # ベジエ区間ごとのポイントリスト　を作成
        points = [org_line[i:i + self.bezier_num + 1] for i in range(0, len(org_line), self.bezier_num)][:-1]
        #self.log("{}".format(len(points)))
        #self.log("{},{}".format(startpnt_is_near,lastpnt_is_near))
        #self.log("{},{},{},{},{},{}".format(start_anchoridx, last_anchoridx, start_vertexidx, last_vertexidx,
        #                                    start_vertexidx % self.bezier_num, last_vertexidx % self.bezier_num))
        # A 部分の修正
        if lastpnt_is_near and last_vertexidx > start_vertexidx: #startpnt_is_nearは修正開始の時点で確定している
            polyline = points[start_anchoridx - 1][0:start_vertexidx % self.bezier_num] + \
                       update_line + \
                       points[last_anchoridx - 1][last_vertexidx % self.bezier_num:]
            #self.history.append({"state": "start_pen"})
            for i in range(start_anchoridx, last_anchoridx):
                self.history.append(
                    {"state": "delete_anchor",
                     "pointidx": start_anchoridx,
                     "point": self.ppoints[start_anchoridx],
                     "ctrlpoint0":self.cpoints[start_anchoridx * 2],
                     "ctrlpoint1":self.cpoints[start_anchoridx * 2 + 1]
                     }
                )
                self.deletePoint(start_anchoridx)
            geom = self.convertLineToSimpleGeom(polyline)
            self.insertGeomToBezier(start_anchoridx,geom,last=False)
            #self.history.append({"state": "end_pen"})
        # B 終点が離れる場合。終点が線上でも逆方向に戻っている場合、始点に閉じる場合。
        elif not lastpnt_is_near or (lastpnt_is_near and last_vertexidx <= start_vertexidx):
            if start_anchoridx == len(self.ppoints):  # 右端の場合はそのまま。
                polyline = update_line
            else:  # ベジエ区間の中の何個目のポイントからか調べて、くっつける
                polyline = points[start_anchoridx - 1][0:start_vertexidx % self.bezier_num] + update_line
            for i in range(start_anchoridx, len(self.ppoints)):
                self.history.append(
                    {"state": "delete_anchor",
                     "pointidx": start_anchoridx,
                     "point": self.ppoints[start_anchoridx],
                     "ctrlpoint0":self.cpoints[start_anchoridx * 2],
                     "ctrlpoint1":self.cpoints[start_anchoridx * 2 + 1]
                     }
                )
                self.deletePoint(start_anchoridx)
            geom = self.convertLineToSimpleGeom(polyline)
            self.insertGeomToBezier(start_anchoridx,geom,last=True)
        self.history.append({"state": "end_pen","direction":"forward"})
        # ベジエの方向を元に戻す
        if direction < 0:
            self.flipBezierLine()
            self.history[-1]["direction"] = "reverse"
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
    def closestPPointOfGeometry(self,point,geom):
        near = False
        (dist, minDistPoint, vertexidx, leftOf) = geom.closestSegmentWithContext(point)
        anchoridx = vertexidx // self.bezier_num + 1
        d = self.canvas.mapUnitsPerPixel() * 10
        if math.sqrt(dist) < d:
            near = True
        return near, anchoridx, vertexidx
    # フィーチャを作成。属性を別のfeatureからコピーしたい場合は指定
    def createFeature(self,geom,feat=None):
        continueFlag = False
        layer = self.canvas.currentLayer()
        provider = layer.dataProvider()
        self.check_crs()
        if self.layerCRSSrsid != self.projectCRSSrsid:
            geom.transform(QgsCoordinateTransform(self.projectCRSSrsid, self.layerCRSSrsid))
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
            layer.addFeature(f)
            layer.endEditCommand()
        else:
            dlg = self.iface.getFeatureForm(layer, f)
            if dlg.exec_():
                layer.addFeature(f)
                layer.endEditCommand()
            else:
                layer.destroyEditCommand()
                reply = QMessageBox.question(None, "Question", u"編集を続けますか？", QMessageBox.Yes,
                                             QMessageBox.No)
                if reply == QMessageBox.Yes:
                    continueFlag = True
        return continueFlag
    # フィーチャを編集
    def editFeature(self,geom,feat,showdlg=True):
        continueFlag = False
        layer = self.canvas.currentLayer()
        self.check_crs()
        if self.layerCRSSrsid != self.projectCRSSrsid:
            geom.transform(QgsCoordinateTransform(self.projectCRSSrsid, self.layerCRSSrsid))
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
                layer.destroyEditCommand()
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
    # マウスがベジエのコントロールポイントのどこにスナップしたか確認
    def getSnapPoint(self,event,layer):
        # どこにスナップしたか？のリスト、スナップしたポイント、線上にスナップした場合のポイントのidを返す
        idx=["","","","",""]
        snaptype = [False,False,False,False,False]
        pnt = [None,None,None,None,None]
        self.snapmarker.hide()
        point = event.pos()
        # snapしていない場合
        orgpoint = self.toMapCoordinates(point)
        pnt[0] = orgpoint
        if self.snapping:
            snapper = QgsMapCanvasSnapper(self.canvas)
            (retval, snapped) = snapper.snapToBackgroundLayers(point)
            if snapped !=[]:
                snppoint = snapped[0].snappedVertex
                self.snapmarker.setCenter(snppoint)
                self.snapmarker.show()
                #ここのpointはQgsPointになっているので、layerが必要
                pnt[0] = self.toMapCoordinates(layer,snppoint)
                snaptype[0]=True
        point = self.toMapCoordinates(point)
        # 「アンカーと近い」かどうか.
        for i, p in reversed(list(enumerate(self.ppoints))):
            snapped, snppoint = self.getSelfSnapPoint(p, point)
            # freeの時にマウス位置がポイントかどうか調べたい場合
            if self.selected_point_idx is None:
                if snapped:
                    snaptype[1] = True
                    idx[1] = i
                    pnt[1] = snppoint
                    self.snapmarker.setCenter(snppoint)
                    self.snapmarker.show()
                    break
            # ドラッグしているポイントが他のポイントと近いかどうかを調べたい場合
            elif self.selected_point_idx != i:
                if snapped:
                    snaptype[1] = True
                    idx[1] = i
                    pnt[1] = snppoint
                    break
        # 「コントロールポイントと近い」かどうか
        for i, p in reversed(list(enumerate(self.cpoints))):
            snapped,snppoint = self.getSelfSnapPoint(p,point)
            if snapped and self.show_anchor and self.mode=="bezier":
                snaptype[2]=True
                idx[2]=i
                pnt[2] = snppoint
                self.snapmarker.setCenter(snppoint)
                self.snapmarker.show()
                break
        # 「線上かどうか for pen」
        if self.rbl.size() > 0:
            p=[]
            for i in range(self.rbl.numberOfVertices()):
                p.append(self.rbl.getPoint(0,i))
            geom = QgsGeometry.fromPolylineXY(p)
            (dist, minDistPoint, afterVertex, leftOf) = geom.closestSegmentWithContext(point)
            d = self.canvas.mapUnitsPerPixel() * 10
            if math.sqrt(dist) < d:
                snaptype[3] = True
                idx[3] = afterVertex // (self.bezier_num+1) + 1
                pnt[3] = minDistPoint
                #self.snapmarker.setCenter(point) #minDistPointにするとペンの時に書きづらい
                #self.snapmarker.show()
        # 「スタートポイントかどうか for pen」
            p=self.rbl.getPoint(0, 0)
            snapped, snppoint = self.getSelfSnapPoint(p, point)
            if snapped:
                snaptype[4]=True
                idx[4]=0
                pnt[4] = snppoint
                self.snapmarker.setCenter(snppoint)
                self.snapmarker.show()
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
    # 始点、終点のコントロールポイントで定義されるベジエ曲線を50点で補間したリストを返す。
    def bezier(self, p1, c1, p2, c2):
        points = []
        for t in range(0, self.bezier_num+1):
            t = 1.0 * t / self.bezier_num
            bx = (1 - t) ** 3 * p1.x() + 3 * t * (1 - t) ** 2 * c1.x() + 3 * t ** 2 * (1 - t) * c2.x() + t ** 3 * p2.x()
            by = (1 - t) ** 3 * p1.y() + 3 * t * (1 - t) ** 2 * c1.y() + 3 * t ** 2 * (1 - t) * c2.y() + t ** 3 * p2.y()
            points.append(QgsPointXY(bx, by))
        return points
    # 50点で補間されたベジエ曲線のリストから始点、終点のコントロールポイントを返す。
    def invert_bezier(self, points):
        # pointsから左右のコントロールポイントを求める
        # t1とt2の時の座標を代入して、連立方程式の解を解く
        ps = np.array(points[0])
        pe = np.array(points[-1])
        #tの分割数 今は固定値で50
        tnum = len(points)-1
        #self.log("{},{},{}".format(tnum,ps,pe))
        t1 = 1.0 / tnum
        p1 = np.array(points[1])
        t2 = 2.0 / tnum
        p2 = np.array(points[2])
        aa = 3 * t1 * (1 - t1) ** 2
        bb = 3 * t1 ** 2 * (1 - t1)
        cc = ps * (1 - t1) ** 3 + pe * t1 ** 3 - p1
        dd = 3 * t2 * (1 - t2) ** 2
        ee = 3 * t2 ** 2 * (1 - t2)
        ff = ps * (1 - t2) ** 3 + pe * t2 ** 3 - p2
        #self.log("{},{},{},{},{},{}".format(aa, bb, cc, dd, ee, ff))
        c0 = (bb * ff - cc * ee) / (aa * ee - bb * dd)
        c1 = (aa * ff - cc * dd) / (bb * dd - aa * ee)
        # c1=(3,3)
        # c2=(10,2)
        #self.log("{},{},{},{}".format(ps,pe,c0,c1))
        return ps, c0, pe, c1
    ######## マーカー、ラバーバンドの表示処理。（ベジエ操作から呼ばれる）
    # 新規のコントロールラインを作成
    def addNewRubberBand(self, rbcls, idx, point):
        rbcl = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        color = QColor(0, 0, 0)
        rbcl.setColor(color)
        rbcl.setWidth(1)
        rbcl.addPoint(point)
        rbcl.addPoint(point)
        rbcls.insert(idx, rbcl)
        return rbcls
    # 新規マーカーを追加
    def insertNewMarker(self, markers, idx, point,color=QColor(0,0,0)):
        # ポイントorコントロールポイントのマーカーをidxの前に追加
        marker = QgsVertexMarker(self.canvas)
        marker.setIconType(QgsVertexMarker.ICON_BOX)
        marker.setColor(color)
        marker.setPenWidth(2)
        marker.setIconSize(5)
        marker.setCenter(point)
        marker.show()
        markers.insert(idx, marker)
        return markers
    # ベジエラインの表示
    def setRubberBandPoints(self, points, rb):
        # 最後に更新
        rb.reset(QgsWkbTypes.LineGeometry)
        for point in points:
            update = point is points[-1]
            rb.addPoint(point, update)
    # すべてのコントロールラインを消す
    def removeAllRubberBand(self, rbcls):
        for rbcl in rbcls:
            self.canvas.scene().removeItem(rbcl)
    # 特定のコントロールラインを消す
    def removeRubberBand(self, rbs, index):
        rb = rbs[index]
        self.canvas.scene().removeItem(rb)
        del rbs[index]
    # 特定のマーカーの削除
    def removeMarker(self, markers, idx):
        m = markers[idx]
        self.canvas.scene().removeItem(m)
        del markers[idx]
    # 全マーカーの削除
    def removeAllMarker(self, markers):
        for m in markers:
            self.canvas.scene().removeItem(m)

    def showBezierMarker(self):
        self.show_anchor = True
        self.showAllMarker(self.pmarkers)
        self.showAllMarker(self.cmarkers)
        self.showAllRubberBand(self.rbcls)
        self.canvas.refresh()
    def hideBezierMarker(self):
        self.show_anchor = False
        #self.hideAllMarker(self.pmarkers)
        self.hideAllMarker(self.cmarkers)
        self.hideAllRubberBand(self.rbcls)
        self.canvas.refresh()
    def showAllMarker(self,markers):
        for m in markers:
            m.show()
    def hideAllMarker(self,markers):
        for m in markers:
            m.hide()
    def showAllRubberBand(self, rbcls):
        for rbcl in rbcls:
            rbcl.setColor(QColor(0, 0, 0, 255))
    def hideAllRubberBand(self, rbcls):
        for rbcl in rbcls:
            rbcl.setColor(QColor(0, 0, 0, 0))
    def check_snapsetting(self):
        proj = QgsProject.instance()
        snapmode = proj.readEntry('Digitizing', 'SnappingMode')[0]
        # QgsMessageLog.logMessage("snapmode:{}".format(snapmode), 'MyPlugin', QgsMessageLog.INFO)
        if snapmode == "advanced":
            snaplayer = proj.readListEntry('Digitizing', 'LayerSnappingList')[0]
            snapenabled = proj.readListEntry('Digitizing', 'LayerSnappingEnabledList')[0]
            snapavoid = proj.readListEntry('Digitizing', 'AvoidIntersectionsList')[0]
            layerid = self.canvas.currentLayer().id()
            if layerid in snaplayer:  # 新規のレイヤーだとない場合がある？
                snaptype = snapenabled[snaplayer.index(layerid)]
                # QgsMessageLog.logMessage("snaptype:{}".format(snaptype), 'MyPlugin', QgsMessageLog.INFO)
                self.snapavoidbool = self.canvas.currentLayer().id() in snapavoid
                if snaptype == "disabled":
                    self.snapping = False
                else:
                    self.snapping = True
            else:
                self.snapping = True
        else:
            snaptype = proj.readEntry('Digitizing', 'DefaultSnapType')[0]
            if snaptype == "off":
                self.snapping = False
            else:
                self.snapping = True
            self.snapavoidbool = False
    def check_crs(self):
        layer = self.canvas.currentLayer()
        renderer = self.canvas.mapSettings()
        self.layerCRSSrsid = layer.crs().srsid()
        self.projectCRSSrsid = renderer.destinationCrs().srsid()
        if renderer.destinationCrs().projectionAcronym() == "longlat":
            QMessageBox.warning(None, "Warning", u"プロジェクトの投影法を緯度経度から変更してください")
    def activate(self):
        self.canvas.setCursor(self.addanchor_cursor)
        self.alt = False
        self.ctrl = False
        self.snapmarker.setColor(QColor(0, 0, 255))
        self.check_snapsetting()
        self.check_crs()
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
