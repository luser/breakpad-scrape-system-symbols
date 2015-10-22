#!/bin/sh
# Run setup.sh before running this script.
# This script will attempt to scrape symbols from iOS system libraries that
# Xcode has pulled from devices connected to this computer.
set -e

venv/bin/gathersymbols -v ./dump_syms ~/Library/Developer/Xcode/iOS\ DeviceSupport/
