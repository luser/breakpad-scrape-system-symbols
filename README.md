This repository contains two scripts intended for use with Breakpad crash reporting.

gathersymbols.py attempts to find system libraries and run Breakpad's dump_syms tool on them to output Breakpad-format symbols. You must place a usable dump_syms binary next to the script. It will produce a symbols.zip in the current directory. By default gathersymbols.py will download a list of missing symbols from Mozilla's Socorro install and only upload symbols that are present in that list, but you can override this behavior by passing `--all` or passing library filenames on the command line.

uploadsymbols.py takes a symbols.zip and a Socorro authentication token and uploads the symbols.zip using Socorro's symbol upload API.

Both scripts require the Python `requests` library to be installed.
