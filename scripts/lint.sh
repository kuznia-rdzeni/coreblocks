#!/bin/sh

MAX_LINE_LENGTH=120

prog_name=$(basename $0)

sub_help(){
    echo "Usage: $prog_name subcommand [filename ...]\n"
    echo "Subcommands:"
    echo "    format                Format the code"
    echo "    check_format          Verify formatting without making any changes"
    echo "    check_format_flake8   Verify formatting using flake8 only"
    echo "    check_format_black    Verify formatting using black only"
    echo "    check_types           Verify typing"
    echo "    verify                Run all checks"
    echo ""
}

sub_check_format_flake8() {
    python3 -m flake8 \
      --max-line-length=$MAX_LINE_LENGTH \
      --exclude ".env,.venv,env,venv,ENV,env.bak,venv.bak,ci,stubs" \
      --extend-ignore=F401,F403,F405,E203 $@
}

sub_check_format_black() {
    python3 -m black \
      --line-length $MAX_LINE_LENGTH \
      --extend-exclude "stubs|ci" $@ \
      --check $@
}

sub_check_format() {
    sub_check_format_flake8 $@ && sub_check_format_black $@
}

sub_format(){
    python3 -m black \
      --line-length $MAX_LINE_LENGTH \
      --extend-exclude "stubs|ci" $@

    sub_check_format_flake8 $@
}

sub_check_types(){
    python3 -m pyright
}

sub_verify(){
    sub_check_format $@ && sub_check_types
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
