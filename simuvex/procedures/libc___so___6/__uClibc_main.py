import simuvex
from ..libc___so___6.__libc_start_main import __libc_start_main as fucker

######################################
# __uClibc_main
######################################
class __uClibc_main(simuvex.SimProcedure):
    ADDS_EXITS = True

    # This is called "fucker" cause otherwise the double underscores cause
    # python to name-mangle and everything gets fucked.
    __init__ = fucker.__init__.__func__
