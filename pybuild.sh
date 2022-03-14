#!/bin/bash

################################################################################
# help                                                                         #
################################################################################
function print_help() {
    # Display Help
    echo "Build script for keopscore/pykeops packages."
    echo
    echo "Usage: $0 [option...]"
    echo
    echo "   -h     Print the help"
    echo "   -l     Build in local mode (without hard-coded keopscore version requirement in pykeops)"
    echo "   -v     Verbose mode"
    echo
    echo "Note: by default, the keopscore version requirement is hard-coded in pykeops."
    echo
    exit 1
}

################################################################################
# utils                                                                        #
################################################################################

# log with verbosity management
function logging() {
    if [[ ${PYBUILD_VERBOSE} == 1 ]]; then
        echo -e $1
    fi
}

################################################################################
# process script options                                                       #
################################################################################

# default options
LOCAL_PYBUILD=0
PYBUILD_VERBOSE=0

# Get the options
while getopts 'hlv' option; do
    case $option in
        h) # display Help
            print_help
            ;;
        l) # local build (no hard-coded keopscore version requirements)
            LOCAL_PYBUILD=1
            logging "## local build (keopscore version requirements is NOT hard-coded in pykeops)"
            ;;
        v) # enable verbosity
            PYBUILD_VERBOSE=1
            logging "## verbose mode"
            ;;
        \?) # Invalid option
            echo "Error: Invalid option"
            exit 1
            ;;
    esac
done

################################################################################
# script setup                                                                 #
################################################################################

# project root directory
PROJDIR=$(git rev-parse --show-toplevel)

# python exec
PYTHON="python3"

# python environment for build
BUILD_VENV=${PROJDIR}/.build_venv

# python build requirements (names of packages to be installed with pip)
BUILD_REQ="pip build pyclean"

# KeOps current version
VERSION=$(cat ./keops_version)

# setup config file
CFG=${PROJDIR}/pykeops/setup.cfg

# requirements
REQ="[options]\ninstall_requires =\n numpy\n pybind11\n keopscore == \"${VERSION}\""

################################################################################
# prepare build (and cleanup after)                                            #
################################################################################

# prepare setup and clean up on exit
function prepare_setup() {
    logging "-- Preparing setup..."
    # hard-code keopscore requirements
    if [[ ! ${LOCAL_PYBUILD} == 1 ]]; then
        echo -e ${REQ} > ${CFG}
    fi
}

function cleanup_setup() {
    logging "-- Cleaning up setup..."
    rm -f ${CFG}
}

prepare_setup
trap cleanup_setup EXIT

################################################################################
# prepare python environment                                                   #
################################################################################

logging "-- Preparing python environment for build..."

if [[ -d ${BUILD_VENV} ]]; then rm -rf ${BUILD_VENV}; fi
${PYTHON} -m venv ${BUILD_VENV}
source ${BUILD_VENV}/bin/activate

pip install -U ${BUILD_REQ}

################################################################################
# clean before build                                                           #
################################################################################

logging "-- Cleaning Python sources before build..."

# remove __pycache__ *.pyc
pyclean ${PROJDIR}/keopscore
pyclean ${PROJDIR}/pykeops

################################################################################
# build keopscore                                                              #
################################################################################

logging "-- Building keopscore..."

${PYTHON} -m build --sdist --outdir ${PROJDIR}/build/dist ${PROJDIR}/keopscore


################################################################################
# build pykeops                                                                #
################################################################################

logging "-- Building pykeops..."

${PYTHON} -m build --sdist --outdir ${PROJDIR}/build/dist ${PROJDIR}/pykeops
