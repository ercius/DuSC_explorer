"""
Interactively display and analyze sparse 4D-STEM data.

author: Peter Ercius
"""

from pathlib import Path
from datetime import datetime

import pyqtgraph as pg
from pyqtgraph.graphicsItems.ROI import Handle
import numpy as np
from tifffile import imsave
from numba import jit, prange
import stempy.io as stio

from qtpy.QtWidgets import *
from qtpy.QtCore import QRectF
from qtpy import QtGui

from pyqtgraph.Qt import QtCore
from PyQt5.QtCore import Qt
from pyqtgraph.graphicsItems.GridItem import GridItem
from qtpy.QtWidgets import QApplication


class DuSC(QWidget):

    def __init__(self, *args, **kwargs):

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
        self.file_path = None  # the pathlib.Path for the file
        self.wavelength = 0.0197
        self.camera_length_mm = 110
        self.physical_pixel_size_mm = 0.01
        self.centerx = 288
        self.centery = 288

        self.unit = 'None'
        
        self.available_colormaps = ['viridis', 'inferno', 'plasma', 'magma','cividis','CET-C5','CET-C5s']
        self.colormap = 'cividis' # default colormap

        super(DuSC, self).__init__(*args, *kwargs)
        self.setWindowTitle("DuSC: Dual Space Crystallography Explorer")
        self.setWindowIcon(QtGui.QIcon('./DuSC_explorer/DuSC_icon_small.ico'))

        # Set the update strategy to the JIT version
        self.update_real = self.update_real_jit
        self.update_diffr = self.update_diffr_jit

        # Add a graphics/view/image
        # Need to set invertY = True and row-major
        self.graphics = pg.GraphicsLayoutWidget()
        self.view = self.graphics.addViewBox(row=0, col=0, invertY=True)
        self.view2 = self.graphics.addViewBox(row=0, col=1, invertY=True)

        self.real_space_image_item = pg.ImageItem(border=pg.mkPen('w'))
        #self.real_space_image_view = pg.ImageView(imageItem=self.real_space_image_item)
        self.view.addItem(self.real_space_image_item)
        self.real_space_image_item.setImage(np.zeros((100, 100), dtype=np.uint32))
        self.view.setAspectLocked()
        #self.real_space_image_view.setPredefinedGradient('viridis')
        self.real_space_image_item.setColorMap(self.colormap)
        
        self.diffraction_pattern_image_item = pg.ImageItem(border=pg.mkPen('w'))
        #self.diffraction_space_image_view = pg.ImageView(imageItem=self.diffraction_pattern_imageview)
        self.view2.addItem(self.diffraction_pattern_image_item)
        self.diffraction_pattern_image_item.setImage(np.zeros((100, 100), dtype=np.uint32))
        self.view2.setAspectLocked()
        #self.diffraction_space_image_view.setPredefinedGradient('viridis')
        self.diffraction_pattern_image_item.setColorMap(self.colormap)
        
        self.diffraction_pattern_image_item.setOpts(axisOrder="row-major")
        self.real_space_image_item.setOpts(axisOrder="row-major")

        self.statusBar = QStatusBar()
        self.statusBar.showMessage("Starting up...")
        
        # Add gridlines to the both real and diffraction space
        self.real_space_grid = GridItem()
        self.diffraction_space_grid = GridItem()
        self.view.addItem(self.real_space_grid)
        self.view2.addItem(self.diffraction_space_grid)

        # Add a File menu
        self.myQMenuBar = QMenuBar(self)
        menu_bar_file = self.myQMenuBar.addMenu('File')
        menu_bar_parameter = self.myQMenuBar.addMenu('Parameters')
        menu_bar_export = self.myQMenuBar.addMenu('Export')
        menu_bar_display = self.myQMenuBar.addMenu('Display')
        display_colormap = menu_bar_display.addMenu('Set colormap')

        open_action = QAction('Open', self)
        open_action.triggered.connect(self.open_file)
        menu_bar_file.addAction(open_action)
        reset_view = QAction('Reset', self)
        reset_view.triggered.connect(self.reset_view)
        menu_bar_file.addAction(reset_view)
        
        # Add 'Parameters' section with 'Input Metadata' pop up
        metadata_action = QAction('Input Metadata', self)
        metadata_action.triggered.connect(self.show_metadata_dialog)
        menu_bar_parameter.addAction(metadata_action)

        export_diff_tif_action = QAction('Export diffraction (TIF)', self)
        export_diff_tif_action.triggered.connect(self._on_export)
        menu_bar_export.addAction(export_diff_tif_action)

        export_diff_smv_action = QAction('Export diffraction (SMV)', self)
        export_diff_smv_action.triggered.connect(self._on_export)
        menu_bar_export.addAction(export_diff_smv_action)

        export_real_action = QAction('Export real (TIF)', self)
        export_real_action.triggered.connect(self._on_export)
        menu_bar_export.addAction(export_real_action)
        
        toggle_log_action = QAction('Toggle log(diffraction)', self)
        toggle_log_action.triggered.connect(self._on_log)
        menu_bar_display.addAction(toggle_log_action)

        # Add a scalebar with checkable push buttons to allow the object to be
        # displayable on the left or right hand side of both images, while also 
        # allowing the user to have an option of non-display. 
        scalebar_display = QLabel('Scalebar:')
        self.scalebar_left_button = QPushButton('Left', self)
        self.scalebar_right_button = QPushButton('Right', self)
        self.scalebar_none_button = QPushButton('None', self)
        self.scalebar_left_button.setCheckable(True)
        self.scalebar_right_button.setCheckable(True)
        self.scalebar_none_button.setCheckable(True)
        self.scalebar_button_group = QButtonGroup(self)
        self.scalebar_button_group.addButton(self.scalebar_left_button)
        self.scalebar_button_group.addButton(self.scalebar_right_button)
        self.scalebar_button_group.addButton(self.scalebar_none_button)
        # Directly linking each button with their respective function in toggle_scalebar
        self.scalebar_left_button.clicked.connect(lambda: self.toggle_scalebar('left'))
        self.scalebar_right_button.clicked.connect(lambda: self.toggle_scalebar('right'))
        self.scalebar_none_button.clicked.connect(lambda: self.toggle_scalebar('none'))
        button_widget = QWidget(self)
        button_layout = QHBoxLayout(button_widget)
        button_layout.addWidget(scalebar_display)
        button_layout.addWidget(self.scalebar_left_button)
        button_layout.addWidget(self.scalebar_right_button)
        button_layout.addWidget(self.scalebar_none_button)
        button_layout.setContentsMargins(36, 0, 0, 0)
        button_action = QWidgetAction(self)
        button_action.setDefaultWidget(button_widget)
        menu_bar_display.addAction(button_action)

        self.cm_actions = {}
        for cm in self.available_colormaps:
            self.cm_actions[cm] = QAction(cm, self)
            self.cm_actions[cm].triggered.connect(self._on_use_colormap)
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
        self.add_scale_bars()
        self.add_concentric_rings()
        self.open_file()

        self.real_space_roi.sigRegionChanged.connect(self.update_diffr)
        self.diffraction_space_roi.sigRegionChanged.connect(self.update_real)
        self.real_space_roi.sigRegionChanged.connect(self._update_position_message)
        self.diffraction_space_roi.sigRegionChanged.connect(self._update_position_message)

    # Parts of this code were copied and adjusted from the SMV popup code. Will need to further adjust, so that the users input has an effect on the rings, etc. 

    def reset_view(self):
        # Reset the real space ROI to its initial position and size
        self.real_space_roi.setPos([ii // 4 + ii //8 for ii in self.scan_dimensions][::-1])
        self.real_space_roi.setSize([ii // 4 for ii in self.scan_dimensions][::-1])
        
        # Reset the diffraction space ROI to its initial position and size
        self.diffraction_space_roi.setPos([ii // 4 + ii // 8 for ii in self.frame_dimensions][::-1])
        self.diffraction_space_roi.setSize([ii // 4 for ii in self.frame_dimensions][::-1])
        
        # Reinitialize the images
        self.update_real()
        self.update_diffr()
        
        # Reset the view range to the initial state
        self.view.setRange(self.real_space_limit)
        self.view2.setRange(self.diffraction_pattern_limit)
        
        # Reset metadata to initial state
        self.wavelength = 0.0197
        self.camera_length_mm = 110
        self.physical_pixel_size_mm = 0.01
        self.centerx = 288
        self.centery = 288
        self.unit = 'None'

        # Reinitialize scale bars
        self.add_scale_bars()
        
        # Hide scale bars
        self.toggle_scalebar('none')
        
        # Uncheck scalebar buttons
        self.scalebar_button_group.setExclusive(False)
        self.scalebar_left_button.setChecked(False)
        self.scalebar_right_button.setChecked(False)
        self.scalebar_none_button.setChecked(True)
        self.scalebar_button_group.setExclusive(True)
        
        # Remove concentric rings and labels
        for ring in getattr(self, 'rings', []):
            self.view2.removeItem(ring)
        for label in getattr(self, 'labels', []):
            self.view2.removeItem(label)
        self.rings = []
        self.labels = []
        
        # Reinitialize concentric rings
        self.add_concentric_rings()
        self.update_scalebar_labels()
                                                
        self.statusBar.showMessage("View reset to full display.")
                                                
    def show_metadata_dialog(self):
        self.popUp = QDialog(self)
        self.popUp.setWindowTitle("Input Metadata")

        # Current attribute values to pre-populate the input fields
        self.setting1 = QLineEdit(str(self.wavelength))
        self.setting2 = QLineEdit(str(self.camera_length_mm))
        self.setting3 = QLineEdit(str(self.physical_pixel_size_mm))
        self.setting4 = QLineEdit(str(self.centerx))
        self.setting5 = QLineEdit(str(self.centery))

        popUpLayout = QFormLayout()
        popUpLayout.addRow('Wavelength (angstroms)', self.setting1)
        popUpLayout.addRow('Camera length (mm)', self.setting2)
        popUpLayout.addRow('Physical pixel size (mm)', self.setting3)
        popUpLayout.addRow('Beam center row (pixels)', self.setting5)
        popUpLayout.addRow('Beam center column (pixels)', self.setting4)

        # I created push buttons allowing the user to choose between various units for their respective rings
        unit_label = QLabel('Resolution Rings:')
        self.angstrom_button = QPushButton('Å')
        self.mrad_button = QPushButton('Mrad')
        self.inverse_angstrom_button = QPushButton('Å⁻¹')
        self.none_button = QPushButton('None')
        self.unit_button_group = QButtonGroup(self)
        self.unit_button_group.addButton(self.angstrom_button)
        self.unit_button_group.addButton(self.mrad_button)
        self.unit_button_group.addButton(self.inverse_angstrom_button)
        self.unit_button_group.addButton(self.none_button)
        self.angstrom_button.setCheckable(True)
        self.mrad_button.setCheckable(True)
        self.inverse_angstrom_button.setCheckable(True)
        self.none_button.setCheckable(True)
        # Connecting each button with the respective update_ring_labels function
        self.angstrom_button.clicked.connect(self.update_ring_labels)
        self.mrad_button.clicked.connect(self.update_ring_labels)
        self.inverse_angstrom_button.clicked.connect(self.update_ring_labels)
        self.none_button.clicked.connect(self.update_ring_labels)

        # Basic aesthetics portion for the layout of the buttons, etc
        unit_widget = QWidget(self)
        unit_layout = QHBoxLayout(unit_widget)
        unit_layout.addWidget(unit_label)
        unit_layout.addWidget(self.angstrom_button)
        unit_layout.addWidget(self.mrad_button)
        unit_layout.addWidget(self.inverse_angstrom_button)
        unit_layout.addWidget(self.none_button)
        popUpLayout.addRow(unit_widget) 

        save_button_widget = QWidget(self.popUp)
        save_button_layout = QVBoxLayout(save_button_widget)
        save_button_layout.setContentsMargins(0, 0, 130, 0)  # Set custom margins (left, top, right, bottom)

        save_button = QPushButton('Save and Apply')
        save_button.clicked.connect(self.close_Metadata_popup)
        save_button_layout.addWidget(save_button)
        
        popUpLayout.addWidget(save_button_widget)

        self.popUp.setLayout(popUpLayout)
        self.popUp.exec()

    def close_Metadata_popup(self):
        # Save the user input back to the class attributes
        self.wavelength = float(self.setting1.text())
        self.camera_length_mm = float(self.setting2.text())
        self.physical_pixel_size_mm = float(self.setting3.text())
        self.centerx = int(self.setting4.text()) 
        self.centery = int(self.setting5.text())

        self.popUp.close()
        # This portion will perform any necessary updates or calculations with the new metadata
        self.update_ring_labels
        self.add_concentric_rings()
        self.update_scalebar_labels()

    def _update_position_message(self):
        self.statusBar.showMessage(
            f'{self.file_path.name}; '
            f'Real: ({int(self.real_space_roi.pos().y())}, {int(self.real_space_roi.pos().x())}), '
            f'({int(self.real_space_roi.size().y())}, {int(self.real_space_roi.size().x())}); '
            f'Diffraction: ({int(self.diffraction_space_roi.pos().y())}, {int(self.diffraction_space_roi.pos().x())}), '
            f'({int(self.diffraction_space_roi.size().y())}, {int(self.diffraction_space_roi.size().x())})'
        )

    def _on_use_colormap(self):
        action = self.sender()
        self.diffraction_pattern_image_item.setColorMap(action.text())
        self.real_space_image_item.setColorMap(action.text())
    
    def SMV_popup(self):
        """Generate pop-up window where user can input correct metadata written to SMV file"""
        self.popUp = QDialog(self)
        self.popUp.setWindowTitle("Input metadata for SMV")

        self.setting1 = QLineEdit(str(self.wavelength))
        self.setting2 = QLineEdit(str(self.camera_length_mm))
        self.setting3 = QLineEdit(str(self.physical_pixel_size_mm))
        self.setting4 = QLineEdit(str(self.centerx))
        self.setting5 = QLineEdit(str(self.centery))
        
        popUpLayout = QFormLayout()
        popUpLayout.addRow('Wavelength (angstroms)', self.setting1)
        popUpLayout.addRow('Camera length (mm)', self.setting2)
        popUpLayout.addRow('Physical pixel size (mm)', self.setting3)

        # Use row / col formatting for 
        popUpLayout.addRow('Beam center row (pixels)', self.setting5)
        popUpLayout.addRow('Beam center column (pixels)', self.setting4)
        save_button = QPushButton('Save')
        save_button.clicked.connect(self.close_SMV_popup)
        popUpLayout.addWidget(save_button)

        self.popUp.setLayout(popUpLayout)
        self.popUp.exec()

    def close_SMV_popup(self):
        """Save input and close pop-up window"""
        self.wavelength = self.setting1.text()
        self.CL = self.setting2.text()
        self.pixelsize = self.setting3.text()
        self.centerx = self.setting4.text() # col
        self.centery = self.setting5.text() # row

        self.popUp.close()
    
    def _on_export(self):
        """Export the shown diffraction pattern as raw data in TIF file format"""
        action = self.sender()

        # Get a file path to save to in current directory
        fd = pg.FileDialog()
        if 'TIF' in action.text():
            fd.setNameFilter("TIF (*.tif)")
        elif 'SMV' in action.text():
            self.SMV_popup()
            fd.setNameFilter("IMG (*.IMG)")
        fd.setDirectory(str(self.current_dir))
        fd.setFileMode(pg.FileDialog.AnyFile)
        fd.setAcceptMode(pg.FileDialog.AcceptSave)

        if fd.exec_():
            file_name = fd.selectedFiles()[0]
            out_path = Path(file_name)
        else:
            return

        # Get the data and change to float
        if action.text() == 'Export diffraction (TIF)':
            if out_path.suffix != '.tif':
                out_path = out_path.with_suffix('.tif')
            imsave(out_path, self.dp.reshape(self.frame_dimensions).astype(np.float32))
        elif action.text() == 'Export diffraction (SMV)':
            if out_path.suffix != '.img':
                out_path = out_path.with_suffix('.img')
            self._write_smv(out_path)
        elif action.text() == 'Export real (TIF)':
            imsave(out_path, self.rs.reshape(self.scan_dimensions).astype(np.float32))
        else:
            print('Export: unknown action {}'.format(action.text()))

    def _write_smv(self, out_path):
        """Write out diffraction as SMV formatted file
        Header is 512 bytes of zeros and then filled with ASCII

        camera length, wavelength, and pixel_size are hard coded.
        """

        im = self.dp.reshape(self.frame_dimensions)
        if im.max() > 65535:
            im[im > 65535] = 65535  # maximum 16 bit value allowed
            im[im < 0] = 0  # just in case
            print('warning. Loss of dynamic range due to conversion from 32 bit to 16 bit')
        im = im.astype(np.uint16)
        dtype = 'unsigned_short'

        #if self.dp.dtype == np.uint16:
        #    dtype = 'unsigned_short'
        #elif im.dtype == np.uint32:
        #    dtype = 'unsigned_long'
        #else:
        #    raise TypeError('Unsupported dtype: {}'.format(im.dtype))

        # Write 512 bytes of zeros
        with open(out_path, 'wb') as f0:
            f0.write(np.zeros(512, dtype=np.uint8))
        # Write the header over the zeros as needed
        with open(out_path, 'r+', newline='\n') as f0:
            f0.write("{\nHEADER_BYTES=512;\n")
            f0.write("DIM=2;\n")
            f0.write("BYTE_ORDER=little_endian;\n")
            f0.write(f"TYPE={dtype};\n")
            f0.write(f"SIZE1={im.shape[1]};\n")  # size1 is columns
            f0.write(f"SIZE2={im.shape[0]};\n")  # size 2 is rows
            f0.write(f"PIXEL_SIZE={self.pixelsize};\n")  # physical pixel size in micron
            f0.write(f"WAVELENGTH={self.wavelength};\n")  # wavelength
            f0.write(f"DISTANCE={self.CL};\n")
            f0.write("PHI=0.0;\n")
            f0.write(f"BEAM_CENTER_X={self.centerx};\n")
            f0.write(f"BEAM_CENTER_Y={self.centery};\n")
            f0.write("BIN=1x1;\n")
            f0.write(f"DATE={str(datetime.now())};\n")
            f0.write("DETECTOR_SN=1;\n")  # detector serial number
            f0.write("OSC_RANGE=1.0;\n")
            f0.write("OSC_START=0;\n")
            f0.write("IMAGE_PEDESTAL=0;\n")
            f0.write("TIME=10.0;\n")
            f0.write("TWOTHETA=0;\n")

            # Append coordinates and size of real-space box so there is a permanent record of this in metadata
            f0.write(f"4DCAMERA_REAL_X={int(self.real_space_roi.pos().x())};\n")
            f0.write(f"4DCAMERA_REAL_Y={int(self.real_space_roi.pos().y())};\n")
            f0.write(f"4DCAMERA_BOXSIZE_X={int(self.real_space_roi.size().x())};\n")
            f0.write(f"4DCAMERA_BOXSIZE_Y={int(self.real_space_roi.size().y())};\n")
            f0.write(f"4DCAMERA_FILENAME={self.file_path.name};\n")
            f0.write("}\n")
        # Append the binary image data at the end of the header
        with open(out_path, 'rb+') as f0:
            f0.seek(512, 0)
            f0.write(im)

    def _on_log(self):
        self.log_diffraction = not self.log_diffraction
        self.update_diffr()

    def open_file(self):
        """ Show a dialog to choose a file to open.
        """

        fd = pg.FileDialog()
        fd.setNameFilter("Sparse Stempy (*.4dc *.h5)")
        fd.setDirectory(str(self.current_dir))
        fd.setFileMode(pg.FileDialog.ExistingFile)

        if fd.exec_():
            file_names = fd.selectedFiles()
            self.current_dir = Path(file_names[0]).parent
            self.file_path = Path(file_names[0])
            self.setData(self.file_path)

    @staticmethod
    def temp(aa):
        """Temporary empty function to avoid printing warning"""
        pass

    def setData(self, fPath):
        """ Load the data from the HDF5 file. Must be in
        the format output by stempy.io.save_electron_data().

        Parameters
        ----------
        fPath : pathlib.Path
            The path of to the file to load.
        """
        self.statusBar.showMessage("Loading the sparse data...")

        # Temporary: remove "full expansion" warning
        stio.sparse_array._warning = self.temp

        # Load data as a SparseArray class
        self.sa = stio.SparseArray.from_hdf5(str(fPath))

        self.sa.allow_full_expand = True
        self.scan_dimensions = self.sa.scan_shape
        self.frame_dimensions = self.sa.frame_shape
        self.num_frames_per_scan = self.sa.num_frames_per_scan
        print('scan dimensions = {}'.format(self.scan_dimensions))

        # Pre-calculate to speed things up
        self.statusBar.showMessage("Converting the data...")
        # Create a non-ragged array with zero padding
        mm = 0
        for ev in self.sa.data.ravel():
            if ev.shape[0] > mm:
                mm = ev.shape[0]
        print('non-ragged array shape: {}'.format((self.sa.data.ravel().shape[0], mm)))

        self.fr_full = np.zeros((self.sa.data.ravel().shape[0], mm), dtype=self.sa.data[0][0].dtype)
        for ii, ev in enumerate(self.sa.data.ravel()):
            self.fr_full[ii, :ev.shape[0]] = ev
        self.fr_full_3d = self.fr_full.reshape((*self.scan_dimensions, self.num_frames_per_scan, self.fr_full.shape[1]))

        print('non-ragged array size = {} GB'.format(self.fr_full.nbytes / 1e9))
        print('Full memory requirement = {} GB'.format(3 * self.fr_full.nbytes / 1e9))

        # Find the row and col for each electron strike
        self.fr_rows = (self.fr_full // int(self.frame_dimensions[0])).reshape(self.scan_dimensions[0] * self.scan_dimensions[1], self.num_frames_per_scan, mm)
        self.fr_cols = (self.fr_full  % int(self.frame_dimensions[1])).reshape(self.scan_dimensions[0] * self.scan_dimensions[1], self.num_frames_per_scan, mm)

        self.dp = np.zeros(self.frame_dimensions[0] * self.frame_dimensions[1], np.uint32)
        self.rs = np.zeros(self.scan_dimensions[0] * self.scan_dimensions[1], np.uint32)

        self.diffraction_pattern_limit = QRectF(0, 0, self.frame_dimensions[1], self.frame_dimensions[0])
        self.diffraction_space_roi.maxBounds = self.diffraction_pattern_limit

        self.real_space_limit = QRectF(0, 0, self.scan_dimensions[1], self.scan_dimensions[0])
        self.real_space_roi.maxBounds = self.real_space_limit

        self.real_space_roi.setSize([ii // 4 for ii in self.scan_dimensions][::-1])
        self.diffraction_space_roi.setSize([ii // 4 for ii in self.frame_dimensions][::-1])

        self.real_space_roi.setPos([ii // 4 + ii //8 for ii in self.scan_dimensions][::-1])
        self.diffraction_space_roi.setPos([ii // 4 + ii // 8 for ii in self.frame_dimensions][::-1])

        self.update_real()
        self.update_diffr()
                
        self.statusBar.showMessage('loaded {}'.format(fPath.name))
        # 5 rings, distance between each ring is around 50 pixels
        # Attempting to incorporate a scale bar into both real space and diffraction space images
        # Method I utilized to generate a picture of the scale bar
    
    def generate_picture(self, length, height, label, color, font_size):
        picture = QtGui.QPicture()
        painter = QtGui.QPainter(picture)
        pen = QtGui.QPen(QtGui.QColor(color))
        brush = QtGui.QBrush(QtGui.QColor(color))
        painter.setPen(pen)
        painter.setBrush(brush)

        font = QtGui.QFont()
        font.setPointSize(font_size)
        painter.setFont(font)

        painter.drawRect(0, -20 - int(height), int(length), int(height))

        painter.end()

        return picture

    # Generating a label for the scale bar
    def generate_label(self, space_type):
        if space_type == "real":
            # Calculating the label in nanometers for real space
            nm_label = self.physical_pixel_size_mm * 1e6
            return f"{round(nm_label)} nm"
        elif space_type == "diffraction":
            # Calculating the label in reciprocal angstroms for diffraction space
            angstrom = self.physical_pixel_size_mm * 1e7
            reciprocal_angstrom_label = 1 / angstrom 
            return f"{reciprocal_angstrom_label:g} Å⁻¹"

    # Method I utilized to add a scale bar to the view
    def add_scale_bar(self, view, image_item, color, font_size, space_type):
        dimensions = image_item.image.shape
        scale_height = 7  # Scale height in pixels

        scale_length = 100 # Scale length in pixels

        label = self.generate_label(space_type)

        picture = self.generate_picture(scale_length, scale_height, label, color, font_size)
        scale_bar = pg.GraphicsObject()
        scale_bar.paint = lambda p, *args: p.drawPicture(0, 0, picture)
        scale_bar.boundingRect = lambda: QtCore.QRectF(picture.boundingRect())
        view.addItem(scale_bar)
        
        scale_bar.setPos(20, image_item.height() - scale_height)
        
        label_item = QGraphicsTextItem(label)
        label_item.setFont(QtGui.QFont("Arial", font_size))
        label_item.setDefaultTextColor(QtGui.QColor(color))
        view.addItem(label_item)
        label_item.setPos(20 + scale_length / 2 - label_item.boundingRect().width() / 2, image_item.height() - scale_height - 35)

        scale_bar.setVisible(False)
        label_item.setVisible(False)

        return scale_bar, label_item
    
    # Adding scale bars to both real and diffraction space images
    def add_scale_bars(self):
        color = 'white'
        font_size = 12


        if not hasattr(self, 'real_space_scale_bar') or self.real_space_scale_bar is None:
            self.real_space_scale_bar, self.real_space_scale_label = self.add_scale_bar(self.view, self.real_space_image_item, color, font_size, "real")
        if not hasattr(self, 'diffraction_space_scale_bar') or self.diffraction_space_scale_bar is None:
            self.diffraction_space_scale_bar, self.diffraction_space_scale_label = self.add_scale_bar(self.view2, self.diffraction_pattern_image_item, color, font_size, "diffraction")


    # Updating the position and text of the scale bar labels
    def update_label_position(self, scale_bar, scale_label, image_item, label_text):
        scale_label.setPlainText(label_text)
        scale_length = scale_bar.boundingRect().width()
        bar_x = scale_bar.pos().x()
        label_x = bar_x + scale_length / 2 - scale_label.boundingRect().width() / 2
        label_y = image_item.height() - scale_label.boundingRect().height() - 35
        scale_label.setPos(label_x, label_y)

    # Updating the labels of the scale bars 
    def update_scalebar_labels(self):
        if self.real_space_scale_bar and self.real_space_scale_label:
            nm_label = self.physical_pixel_size_mm * 1e6
            real_space_label_text = f"{round(nm_label)} nm"
            self.update_label_position(self.real_space_scale_bar, self.real_space_scale_label, self.real_space_image_item, real_space_label_text)

        if self.diffraction_space_scale_bar and self.diffraction_space_scale_label:
            angstrom = self.physical_pixel_size_mm * 1e7
            reciprocal_angstrom_label = 1 / angstrom 
            diffraction_space_label_text = f"{reciprocal_angstrom_label:g} Å⁻¹"
            self.update_label_position(self.diffraction_space_scale_bar, self.diffraction_space_scale_label, self.diffraction_pattern_image_item, diffraction_space_label_text)
    
    def set_scale_bar_position(self, scale_bar, scale_label, image_item, position, offset=20):
        if position == 'left':
            x_pos = offset
            scale_bar.setVisible(True)
            scale_label.setVisible(True)
        elif position == 'right':
            x_pos = image_item.width() - scale_bar.boundingRect().width() - offset
            scale_bar.setVisible(True)
            scale_label.setVisible(True)
        else:  # 'none'
            scale_bar.setVisible(False)
            scale_label.setVisible(False)
            return

        y_pos = image_item.height() - scale_bar.boundingRect().height()
        scale_bar.setPos(x_pos, y_pos)

        scale_length = scale_bar.boundingRect().width()
        label_x = x_pos + scale_length / 2 - scale_label.boundingRect().width() / 2
        label_y = image_item.height() - scale_label.boundingRect().height() - 35
        scale_label.setPos(label_x, label_y)

    def toggle_scalebar(self, position):
        if not hasattr(self, 'real_space_scale_bar') or self.real_space_scale_bar is None:
            self.add_scale_bars()
                                                
        if self.real_space_scale_bar and self.real_space_scale_label:
            self.set_scale_bar_position(self.real_space_scale_bar, self.real_space_scale_label, self.real_space_image_item, position)
        if self.diffraction_space_scale_bar and self.diffraction_space_scale_label:
            self.set_scale_bar_position(self.diffraction_space_scale_bar, self.diffraction_space_scale_label, self.diffraction_pattern_image_item, position)

    # Creating rings and labels for the diffraction space image
    def create_ring_and_label(self, radius_pixels, theta, i):
        ring = QGraphicsEllipseItem(self.centerx - radius_pixels, self.centery - radius_pixels, 2 * radius_pixels, 2 * radius_pixels)
        ring.setPen(pg.mkPen('black', width=3))
        self.view2.addItem(ring)
        self.rings.append(ring)

        # Formulas to calculate the respective units of the rings
        if self.unit == 'Angstrom':
            d = self.wavelength / (2 * np.sin(theta))
            label_text = f"{d:.2f} Å"
        elif self.unit == 'Mrad':
            theta_mrad = theta * 1000
            label_text = f"{theta_mrad:.2f} Mrad"
        elif self.unit == 'Inverse Angstrom':
            s = np.sin(theta) / self.wavelength
            label_text = f"{s:.2f} Å⁻¹"

        label_item = QGraphicsTextItem(label_text)
        label_item.setFont(QtGui.QFont("Arial", 8))
        label_item.setDefaultTextColor(QtGui.QColor('white'))
        self.view2.addItem(label_item)

        angle = np.pi / 2  # 90 degrees
        label_x = self.centerx
        label_y = self.centery - (radius_pixels + 25) * np.sin(angle)
        label_item.setPos(label_x, label_y)
        self.labels.append(label_item)

    def add_concentric_rings(self):     
        for ring in getattr(self, 'rings', []):
            self.view2.removeItem(ring)
        for label in getattr(self, 'labels', []):
            self.view2.removeItem(label)

        if self.unit == 'None':
            return

        num_rings = 5
        ring_spacing = 50  # In pixels

        self.rings = []
        self.labels = []

        # Converting camera length and pixel size from mm to angstroms
        camera_length_angstroms = self.camera_length_mm * 1e7  # Convert mm to angstroms
        pixel_size_angstroms = self.physical_pixel_size_mm * 1e7  # Convert mm to angstroms

        for i in range(1, num_rings + 1):
            # I calculated the radius of the ring in pixels and angstroms
            radius_pixels = ring_spacing * i
            radius_angstroms = radius_pixels * pixel_size_angstroms
            two_theta = np.arctan(radius_angstroms / camera_length_angstroms)
            theta = two_theta / 2  # rad
            self.create_ring_and_label(radius_pixels, theta, i)

    def update_ring_labels(self):
        if self.angstrom_button.isChecked():
            self.unit = 'Angstrom'
        elif self.mrad_button.isChecked():
            self.unit = 'Mrad'
        elif self.inverse_angstrom_button.isChecked():
            self.unit = 'Inverse Angstrom'
        elif self.none_button.isChecked():
            self.unit = 'None'
        self.add_concentric_rings()

    def update_diffr_stempy(self):
        """ Update the diffraction space image by summing in real space
        """
        self.dp = self.sa[int(self.real_space_roi.pos().y()):int(self.real_space_roi.pos().y() + self.real_space_roi.size().y()) + 1,
        int(self.real_space_roi.pos().x()):int(self.real_space_roi.pos().x() + self.real_space_roi.size().x()) + 1, :, :]
        self.dp = self.dp.sum(axis=(0, 1))

        if self.log_diffraction:
            self.diffraction_pattern_image_item.setImage(np.log(self.dp + 1), autoRange=True)
        else:
            self.diffraction_pattern_image_item.setImage(self.dp, autoRange=True)

    def update_diffr_jit(self):
        self.dp[:] = self.getDenseFrame_jit(
            self.fr_full_3d[int(self.real_space_roi.pos().y()):int(self.real_space_roi.pos().y() + self.real_space_roi.size().y()) + 1,
            int(self.real_space_roi.pos().x()):int(self.real_space_roi.pos().x() + self.real_space_roi.size().x()) + 1, :, :],
            self.frame_dimensions)

        im = self.dp.reshape(self.frame_dimensions)
        if self.log_diffraction:
            self.diffraction_pattern_image_item.setImage(np.log(im + 1), autoRange=True)
        else:
            self.diffraction_pattern_image_item.setImage(im, autoRange=True)

    def update_real_stempy(self):
        """ Update the real space image by summing in diffraction space
        """
        self.rs = self.sa[:, :,
            int(self.diffraction_space_roi.pos().y()) - 1:int(self.diffraction_space_roi.pos().y() + self.diffraction_space_roi.size().y()) + 0,
            int(self.diffraction_space_roi.pos().x()) - 1:int(self.diffraction_space_roi.pos().x() + self.diffraction_space_roi.size().x()) + 0]
        self.rs = self.rs.sum(axis=(2, 3))
        self.real_space_image_item.setImage(self.rs, autoRange=True)

    def update_real_jit(self):
        self.rs[:] = self.getImage_jit(self.fr_rows, self.fr_cols,
            int(self.diffraction_space_roi.pos().y()) - 1,
            int(self.diffraction_space_roi.pos().y() + self.diffraction_space_roi.size().y()) + 0,
            int(self.diffraction_space_roi.pos().x()) - 1,
            int(self.diffraction_space_roi.pos().x() + self.diffraction_space_roi.size().x()) + 0)
        im = self.rs.reshape(self.scan_dimensions)
        self.real_space_image_item.setImage(im, autoRange=True)
        

    @staticmethod
    @jit(["uint32[:](uint32[:,:,:], uint32[:,:,:], int64, int64, int64, int64)"], nopython=True, nogil=True, parallel=True)
    def getImage_jit(rows, cols, left, right, bot, top):
        """ Sum number of electron strikes within a square box
        significant speed up using numba.jit compilation.

        Parameters
        ----------
        rows : 2D ndarray, (M, num_frames, N)
            The row of the electron strike location. Floor divide by frame_dimenions[0]. M is
            the raveled scan_dimensions axis and N is the zero-padded electron
            strike position location.
        cols : 2D ndarray, (M, num_frames, N)
            The column of the electron strike locations. Modulo divide by frame_dimensions[1]
        left, right, bot, top : int
            The locations of the edges of the boxes

        Returns
        -------
        : ndarray, 1D
            An image composed of the number of electrons for each scan position summed within the boxed region in
        diffraction space.

        """
        
        im = np.zeros(rows.shape[0], dtype=np.uint32)
        
        # For each scan position (ii) sum all events (kk) in each frame (jj)
        for ii in prange(im.shape[0]):
            ss = 0
            for jj in range(rows.shape[1]):
                for kk in range(rows.shape[2]):
                    t1 = rows[ii, jj, kk] > left
                    t2 = rows[ii, jj, kk] < right
                    t3 = cols[ii, jj, kk] > bot
                    t4 = cols[ii, jj, kk] < top
                    t5 = t1 * t2 * t3 * t4
                    if t5:
                        ss += 1
            im[ii] = ss
        return im

    @staticmethod
    @jit(nopython=True, nogil=True, parallel=True)
    #@jit(["uint32[:](uint32[:,:,:,:], UniTuple(int64, 2))"], nopython=True, nogil=True, parallel=True)
    def getDenseFrame_jit(frames, frame_dimensions):
        """ Get a frame summed from the 3D array.

        Parameters
        ----------
        frames : 3D ndarray, (I, J, K, L)
            A set of sparse frames to sum. Each entry is used as the strike location of an electron. I, J, K, L
            corresond to scan_dimension0, scan_dimension1, num_frame, event.
        frame_dimensions : tuple
            The size of the frame

        Returns
        -------
        : ndarray, 2D
        An image composed of the number of electrons in each detector pixel.


        """
        dp = np.zeros((frame_dimensions[0] * frame_dimensions[1]), np.uint32)
        # nested for loop for: scan_dimension0, scan_dimension1, num_frame, event
        for ii in prange(frames.shape[0]):
            for jj in prange(frames.shape[1]):
                for kk in prange(frames.shape[2]):
                    for ll in prange(frames.shape[3]):
                        pos = frames[ii, jj, kk, ll]
                        if pos > 0:
                            dp[pos] += 1
        return dp

def open_file():
    """Start the graphical user interface by opening a file. This is used from a python interpreter."""
    main()

def main():
    """Main function used to start the GUI."""
    
    qapp = QApplication([])
    DuSC_view = DuSC()
    DuSC_view.show()
    qapp.exec_()

if __name__ == '__main__':
    main()

