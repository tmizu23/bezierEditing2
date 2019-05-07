# -*- coding: utf-8 -*-
from qgis.core import *
from qgis.PyQt.QtGui import *
from qgis.gui import *

class BezierMarker:

    def __init__(self, canvas, bezier_geometry):
        self.canvas = canvas
        self.b = bezier_geometry
        self.anchor_marks = []  # アンカーのマーカーリスト
        self.handle_marks = []  # ハンドルのマーカーリスト
        self.handle_rbls = []  # ハンドルのラインリスト

        # ベジエ曲線のライン
        self.bezier_rbl = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.bezier_rbl.setColor(QColor(255, 0, 0,150))
        self.bezier_rbl.setWidth(2)
            
    # ベジエ曲線とすべてのマーカーを削除する
    def removeBezierLineMarkers(self):
        self._removeAllMarker(self.anchor_marks)  # アンカーマーカーの削除
        self._removeAllMarker(self.handle_marks)  # ハンドルマーカーの削除
        self._removeAllRubberBand(self.handle_rbls)  # ハンドルのラインの削除
        self.anchor_marks = []
        self.handle_marks = []
        self.handle_rbls = []
        self.bezier_rbl.reset(QgsWkbTypes.LineGeometry)  # ベイジライン

    # ベジエ曲線とすべてのマーカーを表示する
    def showBezierLineMarkers(self,show_handle=None):
        self.removeBezierLineMarkers()
        for point in self.b.anchor:
            self._setAnchorHandleMarker(self.anchor_marks, len(self.anchor_marks), point)
            self._setAnchorHandleMarker(self.handle_marks, len(self.handle_marks), point, QColor(125, 125, 125))
            self._setAnchorHandleMarker(self.handle_marks, len(self.handle_marks), point, QColor(125, 125, 125))
            self._setHandleLine(self.handle_rbls, len(self.handle_marks), point)
            self._setHandleLine(self.handle_rbls, len(self.handle_marks), point)
        for idx, point in enumerate(self.b.handle):
            self.handle_rbls[idx].movePoint(1, point, 0)
            self.handle_marks[idx].setCenter(point)
        self._setBezierLine(self.b.points, self.bezier_rbl)

        if show_handle is not None:
            self.showHandle(show_handle)

    # アンカーを追加してベジエ曲線の表示を更新
    def addAnchorMarker(self, idx, point):
        if idx == -1:
            idx = len(self.anchor_marks)
        # アンカーのマーカー追加
        self._setAnchorHandleMarker(self.anchor_marks, idx, point)
        # ハンドルのマーカーとラインの追加（両側）
        self._setAnchorHandleMarker(self.handle_marks, 2 * idx, point, QColor(125, 125, 125))
        self._setAnchorHandleMarker(self.handle_marks, 2 * idx, point, QColor(125, 125, 125))
        self._setHandleLine(self.handle_rbls, 2 * idx, point)
        self._setHandleLine(self.handle_rbls, 2 * idx, point)
        # ベジエ曲線の表示
        self._setBezierLine(self.b.points, self.bezier_rbl)

    # アンカーを削除してベジエ曲線の表示を更新
    def deleteAnchorMarker(self, idx):
        self._removeMarker(self.handle_marks, 2 * idx)
        self._removeRubberBand(self.handle_rbls, 2 * idx)
        self._removeMarker(self.handle_marks, 2 * idx)
        self._removeRubberBand(self.handle_rbls, 2 * idx)
        self._removeMarker(self.anchor_marks, idx)
        self._setBezierLine(self.b.points, self.bezier_rbl)

    # アンカーを移動してベジエ曲線の表示を更新
    def moveAnchorMarker(self, idx, point):
        # アンカーのマーカを移動
        self.anchor_marks[idx].setCenter(point)
        # ハンドルのマーカーとラインを移動
        self.handle_marks[idx * 2].setCenter(self.b.getHandle(idx * 2))
        self.handle_marks[idx * 2 + 1].setCenter(self.b.getHandle(idx * 2 + 1))
        self.handle_rbls[idx * 2].movePoint(0, point, 0)
        self.handle_rbls[idx * 2 + 1].movePoint(0, point, 0)
        self.handle_rbls[idx * 2].movePoint(1, self.b.getHandle(idx * 2), 0)
        self.handle_rbls[idx * 2 + 1].movePoint(1, self.b.getHandle(idx * 2 + 1), 0)
        # ベジエ曲線の表示
        self._setBezierLine(self.b.points, self.bezier_rbl)

    # ハンドルを移動してベジエ曲線の表示を更新
    def moveHandleMarker(self, idx, point):
        # ハンドルのラインの終点を移動
        self.handle_rbls[idx].movePoint(1, point, 0)
        # ハンドルのマーカーを移動
        self.handle_marks[idx].setCenter(point)
        # ベジエ曲線の表示
        self._setBezierLine(self.b.points, self.bezier_rbl)

    # ハンドルの表示、非表示を切り替える
    def showHandle(self,show):
        if show:
            self._showAllMarker(self.handle_marks)
            self._showAllRubberBand(self.handle_rbls)
        else:
            self._hideAllMarker(self.handle_marks)
            self._hideAllRubberBand(self.handle_rbls)
        self.canvas.refresh()

    # ベジエ曲線の表示
    def _setBezierLine(self, points, rbl):
        # 最後に更新
        rbl.reset(QgsWkbTypes.LineGeometry)
        for point in points:
            update = point is points[-1]
            rbl.addPoint(point, update)

    # 新規のアンカー、ハンドルのマーカーを作成
    def _setAnchorHandleMarker(self, markers, idx, point, color=QColor(0, 0, 0)):
        # ポイントorハンドルのマーカーをidxの前に追加
        marker = QgsVertexMarker(self.canvas)
        marker.setIconType(QgsVertexMarker.ICON_BOX)
        marker.setColor(color)
        marker.setPenWidth(2)
        marker.setIconSize(5)
        marker.setCenter(point)
        marker.show()
        markers.insert(idx, marker)
        return markers

    # 新規のハンドルラインを作成
    def _setHandleLine(self, rbls, idx, point):
        rbl = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        rbl.setColor(QColor(0, 0, 0))
        rbl.setWidth(1)
        rbl.addPoint(point)
        rbl.addPoint(point)
        rbls.insert(idx, rbl)
        return rbls

    # 特定のマーカーの削除
    def _removeMarker(self, markers, idx):
        m = markers[idx]
        self.canvas.scene().removeItem(m)
        del markers[idx]

    # 全マーカーの削除
    def _removeAllMarker(self, markers):
        for m in markers:
            self.canvas.scene().removeItem(m)

    # 全マーカーの表示
    def _showAllMarker(self, markers):
        for m in markers:
            m.show()

    # 全マーカーの非表示
    def _hideAllMarker(self, markers):
        for m in markers:
            m.hide()

    # 特定のラバーバンドの削除
    def _removeRubberBand(self, rbls, index):
        rbl = rbls[index]
        self.canvas.scene().removeItem(rbl)
        del rbls[index]
    
    # 全ラバーバンドの削除
    def _removeAllRubberBand(self, rbls):
        for rbl in rbls:
            self.canvas.scene().removeItem(rbl)
    
    # 全ラバーバンドの表示    
    def _showAllRubberBand(self, rbls):
        for rbl in rbls:
            rbl.setColor(QColor(0, 0, 0, 255))
    
    # 全ラバーバンドの非表示
    def _hideAllRubberBand(self, rbls):
        for rbl in rbls:
            rbl.setColor(QColor(0, 0, 0, 0))