#
# Pretty printer of formulas from our internal format
#

import os
import sys

from .parser import Operator as Op

# Map each operator to its preferred symbol and priority
PRETTY_MAP = {
	Op.NEGATION: ('¬', 5),
	Op.DISJUNCTION: ('∨', 2),
	Op.CONJUNCTION: ('∧', 3),
	Op.IMPLICATION: ('→', 0),
	Op.EXCLUSION: ('⊕', 1),
	Op.EQUIVALENCE: ('↔', 0),
	Op.NEXT: ('X', 5),
	Op.EVENTUALLY: ('F', 5),
	Op.ALWAYS: ('G', 5),
	Op.UNTIL: ('U', 4),
	Op.WUNTIL: ('W', 4),
	Op.RELEASE: ('R', 4),
	Op.SRELEASE: ('M', 4),
	Op.EXISTS: ('E', 5),
	Op.FORALL: ('A', 5),
}


def colorizer(stype: Op, text: str):
	"""Colorize identifiers"""

	match stype:
		case Op.VAR:
			color = 33
		case Op.LIT:
			color = 34
		case _:  # stype == 'CTX':
			color = 35

	return f'\x1b[{color}m{text}\x1b[0m'


def html_colorizer(stype: Op, text: str):
	"""Colorize identifiers in HTML"""

	match stype:
		case Op.VAR:
			color = 'green'
		case Op.LIT:
			color = 'blue'
		case _:  # stype == 'CTX':
			color = 'magenta'

	return f'<span style="color: {color};">{text}</span>'


def no_colorizer(_, text: str):
	"""Keep identifiers are is"""

	return text


# Default colorizer depends on whether the output stream is a TTY
DEFAULT_COLORIZER = colorizer if os.isatty(sys.stdout.fileno()) else no_colorizer


def _put_parens(pair, priority):
	"""Auxiliary function to put parentheses"""

	# The pair contains the symbol and its priority
	symbol, sprio = pair

	return f'({symbol})' if sprio <= priority else symbol


def _pretty_print(ast, colorizer):
	"""Pretty print the formula AST"""

	head, *args = ast

	match head:
		case Op.VAR:
			return colorizer(head, args[0]), 6

		case Op.LIT:
			return colorizer(head, 'true' if args[0] else 'false'), 6

		case Op.CTX:
			return f'{colorizer(head, args[0])}[{_pretty_print(args[1], colorizer)[0]}]', 6

		case Op.HOLE:
			return '🕳', 6

	# Symbol and priority of this operator
	symbol, prio = PRETTY_MAP[head]

	pp_args = [_put_parens(_pretty_print(arg, colorizer), prio) for arg in args]

	return f'{symbol}{pp_args[0]}' if len(args) == 1 else f' {symbol} '.join(pp_args), prio


def pretty_print(ast, color=True):
	"""Pretty print a formula"""

	return _pretty_print(ast, (DEFAULT_COLORIZER if color else no_colorizer) if isinstance(color, bool) else color)[0]


def _put_mlparens(pair, priority):
	"""Auxiliary function to put parentheses in MathML"""

	symbol, sprio = pair

	return f'<mrow><mo>(</mo>{symbol}<mo>)</mo></mrow>' if sprio <= priority else symbol


def _mathml_print(ast):
	"""Pretty print to MathML"""

	head, *args = ast

	match head:
		case Op.VAR:
			return f'<mi class="math-var">{args[0]}</mi>', 6

		case Op.LIT:
			value = 'true' if args[0] else 'false'
			return f'<mi class="math-lit">{value}</mi>', 6

		case Op.CTX:
			return f'<mi class="math-ctx">{args[0]}</mi><mo>[</mo>{_mathml_print(args[1])[0]}<mo>]</mo>', 6

		case Op.HOLE:
			return '<mi>🕳</mi>', 6

	# Symbol and priority of this operator
	symbol, prio = PRETTY_MAP[head]
	css_class = ' class="tempop"' if symbol.isalpha() else ''
	if symbol in 'GFX':
		css_class += ' lspace="0"'

	pp_args = [_put_mlparens(_mathml_print(arg), prio) for arg in args]

	return (f'<mo{css_class}>{symbol}</mo> {pp_args[0]}' if len(args) == 1
	        else f'<mo{css_class}>{symbol}</mo>'.join(pp_args), prio)


def mathml_print(ast):
	"""Pretty print to MathML"""

	return f'<math><mrow>{_mathml_print(ast)[0]}</mrow></math>'
