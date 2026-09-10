"""Learning: the state description, the deck-pair sampler, and the training loop around them.

Everything in this package that a self-play game touches is pure Python and stdlib only, because
the same code runs in the browser under Pyodide. Training tools that never run in the browser may
use numpy; nothing here does.
"""
