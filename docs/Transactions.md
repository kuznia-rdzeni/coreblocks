# Documentation for Coreblocks transaction framework

## Introduction

Coreblocks utilizes a transaction framework for modularizing the design.
It is inspired by the [Bluespec](http://bluespec.com/) programming language (see: [Bluespec wiki](http://wiki.bluespec.com/), [Bluespec compiler](https://github.com/B-Lang-org/bsc)).

The basic idea is to interface hardware modules using _transactions_ and _methods_.
A transaction is a state-changing operation performed by the hardware in a single clock cycle.
Transactions are atomic: in a given clock cycle, a transaction either executes in its entriety, or not at all.
A transaction is executed only if it is ready for execution and it does not _conflict_ with another transaction scheduled for execution in the same clock cycle.

A transaction defined in a given hardware module can depend on other hardware modules via the use of methods.
A method can be _called_ by a transaction or by other methods.
Execution of methods is directly linked to the execution of transactions: a method only executes if some transaction which calls the method (directly or indirectly, via other methods) is executed.
If multiple transactions try to call the same method in the same clock cycle, the transactions conflict, and only one of them is executed.
In this way, access to methods is coordinated via the transaction system to avoid conflicts.

Methods can communicate with their callers in both directions: from caller to method and back.
The communication is structured using Amaranth records.

## Basic usage

### Implementing transactions

The simplest way to implement a transaction as a part of Amaranth `Elaboratable` is by using a `with` block:

```python
class MyThing(Elaboratable):
    ...

    def elaborate(self, platform):
        m = Module()

        ...

        with Transaction().body(m):
            # Operations conditioned on the transaction executing.
            # Including Amaranth assignments, like:

            m.d.comb += sig1.eq(expr1)
            m.d.sync += sig2.eq(expr2)

            # Method calls can also be used, like:

            result = self.method(m, arg_expr)

        ...

        return m
```

The transaction body `with` block works analogously to Amaranth's `with m.If():` blocks: the Amaranth assignments and method calls only "work" in clock cycles when the transaction is executed.
This is implemented in hardware via multiplexers.
Please remember that this is not a Python `if` statement -- the *Python code* inside the `with` block is always executed once.

If a transaction is not always ready for execution (for example, because of the dependence on some resource), a `request` parameter should be used. An Amaranth single-bit expression should be passed.

```python
        with Transaction().body(m, request=expr):
```

### Implementing methods

As methods are used as a way to communicate with other `Elaboratable`s, they are typically declared in the `Elaboratable`'s constructor, and then defined in the `elaborate` method:

```python
class MyOtherThing(Elaboratable):
    def __init__(self):
        ...

        # Declaration of the method.
        # The i/o parameters pass the format of method argument/result, as Amaranth layouts.
        # Both parameters are optional.

        self.my_method = Method(i=input_layout, o=output_layout)

        ...

    def elaborate(self, platform):
        m = Module()

        ...

        @def_method(m, self.my_method)
        def _(arg):
            # Operations conditioned on the method executing.
            # Including Amaranth assignments, like:

            m.d.comb += sig1.eq(expr1)
            m.d.sync += sig2.eq(expr2)

            # Method calls can also be used, like:

            result = self.other_method(m, arg_expr)

            # Method result should be returned:

            return ret_expr

        ...

        return m
```

The `def_method` technique presented above is a convenience syntax, but it works just like other Amaranth `with` blocks.
In particular, the *Python code* inside the unnamed `def` function is always executed once.

A method defined in one `Elaboratable` is usually passed to other `Elaboratable`s via constructor parameters.
For example, the `MyThing` constructor could be defined as follows.
Only methods should be passed around, not entire `Elaboratable`s!

```python
class MyThing(Elaboratable):
    def __init__(self, method):
        self.method = method

        ...

    ...
```

### Method or transaction?

Sometimes, there might be two alternative ways to implement some functionality:

* Using a transaction, which calls methods on other `Elaboratable`s.
* Using a method, which is called from other `Elaboratable`s.

Deciding on a best method is not always easy.
An important question to ask yourself is -- is this functionality something that runs independently from other things (not in lock-step)?
If so, maybe it should be a transaction.
Or is it something that is dependent on some external condition?
If so, maybe it should be a method.

If in doubt, methods are preferred.
This is because if a functionality is implemented as a method, and a transaction is needed, one can use a transaction which calls this method and does nothing else.
Such a transaction is included in the library -- it's named `AdapterTrans`.

## The library

The transaction framework is designed to facilitate code re-use.
It includes a library, which contains `Elaboratable`s providing useful methods and transactions.

TODO
