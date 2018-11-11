#!/bin/sh
set -e

virtualenv venv
venv/bin/python setup.py install
chmod +x dump_syms
