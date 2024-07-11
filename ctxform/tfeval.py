#
# Evaluation of LTL (and Boolean) formulae
#

import itertools
import os
import sys

from .parser import Operator as Op
from .printer import pretty_print

# Color for tables
if os.isatty(sys.stdout.fileno()):
	V_ONE = '\x1b[33m1\x1b[0m'
	V_ZERO = '\x1b[31m0\x1b[0m'
	V_UNKNOWN = '\x1b[34m?\x1b[0m'

else:
	V_ONE = '1'
	V_ZERO = '0'
	V_UNKNOWN = '?'


def _negation(arg):
	return None if arg is None else not arg


def _conjunction(left, right):
	return None if (left is None or right is None) else (True if (left and right) else False)


def _disjunction(left, right):
	return True if (left or right) else (None if (left is None or right is None) else False)


def _implication(left, right):
	return True if (left is False or right) else (None if (left is None or right is None) else False)


def _equivalence(left, right):
	return None if (left is None or right is None) else (left == right)


def _exclusion(left, right):
	return None if (left is None or right is None) else (left != right)


# Trace in a valuation
Trace = tuple[tuple[bool | None, ...], tuple[bool | None, ...]]


class Valuation:
	"""Generalized valuation"""

	__slots__ = ('d', 'cycle_len', 'prefix_len')

	d: dict[str, Trace]
	cycle_len: int
	prefix_len: int

	def __init__(self, d: dict):
		self.d = d

		prefix, cycle = next(iter(self.d.values()))

		self.cycle_len = len(cycle)
		self.prefix_len = len(prefix)

	def __repr__(self):
		return f'Valuation({self.d})'

	@staticmethod
	def print_list(segm):
		return ''.join((V_ONE if v else (V_UNKNOWN if v is None else V_ZERO)) for v in segm)

	def __str__(self):
		lines = []

		for var, values in sorted(self.d.items(), key=lambda v: str(v[0])):
			var_str = var if isinstance(var, str) else pretty_print(var)
			lines.append(f'{self.print_list(values[0])}|{self.print_list(values[1])} ← {var_str}')

		return '\n'.join(lines)

	@classmethod
	def from_trace(cls, prefix, cycle):
		"""Convert a trace to a valuation"""
		all_vars = set().union(*(step.keys() for step in prefix), *(step.keys() for step in cycle))

		return cls({var: (
			tuple(step.get(var) for step in prefix),
			tuple(step.get(var) for step in cycle)
		) for var in all_vars})

	@staticmethod
	def values_trace(trace, k, length):
		"""Value of ap from a full trace period from k"""

		prefix, cycle = trace

		return itertools.islice(itertools.chain(prefix, itertools.cycle(cycle)), k, k + length)

	def values(self, ap, k, length=None):
		"""Value of ap from a full trace period from k"""

		length = (self.cycle_len + self.prefix_len) if length is None else length
		return self.values_trace(self.d[ap], k, length)

	def get_vars(self):
		"""Get propositional variables"""

		return {key for key in self.d.keys() if isinstance(key, str)}

	def evaluate_binary(self, args, fn) -> Trace:
		"""Evaluate a binary pointwise (Boolean) function combining results"""

		return self.evaluate_binary_raw(self.evaluate(args[0]), self.evaluate(args[1]), fn)

	def evaluate_binary_raw(self, a: Trace, b: Trace, fn) -> Trace:
		"""Evaluate a binary pointwise (Boolean) function combining results"""

		prefix1, cycle1 = a
		prefix2, cycle2 = b

		return (tuple(fn(x, y) for x, y in zip(prefix1, prefix2)),
		        tuple(fn(x, y) for x, y in zip(cycle1, cycle2)))

	def evaluate_eventually(self, a: Trace) -> Trace:
		"""Evaluate eventually over a trace"""

		prefix, cycle = a

		if True in cycle:
			return (True,) * len(prefix), (True,) * len(cycle)

		if None in cycle:
			new_prefix, value = [True] * len(prefix), None

			for k in reversed(range(len(prefix))):
				if prefix[k]:
					break
				else:
					new_prefix = None

			return tuple(new_prefix), (None,) * len(cycle)

		new_prefix, value = [True] * len(prefix), False

		for k in reversed(range(len(prefix))):
			if prefix[k]:
				break
			elif prefix[k] is None:
				value = None

			new_prefix[k] = value

		return tuple(new_prefix), (False,) * len(cycle)

	def evaluate_always(self, a: Trace) -> Trace:
		"""Evaluate always over a trace"""

		prefix, cycle = a

		if False in cycle:
			return (False,) * len(prefix), (False,) * len(cycle)

		if None in cycle:
			return (None,) * len(prefix), (None,) * len(cycle)

		new_prefix = [False] * len(prefix)

		for k in reversed(range(len(prefix))):
			if prefix[k]:
				new_prefix[k] = True
			else:
				break

		return tuple(new_prefix), (True,) * len(cycle)

	def evaluate_until(self, a: Trace, b: Trace) -> Trace:
		"""Evaluate until over two traces"""

		prefix1, cycle1 = a
		prefix2, cycle2 = b

		new_prefix, new_cycle = [None] * len(prefix1), [None] * len(cycle1)

		# Set true where b holds
		for k, v in enumerate(prefix2):
			if v:
				new_prefix[k] = True

		for k, v in enumerate(cycle2):
			if v:
				new_cycle[k] = True

		# Propagate true where b holds
		prev = new_cycle[0]

		if True in cycle2:
			# We only need a second round if new_cycle[0] changed
			# and only until the first True, but let optimize later
			for _ in (1, 2):
				for k in reversed(range(len(cycle1))):
					if prev and cycle1[k]:
						new_cycle[k] = True

					elif cycle1[k] is False and cycle2[k] is False:
						new_cycle[k] = False

					prev = new_cycle[k]
		else:
			new_cycle = [False] * len(new_cycle)
			prev = False

		# Propagate in the prefix
		for k in reversed(range(len(prefix1))):
			if prev and prefix1[k]:
				new_cycle[k] = True

			elif prefix1[k] is False and prefix2[k] is False:
				new_cycle[k] = False

			prev = new_cycle[k]

		return new_prefix, new_cycle

	def evaluate_wuntil(self, a: Trace, b: Trace) -> Trace:
		"""Evaluate the weak until"""

		return self.evaluate_binary_raw(self.evaluate_until(a, b), self.evaluate_always(a), _disjunction)

	def evaluate(self, formula) -> Trace:
		"""Evaluate the formula, giving an auxiliary valuation with the result"""

		head, *args = formula

		match head:
			case Op.VAR:
				values = self.d.get(args[0])
				return values if values else ((None,) * self.prefix_len, (None,) * self.cycle_len)

			case Op.LIT:
				return (args[0],) * self.prefix_len, (args[0],) * self.cycle_len

			case Op.HOLE:
				raise ValueError('cannot evaluate a hole')

			case Op.CTX:
				# This has been translated to an atomic proposition
				return self.d[args[1]]

			case Op.NEGATION:
				arg_prefix, arg_cycle = self.evaluate(args[0])

				return tuple(_negation(x) for x in arg_prefix), tuple(_negation(x) for x in arg_cycle)

			case Op.CONJUNCTION:
				return self.evaluate_binary(args, _conjunction)

			case Op.DISJUNCTION:
				return self.evaluate_binary(args, _disjunction)

			case Op.EXCLUSION:
				return self.evaluate_binary(args, _exclusion)

			case Op.IMPLICATION:
				return self.evaluate_binary(args, _implication)

			case Op.EQUIVALENCE:
				return self.evaluate_binary(args, _equivalence)

			case Op.NEXT:
				prefix, cycle = self.evaluate(args[0])

				return prefix[1:] + cycle[:1], cycle[1:] + cycle[:1]

			case Op.ALWAYS:
				return self.evaluate_always(self.evaluate(args[0]))

			case Op.EVENTUALLY:
				return self.evaluate_eventually(self.evaluate(args[0]))

			case Op.UNTIL:
				return self.evaluate_until(self.evaluate(args[0]), self.evaluate(args[1]))

			case Op.WUNTIL:
				return self.evaluate_wuntil(self.evaluate(args[0]), self.evaluate(args[1]))

			case Op.RELEASE:
				right = self.evaluate(args[1])
				and_part = self.evaluate_binary_raw(self.evaluate(args[0]), right, _conjunction)
				return self.evaluate_wuntil(right, and_part)

			case Op.SRELEASE:
				right = self.evaluate(args[1])
				and_part = self.evaluate_binary_raw(self.evaluate(args[0]), right, _conjunction)
				return self.evaluate_until(right, and_part)

		raise ValueError(f'unknown type {head}')
