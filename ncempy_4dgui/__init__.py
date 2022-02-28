"""
Interactively display and analyze sparse 4D-STEM data.

author: Peter Ercius
"""

from pathlib import Path

import pyqtgraph as pg
import numpy as np
from tifffile import imsave
from numba import jit
import stempy.io as stio

from qtpy.QtWidgets import *
from qtpy.QtCore import QRectF
from qtpy import QtGui


class fourD(QWidget):

    def __init__(self, *args, **kwargs):

        self.real_space_limit = None
        self.diffraction_pattern_limit = None
        self.sa = None
        self.current_dir = Path.home()
        self.scale = 1
        self.center = (287, 287)
        self.scan_dimensions = (0, 0)
        self.frame_dimensions = (576, 576)
        self.fr_full = None
        self.fr_full_3d = None
        self.fr_rows = None
        self.fr_cols = None
        self.dp = None
        self.rs = None
        self.log_diffraction = True

        super(fourD, self).__init__(*args, *kwargs)
        self.setWindowTitle("Stempy: Sparse 4D Data Explorer")
        self.setWindowIcon(QtGui.QIcon('MF_logo_only_small.ico'))

        # Set the update strategy to the JIT version
        self.update_real = self.update_real_jit
        self.update_diffr = self.update_diffr_jit

        # Add a graphics/view/image
        # Need to set invertY = True and row-major
        self.graphics = pg.GraphicsLayoutWidget()
        self.view = self.graphics.addViewBox(row=0, col=0, invertY=True)
        self.view2 = self.graphics.addViewBox(row=0, col=1, invertY=True)

        self.real_space_imageview = pg.ImageItem(border=pg.mkPen('w'))
        self.view.addItem(self.real_space_imageview)
        self.real_space_imageview.setImage(np.zeros((100, 100), dtype=np.uint32))
        self.view.setAspectLocked()

        self.diffraction_pattern_imageview = pg.ImageItem(border=pg.mkPen('w'))
        self.view2.addItem(self.diffraction_pattern_imageview)
        self.diffraction_pattern_imageview.setImage(np.zeros((100, 100), dtype=np.uint32))
        self.view2.setAspectLocked()

        self.diffraction_pattern_imageview.setOpts(axisOrder="row-major")
        self.real_space_imageview.setOpts(axisOrder="row-major")

        self.statusBar = QStatusBar()
        self.statusBar.showMessage("Starting up...")

        # Add a File menu
        self.myQMenuBar = QMenuBar(self)
        menu_bar_file = self.myQMenuBar.addMenu('File')
        menu_bar_export = self.myQMenuBar.addMenu('Export')
        menu_bar_display = self.myQMenuBar.addMenu('Display')
        open_action = QAction('Open', self)
        open_action.triggered.connect(self.open_file)
        menu_bar_file.addAction(open_action)
        export_diff_action = QAction('Export diffraction', self)
        export_diff_action.triggered.connect(self._on_export)
        menu_bar_export.addAction(export_diff_action)
        export_real_action = QAction('Export real', self)
        export_real_action.triggered.connect(self._on_export)
        menu_bar_export.addAction(export_real_action)
        toggle_log_action = QAction('Toggle log(diffraction)', self)
        toggle_log_action.triggered.connect(self._on_log)
        menu_bar_display.addAction(toggle_log_action)

        self.setLayout(QVBoxLayout())
        self.layout().addWidget(self.myQMenuBar)
        self.layout().addWidget(self.graphics)
        self.layout().addWidget(self.statusBar)

        # Initialize the user interface objects
        # Image ROI
        self.RSroi = pg.RectROI(pos=(0, 0), size=(10, 10),
                                translateSnap=True, snapSize=1, scaleSnap=True,
                                removable=False, invertible=False, pen='g')
        self.view.addItem(self.RSroi)

        # Diffraction ROI
        self.DProi = pg.RectROI(pos=(0, 0), size=(10, 10),
                                translateSnap=True, snapSize=1, scaleSnap=True,
                                removable=False, invertible=False, pen='g')
        self.view2.addItem(self.DProi)

        self.open_file()

        self.RSroi.sigRegionChanged.connect(self.update_diffr)
        self.DProi.sigRegionChanged.connect(self.update_real)

    def _on_export(self):
        """Export the shown diffraction pattern as raw data"""
        action = self.sender()

        # Get a file path to save to in current directory
        fd = pg.FileDialog()
        fd.setNameFilter("TIF (*.tif)")
        fd.setDirectory(str(self.current_dir))
        fd.setFileMode(pg.FileDialog.AnyFile)
        fd.setAcceptMode(pg.FileDialog.AcceptSave)

        if fd.exec_():
            file_name = fd.selectedFiles()[0]
            outPath = Path(file_name)
        else:
            return

        if outPath.suffix != '.tif':
            outPath = outPath.with_suffix('.tif')

        # Get the data and change to float
        if action.text() == 'Export diffraction':
            imsave(outPath, self.dp.astype(np.float32))
        elif action.text() == 'Export real':
            imsave(outPath, self.rs.astype(np.float32))
        else:
            print('Export: unknown action {}'.format(action.text()))

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

            self.setData(Path(file_names[0]))

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
        print('scan dimensions = {}'.format(self.scan_dimensions))

        # Pre-calculate to speed things up
        self.statusBar.showMessage("Converting the data...")
        # Create a non-ragged array with zero padding
        mm = 0
        for ev in self.sa.data.ravel():
            if ev.shape[0] > mm:
                mm = ev.shape[0]
        print('non-ragged array shape: {}'.format((self.sa.data.ravel().shape[0], mm)))

        self.fr_full = np.zeros((self.sa.data.ravel().shape[0], mm), dtype=self.sa.data[0].dtype)
        for ii, ev in enumerate(self.sa.data.ravel()):
            self.fr_full[ii, :ev.shape[0]] = ev
        self.fr_full_3d = self.fr_full.reshape((*self.scan_dimensions, self.fr_full.shape[1]))

        # del frames

        print('non-ragged array size = {} GB'.format(self.fr_full.nbytes / 1e9))

        # Find the row and col for each electron strike
        self.fr_rows = self.fr_full // 576
        self.fr_cols = self.fr_full % 576

        self.dp = np.zeros(self.frame_dimensions[0] * self.frame_dimensions[1], np.uint32)
        self.rs = np.zeros(self.scan_dimensions[0] * self.scan_dimensions[1], np.uint32)

        self.diffraction_pattern_limit = QRectF(0, 0, self.frame_dimensions[1], self.frame_dimensions[0])
        self.DProi.maxBounds = self.diffraction_pattern_limit

        self.real_space_limit = QRectF(0, 0, self.scan_dimensions[1], self.scan_dimensions[0])
        self.RSroi.maxBounds = self.real_space_limit

        self.RSroi.setSize([ii//4 for ii in self.scan_dimensions])
        self.DProi.setSize([ii//4 for ii in self.frame_dimensions])

        self.RSroi.setPos([0, 0])
        self.DProi.setPos([0, 0])

        self.update_real()
        self.update_diffr()

        self.statusBar.showMessage('loaded {}'.format(fPath.name))

    def update_diffr_stempy(self):
        """ Update the diffraction space image by summing in real space
        """
        self.dp = self.sa[int(self.RSroi.pos().y()):int(self.RSroi.pos().y() + self.RSroi.size().y()) + 1,
                          int(self.RSroi.pos().x()):int(self.RSroi.pos().x() + self.RSroi.size().x()) + 1, :, :]
        self.dp = self.dp.sum(axis=(0, 1))

        if self.log_diffraction:
            self.diffraction_pattern_imageview.setImage(np.log(self.dp + 1), autoRange=True)
        else:
            self.diffraction_pattern_imageview.setImage(self.dp, autoRange=True)

    def update_diffr_jit(self):
        self.dp[:] = self.getDenseFrame_jit(
            self.fr_full_3d[int(self.RSroi.pos().y()):int(self.RSroi.pos().y() + self.RSroi.size().y()) + 1,
                            int(self.RSroi.pos().x()):int(self.RSroi.pos().x() + self.RSroi.size().x()) + 1, :],
            self.frame_dimensions)

        im = self.dp.reshape(self.frame_dimensions)
        if self.log_diffraction:
            self.diffraction_pattern_imageview.setImage(np.log(im + 1), autoRange=True)
        else:
            self.diffraction_pattern_imageview.setImage(im, autoRange=True)

    def update_real_stempy(self):
        """ Update the real space image by summing in diffraction space
        """
        self.rs = self.sa[:, :,
                          int(self.DProi.pos().y()) - 1:int(self.DProi.pos().y() + self.DProi.size().y()) + 0,
                          int(self.DProi.pos().x()) - 1:int(self.DProi.pos().x() + self.DProi.size().x()) + 0]
        self.rs = self.rs.sum(axis=(2, 3))
        self.real_space_imageview.setImage(self.rs, autoRange=True)

    def update_real_jit(self):
        self.rs[:] = self.getImage_jit(self.fr_rows, self.fr_cols,
                                       int(self.DProi.pos().y()) - 1,
                                       int(self.DProi.pos().y() + self.DProi.size().y()) + 0,
                                       int(self.DProi.pos().x()) - 1,
                                       int(self.DProi.pos().x() + self.DProi.size().x()) + 0)
        im = self.rs.reshape(self.scan_dimensions)
        self.real_space_imageview.setImage(im, autoRange=True)

    @staticmethod
    @jit(nopython=True, nogil=True, parallel=True)
    def getImage_jit(rows, cols, left, right, bot, top):
        """ Sum number of electron strikes within a square box
        significant speed up using numba.jit compilation.

        Parameters
        ----------
        rows : 2D ndarray, (M, N)
            The row of the electron strike location. Floor divide by 576. M is
            the raveled scan_dimensions axis and N is the zero-padded electron
            strike position location.
        cols : 2D ndarray, (M, N)
            The column of the electron strike locations. Modulo divide by 576
        left, right, bot, top : int
            The locations of the edges of the boxes

        Returns
        -------
        : ndarray, 2D
            An image composed of the number of electrons for each scan position summed within the boxed region in
        diffraction space.

        """
        im = np.zeros(rows.shape[0], dtype=np.uint32)

        for ii in range(rows.shape[0]):
            kk = 0
            for jj in range(rows.shape[1]):
                t1 = rows[ii, jj] > left
                t2 = rows[ii, jj] < right
                t3 = cols[ii, jj] > bot
                t4 = cols[ii, jj] < top
                t5 = t1 * t2 * t3 * t4
                if t5:
                    kk += 1
            im[ii] = kk
        return im

    @staticmethod
    @jit(nopython=True, nogil=True, parallel=True)
    def getDenseFrame_jit(frames, frame_dimensions):
        """ Get a frame summed from the 3D array.

        Parameters
        ----------
        frames : 3D ndarray, (M, N, K)
            A set of sparse frames to sum. Each entry is used as the strike location of an electron. T
        frame_dimensions : tuple
            The size of the frame

        Returns
        -------
        : ndarray, 2D
        An image composed of the number of electrons in each detector pixel.


        """
        dp = np.zeros((frame_dimensions[0] * frame_dimensions[1]), np.uint32)
        for ii in range(frames.shape[0]):
            for jj in range(frames.shape[1]):
                for kk in range(frames.shape[2]):
                    pos = frames[ii, jj, kk]
                    if pos > 0:
                        dp[pos] += 1
        return dp


def open_file():
    """Start the graphical user interface by opening a file. This is used from a python interpreter."""
    main()


def main():
    """Main function used to start the GUI."""
    qapp = QApplication([])
    fourD_view = fourD()
    fourD_view.show()
    qapp.exec_()
