# Dual Space Crystallography Explorer (DuSC_explorer)

A graphical user interface based on stempy and pyqtgraph to visualize sparse 4D-STEM data sets.

# Installation

## Using `pip`

The easiest way to install is to use python's pip command:

 - (Optional) Set up a virtual environment (e.g. using conda)
 - Run the following command at a command prompt
 ```bash
pip install DuSC_explorer
```
 - See the "compatibility" section below for installing QT bindings.

## From source

If you want to develop or get the newest changes:

 - Clone the repository using git.
 - Change directories to the base directory containing the `pyproject.toml` file.
 - Install locally and editable by running this in a terminal
```bash
pip install -e .
```

# Tutorial

To get started with the program please see our [tutorial](https://github.com/ercius/DuSC_explorer/blob/main/DuSC_explorer_tutorial.md). You can also download example data from a recently published paper from this Zenodo repository:
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.10387146.svg)](https://doi.org/10.5281/zenodo.10387146).

# Compatibility

This program requires pyqtgraph >=0.13. You may also need to install different versions of QT depending on your operating system. Python 3.9 and PyQt6 have been tested to work as specified in the table on the [pyqtgaph Github README](https://github.com/pyqtgraph/pyqtgraph?tab=readme-ov-file#requirements)

# Running the program

If you installed using pip or from source (see above) then you can simply type the program name in the command line and press enter:

```bash
$ DuSC_explorer
```

in a terminal or command prompt in the correct virtual environment and the GUI should start.

Alternatively, in a python interpreter for the correct environment you can run these commands to start the GUI:

```python
>>> import DuSC_explorer
>>> DuSC_explorer.open_file()
```

![GUI example](images/dusc_explorer2.png)
