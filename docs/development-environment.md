# Development environment

## Setting up

In order to prepare the development environment, please follow the steps below:

1. Install the Python 3.11 interpreter and pip package manager.
    * Optionally create a Python virtual environment with `python3 -m venv venv` in the project directory and activate it using generated script: `. venv/bin/activate`.
2. Install all required libraries with `pip3 install -r requirements-dev.txt`.
3. Install `riscv64-unknown-elf` binutils using your favourite package manager. On Debian-based distros the package is called `binutils-riscv64-unknown-elf`, on Arch-based - `riscv64-unknown-elf-binutils`.
4. Optionally, install all precommit hooks with `pre-commit install`. This will automatically run the linter before commits.

## Using scripts

The development environment contains a number of scripts which are run in CI, but are also intended for local use. They are:

### run\_tests.py

Runs the unit tests. By default, every available test is run. Tests from a specific file can be run using the following call (`test_transactions` is used as an example):

```
scripts/run_tests.py test_transactions
```

One can even run a specific test class from a file:

```
scripts/run_tests.py test_transactions.TestScheduler
```

Or a specific test method:

```
scripts/run_tests.py test_transactions.TestScheduler.test_single
```

The argument to `run_tests.py` is actually used to search within the full names of tests. The script runs all the tests which match the query. Thanks to this, if a given test class name is unique, just the class name can be used as an argument.

The `run_tests.py` script has the following options:

* `-l`, `--list` -- lists available tests. This option is helpful, e.g., to find a name of a test generated using the `parameterized` package.
* `-t`, `--trace` -- generates waveforms in the `vcd` format and `gtkw` files for the `gtkwave` tool. The files are saved in the `test/__traces__/` directory. Useful for debugging and test-driven development.
* `-p`, `--profile` -- generates Transactron execution profile information, which can then be read by the script `tprof.py`. The files are saved in the `test/__profile__/` directory. Useful for analyzing performance.
* `-v`, `--verbose` -- makes the test runner more verbose. It will, for example, print the names of all the tests being run.

### lint.sh

Checks the code formatting and typing. It should be run as follows:

```
scripts/lint.sh subcommand [filename...]
```

The following main subcommands are available:

* `format` -- reformats the code using `black`.
* `check_format` -- verifies code formatting using `black` and `flake8`.
* `check_types` -- verifies typing using `pyright`.
* `verify` -- runs all checks. The same set of checks is run in CI.

When confronted with `would reformat [filename]` message from `black` you may run:

```
black --diff [filename]
```
This way you may display the changes `black` would apply to `[filename]` if you chose the `format` option for `lint.sh` script. This may help you locate the formatting issues.

### core\_graph.py

Visualizes the core architecture as a graph. The script outputs a file in one of supported graph formats, which need to be passed to an appropriate tool to get a graph.

The `core_graph.py` script has the following options:

* `-p`, `--prune` -- removes disconnected nodes from the output graph.
* `-f FORMAT`, `--format FORMAT` -- selects the output format. Supported formats are `elk` (for [Eclipse Layout Kernel](https://www.eclipse.org/elk/)), `dot` (for [Graphviz](https://graphviz.org/)), `mermaid` (for [Mermaid](https://mermaid.js.org/)).

### build\_docs.sh

Generates local documentation using [Sphinx](https://www.sphinx-doc.org/). The generated HTML files are located in `build/html`.

### tprof.py

Processes Transactron profile files and presents them in a readable way.
To generate a profile file, the `run_tests.py` script should be used with the `--profile` option.
The `tprof.py` can then be run as follows:

```
scripts/tprof.py test/__profile__/profile_file.json
```

This displays the profile information about transactions by default.
For method profiles, one should use the `--mode=methods` option.

The columns have the following meaning:

* `name` -- the name of the transaction or method in question. The method names are displayed together with the containing module name to differentiate between identically named methods in different modules.
* `source location` -- the file and line where the transaction or method was declared. Used to further disambiguate transaction/methods.
* `locked` -- for methods, shows the number of cycles the method was locked by the caller (called with a false condition). For transactions, shows the number of cycles the transaction could run, but was forced to wait by another, conflicting, transaction.
* `run` -- shows the number of cycles the given method/transaction was running.

To display information about method calls, one can use the `--call-graph` option.
When displaying transaction profiles, this option produces a call graph. For each transaction, there is a tree of methods which are called by this transaction.
Counters presented in the tree shows information about the calls from the transaction in the root of the tree: if a method is also called by a different transaction, these calls are not counted.
When displaying method profiles, an inverted call graph is produced: the transactions are in the leaves, and the children nodes are the callers of the method in question.
In this mode, the `locked` field in the tree shows how many cycles a given method or transaction was responsible for locking the method in the root.

Other options of `tprof.py` are:

* `--sort` -- selects which column is used for sorting rows.
* `--filter-name` -- filters rows by name. Regular expressions can be used.
* `--filter-loc` -- filters rows by source locations. Regular expressions can be used.
