from setuptools import setup, find_packages
import sys
import os


here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.rst')).read()

version = '0.0.2rc0'

install_requires = ['pycrypto', 'sphinx', 'termcolor']
packages_list = ['documenter']


setup(name='documenter',
      version=version,
      description="A helper package to publish documentation.",
      long_description=README,
      classifiers=['Development Status :: 3 - Alpha',
                   'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
                   'Operating System :: OS Independent',
                   'Topic :: Software Development :: Documentation'],
      keywords=['documentation', 'sphinx', 'github'],
      author="Sylvain Arreckx",
      author_email="sylvain.arreckx@gmail.com",
      url='https://github.com/syarra/Documenter.py',
      license="GPL v3",
      package_dir={"documenter": "documenter"},
      packages=packages_list,
      zip_safe=False,
      install_requires=install_requires,
      tests_require=['pytest'],
      setup_requires=['pytest-runner'],)
