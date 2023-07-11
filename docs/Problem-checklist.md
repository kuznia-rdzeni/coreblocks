# Problem checklist

If something doesn't work and you're puzzled as to why - go through this checklist to see if any of these points apply in your case:

1. Make sure that you use `yield from` when calling generator functions in tests - e.g. `TestbenchIO` functions (notable exception: `yield Settle()` instead of `yield from Settle()`)

2. If a signal has an unexpected value in tests try adding `yield Settle()` right before you read it.

3. Make sure you don't do `.eq` on two records with different layouts. Use `assign` from `coreblocks.utils` instead.

4. Make sure all amaranth statements are added to some domain.

5. Check if your code doesn't have any combinational loops - especially if your simulation hangs.

6. Check that you don't use repeatedly any methods/transactions inside `condition` that use `condition` themselves. This leads to exponential complexity.


Please extend this list if you spot yourself doing an easy-to-fix mistake.
