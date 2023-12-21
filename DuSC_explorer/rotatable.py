"""
Load TitanX data and show real and reciprocal space.

The real space ROI can be rotated

author: Peter Ercius
date: 2023/11/02

"""

from pathlib import Path

import pyqtgraph as pg
from pyqtgraph.graphicsItems.ROI import Handle
import numpy as np
from scipy import ndimage
import ncempy 
from tifffile import imwrite

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
        self.tt = None
        self.dp = None
        self.rs = None
        self.log_diffraction = True
        self.handle_size = 10

        self.available_colormaps = ['thermal', 'flame', 'yellowy', 'bipolar', 'spectrum', 'cyclic', 'greyclip', 'grey',
                                    'viridis', 'inferno', 'plasma', 'magma']
        self.colormap = pg.colormap.getFromMatplotlib('grey')

        super(fourD, self).__init__(*args, *kwargs)
        self.setWindowTitle("NCEM: TitanX 4D Data Explorer")
        self.setWindowIcon(QtGui.QIcon('MF_logo_only_small.ico'))

        # Set the update strategy to the JIT version
        #self.update_real = self.update_real_stempy
        #self.update_diffr = self.update_diffr_stempy

        # Add a graphics/view/image
        # Need to set invertY = True and row-major
        self.graphics = pg.GraphicsLayoutWidget()
        self.view = self.graphics.addViewBox(row=0, col=0, invertY=True)
        self.view2 = self.graphics.addViewBox(row=0, col=1, invertY=True)
        
        self.real_space_image_item = pg.ImageItem(border=pg.mkPen('w'))
        self.real_space_image_item.setImage(self.rs)
        self.view.addItem(self.real_space_image_item)
        self.real_space_image_item.setColorMap(self.colormap)
        
        self.view.setAspectLocked()

        self.diffraction_pattern_image_item = pg.ImageItem(border=pg.mkPen('w'))
        self.diffraction_pattern_image_item.setImage(np.zeros((100, 100), dtype=np.uint32))
        self.view2.addItem(self.diffraction_pattern_image_item)
        self.view2.setAspectLocked()
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
        
        self.open_file()
        
        self.real_space_roi.addRotateHandle((0, 0), (0.5, 0.5))
        
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
    
    def open_file(self):
        """ Show a dialog to choose a file to open.
        """

        fd = pg.FileDialog()
        fd.setNameFilter("Sparse Stempy (*.dm3 *.dm4)")
        fd.setDirectory(str(self.current_dir))
        fd.setFileMode(pg.FileDialog.ExistingFile)

        if fd.exec_():
            file_names = fd.selectedFiles()
            self.current_dir = Path(file_names[0]).parent

            self.setData(Path(file_names[0]))
    
    def setData(self, fPath):
        """ Load the data from the DM file.

        Parameters
        ----------
        fPath : pathlib.Path
            The path of to the file to load.
        """
        self.statusBar.showMessage("Loading the data...")

        # Load data as a SparseArray class
        with ncempy.io.dm.fileDM(fPath) as f0:
            dm0 = f0.getDataset(0)

            scanI = int(f0.allTags['.ImageList.2.ImageTags.Series.nimagesx'])
            scanJ = int(f0.allTags['.ImageList.2.ImageTags.Series.nimagesy'])
            numkI = dm0['data'].shape[2]
            numkJ = dm0['data'].shape[1]

            self.sa = dm0['data'].reshape([scanJ,scanI,numkJ,numkI])
        
        print('Data shape is {}'.format(self.sa.shape))
        
        self.scan_dimensions = (scanJ, scanI)
        self.frame_dimensions = (numkJ, numkI)
        self.num_frames_per_scan = 1
        print('scan dimensions = {}'.format(self.scan_dimensions))

        self.dp = np.zeros((self.frame_dimensions[0], self.frame_dimensions[1]), np.uint32)
        self.rs = np.zeros((self.scan_dimensions[0], self.scan_dimensions[1]), np.uint32)
        
        self.diffraction_pattern_limit = QRectF(0, 0, self.frame_dimensions[0], self.frame_dimensions[1])
        self.diffraction_space_roi.maxBounds = self.diffraction_pattern_limit

        self.real_space_limit = QRectF(0, 0, self.scan_dimensions[0], self.scan_dimensions[1])
        self.real_space_roi.maxBounds = self.real_space_limit

        self.real_space_roi.setSize([ii // 4 for ii in self.scan_dimensions])
        self.diffraction_space_roi.setSize([ii // 4 for ii in self.frame_dimensions])

        self.real_space_roi.setPos([ii // 4 + ii //8 for ii in self.scan_dimensions])
        self.diffraction_space_roi.setPos([ii // 4 + ii // 8 for ii in self.frame_dimensions])
       
        self.update_real()
        self.update_diffr()
                
        self.statusBar.showMessage('loaded {}'.format(fPath.name))
    

    def update_diffr(self):
        """ Update the diffraction space image by summing in real space
        """
        # Get the region of the real space ROI
        out = self.real_space_roi.getArrayRegion(self.dp, self.real_space_image_item,returnMappedCoords=True,order=0)
        # Setup a mask with the correct dimensions
        mask = np.zeros(self.scan_dimensions, dtype=bool)
        mask[np.round(out[1][0].astype(np.uint16)), np.round(out[1][1]).astype(np.uint16)] = 1
        ndimage.binary_closing(mask, output=mask)
        
        out2 = self.real_space_roi.getArraySlice(self.dp, self.real_space_image_item)

        temp = self.sa[out2[0][0],out2[0][1],:,:]
        mask = mask[out2[0][0],out2[0][1]]
        self.dp = temp.sum(axis=(0,1),where=mask[:,:,None,None], dtype=np.uint16)

        self.diffraction_pattern_image_item.setImage(np.log(self.dp + 1))

    def update_real(self):
        """ Update the real space image by summing in diffraction space
        """
        self.rs = self.sa[:, :,
                  int(self.diffraction_space_roi.pos().y()) - 1:int(self.diffraction_space_roi.pos().y() + self.diffraction_space_roi.size().y()) + 0,
                  int(self.diffraction_space_roi.pos().x()) - 1:int(self.diffraction_space_roi.pos().x() + self.diffraction_space_roi.size().x()) + 0]
        self.rs = self.rs.sum(axis=(2, 3))
        self.real_space_image_item.setImage(self.rs, autoRange=True)
    
    def _on_export(self):
        """Export the shown diffraction pattern as raw data in TIF file format"""
        action = self.sender()

        # Get a file path to save to in current directory
        fd = pg.FileDialog()
        if 'TIF' in action.text():
            fd.setNameFilter("TIF (*.tif)")
        elif 'SMV' in action.text():
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
            imwrite(out_path, self.dp.reshape(self.frame_dimensions).astype(np.float32))
        elif action.text() == 'Export diffraction (SMV)':
            if out_path.suffix != '.img':
                out_path = out_path.with_suffix('.img')
            self._write_smv(out_path)
        elif action.text() == 'Export real (TIF)':
            imwrite(out_path, self.rs.reshape(self.scan_dimensions).astype(np.float32))
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
        with open(out_path, 'r+') as f0:
            f0.write("{\nHEADER_BYTES=512;\n")
            f0.write("DIM=2;\n")
            f0.write("BYTE_ORDER=little_endian;\n")
            f0.write(f"TYPE={dtype};\n")
            f0.write(f"SIZE1={im.shape[1]};\n")  # size1 is columns
            f0.write(f"SIZE2={im.shape[0]};\n")  # size 2 is rows
            f0.write(f"PIXEL_SIZE={pixel_size};\n") # physical pixel size in micron
            f0.write(f"WAVELENGTH={lamda};\n") # wavelength
            if mag:
                f0.write(f"DISTANCE={int(mag)};\n")
            f0.write("PHI=0.0;\n")
            f0.write("BEAM_CENTER_X=1.0;\n")
            f0.write("BEAM_CENTER_Y=1.0;\n")
            f0.write("BIN=1x1;\n")
            f0.write("DATE=Thu Oct 21 23:06:09 2021;\n")
            f0.write("DETECTOR_SN=unknown;\n")
            f0.write("OSC_RANGE=1.0;\n")
            f0.write("OSC_START=0;\n")
            f0.write("IMAGE_PEDESTAL=0;\n")
            f0.write("TIME=10.0;\n")
            f0.write("TWOTHETA=0;\n")
            f0.write("}\n")
        # Append the binary image data at the end of the header
        with open(out_path, 'rb+') as f0:
            f0.seek(512, 0)
            f0.write(im)
if __name__ == '__main__':
    """Main function used to start the GUI."""
    
    qapp = QApplication([])
    fourD_view = fourD()
    fourD_view.show()
    qapp.exec_()
