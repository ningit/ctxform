#
# Entry point of the contextual formula tool
#

import os
import sys

import lark

from .logics import PARSER_CLASS, PROBLEM_CLASS
from .transform import InvalidFormulaError
from .printer import pretty_print


def _show_witnesses(witnesses):
	"""Show witnesses"""

	if not isinstance(witnesses, tuple):
		witnesses = (witnesses,)
		titles = ('',)
	else:
		titles = (' for L → R', ' for R → L')

	for contexts, title in zip(witnesses, titles):
		print(f'Witnesses{title}:')

		for k, (ctx_var, formula) in enumerate(contexts.items()):
			marker = ' └' if k == len(contexts) - 1 else ' ├'
			print(f'{marker} {ctx_var:3} ≔  {pretty_print(formula)}')


def _show_details(args, problem):
	"""Show details with verbosity enabled"""

	# Generated formula
	if args.v >= 2:
		print('Generated formula:')
		print('| L =', pretty_print(problem.gen_left))
		print('| R = ', pretty_print(problem.gen_right))
		print('| C = ', pretty_print(problem.gen_cond))

	# Simplified by Spot
	if args.v >= 1 and problem.HAS_SIMPLIFIED:
		print('Reduced Spot formula:')
		print('| L =', problem.spot_left)
		print('| R =', problem.spot_right)
		print('| C =', problem.spot_cond)


def _show_more_details(args, problem):
	"""Show details after solving with verbosity enabled"""

	if args.v >= 2 and problem.HAS_AUTOMATA:
		print('Automaton number of states:')
		print('| L =', problem.aut_left.num_states(), f'(!L = {problem.aut_not_left.num_states()})')
		print('| R =', problem.aut_right.num_states(), f'(!R = {problem.aut_not_right.num_states()})')
		print('| C =', problem.aut_cond.num_states())


def main():
	import argparse
	import readline

	argp = argparse.ArgumentParser(description='Check equivalence of formulas in LTL/CTL with contexts')
	argp.add_argument('-v', help='Increase verbosity', action='count', default=0)
	argp.add_argument('--any-formula', '-a',
	                  help='Check the equivalence for any formula, not just monotonic ones',
	                  action='store_true')
	argp.add_argument('--logic', '-l', help='Restrict to given logic (among ltl, bool, ctl)',
	                  choices=('ltl', 'bool', 'ctl'), default='ltl')
	argp.add_argument('--witness', '-w', help='Choose when to show the context witness of non-equivalence',
	                  choices=('yes', 'no', 'auto'), default='auto')
	argp.add_argument('--timeout', '-t', help='Timeout for CTL computations', type=int, default=20)
	argp.add_argument('--no-simplify', help='Avoid simplifying the canonical context',
	                  dest='simplify', action='store_false')
	argp.add_argument('--check-with-canonical', action='store_true',
	                  help='Check equivalence with the canonical instantiation too (disabled if witness is no)')

	args = argp.parse_args()

	# Select the parser and start the REPL
	parser = PARSER_CLASS[args.logic]()

	interactive = os.isatty(sys.stdin.fileno())
	prompt = '({})> ' if interactive else ''

	try:
		while True:
			# Ask for input
			left_str = input(prompt.format('L'))
			right_str = input(prompt.format('R'))

			try:
				# Try to parse the given formulas
				where = 'left'
				left = parser.parse(left_str)
				where = 'right'
				right = parser.parse(right_str)

			except lark.exceptions.LarkError as e:
				print(f'\x1b[1m{where} formula: \x1b[31merror:\x1b[0m {type(e).__name__}')
				continue

			# Print the given formulas for non-interactive input
			if not interactive:
				print(left_str, '\x1b[1m=?\x1b[0m', right_str)

			try:
				# Build and solve the problem for the given logic and formulas
				problem = PROBLEM_CLASS[args.logic](left, right, any_formula=args.any_formula)
				_show_details(args, problem)
				equiv, lnr, rnl = problem.solve(timeout=args.timeout)

			except InvalidFormulaError as nbe:
				print(f'\x1b[31merror:\x1b[0m {nbe}')
				continue

			_show_more_details(args, problem)

			if equiv:
				print('\x1b[1;33myes\x1b[0m')

			else:
				if lnr is None:
					msg = 'The first formula is covered by the second one (L → R).'
				elif rnl is None:
					msg = 'The second formula is covered by the first one (R → L).'
				else:
					msg = 'The two formulas are incomparable.'

				print(f'\x1b[1;31m{msg}\x1b[0m')

				if lnr:
					symbol = '├' if rnl else '└'
					print(f' {symbol} Not in R:', lnr)

				if rnl:
					print(' └ Not in L:', rnl)

			# Show witnesses and check equivalence using them
			if args.witness == 'auto' and not equiv or args.witness == 'yes':
				# We may want to check the result with the other method
				if args.check_with_canonical:
					witnesses, holds = problem.solve_with_context(simplify=args.simplify, timeout=args.timeout)
				else:
					witnesses, holds = problem.canonical_context(simplified=args.simplify), equiv

				if witnesses:
					_show_witnesses(witnesses)
					if holds != equiv:
						print(f'⚠️  The result with the substitution method ({holds}) does not coincide.')

	except (EOFError, KeyboardInterrupt):
		pass


if __name__ == '__main__':
	main()
