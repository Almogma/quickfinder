#-----------------------------------------------------------
#
# QGIS Quick Finder Plugin
# Copyright (C) 2013 Denis Rouzaud
#
#-----------------------------------------------------------
#
# licensed under the terms of GNU GPL 2
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
#---------------------------------------------------------------------

import unicodedata

from PyQt4.QtCore import Qt, pyqtSlot, QCoreApplication, QVariant
from PyQt4.QtGui import QDockWidget, QMessageBox
from qgis.core import QgsFeature, QgsFeatureRequest, QgsRectangle
from qgis.gui import QgsMessageBar

from ..qgiscombomanager import VectorLayerCombo, FieldCombo
from ..core.mysettings import MySettings
from ..ui.ui_quickfinder import Ui_quickFinder


def remove_accents(data):
    return ''.join(x for x in unicodedata.normalize('NFKD', data) if unicodedata.category(x)[0] == 'L').lower()


class FinderDock(QDockWidget, Ui_quickFinder):
    def __init__(self, iface):
        self.iface = iface
        QDockWidget.__init__(self)
        self.setupUi(self)
        self.layerComboManager = VectorLayerCombo(self.layerCombo)
        self.fieldComboManager = FieldCombo(self.fieldCombo, self.layerComboManager)
        self.layerComboManager.layerChanged.connect(self.layerChanged)
        self.modeButtonGroup.buttonClicked.connect(self.layerChanged)
        self.fieldComboManager.fieldChanged.connect(self.layerChanged)
        self.fieldComboManager.fieldChanged.connect(self.fieldChanged)
        self.layer = None
        self.operatorBox.hide()
        self.processWidgetGroup.hide()
        self.layerChanged()
        if MySettings().value("dockArea") == 1:
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self)
        else:
            self.iface.addDockWidget(Qt.LeftDockWidgetArea, self)
        self.setVisible(False)

    def showEvent(self, e):
        layer = self.iface.legendInterface().currentLayer()
        self.layerComboManager.setLayer(layer)

    def layerChanged(self):
        self.modeWidgetGroup.setEnabled(False)
        self.searchWidgetGroup.setEnabled(False)
        self.idLine.clear()
        self.layer = self.layerComboManager.getLayer()
        if self.layer is None:
            return
        self.modeWidgetGroup.setEnabled(True)
        if self.fieldButton.isChecked() and self.fieldCombo.currentIndex() == -1:
            return
        self.searchWidgetGroup.setEnabled(True)
        self.on_selectBox_clicked()

    def fieldChanged(self):
        if self.layer is None:
            return
        fieldIndex = self.fieldComboManager.getFieldIndex()
        if fieldIndex is None:
            return
        fieldType = self.layer.dataProvider().fields()[fieldIndex].type()
        # if field is a string set operator to "LIKE"
        if fieldType == QVariant.String:
            self.operatorBox.setCurrentIndex(6)
        # if field is not string, do not use "LIKE"
        if fieldType != QVariant.String and self.operatorBox.currentIndex() == 6:
            self.operatorBox.setCurrentIndex(0)

               
    @pyqtSlot(name="on_selectBox_clicked")
    def on_selectBox_clicked(self):
        if self.layer is None or not self.selectBox.isChecked():
            self.panBox.setEnabled(False)
            self.scaleBox.setEnabled(False)
        else:
            self.panBox.setEnabled(self.layer.hasGeometryType())
            self.scaleBox.setEnabled(self.layer.hasGeometryType() and self.panBox.isChecked())

    @pyqtSlot(name="on_cancelButton_pressed")
    def cancelSearch(self):
        self.continueSearch = False

    @pyqtSlot(name="on_goButton_pressed")
    def search(self):
        self.layer = self.layerComboManager.getLayer()
        if self.layer is None:
            return
        toFind = self.idLine.text()
        f = QgsFeature()
        if self.idButton.isChecked():
            try:
                id = long(toFind)
            except ValueError:
                self.iface.messageBar().pushMessage("Quick Finder", "ID must be strictly composed of digits.",
                                                    QgsMessageBar.WARNING, 3)
                return

            if self.layer.getFeatures(QgsFeatureRequest().setFilterFid(id).setFlags(QgsFeatureRequest.NoGeometry)).nextFeature(f) is False:
                self.iface.messageBar().pushMessage("Quick Finder", "No results found.", QgsMessageBar.INFO, 2)
                return
            self.iface.messageBar().pushMessage("Quick Finder", "Feature found!", QgsMessageBar.INFO, 2)
            self.processResults([f.id()])
        else:
            results = []
            fieldName = self.fieldComboManager.getFieldName()
            fieldIndex = self.fieldComboManager.getFieldIndex()
            if fieldName == "":
                self.iface.messageBar().pushMessage("Quick Finder", "Choose a field first.", QgsMessageBar.WARNING, 3)
                return
            operator = self.operatorBox.currentIndex()
            if operator in (1, 2, 3, 4, 5):
                try:
                    float(toFind)
                except ValueError:
                    self.iface.messageBar().pushMessage("Quick Finder", "Value must be numeric for chosen operator",
                                                        QgsMessageBar.WARNING, 3)
                    return
            # show progress bar
            self.progressBar.setMinimum(0)
            self.progressBar.setMaximum(self.layer.featureCount())
            self.progressBar.setValue(0)
            self.processWidgetGroup.show()
            # disable rest of UI
            self.layerWidgetGroup.setEnabled(False)
            self.modeWidgetGroup.setEnabled(False)
            self.searchWidgetGroup.setEnabled(False)
            # create feature request
            featReq = QgsFeatureRequest()
            featReq.setFlags(QgsFeatureRequest.NoGeometry)
            featReq.setSubsetOfAttributes([fieldIndex])
            iter = self.layer.getFeatures(featReq)
            # process
            k = 0
            self.continueSearch = True
            while iter.nextFeature(f) and self.continueSearch:
                k += 1
                if self.evaluate(f[fieldName], toFind, operator):
                    results.append(f.id())
                self.progressBar.setValue(k)
                QCoreApplication.processEvents()
            # reset UI
            self.processWidgetGroup.hide()
            self.layerWidgetGroup.setEnabled(True)
            self.modeWidgetGroup.setEnabled(True)
            self.searchWidgetGroup.setEnabled(True)
            # process results
            if self.continueSearch:
                self.iface.messageBar().pushMessage("Quick Finder", "%u features found!" % len(results),
                                                    QgsMessageBar.INFO, 2)
                self.processResults(results)
                    
    def evaluate(self, v1, v2, operator):
        if operator == 0:
            return v1 == v2
        elif operator == 1:
            return float(v1) == float(v2)
        elif operator == 2:
            return float(v1) <= float(v2)
        elif operator == 3:
            return float(v1) >= float(v2)
        elif operator == 4:
            return float(v1) < float(v2)
        elif operator == 5:
            return float(v1) > float(v2)
        elif operator == 6:
            try:
                remove_accents(v1).index(remove_accents(v2))
                return True
            except ValueError:
                return False

    def processResults(self, results):
        if self.layer is None:
            return
        if self.selectBox.isChecked():
            self.layer.setSelectedFeatures(results)
            if len(results) == 0:
                return

            if self.panBox.isEnabled() and self.panBox.isChecked():
                canvas = self.iface.mapCanvas()
                rect = canvas.mapRenderer().layerExtentToOutputExtent(self.layer, self.layer.boundingBoxOfSelected())
                if rect is not None:
                    if self.scaleBox.isEnabled() and self.scaleBox.isChecked():
                        rect.scale(1.5)
                        canvas.setExtent(rect)
                    else:
                        canvas.setExtent(QgsRectangle(rect.center(), rect.center()))
                canvas.refresh()
        if self.formBox.isChecked():
            nResults = len(results)
            if nResults > 25:
                return
            if nResults > 3:
                reply = QMessageBox.question(self.iface.mainWindow(), "Quick Finder",
                                             "%s results were found. Are you sure to open the %s feature forms ?" %
                                             (nResults, nResults), QMessageBox.Yes, QMessageBox.No)
                if reply == QMessageBox.No:
                    return
            f = QgsFeature()
            for id in results:
                if self.layer.getFeatures(QgsFeatureRequest().setFilterFid(id)).nextFeature(f):
                    self.iface.openFeatureForm(self.layer, f)

