from common import *
from enum import Enum, auto
from typing import TypeVar
from dataclasses import dataclass
from message_queue import *

# TODO add support for @Arusekk syntax trick
# TODO add to MessageFrameworkProcess possibility to add functions
# TODO add graph description
# TODO add clearing

class MessageFrameworkCommand():
    pass

class EndOfInput(MessageFrameworkCommand):
    pass

_MFVerificationDataType = MessageFrameworkCommand | RecordIntDict
T = TypeVar('T')


class MessageFrameworkProcess():
    """
    tb : TestbenchIO
        Method under test
    transformation_in : Callable
        Function used to transform incoming *verification* data
    transformation_out : Callable
        Function used to produce *verification* data for other testing processes
        using as arguments transformed input verification data and test data from
        tested method.
    checker : Callable
        Function to check correctness of test data from method using transformed
        input verification data.
    """
    def __init__(self,in_verif_data : MessageQueueInterface, out_verif_data : MessageQueueInterface, tb : Optional[TestbenchIO]):
        self.tb =tb
        self.in_verif_data = in_verif_data
        self.out_verif_data = out_verif_data

        self.passive = False
        self.transformation_in : Optional[Callable[[RecordIntDict],RecordIntDictRet]] = None
        self.transformation_out : Optional[Callable[[RecordIntDict, RecordIntDict],RecordIntDictRet]] = None
        self.prepare_send_data : Optional[Callable[[RecordIntDict],RecordIntDictRet]] = None
        self.checker : Optional[Callable[[RecordIntDict, RecordIntDict], None]] = None
        self.iteration_count : Optional[int] = None

    def _get_test_data(self, arg_to_send : RecordIntDict):
        if self.tb is not None:
            out_data = yield from self.tb.call(arg_to_send)
            return out_data
        return {}

    def _get_verifcation_input(self) -> TestGen[_MFVerificationDataType]:
        while not self.in_verif_data:
            yield
        return self.in_verif_data.pop()

    def _transform_input(self, data : RecordIntDict) -> RecordIntDictRet:
        if self.transformation_in is not None:
            return self.transformation_in(data)
        else:
            return data

    def _transform_output(self, verification_input, test_data):
        if self.transformation_out is not None:
            return self.transformation_out(verification_input, test_data)
        else:
            return {}

    def _get_send_data(self, verif_input):
        if self.prepare_send_data is None:
            return {}
        else:
            return self.prepare_send_data(verif_input)

    def _call_checker(self, verification_input, test_data):
        if self.checker is None:
            return None
        self.checker(verification_input, test_data)

    def generate_wrapper(self):
        def f():
            if self.passive:
                yield Passive()
            i = 0
            while self.iteration_count is None or (i < self.iteration_count):
                i+=1
                raw_verif_input = yield from self._get_verifcation_input()
                if isinstance(raw_verif_input, MessageFrameworkCommand):
                    if isinstance(raw_verif_input, EndOfInput):
                        break
                    raise RuntimeError(f"Got unknown MessageFrameworkCommand: {raw_verif_input}")
                transformed_verif_input = self._transform_input(raw_verif_input)
                send_data = self._get_send_data(transformed_verif_input)
                test_data = yield from self._get_test_data(send_data)
                self._call_checker(transformed_verif_input, test_data)
                transformed_output = self._transform_output(transformed_verif_input, test_data)
                self.out_verif_data.append(transformed_output)
        return f


class TestCaseWithMessageFramework(TestCaseWithSimulator):

    @dataclass
    class ProcessEntry():
        proc : MessageFrameworkProcess
        in_combiner : MessageQueueCombiner
        out_broadcaster : MessageQueueBroadcaster

    def __init__(self):
        super().__init__()
        self.processes : dict[str, TestCaseWithMessageFramework.ProcessEntry] = {}

    def register_process(self, name : str, tb : Optional[TestbenchIO]) -> MessageFrameworkProcess:
        combiner = MessageQueueCombiner()
        broadcaster = MessageQueueBroadcaster()
        proc = MessageFrameworkProcess(combiner, broadcaster, tb)
        self.processes[name] = TestCaseWithMessageFramework.ProcessEntry(proc, combiner, broadcaster)
        return proc

    def add_data_flow(self, from_name : str, to_name : str, *, filter : Optional[Callable[..., Any]] = None):
        msg_q = MessageQueue()

        proc_from = self.processes[from_name]
        proc_from.out_broadcaster.add_destination(msg_q)

        proc_to = self.processes[to_name]
        proc_to.in_combiner.add_source(msg_q)
