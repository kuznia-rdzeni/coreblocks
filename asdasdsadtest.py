from enum import IntFlag, auto, Enum
from typing_extensions import override
from typing import Type

class DynamicIntFlag(IntFlag):
    @classmethod
    def find(cls, name):
        if hasattr(cls, name):
            return cls[name]
        return -1
    
    def __getitem__(self, name):
        print(name)
        return 0
        return self.find(name)

def create_flags(names) -> DynamicIntFlag:
    # create a new subclass of IntFlag with auto-generated values
    flags = IntFlag('Flags', {name: auto() for name in names})

    return flags

# example usage
names = ['A', 'B', 'C']
flags = create_flags(names)

# flags is now an IntFlag object with auto-generated values for A, B, and C
"""
print(int(flags.find("A")))  # prints 1
print(int(flags.find("B")))  # prints 2
print(int(flags.find("C")))  # prints 4
print(hasattr(flags, 'D'))  # prints 4
print(flags.find('D'))  # prints 4
"""

def find(flags, name):
    if hasattr(flags, name):
        return flags[name]
    return -1

print(find(flags, 'A'))