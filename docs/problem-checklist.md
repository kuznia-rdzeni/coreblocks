# Problem checklist

If something doesn't work and you're puzzled as to why - go through this checklist to see if any of these points apply in your case:

1. Make sure that you use `await` when calling async functions in tests - e.g. `TestbenchIO` functions.

2. Make sure you don't do `.eq` on two structures with different layouts. Use `assign` from `transactron.utils` instead.

3. Make sure all Amaranth statements are added to some domain.

4. Check if your code doesn't have any combinational loops - especially if your simulation hangs.

Please extend this list if you spot yourself doing an easy-to-fix mistake.
