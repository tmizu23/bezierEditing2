# -*- coding: utf-8 -*-
from qgis.core import *
from .fitCurves import *
import math
import numpy as np

class BezierGeometry:

    def __init__(self):
        self.INTERPORATION = 10
        self.points = []  # 補間点
        self.anchor = []  # ポイント
        self.handle = []  # コントロールポイント

    @classmethod
    def convertPointToBezier(cls, point):
        b = cls()
        b.addAnchor(0, point)
        return b

    @classmethod
    def convertLineToBezier(cls, polyline):
        b = cls()
        point_list = b.pointList(polyline)
        for i, points_i in enumerate(point_list):
            ps, cs, pe, ce = b._invertBezier(points_i)
            p0 = QgsPointXY(ps[0], ps[1])
            p1 = QgsPointXY(pe[0], pe[1])
            c0 = QgsPointXY(ps[0], ps[1])
            c1 = QgsPointXY(cs[0], cs[1])
            c2 = QgsPointXY(ce[0], ce[1])
            c3 = QgsPointXY(pe[0], pe[1])
            if i == 0:
                b.addAnchor(-1, p0)
                b.moveHandle(i * 2, c0)
                b.moveHandle(i * 2 + 1, c1)
                b.addAnchor(-1, p1)
                b.moveHandle((i + 1) * 2, c2)
                b.moveHandle((i + 1) * 2 + 1, c3)
            else:
                b.moveHandle(i * 2 + 1, c1)
                b.addAnchor(-1, p1)
                b.moveHandle((i + 1) * 2, c2)
                b.moveHandle((i + 1) * 2 + 1, c3)
        return b

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

    # アンカーとハンドルを追加してベジエ曲線を更新
    def addAnchor(self, idx, point):
        if idx==-1:
            idx=self.anchorCount()
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
            self.points = self.anchor
        elif idx == 1 and idx == self.anchorCount() - 1:  # 新規追加の2点目のとき。最初の表示
            self.points = pointsB
        elif idx >= 2 and idx == self.anchorCount() - 1:  # 2点目以降の追加とき
            self.points = self.points + pointsB[1:]
        else:  # 両側のアンカーがすでにあって挿入のとき
            self.points[self.pointsIdx(idx - 1):self.pointsIdx(idx) + 1] = pointsB + pointsA[1:]



    # アンカーを削除してベジエ曲線を更新
    def deleteAnchor(self, idx):
        # 左端の削除
        if idx == 0:
            del self.points[0:self.INTERPORATION]
        # 右端の削除
        elif idx + 1 == self.anchorCount():
            del self.points[self.pointsIdx(idx - 1) + 1:]
        # 中間の削除
        else:
            p1 = self.getAnchor(idx - 1)
            p2 = self.getAnchor(idx + 1)
            c1 = self.getHandle((idx - 1) * 2 + 1)
            c2 = self.getHandle((idx + 1) * 2)
            points = self._bezier(p1, c1, p2, c2)
            self.points[self.pointsIdx(idx - 1):self.pointsIdx(idx + 1) + 1] = points

        self._delHandle(2 * idx)
        self._delHandle(2 * idx)
        self._delAnchor(idx)

        return

    # 特定のアンカーを移動してベジエ曲線を更新
    def moveAnchor(self, idx, point):
        diff = point - self.getAnchor(idx)
        self._setAnchor(idx, point)
        self._setHandle(idx*2, self.getHandle(idx * 2)+diff)
        self._setHandle(idx*2+1,self.getHandle(idx * 2+1)+diff)
        # ベジエを更新
        # 右側
        if idx < self.anchorCount()-1:
            p1 = self.getAnchor(idx)
            p2 = self.getAnchor(idx + 1)
            c1 = self.getHandle(idx * 2+1)
            c2 = self.getHandle(idx * 2 + 2)
            points = self._bezier(p1, c1, p2, c2)
            self.points[self.pointsIdx(idx):self.pointsIdx(idx + 1) + 1] = points
        # 左側
        if idx >= 1:
            p1 = self.getAnchor(idx - 1)
            p2 = self.getAnchor(idx)
            c1 = self.getHandle(idx * 2 - 1)
            c2 = self.getHandle(idx * 2)
            points = self._bezier(p1, c1, p2, c2)
            self.points[self.pointsIdx(idx - 1):self.pointsIdx(idx) + 1] = points

    # ハンドルを移動してベジエ曲線を更新
    def moveHandle(self, idx, point):
        self._setHandle(idx,point)
        # ベジエの更新
        # ポイント2点目以降なら更新
        if self.anchorCount() > 1:
            #右側
            if idx % 2 == 1 and idx < self._handleCount()-1:
                idxP = idx // 2
                p1 = self.getAnchor(idxP)
                p2 = self.getAnchor(idxP + 1)
                c1 = self.getHandle(idx)
                c2 = self.getHandle(idx + 1)
            #左側
            elif idx % 2 == 0 and idx >= 1:
                idxP = (idx - 1) // 2
                p1 = self.getAnchor(idxP)
                p2 = self.getAnchor(idxP + 1)
                c1 = self.getHandle(idx - 1)
                c2 = self.getHandle(idx)
            #上記以外は何もしない
            else:
                return
            points = self._bezier(p1, c1, p2, c2)
            self.points[self.pointsIdx(idxP):self.pointsIdx(idxP + 1) + 1] = points

    # ベジエ曲線を逆順に変更
    def flipBezierLine(self):
        self.anchor.reverse()
        self.handle.reverse()
        self.points.reverse()

    # ベジエ曲線のラインからアンカー間のポイントリストを返す
    def pointList(self, polyline):
        #INTERPORATION+1の個数づつ取り出す（アンカーの点は重複させるので+1になる）。最後の要素は余分なので取り除く。
        return [polyline[i:i + self.INTERPORATION+1] for i in range(0, len(polyline), self.INTERPORATION)][:-1]

    # ベジエ曲線のインデックスからアンカー間のポイントリストのインデックスを返す
    def pointListIdx(self, point_idx):
        return (point_idx - 1) % self.INTERPORATION + 1

    # アンカーのインデックスからベジエ曲線のインデックスを返す
    def pointsIdx(self, anchor_idx):
        return anchor_idx * self.INTERPORATION

    # ベジエ曲線のインデックスからアンカーのインデックス（後方）を返す
    def AnchorIdx(self, point_idx):
        return (point_idx - 1) // self.INTERPORATION + 1

    # ポイントをベジエ曲線に挿入してハンドルを調整
    def insertAnchorPointToBezier(self,point_idx, point):
        anchor_idx = self.AnchorIdx(point_idx)
        c1a, c2a, c1b, c2b = self._recalcHandlePosition(point_idx, anchor_idx, point)
        self.addAnchor(anchor_idx, point)
        self.moveHandle((anchor_idx - 1) * 2 + 1, c1a)
        self.moveHandle((anchor_idx - 1) * 2 + 2, c2a)
        self.moveHandle((anchor_idx - 1) * 2 + 3, c1b)
        self.moveHandle((anchor_idx - 1) * 2 + 4, c2b)

    # ラインのジオメトリをベジエ曲線に挿入
    def insertGeomToBezier(self, offset, geom, last=True):
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
                    self.addAnchor(0, p0)
                    pointnum=pointnum+1
                p1 = QgsPointXY(bezier[3][0], bezier[3][1])
                c1 = QgsPointXY(bezier[1][0], bezier[1][1])
                c2 = QgsPointXY(bezier[2][0], bezier[2][1])
                self.moveHandle(i * 2 + 1, c1)
                self.addAnchor(i + 1, p1)
                self.moveHandle((i + 1) * 2, c2)
                pointnum = pointnum + 1

            elif offset > 0:
                p1 = QgsPointXY(bezier[3][0], bezier[3][1])
                c1 = QgsPointXY(bezier[1][0], bezier[1][1])
                c2 = QgsPointXY(bezier[2][0], bezier[2][1])
                idx = (offset - 1 + i) * 2 + 1
                self.moveHandle(idx, c1)
                if i != len(beziers) - 1 or last:  # last=Fだと最後の点を挿入しない。
                    self.addAnchor(offset + i, p1)
                    pointnum = pointnum + 1
                self.moveHandle(idx + 1, c2)

        return pointnum, cp_first, cp_last

    # ベジエ曲線をpointの位置で二つのラインに分割したラインを返す
    def splitLine(self, point_idx, point):
        self.insertAnchorPointToBezier(point_idx, point)
        # 二つに分ける
        anchor_idx = self.AnchorIdx(point_idx)
        lineA = self.points[0:self.pointsIdx(anchor_idx) + 1]
        lineB = self.points[self.pointsIdx(anchor_idx):]

        return lineA, lineB

    # ベジエ曲線にアンカーを追加する際にアンカー間のポイントリストから両側のハンドル位置を再計算する
    def _recalcHandlePosition(self, point_idx, anchor_idx, pnt):

        bezier_idx = self.pointListIdx(point_idx)
        if 2 < bezier_idx:  # pointsが4点以上あれば再計算できる.挿入の左側
            pointsA = self.points[self.pointsIdx(anchor_idx - 1):point_idx] + [pnt]
            ps, cs, pe, ce = self._invertBezier(pointsA)
            c1a = QgsPointXY(cs[0], cs[1])
            c2a = QgsPointXY(ce[0], ce[1])
            # self.log("{},{}".format(cs,ce))
        else:  # 4点未満の場合は、ハンドルをアンカーと同じにして直線で結ぶ
            c1a = self.points[self.pointsIdx(anchor_idx - 1)]
            c2a = pnt
        if self.INTERPORATION - 1 > bezier_idx:  # 挿入の右側
            pointsB = [pnt] + self.points[point_idx:self.pointsIdx(anchor_idx) + 1]
            ps, cs, pe, ce = self._invertBezier(pointsB, type="B")
            c1b = QgsPointXY(cs[0], cs[1])
            c2b = QgsPointXY(ce[0], ce[1])
            # self.log("{},{}".format(cs, ce))
        else:
            c1b = pnt
            c2b = self.points[self.pointsIdx(anchor_idx)]

        return (c1a,c2a,c1b,c2b)

    # 始点、終点のコントロールポイントで定義されるベジエ曲線をbezier_numの数で補間したリストを返す。
    def _bezier(self, p1, c1, p2, c2):
        points = []
        for t in range(0, self.INTERPORATION+1):
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
        #tの分割数
        tnum = len(points)-1
        #self.log("{},{},{}".format(tnum,ps,pe))
        if type=="A":
            t1 = 1.0 / tnum
            p1 = np.array(points[1])
            t2 = 2.0 / tnum
            p2 = np.array(points[2])
        elif type=="B":
            t1 = (tnum-1) / tnum
            p1 = np.array(points[-2])
            t2 = (tnum-2) / tnum
            p2 = np.array(points[-3])

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

    def log(self, msg):
        QgsMessageLog.logMessage(msg, 'MyPlugin', Qgis.Info)