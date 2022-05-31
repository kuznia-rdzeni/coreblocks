#!/bin/sh

MAX_LINE_LENGTH=120

prog_name=$(basename $0)

sub_help(){
    echo "Usage: $prog_name subcommand [filename ...]\n"
    echo "Subcommands:"
    echo "    format   Format the code"
    echo "    verify   Verify formatting without making any changes"
    echo ""
}

sub_verify_flake8() {
    python3 -m flake8 \
      --max-line-length=$MAX_LINE_LENGTH \
      --exclude ".env,.venv,env,venv,ENV,env.bak,venv.bak" \
      --extend-ignore=F401,F403,F405,E203 $@
}

sub_verify_black() {
    python3 -m black \
        --line-length $MAX_LINE_LENGTH \
        --check $@
}

sub_verify() {
    sub_verify_black $@
    BLACK_RET=$?
    sub_verify_flake8 $@
    return $([[ $? == 0 ]] && [[ $BLACK_RET == 0 ]])
}

sub_format(){
    python3 -m black \
      --line-length $MAX_LINE_LENGTH $@

    sub_verify_flake8 $@
}

subcommand=$1
case $subcommand in
    "" | "-h" | "--help")
        sub_help
        ;;
    *)
        shift

        FILES=${@:-"."}
        sub_${subcommand} $FILES
        RETVAL=$?

        if [ $RETVAL = 127 ]; then
            echo "Error: '$subcommand' is not a known subcommand." >&2
            echo "       Run '$prog_name --help' for a list of known subcommands." >&2
        fi

        ;;
esac

RETVAL=${RETVAL:=$?}
exit $RETVAL
