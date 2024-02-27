# Dual Space Crystallography Explorer (DuSC_explorer)

A graphical user interface based on stempy and pyqtgraph to visualize sparse 4D-STEM data sets.

# Installation

## Using `pip`

The easiest way to install is to use python's pip command:

 - (Optional) Set up a virtual environment
 - Run `$ pip install DuSC_explorer`

## From source

If you want to develop or get the newest changes:

 - Clone the repository using git.
 - Change directories to the base directory containing the `pyproject.toml` file
 - Install locally and editable using ``$ pip install -e .``

# Compatibility

This program requires pyqtgraph >=0.13. You may also need to install different versions of QT depending on your operating system. Python 3.9 and PyQt6 have been tested to work as specified in the table on the [pyqtgaph Github README] (https://github.com/pyqtgraph/pyqtgraph#qt-bindings-test-matrix)

# Running the program

If you installed using pip or from source (see above) then you can type

``$ DuSC_explorer``

at a terminal or command prompt in the correct virtual environment and the GUI should start.

Alternatively, in a python interpreter for the correct environment you can run these commands:

``>>> import DuSC_explorer``

``>>> DuSC_explorer.open_file()``

to start the GUI. 
