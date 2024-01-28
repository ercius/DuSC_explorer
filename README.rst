========
Dual Space Crystallogrpahy (DuSC) Explorer
========

A graphical user interface based on pyqtgraph to visualize sparse 4D-STEM data sets. 

============
Installation
============

DuSC is based on pyqtgraph. Install this first according to the `installation instructions <https://pyqtgraph.readthedocs.io/en/latest/getting_started/installation.html>`_. For example:

``$ pip install pyqtgraph``

Next, clone the DuSC repository using Git and install from source by typing:

``$ pip install -e .``

in the source directory.

In some cases, you also need to install PyQT or Pyside. This should be installed with pyqtgrpah in the first action above but not always. In case you see error related to QT try:

``$ pip install PyQt6``

Note: A pypi version is coming soon to make this much easier!

=============
Compatibility
=============

This program requires pyqtgraph >=0.11. You will also need to install the corresponding version of QT depending on your operating system. Python 3.9 and PyQt6 are confirmed to work together.

===================
Running the Program
===================

If you installed the source (see above) then you can type

``$ DuSC_explorer``

in a terminal or command prompt and the program should start.

Alternatively, in a terminal you can run these commands:

``$ python``

``>>> import DuSC_explorer``

``>>> DuSC_explorer.open_file()``

and a file selector will open. Select a file and the program will load the file.