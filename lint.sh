#!/bin/sh

MAX_LINE_LENGTH=120

prog_name=$(basename $0)
  
sub_help(){
    echo "Usage: $prog_name [subcommand]\n"
    echo "Subcommands:"
    echo "    format   Format the code"
    echo "    verify   Verify formatting without making any changes"
    echo ""
}

sub_verify() {
    flake8 \
    --max-line-length=$MAX_LINE_LENGTH \
    --ignore=F401,F403,F405 .
}

sub_format(){
    black --line-length $MAX_LINE_LENGTH .
    sub_verify
}
  
subcommand=$1
case $subcommand in
    "")
        sub_format
        ;;
    "-h" | "--help")
        sub_help
        ;;
    *)
        shift
        sub_${subcommand} $@
        if [ $? = 127 ]; then
            echo "Error: '$subcommand' is not a known subcommand." >&2
            echo "       Run '$prog_name --help' for a list of known subcommands." >&2
            exit 1
        fi
        ;;
esac
