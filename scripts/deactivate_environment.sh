#!/bin/sh

if [ $COREBLOCKS_ENV == "active" ]; then

    # Unset all the paths
    unset MAIN_DIR
    unset SCRIPTS_PATH

    # Deactivate virtualenv
    if [ $VIRTUAL_ENV ]; then
        deactivate
    fi

    unset COREBLOCKS_ENV
fi
