#!/bin/sh

# Skip sourcing if environemnt already active
if [ COREBLOCKS_ENV != "active" ]; then

    # Set all the paths
    MAIN_DIR=${PWD%%coreblocks*}coreblocks/
    SCRIPTS_PATH=$MAIN_DIR/scripts

    # Set python venv if present
    if [ ! $VIRTUAL_ENV ]; then
        VENV_DIRS=(".venv" "venv" "env" ".env" "ENV")
        for file in ${VENV_DIRS[*]}; do
            if [ -d $MAIN_DIR$file ]; then
                . $MAIN_DIR$file/bin/activate &> /dev/null
                break
            fi
        done
        unset VENV_DIRS
    fi

    COREBLOCKS_ENV="active"
fi
