"""
Test script to check only the GUI. No processing is done.

author: Peter Ercius
"""

from pathlib import Path

import pyqtgraph as pg
from pyqtgraph.graphicsItems.ROI import Handle
import numpy as np

from qtpy.QtWidgets import *
from qtpy.QtCore import QRectF
from qtpy import QtGui


class fourD(QWidget):

    def __init__(self, *args, **kwargs):
        # test
        self.real_space_limit = None
        self.diffraction_pattern_limit = None
        self.sa = None
        self.current_dir = Path.home()
        self.scale = 1
        self.center = (287, 287)
        self.scan_dimensions = (0, 0)
        self.frame_dimensions = (576, 576)
        self.num_frames_per_scan = None
        self.fr_full = None
        self.fr_full_3d = None
        self.fr_rows = None
        self.fr_cols = None
        self.dp = None
        self.rs = None
        self.log_diffraction = True
        self.handle_size = 10

        self.available_colormaps = ['thermal', 'flame', 'yellowy', 'bipolar', 'spectrum', 'cyclic', 'greyclip', 'grey',
                                    'viridis', 'inferno', 'plasma', 'magma']
        self.colormap = 'viridis'

        super(fourD, self).__init__(*args, *kwargs)
        self.setWindowTitle("Stempy: Sparse 4D Data Explorer")
        self.setWindowIcon(QtGui.QIcon('MF_logo_only_small.ico'))

        # Set the update strategy to the JIT version
        self.update_real = self.update_real_stempy
        self.update_diffr = self.update_diffr_stempy

        # Add a graphics/view/image
        # Need to set invertY = True and row-major
        self.graphics = pg.GraphicsLayoutWidget()
        self.view = self.graphics.addViewBox(row=0, col=0, invertY=True)
        self.view2 = self.graphics.addViewBox(row=0, col=1, invertY=True)
        
        self.real_space_image_item = pg.ImageItem(border=pg.mkPen('w'))
        self.real_space_image_item.setImage(np.random.rand(100,100))
        self.view.addItem(self.real_space_image_item)
        self.real_space_image_item.setColorMap('viridis')
        
        self.view.setAspectLocked()

        self.diffraction_pattern_image_item = pg.ImageItem(border=pg.mkPen('w'))
        self.diffraction_pattern_image_item.setImage(np.zeros((100, 100), dtype=np.uint32))
        self.view2.addItem(self.diffraction_pattern_image_item)
        self.view2.setAspectLocked()
        self.diffraction_pattern_image_item.setColorMap('viridis')

        #self.diffraction_pattern_imageview.setOpts(axisOrder="row-major")
        #self.real_space_image_item.setOpts(axisOrder="row-major")

        self.statusBar = QStatusBar()
        self.statusBar.showMessage("Starting up...")

        # Add a File menu
        self.myQMenuBar = QMenuBar(self)
        menu_bar_file = self.myQMenuBar.addMenu('File')
        menu_bar_export = self.myQMenuBar.addMenu('Export')
        menu_bar_display = self.myQMenuBar.addMenu('Display')
        display_colormap = menu_bar_display.addMenu('Set colormap')
        open_action = QAction('Open', self)
        #open_action.triggered.connect(self.open_file)
        menu_bar_file.addAction(open_action)
        export_diff_tif_action = QAction('Export diffraction (TIF)', self)
        #export_diff_tif_action.triggered.connect(self._on_export)
        menu_bar_export.addAction(export_diff_tif_action)
        export_diff_smv_action = QAction('Export diffraction (SMV)', self)
        #export_diff_smv_action.triggered.connect(self._on_export)
        menu_bar_export.addAction(export_diff_smv_action)
        export_real_action = QAction('Export real (TIF)', self)
        #export_real_action.triggered.connect(self._on_export)
        menu_bar_export.addAction(export_real_action)
        toggle_log_action = QAction('Toggle log(diffraction)', self)
        #toggle_log_action.triggered.connect(self._on_log)
        menu_bar_display.addAction(toggle_log_action)

        self.cm_actions = {}
        for cm in self.available_colormaps:
            self.cm_actions[cm] = QAction(cm, self)
            #self.cm_actions[cm].triggered.connect(self._on_use_colormap)
            display_colormap.addAction(self.cm_actions[cm])

        self.setLayout(QVBoxLayout())
        self.layout().addWidget(self.myQMenuBar)
        self.layout().addWidget(self.graphics)
        self.layout().addWidget(self.statusBar)

        # Initialize the user interface objects
        # Image ROI
        self.real_space_roi = pg.RectROI(pos=(0, 0), size=(10, 10),
                                         translateSnap=True, snapSize=1, scaleSnap=True,
                                         removable=False, invertible=False, pen='g')
        self.view.addItem(self.real_space_roi)

        # Diffraction ROI
        self.diffraction_space_roi = pg.RectROI(pos=(0, 0), size=(10, 10),
                                                translateSnap=True, snapSize=1, scaleSnap=True,
                                                removable=False, invertible=False, pen='g')
        for hh in self.diffraction_space_roi.getHandles() + self.real_space_roi.getHandles():
            hh.radius = self.handle_size
            hh.buildPath()
            hh.update()

        self.view2.addItem(self.diffraction_space_roi)

        #self.open_file()

        self.real_space_roi.sigRegionChanged.connect(self.update_diffr)
        self.diffraction_space_roi.sigRegionChanged.connect(self.update_real)
        self.real_space_roi.sigRegionChanged.connect(self._update_position_message)
        self.diffraction_space_roi.sigRegionChanged.connect(self._update_position_message)

    def _update_position_message(self):
        self.statusBar.showMessage(
            f'Real: ({int(self.real_space_roi.pos().y())}, {int(self.real_space_roi.pos().x())}), '
            f'({int(self.real_space_roi.size().y())}, {int(self.real_space_roi.size().x())}); '
            f'Diffraction: ({int(self.diffraction_space_roi.pos().y())}, {int(self.diffraction_space_roi.pos().x())}), '
            f'({int(self.diffraction_space_roi.size().y())}, {int(self.diffraction_space_roi.size().x())})'
        )


    def update_diffr_stempy(self):
        """ Update the diffraction space image by summing in real space
        """
        pass

    def update_real_stempy(self):
        """ Update the real space image by summing in diffraction space
        """
        pass

if __name__ == '__main__':
    """Main function used to start the GUI."""
    
    qapp = QApplication([])
    fourD_view = fourD()
    fourD_view.show()
    qapp.exec_()
