import os
import logging

import riscof.utils as utils
from riscof.pluginTemplate import pluginTemplate

logger = logging.getLogger()


# This is a slightly modified default configuration for RISCOF DUT
# Changes:
# * adapt to other toolchain and run scripts
# * produce two makefiles instead of one
# * always generate all makefiles and just skip execution on target_run=0 option


class coreblocks(pluginTemplate):  # noqa: N801
    __model__ = "coreblocks"

    __version__ = "XXX"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        config = kwargs.get("config")

        # If the config node for this DUT is missing or empty. Raise an error. At minimum we need
        # the paths to the ispec and pspec files
        if config is None:
            print("Please enter input file paths in configuration.")
            raise SystemExit(1)

        # In case of an RTL based DUT, this would be point to the final binary executable of your
        # test-bench produced by a simulator (like verilator, vcs, incisive, etc). In case of an iss or
        # emulator, this variable could point to where the iss binary is located. If 'PATH variable
        # is missing in the config.ini we can hardcode the alternate here.
        # temporary!
        coreblocks_path = config["PATH"] if "PATH" in config else "coreblocks"
        self.dut_exe = "python3 " + os.path.join(coreblocks_path, "scripts", "run_signature.py")
        self.dut_exe += " -b cocotb"

        # Number of parallel jobs that can be spawned off by RISCOF
        # for various actions performed in later functions, specifically to run the tests in
        # parallel on the DUT executable. Can also be used in the build function if required.
        self.num_jobs = str(config["jobs"] if "jobs" in config else 1)

        # Path to the directory where this python file is located. Collect it from the config.ini
        self.pluginpath = os.path.abspath(config["pluginpath"])

        # Collect the paths to the  riscv-config absed ISA and platform yaml files. One can choose
        # to hardcode these here itself instead of picking it from the config.ini file.
        self.isa_spec = os.path.abspath(config["ispec"])
        self.platform_spec = os.path.abspath(config["pspec"])

        # We capture if the user would like the run the tests on the target or
        # not. If you are interested in just compiling the tests and not running
        # them on the target, then following variable should be set to False
        if "target_run" in config and config["target_run"] == "0":
            self.target_run = False
        else:
            self.target_run = True

    def initialise(self, suite, work_dir, archtest_env):
        # capture the working directory. Any artifacts that the DUT creates should be placed in this
        # directory. Other artifacts from the framework and the Reference plugin will also be placed
        # here itself.
        self.work_dir = work_dir

        # capture the architectural test-suite directory.
        self.suite_dir = suite

        # Note the march is not hardwired here, because it will change for each
        # test. Similarly the output elf name and compile macros will be assigned later in the
        # runTests function
        # Change: Always use riscv64
        self.compile_cmd = (
            "riscv64-unknown-elf-gcc -march={0} \
         -static -mcmodel=medany -fvisibility=hidden -nostdlib -nostartfiles -g\
         -T "
            + self.pluginpath
            + "/env/link.ld\
         -I "
            + self.pluginpath
            + "/env/\
         -I "
            + archtest_env
            + " {2} -o {3} {4}"
        )

        # add more utility snippets here

    def build(self, isa_yaml, platform_yaml):
        # load the isa yaml as a dictionary in python.
        ispec = utils.load_yaml(isa_yaml)["hart0"]

        # capture the XLEN value by picking the max value in 'supported_xlen' field of isa yaml. This
        # will be useful in setting integer value in the compiler string (if not already hardcoded);
        self.xlen = "64" if 64 in ispec["supported_xlen"] else "32"

        self.isa = ispec["ISA"].lower()

        # The following assumes you are using the riscv-gcc toolchain.
        self.compile_cmd = self.compile_cmd + " -mabi=" + ("lp64 " if 64 in ispec["supported_xlen"] else "ilp32 ")

    def runTests(self, testList):  # noqa: N802 N803
        # Delete Makefile if it already exists.
        if os.path.exists(self.work_dir + "/Makefile." + self.name[:-1]):
            os.remove(self.work_dir + "/Makefile." + self.name[:-1])

        # For coreblocks generate two makefiles - one for build and one for run.
        # It is needed because of use of separate containers, and allows caching built tests
        make_build = utils.makeUtil(makefilePath=os.path.join(self.work_dir, "Makefile.build-" + self.name[:-1]))
        make_run = utils.makeUtil(makefilePath=os.path.join(self.work_dir, "Makefile.run-" + self.name[:-1]))

        # set the make command that will be used. The num_jobs parameter was set in the __init__
        # function earlier
        make_build.makeCommand = "make -k -j" + self.num_jobs
        make_run.makeCommand = "make -k -j" + self.num_jobs

        # we will iterate over each entry in the testList. Each entry node will be refered to by the
        # variable testname.
        for testname in testList:
            # for each testname we get all its fields (as described by the testList format)
            testentry = testList[testname]

            # we capture the path to the assembly file of this test
            test = testentry["test_path"]

            # capture the directory where the artifacts of this test will be dumped/created. RISCOF is
            # going to look into this directory for the signature files
            test_dir = testentry["work_dir"]

            # name of the elf file after compilation of the test
            elf = testname + ".elf"

            # name of the signature file as per requirement of RISCOF. RISCOF expects the signature to
            # be named as DUT-<dut-name>.signature. The below variable creates an absolute path of
            # signature file.
            sig_file = os.path.join(test_dir, self.name[:-1] + ".signature")

            # for each test there are specific compile macros that need to be enabled. The macros in
            # the testList node only contain the macros/values. For the gcc toolchain we need to
            # prefix with "-D". The following does precisely that.
            compile_macros = " -D" + " -D".join(testentry["macros"])

            # substitute all variables in the compile command that we created in the initialize
            # function
            buildcmd = self.compile_cmd.format(testentry["isa"].lower(), self.xlen, test, elf, compile_macros)

            simcmd = self.dut_exe + " -o={0} {1}".format(sig_file, elf)

            # concatenate all commands that need to be executed within a make-target.
            target_build = "cd {0}; {1};".format(testentry["work_dir"], buildcmd)
            target_run = "mkdir -p {0}; cd {1}; {2};".format(testentry["work_dir"], self.work_dir, simcmd)

            # for some reason C extension enables priv tests. Disable them for now. Not ready yet!
            if "privilege" in test_dir:
                print("SKIP generating", test_dir, test)
                continue

            # create a target. The makeutil will create a target with the name "TARGET<num>" where num
            # starts from 0 and increments automatically for each new target that is added
            make_build.add_target(target_build)
            make_run.add_target(target_run)

        if self.target_run:
            # once the make-targets are done and the makefile has been created, run all the targets in
            # parallel using the make command set above.
            make_build.execute_all(self.work_dir)
            make_run.execute_all(self.work_dir)
