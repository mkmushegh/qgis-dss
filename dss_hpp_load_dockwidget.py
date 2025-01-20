# -*- coding: utf-8 -*-
import os
import sys
import traceback
from qgis.PyQt import QtWidgets, uic, QtGui
from qgis.PyQt.QtCore import pyqtSignal, QVariant, Qt
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import (
    QgsPointXY,
    QgsSpatialIndex,
    QgsFeatureRequest,
    QgsCoordinateTransform,
    QgsProject,
    QgsGeometry,
    QgsFeature,
    QgsVectorLayer,
    QgsWkbTypes,
    Qgis,
    QgsMessageLog,
    QgsField,
    QgsGraduatedSymbolRenderer, 
    QgsRendererRange, 
    QgsSymbol,
    QgsFillSymbol,
    QgsLinePatternFillSymbolLayer,
    QgsLineSymbol,
    QgsSimpleLineSymbolLayer,
    QgsUnitTypes,
    QgsRenderContext,
    QgsCurve,
    QgsFields
)
from qgis.gui import QgsMapToolEmitPoint
from PyQt5.QtGui import QColor

FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'dss_hpp_load_dockwidget_base.ui'))

MESSAGE_CATEGORY = 'Messages'

def enable_remote_debugging():
    try:
        import ptvsd
        QgsMessageLog.logMessage("ptvsd imported successfully!", MESSAGE_CATEGORY, Qgis.Info)
        if ptvsd.is_attached():
            QgsMessageLog.logMessage("Remote Debug for Visual Studio is already active", MESSAGE_CATEGORY, Qgis.Info)
            return
        ptvsd.enable_attach(address=('localhost', 5678))
        QgsMessageLog.logMessage("Attached remote Debug for Visual Studio", MESSAGE_CATEGORY, Qgis.Info)
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        format_exception = traceback.format_exception(exc_type, exc_value, exc_traceback)
        QgsMessageLog.logMessage(str(e), MESSAGE_CATEGORY, Qgis.Critical)        
        QgsMessageLog.logMessage(repr(format_exception[0]), MESSAGE_CATEGORY, Qgis.Critical)
        QgsMessageLog.logMessage(repr(format_exception[1]), MESSAGE_CATEGORY, Qgis.Critical)
        QgsMessageLog.logMessage(repr(format_exception[2]), MESSAGE_CATEGORY, Qgis.Critical)


