# -*- coding: utf-8 -*-
from qgis.PyQt.QtWidgets import QAction, QMenu, QMessageBox
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsApplication
from qgis.utils import iface
from .dss_watershed_load_dockwidget import WatershedLoadDockWidget
from .dss_hpp_load_dockwidget import HPPLoadDockWidget
import os

class DSSMenuPlugin:
    def __init__(self, iface):
        """
        Constructor: QGIS calls this first when initializing the plugin.
        'iface' is the QgisInterface instance, which allows the plugin
        to access QGIS functionality.
        """
        self.iface = iface
        self.menu = None   # Will hold the reference to our custom menu
        self.actions = []  # Keep track of our custom actions so we can remove them later
        self.watershed_load_widget = None
        self.hpp_load_widget = None

    def open_watershed_load_widget(self):
        if not self.watershed_load_widget:
            # Pass the QGIS interface as the first argument and the QMainWindow as the parent
            self.watershed_load_widget = WatershedLoadDockWidget(self.iface, parent=self.iface.mainWindow())
            self.iface.addDockWidget(Qt.LeftDockWidgetArea, self.watershed_load_widget)
        else:
            self.watershed_load_widget.show()
            
    def open_hpp_load_widget(self):
        if not self.hpp_load_widget:
            self.hpp_load_widget = HPPLoadDockWidget(self.iface, parent=self.iface.mainWindow())
            # Add to QGIS
            self.iface.addDockWidget(Qt.LeftDockWidgetArea, self.hpp_load_widget)
        else:
            # If it's already created, just show it
            self.hpp_load_widget.show()
    
    def empty_action(self):
        pass

    def show_about(self):
        """
        Opens a message box with "About DSS" information.
        """

        info_text = (
            "Decision Support System\n"
            "for Integrated Water Resources Management\n\n"
            "Version 0.0.1\n"
            "© 2024-2025"
        )

        QMessageBox.information(
            self.iface.mainWindow(),
            "About DSS",
            info_text
        )

    def initGui(self):
        """
        Called by QGIS to initialize the GUI. We create the top-level menu here,
        and add submenus/actions.
        """
        self.menu = QMenu("DSS", self.iface.mainWindow().menuBar())
        self.menu.setObjectName("DSSMenuPluginMenu")
        self.iface.mainWindow().menuBar().insertMenu(self.iface.firstRightStandardMenu().menuAction(), self.menu)

        add_import_menu = QMenu("Add/Import Data", self.iface.mainWindow())
        self.menu.addMenu(add_import_menu)
        
        self.menu.addSeparator()
        
        #================= Hydrological Model =================
        hydrological_model_menu = QMenu("Hydrological Model", self.iface.mainWindow())
        self.menu.addMenu(hydrological_model_menu)

        # ----Water Balance----
        water_balance_menu = QMenu("Water Balance", self.iface.mainWindow())
        hydrological_model_menu.addMenu(water_balance_menu)
        
        precipitation_action = QAction("Precipitation", self.iface.mainWindow())
        precipitation_action.triggered.connect(self.empty_action)
        water_balance_menu.addAction(precipitation_action)
        
        evaporation_action = QAction("Evaporation", self.iface.mainWindow())
        evaporation_action.triggered.connect(self.empty_action)
        water_balance_menu.addAction(evaporation_action)
        
        natural_flow_action = QAction("Natural Flow", self.iface.mainWindow())
        natural_flow_action.triggered.connect(self.empty_action)
        water_balance_menu.addAction(natural_flow_action)
        
        surface_natural_flow_action = QAction("Surface Natural Flow", self.iface.mainWindow())
        surface_natural_flow_action.triggered.connect(self.empty_action)
        water_balance_menu.addAction(surface_natural_flow_action)
        
        precipitation_runoff_action = QAction("Precipitation/Runoff", self.iface.mainWindow())
        precipitation_runoff_action.triggered.connect(self.empty_action)
        water_balance_menu.addAction(precipitation_runoff_action)
        
        deep_flow_action = QAction("Deep Flow", self.iface.mainWindow())
        deep_flow_action.triggered.connect(self.empty_action)
        water_balance_menu.addAction(deep_flow_action)
        
        water_balance_menu.addSeparator()
        
        water_balance_action = QAction("Water Balance", self.iface.mainWindow())
        water_balance_action.triggered.connect(self.empty_action)
        water_balance_menu.addAction(water_balance_action)

        # ----Water Supply and Demand Balance----
        water_supply_and_demand_balance_menu = QMenu("Water Supply and Demand Balance", self.iface.mainWindow())
        hydrological_model_menu.addMenu(water_supply_and_demand_balance_menu)
        
        ecological_flow_action = QAction("Ecological Flow", self.iface.mainWindow())
        ecological_flow_action.triggered.connect(self.empty_action)
        water_supply_and_demand_balance_menu.addAction(ecological_flow_action)
        
        water_supply_and_demand_balance_menu.addSeparator()
        
        water_supply_and_demand_balance_action = QAction("Water Supply and Demand Balance", self.iface.mainWindow())
        water_supply_and_demand_balance_action.triggered.connect(self.empty_action)
        water_supply_and_demand_balance_menu.addAction(water_supply_and_demand_balance_action)
        
        # ----Hydroenergy Potential----
        hydroenergy_potential_action = QAction("Hydroenergy Potential", self.iface.mainWindow())
        hydroenergy_potential_action.triggered.connect(self.empty_action)
        hydrological_model_menu.addAction(hydroenergy_potential_action)
        
        # ----Water Quality Assessment----
        water_quality_assessment_menu = QMenu("Water Quality Assessment", self.iface.mainWindow())
        hydrological_model_menu.addMenu(water_quality_assessment_menu)
        
        water_quality_surface_water_menu = QMenu("Surface Water", self.iface.mainWindow())
        water_quality_assessment_menu.addMenu(water_quality_surface_water_menu)
        
        wq_surface_water_classification_action = QAction("Classification", self.iface.mainWindow())
        wq_surface_water_classification_action.triggered.connect(self.empty_action)
        water_quality_surface_water_menu.addAction(wq_surface_water_classification_action)
        
        wq_surface_water_hydrochemical_content_action = QAction("Hydrochemical Content", self.iface.mainWindow())
        wq_surface_water_hydrochemical_content_action.triggered.connect(self.empty_action)
        water_quality_surface_water_menu.addAction(wq_surface_water_hydrochemical_content_action)
        
        water_quality_groundwater_menu = QMenu("Groundwater", self.iface.mainWindow())
        water_quality_assessment_menu.addMenu(water_quality_groundwater_menu)

        wq_groundwater_quality_action = QAction("Groundwater Quality", self.iface.mainWindow())
        wq_groundwater_quality_action.triggered.connect(self.empty_action)
        water_quality_groundwater_menu.addAction(wq_groundwater_quality_action)
        
        water_resources_load_menu = QMenu("Degree of Load on Water Resources", self.iface.mainWindow())
        hydrological_model_menu.addMenu(water_resources_load_menu)
        
        watershed_load_action = QAction("Watershed", self.iface.mainWindow())
        watershed_load_action.triggered.connect(self.open_watershed_load_widget)
        water_resources_load_menu.addAction(watershed_load_action)
        
        hpp_load_action = QAction("HPP", self.iface.mainWindow())
        hpp_load_action.triggered.connect(self.open_hpp_load_widget)
        water_resources_load_menu.addAction(hpp_load_action)

        #================= Climate Change Model =================
        climate_change_model_menu = QMenu("Climate Change Model", self.iface.mainWindow())
        self.menu.addMenu(climate_change_model_menu)
        
        self.menu.addSeparator()
        
        #================= Language =================
        language_menu = QMenu("Language", self.iface.mainWindow())
        self.menu.addMenu(language_menu)
        
        icon = QIcon(os.path.dirname(__file__) + "/icons/us.png")
        language_english_action = QAction(icon, "English", self.iface.mainWindow())
        language_english_action.triggered.connect(self.empty_action)
        language_menu.addAction(language_english_action)
        
        icon = QIcon(os.path.dirname(__file__) + "/icons/am.png")
        language_armenian_action = QAction(icon, u"Հայերեն", self.iface.mainWindow())
        language_armenian_action.triggered.connect(self.empty_action)
        language_menu.addAction(language_armenian_action)
        
        self.menu.addSeparator()
        
        #================= About =================
        icon = QIcon(os.path.dirname(__file__) + "/icons/about.png")
        about_action = QAction(icon, u"About DSS", self.iface.mainWindow())
        about_action.triggered.connect(self.show_about)
        self.menu.addAction(about_action)

    def unload(self):
        """Called by QGIS (or the reloader) when the plugin is unloaded."""
        if self.menu:
            # Remove your top-level menu
            self.iface.mainWindow().menuBar().removeAction(self.menu.menuAction())
            
            # Optionally delete the menu so it doesn’t linger
            self.menu.deleteLater()
            self.menu = None

        # Also clear out your actions so you don't accidentally re-add them
        self.actions = []

