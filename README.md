# Equivalence checker for contextual formulas

This is an equivalence checker for contextual formulas in propositional logic, LTL, and CTL. Contextual formulas extend ordinary formulas with expressions *c*\[φ\], where *c* is a context variable and φ is a contextual formula. Contexts are ordinary formulas with a special variable \[\], the *hole*, and contextual formula is instantiated with a context for each context variable *c* by replacing *c*\[φ\] expressions with the context where the hole is in turn replaced by φ.  Two contextual formulas are equivalent if all their instantiations are equivalent as ordinary formulas.

The tool's output indicates whether the equivalence holds, one formula implies the other, or they are unrelated. When there is no equivalence, a counterexample is obtained and consists of a context (simplified from the canonical context in the reference) and a valuation or counterexample trace for the propositional variables. Satisfiability and validity can be checked using the constant formulas `true` and `false`.


Usage
-----

The command `python -m ctxform` in the root directory will start a REPL prompt for the two formulas of the identity. By default, LTL formulas are expected, but a different logic can be chosen with the command-line argument `--logic name` (or `-l name`) where name is either `bool`, `ltl`, or `ctl`. The option `--any-formula` (or `-a`) drops the assumption that the contexts are monotonic, i.e., it check whether the contextual formula holds for any replacement without restrictions. Negation normal form is not required even without the `--any-formula` flag. Other options are listed with `--help`.

The syntax of formulas is that of Spot, as described in the document [*Spot's Temporal Logic Formulas*](https://spot.lre.epita.fr/tl.pdf) by Alexandre Duret-Lutz, extended with the `A` and `E` operators for CTL only.

The tool can also be used as a web interface with the command `python -m ctxform.service -s 8080`. This will start a web service on `http://localhost:8080/` that can be stopped with Ctrl+C.


Dependencies
------------

The tool requires Python 3.10 or a more recent version to run. Morever, it depends on the following packages:

* [`lark`](https://github.com/lark-parser/lark) (for parsing, can be installed with `pip install lark`).
* [`pysat`](https://pysathq.github.io/) (for propositional logic, can be install with `pip install python-sat`).
* [`spot`](https://spot.lre.epita.fr/) (for LTL, instructions to install are available in https://spot.lre.epita.fr/install.html).
* [`clt-sat`](https://github.com/nicolaprezza/CTLSAT) (for CTL, a single binary that can be built from source). Our took will look for the binary in the `bin` subdirectory of the current working directory. Some binaries are available in the release section of this repository.

For the web interface, [`tornado`](https://www.tornadoweb.org/) (which can be installed with `pip install tornado`) is also required.


Benchmarks
----------

The script `test.py` and the lists of formulas `formulas.toml` and `mutated_formulas.toml` have been used to test and benchmark the tool. Since some executions timeout and run out of memory, each equivalence is checked in a confined environment for which a Linux system with systemd is required. Moreover, systemd 255 or above is needed to obtain the memory usage peak, although the script can be run with an older version. The official Python bindings for D-Bus are used to communicate with systemd (usually a package named `python3-dbus` or `dbus-python` in the Linux distribution repositories).

Time and memory bounds can be adjusted with `--timeout` and `--memlimit`.


References
----------

* Javier Esparza, Rubén Rubio. [*Validity of contextual formulas*](https://doi.org/10.4230/LIPIcs.CONCUR.2024.11). CONCUR 2024. LIPIcs 311 (article 11). [Extended version](https://doi.org/10.48550/arXiv.2407.07759) on arXiv.
