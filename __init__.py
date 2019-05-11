# -*- coding: utf-8 -*-
def classFactory(iface):
  from .bezierediting import BezierEditing
  return BezierEditing(iface)



