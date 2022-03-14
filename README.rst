========
4D Camera Graphical User Interface
========

A GUI based on stempy and pyqtgraph to visualize sparse 4D-STEM data sets.

============
Installation
============

Clone the repository and install from source using

``pip install -e .``

from the source directory.

=============
Compatibility
=============

This program requires pyqtgraph 0.11. You may also need to install different versions of QT depending on your
operating system. Python 3.9 and PyQt6 have been tested to work as specified in the table on the [pyqtgaph
Github README] (https://github.com/pyqtgraph/pyqtgraph#qt-bindings-test-matrix)

===============
Running the GUI
===============

If you installed the source (see above) then you can type

``$ ncempy_4dgui``

at a terminal or command prompt and the GUI should start.

Alternatively, in a python interpreter you can run these commands:

``>>> import ncempy_4dgui``

``>>> ncempy_4dgui.open_file()``

to start the GUI.