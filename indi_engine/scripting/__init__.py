"""Action scripting engine for INDIEngine.

Scripts are sandboxed Python files that can execute INDI commands and use
astronomy libraries (astropy, astroquery, fitsio). No file I/O, network
access, or arbitrary imports are permitted.
"""
