"""
Interactively display and analyze sparse 4D-STEM data.

author: Peter Ercius
"""

print('init')

from pathlib import Path

import pyqtgraph as pg
import numpy as np
from tifffile import imsave
import stempy.io as stio

from qtpy.QtWidgets import *
from qtpy.QtCore import QRectF
from qtpy import QtGui


class fourD(QWidget):

    def __init__(self, *args, **kwargs):

        self.RSlimit = None
        self.DPlimit = None
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
        print('Use log?: {}'.format(self.log_diffraction))

        super(fourD, self).__init__(*args, *kwargs)
        self.setWindowTitle("Stempy: Sparse 4D Data Explorer")
        self.setWindowIcon(QtGui.QIcon(r'C:\Users\linol\Downloads\MF_logo_only_small.ico'))

        # Add an graphics/view/image to show either 2D linescan or 3D SI
        # Need to set invertY = True and row-major
        self.graphics = pg.GraphicsLayoutWidget()
        self.view = self.graphics.addViewBox(row=0, col=0, invertY=True)
        self.view2 = self.graphics.addViewBox(row=0, col=1, invertY=True)

        self.RSimageview = pg.ImageItem(border=pg.mkPen('w'))
        self.view.addItem(self.RSimageview)
        self.RSimageview.setImage(np.zeros((100, 100), dtype=np.uint32))
        self.view.setAspectLocked()

        self.DPimageview = pg.ImageItem(border=pg.mkPen('w'))
        self.view2.addItem(self.DPimageview)
        self.DPimageview.setImage(np.zeros((100, 100), dtype=np.uint32))
        self.view2.setAspectLocked()

        self.DPimageview.setOpts(axisOrder="row-major")
        self.RSimageview.setOpts(axisOrder="row-major")

        # self.DPimageview.invertY(False)
        # self.RSimageview.invertY(False)

        self.statusBar = QStatusBar()
        self.statusBar.showMessage("Starting up...")

        # Add a File menu
        self.myQMenuBar = QMenuBar(self)
        menu_bar = self.myQMenuBar.addMenu('File')
        open_action = QAction('Open', self)
        open_action.triggered.connect(self.open_file)
        menu_bar.addAction(open_action)
        export_diff_action = QAction('Export diffraction', self)
        export_diff_action.triggered.connect(self._on_export)
        menu_bar.addAction(export_diff_action)
        export_real_action = QAction('Export real', self)
        export_real_action.triggered.connect(self._on_export)
        menu_bar.addAction(export_real_action)
        toggle_log_action = QAction('Toggle log(diffraction)', self)
        toggle_log_action.triggered.connect(self._on_log)
        menu_bar.addAction(toggle_log_action)

        self.setLayout(QVBoxLayout())
        self.layout().addWidget(self.myQMenuBar)
        self.layout().addWidget(self.graphics)
        self.layout().addWidget(self.statusBar)

        # Initialize the user interface objects
        # Image ROI
        self.RSroi = pg.RectROI(pos=(0, 0), size=(50, 50),
                                translateSnap=True, snapSize=1, scaleSnap=True,
                                removable=False, invertible=False, pen='g')
        self.view.addItem(self.RSroi)

        # Sum ROI
        self.DProi = pg.RectROI(pos=(287 - 50, 287 - 50), size=(50, 50),
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
            # image = self.DPimageview.image
            image = self.dp.reshape(self.frame_dimensions)
        elif action.text() == 'Export real':
            # image = self.RSimageview.image
            image = self.rs.reshape(self.scan_dimensions)
        else:
            print(action.text())

        imsave(outPath, image.astype(np.float32))

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

        # Remove "full expansion" warning
        stio.sparse_array._warning = self.temp

        # Load data as a SparseArray class
        self.sa = stio.SparseArray.from_hdf5(fPath)

        self.sa.allow_full_expand = True
        self.scan_dimensions = self.sa.scan_shape
        self.frame_dimensions = self.sa.frame_shape
        print('initial scan dimensions = {}'.format(self.scan_dimensions))

        self.dp = np.zeros(self.frame_dimensions[0] * self.frame_dimensions[1], np.uint32)
        self.rs = np.zeros(self.scan_dimensions[0] * self.scan_dimensions[1], np.uint32)

        self.DPlimit = QRectF(0, 0, self.frame_dimensions[1], self.frame_dimensions[0])
        self.DProi.maxBounds = self.DPlimit

        self.RSlimit = QRectF(0, 0, self.scan_dimensions[1], self.scan_dimensions[0])
        self.RSroi.maxBounds = self.RSlimit

        self.update_real()
        self.update_diffr()

        self.statusBar.showMessage('loaded {}'.format(fPath.name))


def update_diffr(self):
    """ Update the diffraction space image by summing in real space
    """
    im = self.sa[int(self.RSroi.pos().y()):int(self.RSroi.pos().y() + self.RSroi.size().y()) + 1,
         int(self.RSroi.pos().x()):int(self.RSroi.pos().x() + self.RSroi.size().x()) + 1, :, :].sum(axis=(0, 1))
    if self.log_diffraction:
        self.DPimageview.setImage(np.log(im + .1), autoRange=True)
    else:
        self.DPimageview.setImage(im, autoRange=True)


def update_real(self):
    """ Update the real space image by summing in diffraction space
    """
    # print('{}, {}'.format(self.DProi.pos().x(),self.DProi.pos().y()))
    # print('{}, {}'.format(self.DProi.size().x(),self.DProi.size().y()))
    # print('sa = {}'.format(self.sa.shape))
    self.rs = self.sa[:, :, int(self.DProi.pos().y()) - 1:int(self.DProi.pos().y() + self.DProi.size().y()) + 0,
              int(self.DProi.pos().x()) - 1:int(self.DProi.pos().x() + self.DProi.size().x()) + 0]
    im = self.rs.sum(axis=(2, 3))
    self.RSimageview.setImage(im, autoRange=True)


def main():
    qapp = QApplication([])
    fourD_view = fourD()
    fourD_view.show()
    qapp.exec_()


#if __name__ == '__main__':
#    main()
