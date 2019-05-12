# -*- coding: utf-8 -*-
""""
/***************************************************************************
    BezierEditing
     --------------------------------------
    Date                 : 01 05 2019
    Copyright            : (C) 2019 Takayuki Mizutani
    Email                : mizutani at ecoris dot co dot jp
 ***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from qgis.core import *
from .fitCurves import *
import copy
import math
import numpy as np

class BezierGeometry:

    def __init__(self):
        self.INTERPORATION = 10
        self.points = []  # 補間点
        self.anchor = []  # ポイント
        self.handle = []  # コントロールポイント
        self.history = []  # undo履歴

    @classmethod
    def convertPointToBezier(cls, point):
        bg = cls()
        bg._addAnchor(0, point)
        return bg

    @classmethod
    def convertLineToBezier(cls, polyline):
        bg = cls()
        # if polyline length isn't match cause of edited other tool, it can't convert to bezier line
        if len(polyline) % bg.INTERPORATION != 1:
            return None
        point_list = bg._pointList(polyline)
        for i, points_i in enumerate(point_list):
            ps, cs, pe, ce = bg._invertBezier(points_i)
            p0 = QgsPointXY(ps[0], ps[1])
            p1 = QgsPointXY(pe[0], pe[1])
            c0 = QgsPointXY(ps[0], ps[1])
            c1 = QgsPointXY(cs[0], cs[1])
            c2 = QgsPointXY(ce[0], ce[1])
            c3 = QgsPointXY(pe[0], pe[1])
            if i == 0:
                bg._addAnchor(-1, p0)
                bg._moveHandle(i * 2, c0)
                bg._moveHandle(i * 2 + 1, c1)
                bg._addAnchor(-1, p1)
                bg._moveHandle((i + 1) * 2, c2)
                bg._moveHandle((i + 1) * 2 + 1, c3)
            else:
                bg._moveHandle(i * 2 + 1, c1)
                bg._addAnchor(-1, p1)
                bg._moveHandle((i + 1) * 2, c2)
                bg._moveHandle((i + 1) * 2 + 1, c3)

        return bg

    @classmethod
    def convertPolygonToBezier(cls, polygon):
        bg = cls()
        # if polygon length isn't match cause of edited other tool, it can't convert to bezier line
        if len(polygon) % self.INTERPORATION != 1:
            return None
        bg = bg.convertLineToBezier(polygon[0])
        return bg

    def asGeometry(self, layer_type, layer_wkbtype):
        result = None
        geom = None
        num_anchor = self.anchorCount()

        if layer_type == QgsWkbTypes.PointGeometry and num_anchor == 1:
            geom = QgsGeometry.fromPointXY(self.points[0])
            result = True
        elif layer_type == QgsWkbTypes.LineGeometry and num_anchor >= 2:
            if layer_wkbtype == QgsWkbTypes.LineString:
                geom = QgsGeometry.fromPolylineXY(self.points)
                result = True
            elif layer_wkbtype == QgsWkbTypes.MultiLineString:
                geom = QgsGeometry.fromMultiPolylineXY([self.points])
                result = True
        elif layer_type == QgsWkbTypes.PolygonGeometry and num_anchor >= 3:
            geom = QgsGeometry.fromPolygonXY([self.points])
            result = True
        elif layer_type == QgsWkbTypes.LineGeometry and num_anchor < 2:
            # 　ラインレイヤで1点しかない場合は削除
            result = None
        elif layer_type == QgsWkbTypes.PolygonGeometry and num_anchor < 3:
            # 　ポリゴンレイヤで2点以下しかない場合は削除
            result = None
        else:
            result = False
            # 　それ以外は、レイヤの間違いの可能性のためメッセージのみ
        return result, geom

    def asPolyline(self):
        return self.points

    def add_anchor(self, idx, point, undo=True):
        if undo:
            self.history.append({"state": "add_anchor", "pointidx": idx})
        self._addAnchor(idx, point)

    def move_anchor(self, idx, point, undo=True):
        if undo:
            self.history.append({"state": "move_anchor", "pointidx": idx, "point": point})
        self._moveAnchor(idx, point)

    def delete_anchor(self, idx, point, undo=True):
        if undo:
            self.history.append(
                {"state": "delete_anchor",
                 "pointidx": idx,
                 "point": point,
                 "ctrlpoint0": self.getHandle(idx * 2),
                 "ctrlpoint1": self.getHandle(idx * 2 + 1)
                 }
            )
        self._deleteAnchor(idx)

    def move_handle(self, idx, point, undo=True):
        if undo:
            self.history.append({"state": "move_handle", "pointidx": idx, "point": point})
        self._moveHandle(idx, point)

    def move_handle2(self, anchor_idx, point):
        # アンカーの両側のハンドルを移動
        handle_idx = anchor_idx * 2
        p = self.getAnchor(anchor_idx)
        pb = QgsPointXY(p[0] - (point[0] - p[0]), p[1] - (point[1] - p[1]))
        self._moveHandle(handle_idx, pb)
        self._moveHandle(handle_idx + 1, point)
        return handle_idx, pb

    def delete_handle(self, idx, point):
        self.history.append(
            {"state": "delete_handle",
             "pointidx": idx,
             "point": point,
             }
        )
        pnt = self.getAnchor(int(idx / 2))
        self._moveHandle(idx, pnt)

    def flip_line(self):
        self.history.append({"state": "flip_line"})
        self._flipBezierLine()

    # ポイントをベジエ曲線に挿入してハンドルを調整
    def insert_anchor(self, point_idx, point):
        anchor_idx = self._AnchorIdx(point_idx)
        self.history.append(
            {"state": "insert_anchor",
             "pointidx": anchor_idx,
             "ctrlpoint0": self.getHandle((anchor_idx - 1) * 2 + 1),
             "ctrlpoint1": self.getHandle((anchor_idx - 1) * 2 + 2)
             }
        )
        self._insertAnchorPointToBezier(point_idx, anchor_idx, point)

    # ジオメトリのペンでの修正
    def modified_by_geometry(self, update_geom, d, snap_to_start):
        bezier_line = self.points
        update_line = update_geom.asPolyline()
        bezier_geom = QgsGeometry.fromPolylineXY(bezier_line)

        # 新規ベジエの場合
        # 1点を新規で打つ場合
        if self.anchorCount() == 1 and len(update_line) == 2:
            self._deleteAnchor(0)
            self.add_anchor(0, update_line[0])
        # 1点もなくて、ラインを書く場合
        elif self.anchorCount() == 1 and len(self.history) == 0 and len(update_line) > 2:
            self._deleteAnchor(0)
            self.history.append({"state": "start_freehand"})
            geom = self._smoothingGeometry(update_line)
            pointnum, _, _ = self._addGeometryToBezier(geom, 0, last=True)
            self.history.append(
                {"state": "insert_geom", "pointidx": 0, "pointnum": pointnum, "cp_first": None,
                 "cp_last": None})
            self.history.append({"state": "end_freehand", "direction": "forward"})
        # 1点あって、ラインで修正する場合
        elif self.anchorCount() == 1 and len(self.history) > 0 and len(update_line) > 2:
            self.history.append({"state": "start_freehand"})
            geom = self._smoothingGeometry(update_line)
            pointnum, _, _ = self._addGeometryToBezier(geom, 1, last=True)
            self.history.append(
                {"state": "insert_geom", "pointidx": 1, "pointnum": pointnum, "cp_first": None,
                 "cp_last": None})
            self.history.append({"state": "end_freehand", "direction": "forward"})
        # ラインをラインで修正する場合
        else:
            startpnt = update_line[0]
            lastpnt = update_line[-1]
            startpnt_is_near, start_anchoridx, start_vertexidx = self._closestAnchorOfGeometry(startpnt, bezier_geom, d)
            lastpnt_is_near, last_anchoridx, last_vertexidx = self._closestAnchorOfGeometry(lastpnt, bezier_geom, d)

            # bezier_lineとupdate_lineの交差する周辺のベクトルの内積を計算。正なら順方向、不なら逆方向
            v1 = np.array(bezier_line[start_vertexidx]) - np.array(bezier_line[start_vertexidx - 1])
            v2 = np.array(update_line[1]) - np.array(update_line[0])
            direction = np.dot(v1, v2)

            self.history.append({"state": "start_freehand"})
            # 逆方向ならbezier_lineとベジエを定義しているのアンカー、ハンドル関連のリストを逆順にする
            if direction < 0:
                self._flipBezierLine()
                reversed_geom = QgsGeometry.fromPolylineXY(bezier_line)
                startpnt_is_near, start_anchoridx, start_vertexidx = self._closestAnchorOfGeometry(startpnt,
                                                                                                   reversed_geom, d)
                lastpnt_is_near, last_anchoridx, last_vertexidx = self._closestAnchorOfGeometry(lastpnt, reversed_geom,
                                                                                                d)

            # 編集箇所の前のハンドルから今のところまでをくっつける
            # ベジエ区間ごとのポイントリスト　を作成
            point_list = self._pointList(bezier_line)
            # A 部分の修正. startpnt_is_nearは修正開始の時点で確定している.
            if lastpnt_is_near and last_vertexidx > start_vertexidx and last_anchoridx <= len(point_list):

                polyline = point_list[start_anchoridx - 1][0:self._pointListIdx(start_vertexidx)] + \
                           update_line + \
                           point_list[last_anchoridx - 1][self._pointListIdx(last_vertexidx):]

                geom = self._smoothingGeometry(polyline)
                for i in range(start_anchoridx, last_anchoridx):
                    self.history.append(
                        {"state": "delete_anchor",
                         "pointidx": start_anchoridx,
                         "point": self.getAnchor(start_anchoridx),
                         "ctrlpoint0": self.getHandle(start_anchoridx * 2),
                         "ctrlpoint1": self.getHandle(start_anchoridx * 2 + 1)
                         }
                    )
                    self._deleteAnchor(start_anchoridx)

                pointnum, cp_first, cp_last = self._addGeometryToBezier(geom, start_anchoridx, last=False)
                self.history.append(
                    {"state": "insert_geom", "pointidx": start_anchoridx, "pointnum": pointnum, "cp_first": cp_first,
                     "cp_last": cp_last})

            # B 終点が離れる場合。終点が線上でも逆方向に戻っている場合、始点に閉じる場合、最終点に近い場合。
            elif not lastpnt_is_near or (lastpnt_is_near and last_vertexidx <= start_vertexidx) or last_anchoridx > len(
                    point_list):

                if start_anchoridx == self.anchorCount():  # 右端の場合はそのまま。
                    polyline = update_line
                else:  # ベジエ区間の中の何個目のポイントからか調べて、くっつける
                    polyline = point_list[start_anchoridx - 1][0:self._pointListIdx(start_vertexidx)] + update_line
                last_anchoridx = self.anchorCount()

                geom = self._smoothingGeometry(polyline)
                for i in range(start_anchoridx, last_anchoridx):
                    self.history.append(
                        {"state": "delete_anchor",
                         "pointidx": start_anchoridx,
                         "point": self.getAnchor(start_anchoridx),
                         "ctrlpoint0": self.getHandle(start_anchoridx * 2),
                         "ctrlpoint1": self.getHandle(start_anchoridx * 2 + 1)
                         }
                    )
                    self._deleteAnchor(start_anchoridx)

                pointnum, cp_first, cp_last = self._addGeometryToBezier(geom, start_anchoridx, last=True)
                self.history.append(
                    {"state": "insert_geom", "pointidx": start_anchoridx, "pointnum": pointnum, "cp_first": cp_first,
                     "cp_last": cp_last})

            self.history.append({"state": "end_freehand", "direction": "forward"})
            # ベジエの方向を元に戻す
            if direction < 0:
                self._flipBezierLine()
                self.history[-1]["direction"] = "reverse"

        # スタートポイントにスナップしていたらスムーズ処理でずれた最後の点を最初のポイントに動かす
        if snap_to_start:
            self._moveAnchor(self.anchorCount() - 1, self.getAnchor(0))

    # ベジエ曲線をpointの位置で二つのラインに分割したラインを返す
    def split_line(self, idx, point, isAnchor):
        if isAnchor:
            lineA = self.points[0:self._pointsIdx(idx) + 1]
            lineB = self.points[self._pointsIdx(idx):]
        else:
            anchor_idx = self._AnchorIdx(idx)
            self._insertAnchorPointToBezier(idx, anchor_idx, point)
            # 二つに分ける
            lineA = self.points[0:self._pointsIdx(anchor_idx) + 1]
            lineB = self.points[self._pointsIdx(anchor_idx):]

        return lineA, lineB

    def anchorCount(self):
        return len(self.anchor)

    def getAnchor(self, idx):
        return self.anchor[idx]

    def getHandle(self, idx):
        return self.handle[idx]

    def reset(self):
        self.points = []  # 補間点
        self.anchor = []  # ポイント
        self.handle = []  # コントロールポイント
        self.history = []  # undoの履歴

    # アンカーと近いかどうか.
    def checkSnapToAnchor(self, point, selected_idx, d):
        snapped = False
        snap_point = None
        snap_idx = None
        for i, p in reversed(list(enumerate(self.anchor))):
            near = self._eachPointIsNear(p, point, d)
            # freeの時にマウス位置がポイントかどうか調べたい場合
            if selected_idx is None:
                if near:
                    snapped = True
                    snap_idx = i
                    snap_point = p
                    break
            # ドラッグしているポイントが他のポイントと近いかどうかを調べたい場合
            elif selected_idx != i:
                if near:
                    snapped = True
                    snap_idx = i
                    snap_point = p
                    break
        return snapped, snap_point, snap_idx

    # ハンドルと近いかどうか
    def checkSnapToHandle(self, point, d):
        snapped = False
        snap_point = None
        snap_idx = None
        for i, p in reversed(list(enumerate(self.handle))):
            near = self._eachPointIsNear(p, point, d)
            if near:
                snapped = True
                snap_idx = i
                snap_point = p
                break
        return snapped, snap_point, snap_idx

    # 線上かどうか
    def checkSnapToLine(self, point, d):
        snapped = False
        snap_point = None
        snap_idx = None
        if self.anchorCount() > 1:
            geom = QgsGeometry.fromPolylineXY(self.points)
            (dist, minDistPoint, afterVertex, leftOf) = geom.closestSegmentWithContext(point)
            if math.sqrt(dist) < d:
                snapped = True
                snap_idx = afterVertex
                snap_point = minDistPoint
        return snapped, snap_point, snap_idx

    # スタートポイントかどうか
    def checkSnapToStart(self, point, d):
        snapped = False
        snap_point = None
        snap_idx = None
        if self.anchorCount() > 0:
            start_anchor = self.getAnchor(0)
            near = self._eachPointIsNear(start_anchor, point, d)
            if near:
                snapped = True
                snap_idx = 0
                snap_point = start_anchor
        return snapped, snap_point, snap_idx

    # アンドゥ処理
    def undo(self):
        if len(self.history) > 0:
            act = self.history.pop()
            if act["state"] == "add_anchor":
                self._deleteAnchor(act["pointidx"])
            elif act["state"] == "move_anchor":
                self._moveAnchor(act["pointidx"], act["point"])
            elif act["state"] == "move_handle":
                self._moveHandle(act["pointidx"], act["point"])
            elif act["state"] == "insert_anchor":
                self._deleteAnchor(act["pointidx"])
                self._moveHandle((act["pointidx"] - 1) * 2 + 1, act["ctrlpoint0"])
                self._moveHandle((act["pointidx"] - 1) * 2 + 2, act["ctrlpoint1"])
            elif act["state"] == "delete_anchor":
                self._addAnchor(act["pointidx"], act["point"])
                self._moveHandle(act["pointidx"] * 2, act["ctrlpoint0"])
                self._moveHandle(act["pointidx"] * 2 + 1, act["ctrlpoint1"])
            elif act["state"] == "delete_handle":
                self._moveHandle(act["pointidx"], act["point"])
            elif act["state"] == "flip_line":
                self._flipBezierLine()
                self.undo()
            elif act["state"] == "end_freehand":
                direction = act["direction"]
                if direction == "reverse":
                    self._flipBezierLine()
                act = self.history.pop()
                while act["state"] != "start_freehand":
                    if act["state"] == "insert_geom":
                        for i in range(act["pointnum"]):
                            self._deleteAnchor(act["pointidx"])
                        if act["cp_first"] is not None:
                            self._moveHandle(act["pointidx"] * 2 - 1, act["cp_first"])
                        if act["cp_last"] is not None:
                            self._moveHandle(act["pointidx"] * 2, act["cp_last"])
                    elif act["state"] == "delete_anchor":
                        self._addAnchor(act["pointidx"], act["point"])
                        self._moveHandle(act["pointidx"] * 2, act["ctrlpoint0"])
                        self._moveHandle(act["pointidx"] * 2 + 1, act["ctrlpoint1"])
                    act = self.history.pop()
                if direction == "reverse":
                    self._flipBezierLine()

        # self.dump_history()
        return len(self.history)

    # 描画の開始ポイントとのスナップを調べる
    def _eachPointIsNear(self, snap_point, point, d):
        near = False
        if (snap_point.x() - d <= point.x() <= snap_point.x() + d) and (
                snap_point.y() - d <= point.y() <= snap_point.y() + d):
            near = True
        return near

    # ポイントをベジエ曲線に挿入してハンドルを調整
    def _insertAnchorPointToBezier(self, point_idx, anchor_idx, point):
        c1a, c2a, c1b, c2b = self._recalcHandlePosition(point_idx, anchor_idx, point)
        self._addAnchor(anchor_idx, point)
        self._moveHandle((anchor_idx - 1) * 2 + 1, c1a)
        self._moveHandle((anchor_idx - 1) * 2 + 2, c2a)
        self._moveHandle((anchor_idx - 1) * 2 + 3, c1b)
        self._moveHandle((anchor_idx - 1) * 2 + 4, c2b)

    # ラインのジオメトリをベジエ曲線に挿入
    def _addGeometryToBezier(self, geom, offset, last=True):
        polyline = geom.asPolyline()
        points = np.array(polyline)
        beziers = fitCurve(points, 10.0)
        pointnum = 0

        if offset != 0:
            cp_first = self.getHandle(offset * 2 - 1)
        else:
            cp_first = None
        if last == False:
            cp_last = self.getHandle(offset * 2)
        else:
            cp_last = None

        for i, bezier in enumerate(beziers):
            if offset == 0:
                if i == 0:
                    p0 = QgsPointXY(bezier[0][0], bezier[0][1])
                    self._addAnchor(0, p0)
                    pointnum = pointnum + 1
                p1 = QgsPointXY(bezier[3][0], bezier[3][1])
                c1 = QgsPointXY(bezier[1][0], bezier[1][1])
                c2 = QgsPointXY(bezier[2][0], bezier[2][1])
                self._moveHandle(i * 2 + 1, c1)
                self._addAnchor(i + 1, p1)
                self._moveHandle((i + 1) * 2, c2)
                pointnum = pointnum + 1

            elif offset > 0:
                p1 = QgsPointXY(bezier[3][0], bezier[3][1])
                c1 = QgsPointXY(bezier[1][0], bezier[1][1])
                c2 = QgsPointXY(bezier[2][0], bezier[2][1])
                idx = (offset - 1 + i) * 2 + 1
                self._moveHandle(idx, c1)
                if i != len(beziers) - 1 or last:  # last=Fだと最後の点を挿入しない。
                    self._addAnchor(offset + i, p1)
                    pointnum = pointnum + 1
                self._moveHandle(idx + 1, c2)

        return pointnum, cp_first, cp_last

    # アンカーとハンドルを追加してベジエ曲線を更新
    def _addAnchor(self, idx, point):
        if idx == -1:
            idx = self.anchorCount()
        self.anchor.insert(idx, point)
        self.handle.insert(idx * 2, point)
        self.handle.insert(idx * 2, point)
        pointsA = []
        pointsB = []
        # 右側. idxが右端だったら右側はなし
        if idx < self.anchorCount() - 1:
            p1 = self.getAnchor(idx)
            p2 = self.getAnchor(idx + 1)
            c1 = self.getHandle(idx * 2 + 1)
            c2 = self.getHandle(idx * 2 + 2)
            pointsA = self._bezier(p1, c1, p2, c2)
        # 左側. idxが0の場合は左側はなし
        if idx >= 1:
            p1 = self.getAnchor(idx - 1)
            p2 = self.getAnchor(idx)
            c1 = self.getHandle(idx * 2 - 1)
            c2 = self.getHandle(idx * 2)
            pointsB = self._bezier(p1, c1, p2, c2)
        if idx == 0:  # 最初のアンカーは追加するだけ
            self.points = copy.copy(self.anchor)
        elif idx == 1 and idx == self.anchorCount() - 1:  # 新規追加の2点目のとき。最初の表示
            self.points = pointsB
        elif idx >= 2 and idx == self.anchorCount() - 1:  # 2点目以降の追加とき
            self.points = self.points + pointsB[1:]
        else:  # 両側のアンカーがすでにあって挿入のとき
            self.points[self._pointsIdx(idx - 1):self._pointsIdx(idx) + 1] = pointsB + pointsA[1:]

        # アンカーを削除してベジエ曲線を更新

    def _deleteAnchor(self, idx):
        # 左端の削除
        if idx == 0:
            del self.points[0:self.INTERPORATION]
        # 右端の削除
        elif idx + 1 == self.anchorCount():
            del self.points[self._pointsIdx(idx - 1) + 1:]
        # 中間の削除
        else:
            p1 = self.getAnchor(idx - 1)
            p2 = self.getAnchor(idx + 1)
            c1 = self.getHandle((idx - 1) * 2 + 1)
            c2 = self.getHandle((idx + 1) * 2)
            points = self._bezier(p1, c1, p2, c2)
            self.points[self._pointsIdx(idx - 1):self._pointsIdx(idx + 1) + 1] = points
        self._delHandle(2 * idx)
        self._delHandle(2 * idx)
        self._delAnchor(idx)

        return

    # 特定のアンカーを移動してベジエ曲線を更新
    def _moveAnchor(self, idx, point):
        diff = point - self.getAnchor(idx)
        self._setAnchor(idx, point)
        self._setHandle(idx * 2, self.getHandle(idx * 2) + diff)
        self._setHandle(idx * 2 + 1, self.getHandle(idx * 2 + 1) + diff)
        # ベジエを更新
        # 1点だけの場合
        if idx == 0 and self.anchorCount() == 1:
            self.points = copy.copy(self.anchor)
        else:
            # 右側
            if idx < self.anchorCount() - 1:
                p1 = self.getAnchor(idx)
                p2 = self.getAnchor(idx + 1)
                c1 = self.getHandle(idx * 2 + 1)
                c2 = self.getHandle(idx * 2 + 2)
                points = self._bezier(p1, c1, p2, c2)
                self.points[self._pointsIdx(idx):self._pointsIdx(idx + 1) + 1] = points
            # 左側
            if idx >= 1:
                p1 = self.getAnchor(idx - 1)
                p2 = self.getAnchor(idx)
                c1 = self.getHandle(idx * 2 - 1)
                c2 = self.getHandle(idx * 2)
                points = self._bezier(p1, c1, p2, c2)
                self.points[self._pointsIdx(idx - 1):self._pointsIdx(idx) + 1] = points

    # ハンドルを移動してベジエ曲線を更新
    def _moveHandle(self, idx, point):
        self._setHandle(idx, point)
        # ベジエの更新
        # ポイント2点目以降なら更新
        if self.anchorCount() > 1:
            # 右側
            if idx % 2 == 1 and idx < self._handleCount() - 1:
                idxP = idx // 2
                p1 = self.getAnchor(idxP)
                p2 = self.getAnchor(idxP + 1)
                c1 = self.getHandle(idx)
                c2 = self.getHandle(idx + 1)
            # 左側
            elif idx % 2 == 0 and idx >= 1:
                idxP = (idx - 1) // 2
                p1 = self.getAnchor(idxP)
                p2 = self.getAnchor(idxP + 1)
                c1 = self.getHandle(idx - 1)
                c2 = self.getHandle(idx)
            # 上記以外は何もしない
            else:
                return
            points = self._bezier(p1, c1, p2, c2)
            self.points[self._pointsIdx(idxP):self._pointsIdx(idxP + 1) + 1] = points

    # ベジエ曲線にアンカーを追加する際にアンカー間のポイントリストから両側のハンドル位置を再計算する
    def _recalcHandlePosition(self, point_idx, anchor_idx, pnt):

        bezier_idx = self._pointListIdx(point_idx)
        if 2 < bezier_idx:  # pointsが4点以上あれば再計算できる.挿入の左側
            pointsA = self.points[self._pointsIdx(anchor_idx - 1):point_idx] + [pnt]
            ps, cs, pe, ce = self._invertBezier(pointsA)
            c1a = QgsPointXY(cs[0], cs[1])
            c2a = QgsPointXY(ce[0], ce[1])
            # self.log("{},{}".format(cs,ce))
        else:  # 4点未満の場合は、ハンドルをアンカーと同じにして直線で結ぶ
            c1a = self.points[self._pointsIdx(anchor_idx - 1)]
            c2a = pnt
        if self.INTERPORATION - 1 > bezier_idx:  # 挿入の右側
            pointsB = [pnt] + self.points[point_idx:self._pointsIdx(anchor_idx) + 1]
            ps, cs, pe, ce = self._invertBezier(pointsB, type="B")
            c1b = QgsPointXY(cs[0], cs[1])
            c2b = QgsPointXY(ce[0], ce[1])
            # self.log("{},{}".format(cs, ce))
        else:
            c1b = pnt
            c2b = self.points[self._pointsIdx(anchor_idx)]

        return (c1a, c2a, c1b, c2b)

    # 始点、終点のコントロールポイントで定義されるベジエ曲線をbezier_numの数で補間したリストを返す。
    def _bezier(self, p1, c1, p2, c2):
        points = []
        for t in range(0, self.INTERPORATION + 1):
            t = 1.0 * t / self.INTERPORATION
            bx = (1 - t) ** 3 * p1.x() + 3 * t * (1 - t) ** 2 * c1.x() + 3 * t ** 2 * (1 - t) * c2.x() + t ** 3 * p2.x()
            by = (1 - t) ** 3 * p1.y() + 3 * t * (1 - t) ** 2 * c1.y() + 3 * t ** 2 * (1 - t) * c2.y() + t ** 3 * p2.y()
            points.append(QgsPointXY(bx, by))
        return points

    # 10点で補間されたベジエ曲線のリストから始点、終点のコントロールポイントを返す。
    def _invertBezier(self, points, type="A"):
        # pointsから左右のコントロールポイントを求める
        # t1とt2の時の座標を代入して、連立方程式の解を解く
        # type B は 後ろの2点を使って連立方程式を解く。挿入時の右側の処理のために使用。
        ps = np.array(points[0])
        pe = np.array(points[-1])
        # tの分割数
        tnum = len(points) - 1
        # self.log("{},{},{}".format(tnum,ps,pe))
        if type == "A":
            t1 = 1.0 / tnum
            p1 = np.array(points[1])
            t2 = 2.0 / tnum
            p2 = np.array(points[2])
        elif type == "B":
            t1 = (tnum - 1) / tnum
            p1 = np.array(points[-2])
            t2 = (tnum - 2) / tnum
            p2 = np.array(points[-3])

        aa = 3 * t1 * (1 - t1) ** 2
        bb = 3 * t1 ** 2 * (1 - t1)
        cc = ps * (1 - t1) ** 3 + pe * t1 ** 3 - p1
        dd = 3 * t2 * (1 - t2) ** 2
        ee = 3 * t2 ** 2 * (1 - t2)
        ff = ps * (1 - t2) ** 3 + pe * t2 ** 3 - p2
        # self.log("{},{},{},{},{},{}".format(aa, bb, cc, dd, ee, ff))
        c0 = (bb * ff - cc * ee) / (aa * ee - bb * dd)
        c1 = (aa * ff - cc * dd) / (bb * dd - aa * ee)
        # c1=(3,3)
        # c2=(10,2)
        # self.log("{},{},{},{}".format(ps,pe,c0,c1))
        return ps, c0, pe, c1

    # ベジエ曲線を逆順に変更
    def _flipBezierLine(self):
        self.anchor.reverse()
        self.handle.reverse()
        self.points.reverse()

    # ベジエ曲線のラインからアンカー間のポイントリストを返す
    def _pointList(self, polyline):
        # INTERPORATION+1の個数づつ取り出す（アンカーの点は重複させるので+1になる）。最後の要素は余分なので取り除く。
        return [polyline[i:i + self.INTERPORATION + 1] for i in range(0, len(polyline), self.INTERPORATION)][:-1]

    # ベジエ曲線のインデックスからアンカー間のポイントリストのインデックスを返す
    def _pointListIdx(self, point_idx):
        return (point_idx - 1) % self.INTERPORATION + 1

    # アンカーのインデックスからベジエ曲線のインデックスを返す
    def _pointsIdx(self, anchor_idx):
        return anchor_idx * self.INTERPORATION

    # ベジエ曲線のインデックスからアンカーのインデックス（後方）を返す
    def _AnchorIdx(self, point_idx):
        return (point_idx - 1) // self.INTERPORATION + 1

    def _setAnchor(self, idx, point):
        self.anchor[idx] = point

    def _delAnchor(self, idx):
        del self.anchor[idx]

    def _handleCount(self):
        return len(self.handle)

    def _setHandle(self, idx, point):
        self.handle[idx] = point

    def _delHandle(self, idx):
        del self.handle[idx]

    # ポインタの次のアンカーのidとvertexのidを返す。アンカーとスナップしている場合は、次のIDを返す。右端のアンカーの処理は注意
    def _closestAnchorOfGeometry(self, point, geom, d):
        """

        """
        near = False
        (dist, minDistPoint, vertexidx, leftOf) = geom.closestSegmentWithContext(point)
        anchoridx = self._AnchorIdx(vertexidx)
        if math.sqrt(dist) < d:
            near = True
        return near, anchoridx, vertexidx

    def _smoothing(self, polyline):
        """
        smoothing by moving average
        """
        poly = np.reshape(polyline, (-1, 2)).T
        num = 8
        b = np.ones(num) / float(num)
        x_pad = np.pad(poly[0], (num - 1, 0), 'edge')
        y_pad = np.pad(poly[1], (num - 1, 0), 'edge')
        x_smooth = np.convolve(x_pad, b, mode='valid')
        y_smooth = np.convolve(y_pad, b, mode='valid')
        poly_smooth = [QgsPointXY(x, y) for x, y in zip(x_smooth, y_smooth)]
        return poly_smooth

    def _smoothingGeometry(self, polyline):
        polyline = self._smoothing(polyline)
        geom = QgsGeometry.fromPolylineXY(polyline)
        return geom

    # for debug
    def dump_history(self):
        self.log("##### history dump ######")
        for h in self.history:
            self.log("{}".format(h.items()))
        self.log("#####      end     ######")

    def log(self, msg):
        QgsMessageLog.logMessage(msg, 'MyPlugin', Qgis.Info)
