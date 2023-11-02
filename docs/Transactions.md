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
        m = TModule()

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

### Implementing methods

As methods are used as a way to communicate with other `Elaboratable`s, they are typically declared in the `Elaboratable`'s constructor, and then defined in the `elaborate` method:

```python
class MyOtherThing(Elaboratable):
    def __init__(self):
        ...

        # Declaration of the method.
        # The i/o parameters pass the format of method argument/result as Amaranth layouts.
        # Both parameters are optional.

        self.my_method = Method(i=input_layout, o=output_layout)

        ...

    def elaborate(self, platform):
        # A TModule needs to be used instead of an Amaranth module

        m = TModule()

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
    def __init__(self, method: Method):
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

### Method argument passing conventions

Even though method arguments are Amaranth records, their use can be avoided in many cases, which results in cleaner code.
Suppose we have the following layout, which is an input layout for a method called `method`:

```python
layout = [("foo", 1), ("bar", 32)]
method = Method(input_layout=layout)
```

The method can be called in multiple ways.
The cleanest and recommended way is to pass each record field using a keyword argument:

```python
method(m, foo=foo_expr, bar=bar_expr)
```

Another way is to pass the arguments using a `dict`:

```python
method(m, {'foo': foo_expr, 'bar': bar_expr})
```

Finally, one can directly pass an Amaranth record:

```python
rec = Record(layout)
m.d.comb += rec.foo.eq(foo_expr)
m.d.comb += rec.bar.eq(bar_expr)
method(m, rec)
```

The `dict` convention can be used recursively when layouts are nested.
Take the following definitions:

```python
layout2 = [("foobar", layout), ("baz", 42)]
method2 = Method(input_layout=layout2)
```

One can then pass the arguments using `dict`s in following ways:

```python
# the preferred way
method2(m, foobar={'foo': foo_expr, 'bar': bar_expr}, baz=baz_expr)

# the alternative way
method2(m, {'foobar': {'foo': foo_expr, 'bar': bar_expr}, 'baz': baz_expr})
```

### Method definition conventions

When defining methods, two conventions can be used.
The cleanest and recommended way is to create an argument for each record field:

```python
@def_method(m, method)
def _(foo: Value, bar: Value):
    ...
```

The other is to receive the argument record directly. The `arg` name is required:

```python
def_method(m, method)
def _(arg: Record):
    ...
```

### Method return value conventions

The `dict` syntax can be used for returning values from methods.
Take the following method declaration:

```python
method3 = Method(input_layout=layout, output_layout=layout2)
```

One can then define this method as follows:

```python
@def_method(m, method3)
def _(foo: Value, bar: Value):
    return {{'foo': foo, 'bar': foo + bar}, 'baz': foo - bar}
```

### Readiness signals

If a transaction is not always ready for execution (for example, because of the dependence on some resource), a `request` parameter should be used.
An Amaranth single-bit expression should be passed.
When the `request` parameter is not passed, the transaction is always requesting execution.

```python
        with Transaction().body(m, request=expr):
```

Methods have a similar mechanism, which uses the `ready` parameter on `def_method`:

```python
        @def_method(m, self.my_method, ready=expr)
        def _(arg):
            ...
```

The `request` signal typically should only depend on the internal state of an `Elaboratable`.
Other dependencies risk introducing combinational loops.
In certain occasions, it is possible to relax this requirement; see e.g. [Scheduling order](#scheduling-order).

## The library

The transaction framework is designed to facilitate code re-use.
It includes a library, which contains `Elaboratable`s providing useful methods and transactions.
The most useful ones are:

* `ConnectTrans`, for connecting two methods together with a transaction.
* `FIFO`, for queues accessed with two methods, `read` and `write`.
* `Adapter` and `AdapterTrans`, for communicating with transactions and methods from plain Amaranth code.
  These are very useful in testbenches.

## Advanced concepts

### Special combinational domains

Transactron defines its own variant of Amaranth modules, called `TModule`.
Its role is to allow to improve circuit performance by omitting unneeded multiplexers in combinational circuits.
This is done by adding two additional, special combinatorial domains, `av_comb` and `top_comb`.

Statements added to the `av_comb` domain (the "avoiding" domain) are not executed when under a false `m.If`, but are executed when under a false `m.AvoidedIf`.
Transaction and method bodies are internally guarded by an `m.AvoidedIf` with the transaction `grant` or method `run` signal.
Therefore combinational assignments added to `av_comb` work even if the transaction or method definition containing the assignments are not running.
Because combinational signals usually don't induce state changes, this is often safe to do and improves performance.

Statements added to the `top_comb` domain are always executed, even if the statement is under false conditions (including `m.If`, `m.Switch` etc.).
This allows for cleaner code, as combinational assignments which logically belong to some case, but aren't actually required to be there, can be as performant as if they were manually moved to the top level.

An important caveat of the special domains is that, just like with normal domains, a signal assigned in one of them cannot be assigned in others.

### Scheduling order

When writing multiple methods and transactions in the same `Elaboratable`, sometimes some dependency between them needs to exist.
For example, in the `Forwarder` module in the library, forwarding can take place only if both `read` and `write` are executed simultaneously.
This requirement is handled by making the the `read` method's readiness depend on the execution of the `write` method.
If the `read` method was considered for execution before `write`, this would introduce a combinational loop into the circuit.
In order to avoid such issues, one can require a certain scheduling order between methods and transactions.

`Method` and `Transaction` objects include a `schedule_before` method.
Its only argument is another `Method` or `Transaction`, which will be scheduled after the first one:

```python
first_t_or_m.schedule_before(other_t_or_m)
```

Internally, scheduling orders exist only on transactions.
If a scheduling order is added to a `Method`, it is lifted to the transaction level.
For example, if `first_m` is scheduled before `other_t`, and is called by `t1` and `t2`, the added scheduling orderings will be the same as if the following calls were made:

```python
t1.schedule_before(other_t)
t2.schedule_before(other_t)
```

### Conflicts

In some situations it might be useful to make some methods or transactions mutually exclusive with others.
Two conflicting transactions or methods can't execute simultaneously: only one or the other runs in a given clock cycle.

Conflicts are defined similarly to scheduling orders:

```python
first_t_or_m.add_conflict(other_t_or_m)
```

Conflicts are lifted to the transaction level, just like scheduling orders.

The `add_conflict` method has an optional argument `priority`, which allows to define a scheduling order between conflicting transactions or methods.
Possible values are `Priority.LEFT`, `Priority.RIGHT` and `Priority.UNDEFINED` (the default).
For example, the following code adds a conflict with a scheduling order, where `first_m` is scheduled before `other_m`:

```python
first_m.add_conflict(other_m, priority = Priority.LEFT)
```

Scheduling conflicts come with a possible cost.
The conflicting transactions have a dependency in the transaction scheduler, which can increase the size and combinational delay of the scheduling circuit.
Therefore, use of this feature requires consideration.

### Transaction and method nesting

Transaction and method bodies can be nested. For example:

```python
with Transaction().body(m):
    # Transaction body.

    with Transaction().body(m):
        # Nested transaction body.
```

Nested transactions and methods can only run if the parent also runs.
The converse is not true: it is possible that only the parent runs, but the nested transaction or method doesn't (because of other limitations).
Nesting implies scheduling order: the nested transaction or method is considered for execution after the parent.
