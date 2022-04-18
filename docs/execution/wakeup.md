# Wakeup logic interface

## Overview

This is a generic interface of wakeup logic and it should be implemented by each wakeup block.

Wakeup block should verify if there is an instruction which is ready to execute. If yes, it should select it and
dispatch it to FU.


## Internal data

They are *implementation defined*. Possible implementations: `CIRC`, `RAND`.


## Interface

### Insert new instruction

Ready when:
- *implementation defined*

Input:
- `position` - position in the RS to which new instruction is going to be inserted
- `start` - signal to start operation

Output:
- *null*

Side effects:
- *implementation defined*