class HPPLoadDockWidget(QtWidgets.QDockWidget, FORM_CLASS):
    closingPlugin = pyqtSignal()

    def __init__(self, iface, parent=None):
        """Constructor."""
        enable_remote_debugging()
        super().__init__(parent)
        self.setupUi(self)
        self.iface = iface
        self.btnCalculate.clicked.connect(self.calculate_hpp_load)

    def closeEvent(self, event):
        self.closingPlugin.emit()
        event.accept()
        
    def select_catchment_features_by_id(self, layer, id_field, value_given):
        selected_features = []
        value_given_str = str(value_given)
        try:
            value_given_num = int(value_given_str)
        except:
            return selected_features

        for feature in layer.getFeatures():
            id_value = feature[id_field]
            if id_value is None:
                continue
            id_value_str = str(id_value)
            try:
                id_value_num = int(id_value_str)
            except:
                continue

            if len(id_value_str) == len(value_given_str):
                if id_value_str[:-2] == value_given_str[:-2] and id_value_num >= value_given_num:
                    selected_features.append(feature)
            else:
                id_value_subset = id_value_str[:len(value_given_str)]
                if id_value_subset[:-2] == value_given_str[:-2] and int(id_value_subset) >= value_given_num:
                    selected_features.append(feature)
        return selected_features

    def calculate_hpp_load(self):
        """
        Calculates HPP load on rivers by matching abstraction and discharge points
        based on a common code field, then finding the nearest river segments.
        If the nearest river feature for abstraction == discharge, we extract
        the sub‐segment between those two nearest points and display it in red.
        """

        # 1. Validate layers
        rivers_layer = self.cmbRivers.currentLayer()
        if not self._validate_layer(rivers_layer, "rivers"):
            return

        hpp_abstraction_layer = self.cmbWaterAbstraction.currentLayer()
        if not self._validate_layer(hpp_abstraction_layer, "HPP water abstraction"):
            return

        hpp_discharge_layer = self.cmbWaterDischarge.currentLayer()
        if not self._validate_layer(hpp_discharge_layer, "HPP water discharge"):
            return
        
        catchments_layer = self.cmbCatchments.currentLayer()
        if not self._validate_layer(hpp_discharge_layer, "ERICA Catchments"):
            return

        # 2. Hardcode or get from UI
        water_abstraction_code_field_name = 'N_Jrar'
        water_discharge_code_field_name = 'N_Jrher'

        # 3. Check fields
        abstraction_fields = [field.name() for field in hpp_abstraction_layer.fields()]
        discharge_fields = [field.name() for field in hpp_discharge_layer.fields()]

        if water_abstraction_code_field_name not in abstraction_fields:
            QMessageBox.warning(
                self,
                "Error",
                f"Field '{water_abstraction_code_field_name}' not found in HPP Abstraction layer."
            )
            return

        if water_discharge_code_field_name not in discharge_fields:
            QMessageBox.warning(
                self,
                "Error",
                f"Field '{water_discharge_code_field_name}' not found in HPP Discharge layer."
            )
            return
        

        # Helper to normalize code
        def normalize_code(code_value):
            code_str = str(code_value).strip()
            try:
                return int(code_str)
            except ValueError:
                return code_str

        # 4. Build discharge code dict (handling multiple codes in one field)
        discharge_code_dict = {}
        for feat in hpp_discharge_layer.getFeatures():
            # This might be "123" or "124,176" or "12 , 13 , 14", etc.
            raw_code_val = feat[water_discharge_code_field_name]
            # Split by comma
            split_codes = str(raw_code_val).split(",")  # e.g. ["124", "176"]
            for single_code_str in split_codes:
                # Trim whitespace
                single_code_str = single_code_str.strip()
                # Normalize (convert numeric if possible)
                code_val_norm = normalize_code(single_code_str)
                # Store the feature in the dict under this code
                discharge_code_dict.setdefault(code_val_norm, []).append(feat)

        # >>> ADDED FOR SUB-SEGMENT EXTRACTION AND MEMORY LAYER <<<

        # Create an in‐memory layer for all extracted sub‐segments (only once).
        # Use the CRS of the rivers layer for consistency:
        crs = rivers_layer.crs().authid()
        self.hpp_segments_layer = QgsVectorLayer(
            f"LineString?crs={crs}",
            "HPP Load Segments",
            "memory"
        )
        dp = self.hpp_segments_layer.dataProvider()

        # Add fields as needed (not strictly required, but can be helpful)
        dp.addAttributes([
            QgsField("AbstrCode", QVariant.String),
        ])
        self.hpp_segments_layer.updateFields()

        # Add to project
        QgsProject.instance().addMapLayer(self.hpp_segments_layer)

        # Style it RED
        context = QgsRenderContext()
        symbol = self.hpp_segments_layer.renderer().symbols(context)[0]
        symbol.setColor(QColor("red"))
        symbol.setWidth(0.8)
        self.hpp_segments_layer.triggerRepaint()

        # Shortcut to the layer’s dataProvider
        dp_segments = self.hpp_segments_layer.dataProvider()

        # Before we add new features, optionally clear out old ones from the previous run:
        dp_segments.deleteFeatures([f.id() for f in self.hpp_segments_layer.getFeatures()])

        # >>> END OF MEMORY LAYER SETUP <<<

        # 5. Loop through each abstraction feature
        for abs_feat in hpp_abstraction_layer.getFeatures():
            abstraction_code_val = abs_feat[water_abstraction_code_field_name]
            abstraction_code_val_norm = normalize_code(abstraction_code_val)

            if abstraction_code_val_norm not in discharge_code_dict:
                QgsMessageLog.logMessage(
                    f"Found no discharge points for abstraction code {abstraction_code_val}.",
                    MESSAGE_CATEGORY,
                    Qgis.Warning
                )
                continue

            matching_discharge_feats = discharge_code_dict[abstraction_code_val_norm]

            if len(matching_discharge_feats) == 1:
                # 1 discharge => proceed
                abs_geom = abs_feat.geometry()
                if not abs_geom or abs_geom.isEmpty():
                    QgsMessageLog.logMessage(
                        f"No abstraction point found for code {abstraction_code_val}.",
                        MESSAGE_CATEGORY,
                        Qgis.Warning
                    )
                    continue

                discharge_feat = matching_discharge_feats[0]
                discharge_geom = discharge_feat.geometry()
                if not discharge_geom or discharge_geom.isEmpty():
                    QgsMessageLog.logMessage(
                        f"No discharge point found for code {abstraction_code_val}.",
                        MESSAGE_CATEGORY,
                        Qgis.Warning
                    )
                    continue

                abs_point = abs_geom.asPoint()
                abs_point = self._transform_point(rivers_layer, hpp_abstraction_layer, abs_point)
                discharge_point = discharge_geom.asPoint()
                discharge_point = self._transform_point(rivers_layer, hpp_discharge_layer, discharge_point)

                nearest_river_abs = self._get_nearest_feature_precise(rivers_layer, abs_point)
                nearest_river_dis = self._get_nearest_feature_precise(rivers_layer, discharge_point)

                if nearest_river_abs and nearest_river_dis:
                    if nearest_river_abs.id() == nearest_river_dis.id():
                        QgsMessageLog.logMessage(
                            f"Abstraction code {abstraction_code_val} uses the same river feature for both points.",
                            MESSAGE_CATEGORY,
                            Qgis.Info
                        )
                        # >>> SUB-SEGMENT EXTRACTION <<<
                        river_geom = nearest_river_abs.geometry()

                        # 3) Get sub‐geometry
                        # Convert the river geometry into a list of line-parts (each part is a list of QgsPointXY).
                        # For a MultiLineString geometry, asMultiPolyline() returns a list-of-lists of points.
                        # For a single LineString, asMultiPolyline() simply returns a 1-element list.
                        multi_parts = river_geom.asMultiPolyline()

                        # We'll store whichever part matches (if any).
                        sub_geom = None

                        # 1) Find a line part that contains both points.
                        for part in multi_parts:
                            part_geom = QgsGeometry.fromPolylineXY(part)  # single linestring geometry

                            # Distances along this linestring for each point
                            start_dist = part_geom.lineLocatePoint(QgsGeometry.fromPointXY(abs_point))
                            end_dist = part_geom.lineLocatePoint(QgsGeometry.fromPointXY(discharge_point))

                            if start_dist == end_dist: # in case part of the multipolygon is far away from both points
                                continue

                            # lineLocatePoint(...) returns -1 if the point is off this line part,
                            # so we only proceed if both distances are >= 0.
                            if start_dist >= 0 and end_dist >= 0:
                                # Ensure start_dist < end_dist
                                if start_dist > end_dist:
                                    start_dist, end_dist = end_dist, start_dist

                                # 1) Get the underlying geometry (QgsLineString, etc.)
                                abstract_geom = part_geom.constGet()  # returns a QgsAbstractGeometryConstPtr

                                # 2) Check if it's a curve (QgsCurve or QgsLineString). For a simple linestring,
                                #    this should be a QgsLineString, which is a subclass of QgsCurve.
                                if isinstance(abstract_geom, QgsCurve):
                                    # 3) Call curveSubstring on the curve. This returns another QgsCurve.
                                    sub_curve = abstract_geom.curveSubstring(start_dist, end_dist)
                                    if sub_curve:
                                        # 4) Wrap in a new QgsGeometry.
                                        sub_geom = QgsGeometry(sub_curve.clone())
                                        # If sub_geom is valid and not empty, we found our sub-segment.
                                        if not sub_geom.isEmpty():
                                            # Found the part that has both points; break out if we only want one match
                                            break
                                else:
                                    QgsMessageLog.logMessage(
                                        "Part geometry is not a curve/linestring. Cannot do curveSubstring.",
                                        MESSAGE_CATEGORY, Qgis.Warning
                                    )
                                    # continue to next part
                            # else continue to next part

                        # after the loop, we check if sub_geom was found:
                        if sub_geom and not sub_geom.isEmpty():
                            new_feat = QgsFeature(self.hpp_segments_layer.fields())
                            new_feat.setGeometry(sub_geom)
                            new_feat.setAttribute(
                                new_feat.fieldNameIndex("AbstrCode"),
                                str(abstraction_code_val)
                            )
                            dp_segments.addFeatures([new_feat])

                    else:
                        QgsMessageLog.logMessage(
                            f"Abstraction code {abstraction_code_val} has different river features: "
                            f"{nearest_river_abs.id()} vs {nearest_river_dis.id()}",
                            MESSAGE_CATEGORY,
                            Qgis.Info
                        )
                        
                        abs_river_geom = nearest_river_abs.geometry()
                        dis_river_geom = nearest_river_dis.geometry()

                        # 1) Find intersection (the confluence or shared segment)
                        intersection_geom = abs_river_geom.intersection(dis_river_geom)

                        if intersection_geom.isEmpty():
                            QgsMessageLog.logMessage(
                                f"No intersection found between river {nearest_river_abs.id()} and "
                                f"river {nearest_river_dis.id()}. Cannot extract sub-segment.",
                                MESSAGE_CATEGORY,
                                Qgis.Warning
                            )
                            # You might choose to continue, skip, or do some fallback
                            continue

                        # If it’s a line or multi-line, that implies they share a segment. 
                        # For a typical confluence, we expect a Point or MultiPoint.
                        if intersection_geom.wkbType() in (QgsWkbTypes.Point, QgsWkbTypes.MultiPoint):
                            # If multi, pick the first point
                            if intersection_geom.isMultipart():
                                points = intersection_geom.asMultiPoint()
                                if not points:
                                    QgsMessageLog.logMessage(
                                        "Intersection is multipoint but empty. Skipping.",
                                        MESSAGE_CATEGORY, Qgis.Warning
                                    )
                                    continue
                                confluence_point = points[0]  # first intersection
                            else:
                                # single point
                                confluence_point = intersection_geom.asPoint()

                            # 2) Now we want the sub-segment of abstraction river from the abstraction point to confluence_point
                            #    We'll locate the chainage along abstraction river for each point
                            abs_point_geom = QgsGeometry.fromPointXY(abs_point)
                            dis_point_geom = QgsGeometry.fromPointXY(discharge_point)
                            conf_point_geom = QgsGeometry.fromPointXY(confluence_point)

                            # start_dist = abs_river_geom.lineLocatePoint(abs_point_geom)
                            # end_dist = abs_river_geom.lineLocatePoint(conf_point_geom)

                            # if start_dist < 0 or end_dist < 0:
                            #     QgsMessageLog.logMessage(
                            #         f"lineLocatePoint returned -1. Possibly points are off the line. Skipping.",
                            #         MESSAGE_CATEGORY,
                            #         Qgis.Warning
                            #     )
                            #     continue

                            # # Ensure start_dist <= end_dist
                            # if start_dist > end_dist:
                            #     start_dist, end_dist = end_dist, start_dist

                            # 3) Extract the sub‐segment from river X
                            # If you are using curveSubstring:
                            multi_parts = abs_river_geom.asMultiPolyline()  # For multi-line geometry
                            sub_geom = None

                            for part in multi_parts:
                                part_geom = QgsGeometry.fromPolylineXY(part)
                                # check distances for each part
                                sdist = part_geom.lineLocatePoint(abs_point_geom)
                                edist = part_geom.lineLocatePoint(conf_point_geom)
                                if sdist==edist:
                                    continue
                                if sdist >= 0 and edist >= 0:
                                    if sdist > edist:
                                        sdist, edist = edist, sdist
                                    abstract_curve = part_geom.constGet()
                                    if isinstance(abstract_curve, QgsCurve):
                                        sub_curve = abstract_curve.curveSubstring(sdist, edist)
                                        if sub_curve:
                                            candidate_sub_geom = QgsGeometry(sub_curve.clone())
                                            if not candidate_sub_geom.isEmpty():
                                                sub_geom = candidate_sub_geom
                                                break

                            if sub_geom and not sub_geom.isEmpty():
                                # 4) Add to memory layer
                                new_feat = QgsFeature(self.hpp_segments_layer.fields())
                                new_feat.setGeometry(sub_geom)
                                new_feat.setAttribute(
                                    new_feat.fieldNameIndex("AbstrCode"),
                                    str(abstraction_code_val)
                                )
                                dp_segments.addFeatures([new_feat])

                                # 5a) Find which catchment(s) contain the abstraction point
                                abstraction_catchments = self._get_intersecting_features(catchments_layer, abs_point_geom)
                                # 5b) Find which catchment(s) contain the discharge point
                                discharge_catchments = self._get_intersecting_features(catchments_layer, dis_point_geom)

                                if not abstraction_catchments:
                                    QgsMessageLog.logMessage(
                                        f"No catchment found for abstraction point of code {abstraction_code_val}.",
                                        MESSAGE_CATEGORY,
                                        Qgis.Warning
                                    )
                                if not discharge_catchments:
                                    QgsMessageLog.logMessage(
                                        f"No catchment found for discharge point of code {abstraction_code_val}.",
                                        MESSAGE_CATEGORY,
                                        Qgis.Warning
                                    )

                                if not abstraction_catchments or not discharge_catchments:
                                    # Can't do flow check
                                    pass
                                else:
                                    # For simplicity, let's assume we just take the *first* intersecting
                                    # polygon for each. If you can have multiple, adapt accordingly.
                                    abs_catchment_feat = abstraction_catchments[0]
                                    dis_catchment_feat = discharge_catchments[0]

                                    # 6) Check if the abstraction's catchment flows into the discharge's catchment
                                    #    This is your custom function. We'll call it flows_into for example.
                                    #    E.g.:
                                    # if self.flows_into(abs_catchment_feat, dis_catchment_feat):
                                    #     ...
                                    # We'll just *assume* it's True for demonstration:
                                    catchment_id_field = "RCode"
                                    selected_catchments = self.select_catchment_features_by_id(catchments_layer, catchment_id_field, dis_catchment_feat[catchment_id_field])
                                    if abs_catchment_feat in selected_catchments:
                                        # 7) If yes, we add the sub-segment on River Y from confluence to discharge

                                        # a) lineLocatePoint on River Y
                                        confluence_geom_pt = QgsGeometry.fromPointXY(confluence_point)
                                        start_dist_y = dis_river_geom.lineLocatePoint(confluence_geom_pt)
                                        end_dist_y = dis_river_geom.lineLocatePoint(dis_point_geom)

                                        if start_dist_y < 0 or end_dist_y < 0:
                                            QgsMessageLog.logMessage(
                                                f"lineLocatePoint returned -1 on River Y (ID={nearest_river_dis.id()}).",
                                                MESSAGE_CATEGORY,
                                                Qgis.Warning
                                            )
                                        else:
                                            # ensure start <= end
                                            if start_dist_y > end_dist_y:
                                                start_dist_y, end_dist_y = end_dist_y, start_dist_y

                                            # b) Extract sub-geometry from River Y
                                            multi_parts_y = dis_river_geom.asMultiPolyline()
                                            sub_geom_y = None

                                            for part in multi_parts_y:
                                                part_geom_y = QgsGeometry.fromPolylineXY(part)
                                                sdist_y = part_geom_y.lineLocatePoint(confluence_geom_pt)
                                                edist_y = part_geom_y.lineLocatePoint(dis_point_geom)
                                                if sdist_y==edist_y:
                                                    continue
                                                if sdist_y >= 0 and edist_y >= 0:
                                                    if sdist_y > edist_y:
                                                        sdist_y, edist_y = edist_y, sdist_y
                                                    abstract_curve_y = part_geom_y.constGet()
                                                    if isinstance(abstract_curve_y, QgsCurve):
                                                        sub_curve_y = abstract_curve_y.curveSubstring(sdist_y, edist_y)
                                                        if sub_curve_y:
                                                            candidate_sub_geom_y = QgsGeometry(sub_curve_y.clone())
                                                            if not candidate_sub_geom_y.isEmpty():
                                                                sub_geom_y = candidate_sub_geom_y
                                                                break

                                            if sub_geom_y and not sub_geom_y.isEmpty():
                                                new_feat_2 = QgsFeature(self.hpp_segments_layer.fields())
                                                new_feat_2.setGeometry(sub_geom_y)
                                                new_feat_2.setAttribute(
                                                    new_feat_2.fieldNameIndex("AbstrCode"),
                                                    str(abstraction_code_val)
                                                )
                                                dp_segments.addFeatures([new_feat_2])
                                            else:
                                                QgsMessageLog.logMessage(
                                                    f"Could not extract sub-segment on River Y (ID={nearest_river_dis.id()})",
                                                    MESSAGE_CATEGORY,
                                                    Qgis.Warning
                                                )
                                    else:
                                        QgsMessageLog.logMessage(
                                            f"Catchment of code {abstraction_code_val} does NOT flow into discharge catchment. Skipping segment.",
                                            MESSAGE_CATEGORY,
                                            Qgis.Info
                                        )
                            else:
                                QgsMessageLog.logMessage(
                                    "Could not extract sub-segment from River X to confluence. Possibly off-geometry or multi-part intersection.",
                                    MESSAGE_CATEGORY,
                                    Qgis.Warning
                                )
                        else:
                            # Intersection is a line or polygon? Possibly they share a segment or something unexpected.
                            QgsMessageLog.logMessage(
                                "River X and Y share a line or polygon intersection (not a simple point). Handling not implemented.",
                                MESSAGE_CATEGORY,
                                Qgis.Warning
                            )
                else:
                    QgsMessageLog.logMessage(
                        f"Abstraction code {abstraction_code_val}: could not find nearest river for abstraction or discharge.",
                        MESSAGE_CATEGORY,
                        Qgis.Warning
                    )

            else:
                # More than 1 discharge or none
                QgsMessageLog.logMessage(
                    f"Found {len(matching_discharge_feats)} discharge points for abstraction code {abstraction_code_val}. Skipping.",
                    MESSAGE_CATEGORY,
                    Qgis.Warning
                )
                pass

        # Once done with all features, refresh the memory layer
        self.hpp_segments_layer.updateExtents()
        self.hpp_segments_layer.triggerRepaint()
        
        self.calculate_coverage()

        QMessageBox.information(self, "Calculation done", "Calculation completed successfully.")



    def _validate_layer(self, layer, layer_name):
        if not layer:
            QMessageBox.warning(self, "Error", f"Please select a {layer_name} layer.")
            return False
        if not layer.isSpatial():
            QMessageBox.warning(self, "Error", f"Selected {layer_name} layer is not spatial.")
            return False
        return True

    def _transform_point(self, target_layer, source_layer, point):
        if not target_layer or not source_layer:
            QgsMessageLog.logMessage(
                "Either target_layer or source_layer is not valid.",
                MESSAGE_CATEGORY,
                Qgis.Warning
            )
            return None

        target_crs = target_layer.crs()
        source_crs = source_layer.crs()

        if not target_crs.isValid() or not source_crs.isValid():
            QgsMessageLog.logMessage(
                "Invalid CRS on either target or source layer.",
                MESSAGE_CATEGORY,
                Qgis.Warning
            )
            return None

        # If layer CRSs differ, reproject the point
        if target_crs != source_crs:
            try:
                xform = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())
                point = xform.transform(point)
                return point
            except Exception as e:
                QgsMessageLog.logMessage(
                    f"Error reprojecting point from {source_crs.authid()} to {target_crs.authid()}: {e}",
                    MESSAGE_CATEGORY,
                    Qgis.Critical
                )
                return None
        else:
            # If CRSs are the same, just return the original point
            return point


    def _get_nearest_feature(self, target_layer, point):
        """
        Finds the nearest feature in `target_layer` to the given `point`,
        automatically reprojecting the point from `source_layer`'s CRS
        to `target_layer`'s CRS if needed.

        :param target_layer: QgsVectorLayer where we do the nearest-neighbor search.
        :param source_layer: QgsVectorLayer from which `point` originated.
        :param point:        QgsPointXY in the CRS of `source_layer`.
        :return: The nearest QgsFeature in `target_layer`, or None if none found.
        """

        # Build the spatial index in the target layer's CRS
        index = QgsSpatialIndex(target_layer.getFeatures())
        nearest_ids = index.nearestNeighbor(point, 5)
        QgsMessageLog.logMessage(
            f"Nearest 5 features for point {point}: {nearest_ids}",
            MESSAGE_CATEGORY, Qgis.Info
        )
        if not nearest_ids:
            return None

        feature_request = QgsFeatureRequest(nearest_ids[0])
        nearest_feat = next(target_layer.getFeatures(feature_request), None)
        return nearest_feat

    def _get_nearest_feature_precise(self, layer, point, k=5):
        """
        Finds the truly nearest feature in `layer` to the given `point`
        by first retrieving up to `k` bounding-box neighbors, then doing
        a real geometry distance check.

        :param layer: QgsVectorLayer to search in.
        :param point: QgsPointXY for the query.
        :param k:     Number of bounding-box neighbors to retrieve.
        :return:      The nearest QgsFeature by geometry distance, or None if none found.
        """
        # Build the spatial index if not done. For repeated calls, you might want to build it once.
        index = QgsSpatialIndex(layer.getFeatures())

        # 1) Find the K nearest bounding boxes
        candidate_ids = index.nearestNeighbor(point, k)
        if not candidate_ids:
            return None

        point_geom = QgsGeometry.fromPointXY(point)

        best_feat = None
        best_dist = float('inf')

        # 2) Among those K candidates, find the actual closest geometry
        for fid in candidate_ids:
            request = QgsFeatureRequest(fid)
            candidate_feat = next(layer.getFeatures(request), None)
            if not candidate_feat:
                continue

            dist = candidate_feat.geometry().distance(point_geom)
            if dist < best_dist:
                best_dist = dist
                best_feat = candidate_feat

        return best_feat

    def _unify_geometries(self, features):
        geometries = [feature.geometry() for feature in features]
        union_geom = QgsGeometry.unaryUnion(geometries)
        return union_geom if not union_geom.isEmpty() else None

    def _transform_geometry(self, geometry, source_crs, target_crs):
        if source_crs != target_crs:
            transformer = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())
            transformed_geom = QgsGeometry(geometry)
            transformed_geom.transform(transformer)
            return transformed_geom
        return geometry

    def _transform_features(self, features, source_crs, target_crs):
        """Transforms the geometries of features from source CRS to target CRS."""
        transformed_features = []
        for feature in features:
            geom = QgsGeometry(feature.geometry())
            if source_crs != target_crs:
                transformer = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())
                geom.transform(transformer)
            feature_copy = QgsFeature(feature)
            feature_copy.setGeometry(geom)
            transformed_features.append(feature_copy)
        return transformed_features

    def _get_intersecting_features(self, layer, geometry):
        index = QgsSpatialIndex(layer.getFeatures())
        candidate_ids = index.intersects(geometry.boundingBox())
        intersecting_features = [
            feature for feature in layer.getFeatures(QgsFeatureRequest(candidate_ids))
            if feature.geometry().intersects(geometry)
        ]
        return intersecting_features
    
    def calculate_coverage(self):
        """
        Create a new memory layer that has all columns from the rivers layer
        plus a coverage percentage of how much is covered by the memory-layer segments.
        """

        # 1) Validate rivers layer
        rivers_layer = self.cmbRivers.currentLayer()
        if not rivers_layer or not rivers_layer.isValid():
            QMessageBox.warning(self, "Error", "Rivers layer is invalid.")
            return
        
        # 2) Validate your memory layer with sub-segments
        if not hasattr(self, 'hpp_segments_layer') or not self.hpp_segments_layer:
            QMessageBox.warning(self, "Error", "HPP Load Segments layer does not exist.")
            return
        if not self.hpp_segments_layer.isValid():
            QMessageBox.warning(self, "Error", "HPP Load Segments layer is not valid.")
            return

        # 3) Build a unified geometry from the memory-layer features (optional, but simpler)
        mem_feats = list(self.hpp_segments_layer.getFeatures())
        if not mem_feats:
            QMessageBox.information(self, "No segments", "Memory layer has no features. Coverage = 0.")
            return

        mem_geometries = [f.geometry() for f in mem_feats if f.geometry() and not f.geometry().isEmpty()]
        if not mem_geometries:
            QMessageBox.information(self, "No valid geometry", "No valid geometry in memory layer features.")
            return

        unified_segments_geom = QgsGeometry.unaryUnion(mem_geometries)
        if unified_segments_geom.isEmpty():
            QMessageBox.information(self, "No coverage", "Unified memory geometry is empty.")
            return

        # 4) Create a new memory layer that clones the rivers layer's fields
        #    plus one new field for coverage percentage.
        river_fields = rivers_layer.fields()
        new_fields = QgsFields(river_fields)
        new_coverage_field_name = "CoveragePct"
        new_fields.append(QgsField(new_coverage_field_name, QVariant.Double))

        # We'll assume your rivers are linestring or multi-linestring
        # We can get the WKB type from the rivers_layer, or do simply "LineString?crs=..."
        # to keep it consistent with the layer's CRS
        crs = rivers_layer.crs().authid()
        coverage_layer = QgsVectorLayer(
            f"{QgsWkbTypes.displayString(rivers_layer.wkbType())}?crs={crs}",
            "RiversCoverage",
            "memory"
        )
        dp_cov = coverage_layer.dataProvider()
        dp_cov.addAttributes(new_fields)
        coverage_layer.updateFields()

        # 5) For each river feature, compute coverage
        for river_feat in rivers_layer.getFeatures():
            river_geom = river_feat.geometry()
            if not river_geom or river_geom.isEmpty():
                continue

            river_length = river_geom.length()
            if river_length <= 0:
                # No meaningful length
                continue

            # Intersection with the unified memory geometry
            intersection_geom = river_geom.intersection(unified_segments_geom)
            covered_length = intersection_geom.length() if intersection_geom else 0.0

            coverage_ratio = covered_length / river_length  # fraction 0..1
            coverage_percent = coverage_ratio * 100.0       # percentage

            # 6) Create new feature for the coverage layer
            new_feat = QgsFeature(coverage_layer.fields())
            # copy geometry from the original river
            new_feat.setGeometry(river_geom)

            # copy attributes from the original river
            attr_map = {}
            for i, field in enumerate(river_fields):
                attr_map[i] = river_feat[i]
            # set coverage in the new field (the last one we appended)
            coverage_field_index = coverage_layer.fields().indexOf(new_coverage_field_name)
            attr_map[coverage_field_index] = coverage_percent

            new_feat.setAttributes(list(attr_map.values()))
            dp_cov.addFeature(new_feat)

        coverage_layer.updateExtents()

        # 7) Add the coverage layer to the project
        QgsProject.instance().addMapLayer(coverage_layer)

        # 8) Optionally style it (e.g., color by coverage %)
        # For instance, a simple graduated style from 0 to 100
        self._apply_coverage_style(coverage_layer, new_coverage_field_name)

        # QMessageBox.information(self, "Coverage done", "Created coverage layer with coverage percentage.")

    def _apply_coverage_style(self, layer, field_name):
        """
        Apply a simple two-category style on 'field_name':
        - < 40%  -> blue
        - >= 40% -> red
        """
        # Create symbols for each category
        blue_symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        blue_symbol.setColor(QColor("blue"))
        blue_symbol.setWidth(0.8)

        red_symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        red_symbol.setColor(QColor("red"))
        red_symbol.setWidth(0.8)

        # Define two ranges:
        #  1) 0 to <40
        #  2) 40 to a large max number
        ranges = []
        ranges.append(QgsRendererRange(0, 40, blue_symbol, "< 40%"))
        ranges.append(QgsRendererRange(40, 999999, red_symbol, "≥ 40%"))

        # Create a graduated symbol renderer
        renderer = QgsGraduatedSymbolRenderer(field_name, ranges)
        # Keep it in 'GraduatedColor' mode so it appears nicely in the legend
        renderer.setMode(QgsGraduatedSymbolRenderer.GraduatedColor)

        layer.setRenderer(renderer)
        layer.triggerRepaint()
