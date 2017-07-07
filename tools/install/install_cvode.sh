# -----------------------------------------------------------------------------
#
# Copyright (c) 2017 Sam Cox, Roberto Sommariva
#
# This file is part of the AtChem2 software package.
#
# This file is covered by the MIT license which can be found in the file
# LICENSE.md at the top level of the AtChem2 distribution.
#
# -----------------------------------------------------------------------------

#!/bin/sh

# This script downloads and installs CVODE 2.9.0 into the directory
# given by input argument $1. Using the fortran compiler executable
# given by input argument $2.
##
# Example usage:
#   ./install_cvode.sh /path/to/install/directory /path/to/fortran/compiler

# Query the operating system, and set LAPACK_LIBS to the default location
OS=$(uname -s)
if [ "$OS" == 'Darwin' ]; then
  LAPACK_LIBS=/usr/lib/liblapack.dylib:/usr/lib/libblas.dylib
else
  LAPACK_LIBS=/usr/lib/liblapack.so:/usr/lib/libblas.so
fi
# Ensure a first argument is provided, and that it is an existing directory
if [ -z "$1" ] ; then
  echo "Please provide an argument to tools/install/install_cvode_osx.sh"
  echo "Example usage: ./install_cvode_osx.sh /path/to/install/directory /path/to/fortran/compiler"
  exit 1
elif [ ! -d "$1" ]; then
  echo "$1 is not a directory"
  echo "Example usage: ./install_cvode_osx.sh /path/to/install/directory /path/to/fortran/compiler"
  exit 1
fi
# If a second argument is provided, check that it is an existing file.
# If it's not provided, then give it a default, so long as that also
# exists.
if [ -z "$2" ] ; then
  if [ -f /usr/bin/gfortran ] ; then
    echo "Default fortran compiler executable selected. To choose another compiler, provide this as a second argument."
    echo "Example usage: ./install_cvode_osx.sh /path/to/install/directory /path/to/fortran/compiler"
  else
    echo "Default fortran compiler 'gfortran' executable selected, but this is not a valid filename."
    echo "Example usage: ./install_cvode_osx.sh /path/to/install/directory /path/to/fortran/compiler"
    exit 1
  fi
  FORT_COMP=/usr/bin/gfortran
else
  FORT_COMP=$2
  if [ ! -f "$2" ] ; then
    echo $2 " selected as fortran compiler, but this is not a valid filename."
    echo "Example usage: ./install_cvode_osx.sh /path/to/install/directory /path/to/fortran/compiler"
    exit 1
  fi
fi
# Move to provided directory
cd $1

wget https://computation.llnl.gov/projects/sundials/download/cvode-2.9.0.tar.gz
tar -zxf cvode-2.9.0.tar.gz
rm cvode-2.9.0.tar.gz
cd cvode-2.9.0/

mkdir build
cd build

cmake -DCMAKE_INSTALL_PREFIX=$1/cvode \
    -DCMAKE_C_COMPILER:FILEPATH=gcc \
    -DCMAKE_Fortran_COMPILER=$FORT_COMP \
    -DLAPACK_ENABLE:BOOL=ON \
    -DLAPACK_LIBRARIES=$LAPACK_LIBS \
    -DFCMIX_ENABLE:BOOL=ON \
    -DEXAMPLES_ENABLE:BOOL=OFF \
    -DCMAKE_MACOSX_RPATH:BOOL=ON \
    ..
make -j8
make install
