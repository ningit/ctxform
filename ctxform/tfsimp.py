#
# Simplification of temporal and Boolean formula
#

from .parser import Operator as Op


def _is_true(formula):
	"""Whether the argument is true"""

	return formula[0] == Op.LIT and formula[1]


def _is_false(formula):
	"""Whether the argument is true"""

	return formula[0] == Op.LIT and not formula[1]


def _negate(formula):
	"""Add negation to a formula with some checks"""

	if formula[0] == Op.NEGATION:
		return formula[1]

	return Op.NEGATION, formula


def _dual_operator(operator):
	"""Dual of an operator"""

	match operator:
		case Op.ALWAYS:
			return Op.EVENTUALLY
		case Op.EVENTUALLY:
			return Op.ALWAYS
		case Op.FORALL:
			return Op.EXISTS
		case Op.EXISTS:
			return Op.FORALL

	return operator


def simplify(formula, valuation):
	"""Simplify a given formula with a valuation"""

	head, *args = formula

	# Simplify arguments
	match head:
		case Op.LIT | Op.VAR | Op.HOLE:
			pass

		case Op.CTX:
			args[1] = simplify(formula, valuation)

		case _:
			args = [simplify(arg, valuation) for arg in args]

	# Simplify at the top level
	match head:
		case Op.VAR:
			if (value := valuation.get(args[0])) is not None:
				return Op.LIT, value

		case Op.NEGATION:
			print(args)
			if args[0][0] == Op.LIT:
				return Op.LIT, not args[0][1]
			elif args[0][0] == Op.NEGATION:
				return args[0][1]

		case Op.DISJUNCTION:
			if any(map(_is_true, args)):
				return Op.LIT, True
			elif _is_false(args[0]):
				return args[1]
			elif _is_false(args[1]) or args[0] == args[1]:
				return args[0]

		case Op.CONJUNCTION:
			if any(map(_is_false, args)):
				return Op.LIT, False
			elif _is_true(args[0]):
				return args[1]
			elif _is_true(args[1]) or args[0] == args[1]:
				return args[0]

		case Op.IMPLICATION:
			if _is_false(args[0]) or _is_true(args[1]):
				return Op.LIT, True
			elif _is_true(args[0]):
				return args[1]
			elif _is_false(args[1]):
				return _negate(args[0])

		case Op.EQUIVALENCE:
			if _is_true(args[0]):
				return args[1]
			elif _is_true(args[1]):
				return args[0]
			elif _is_false(args[0]):
				return _negate(args[1])
			elif _is_false(args[1]):
				return _negate(args[0])

		case Op.EXCLUSION:
			if _is_true(args[0]):
				return _negate(args[1])
			elif _is_true(args[1]):
				return _negate(args[0])
			elif _is_false(args[0]):
				return args[1]
			elif _is_false(args[1]):
				return args[0]

		case Op.NEXT | Op.ALWAYS | Op.EVENTUALLY | Op.FORALL | Op.EXISTS:
			if args[0][0] == Op.LIT:
				return args[0]
			elif args[0][0] == Op.NEGATION:
				return Op.NEGATION, (_dual_operator(head), args[0][1])
			else:
				return head, *args

		case Op.UNTIL:
			if _is_true(args[1]):
				return Op.LIT, True
			elif _is_false(args[1]):
				return Op.LIT, False
			elif _is_false(args[0]):
				return args[1]
			elif _is_true(args[0]):
				return Op.EVENTUALLY, args[1]

		case Op.WUNTIL:
			if _is_true(args[0]) or _is_true(args[1]):
				return Op.LIT, True
			elif _is_false(args[1]):
				return Op.ALWAYS, args[0]
			elif _is_false(args[0]):
				return args[1]

		case Op.RELEASE:
			if _is_true(args[0]) or _is_true(args[1]):
				return Op.LIT, True
			elif _is_false(args[0]):
				return Op.ALWAYS, args[1]
			elif _is_false(args[1]):
				return Op.LIT, False

		case Op.SRELEASE:
			if _is_false(args[0]) or _is_false(args[1]):
				return Op.LIT, False
			elif _is_true(args[0]):
				return args[1]
			elif _is_true(args[1]):
				return Op.EVENTUALLY, args[0]

	return formula
