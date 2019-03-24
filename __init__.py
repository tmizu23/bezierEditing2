# -*- coding: utf-8 -*-

from __future__ import absolute_import
def name():
    return "Bezier editing2"


def description():
    return "BezierCurve line/polygon editing"


def version():
    return "Version 2.0.0"


def icon():
    return "icon.png"


def qgisMinimumVersion():
    return "2.18"

def author():
    return "Takayuki Mizutani"

def email():
    return "mizutani.takayuki@gmail.com"

def classFactory(iface):
  from .bezierediting import BezierEditing2
  return BezierEditing2(iface)

