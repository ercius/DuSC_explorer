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
from numba.types.containers import UniTuple
import stempy.io as stio

from qtpy.QtWidgets import *
from qtpy.QtCore import QRectF
from qtpy import QtGui


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
        
        self.available_colormaps = ['viridis', 'inferno', 'plasma', 'magma','cividis','CET-C5','CET-C5s']
        self.colormap = 'viridis' # default colormap

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

        # Add a File menu
        self.myQMenuBar = QMenuBar(self)
        menu_bar_file = self.myQMenuBar.addMenu('File')
        menu_bar_export = self.myQMenuBar.addMenu('Export')
        menu_bar_display = self.myQMenuBar.addMenu('Display')
        display_colormap = menu_bar_display.addMenu('Set colormap')
        open_action = QAction('Open', self)
        open_action.triggered.connect(self.open_file)
        menu_bar_file.addAction(open_action)
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

        self.open_file()

        self.real_space_roi.sigRegionChanged.connect(self.update_diffr)
        self.diffraction_space_roi.sigRegionChanged.connect(self.update_real)
        self.real_space_roi.sigRegionChanged.connect(self._update_position_message)
        self.diffraction_space_roi.sigRegionChanged.connect(self._update_position_message)

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

        # defaults: 300 keV, 85 mm indicated CL = 110 mm corrected, unbinned 0.01 mm pixel size, assume dead center
        self.setting1 = QLineEdit("0.0197")
        self.setting2 = QLineEdit("110")
        self.setting3 = QLineEdit("0.01")
        self.setting4 = QLineEdit("288")
        self.setting5 = QLineEdit("288")

        popUpLayout = QFormLayout()
        popUpLayout.addRow('Wavelength (angstroms)', self.setting1)
        popUpLayout.addRow('Camera length (mm)', self.setting2)
        popUpLayout.addRow('Physical pixel size (mm)', self.setting3)
        popUpLayout.addRow('Beam center x (pixels)', self.setting4)
        popUpLayout.addRow('Beam center y (pixels)', self.setting5)
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
        self.centerx = self.setting4.text()
        self.centery = self.setting5.text()

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
        # Hard coded metadata
        mag = 110  # camera length in mm
        lamda = 1.9687576525122874e-12
        pixel_size = 10e-6  # micron

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
        self.fr_rows = (self.fr_full // 576).reshape(self.scan_dimensions[0] * self.scan_dimensions[1], self.num_frames_per_scan, mm)
        self.fr_cols = (self.fr_full  % 576).reshape(self.scan_dimensions[0] * self.scan_dimensions[1], self.num_frames_per_scan, mm)

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
            The row of the electron strike location. Floor divide by 576. M is
            the raveled scan_dimensions axis and N is the zero-padded electron
            strike position location.
        cols : 2D ndarray, (M, num_frames, N)
            The column of the electron strike locations. Modulo divide by 576
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
