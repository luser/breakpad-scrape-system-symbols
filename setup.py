#!/usr/bin/env python

from setuptools import setup, find_packages

setup(name='scrapesymbols',
      version='1.0',
      description='Breakpad symbol scraping',
      author='Ted Mielczarek',
      author_email='ted@mielczarek.org',
      url='https://github.com/luser/breakpad-scrape-system-symbols',
      packages=['scrapesymbols'],
      install_requires = ['requests', 'futures'],
      entry_points={
          'console_scripts': [
              'gathersymbols = scrapesymbols.gathersymbols:main'
          ]
      }
     )
