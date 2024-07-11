#
# Common functions for all logics
#

from .parser import Operator as Op
from .transform import Transformer


def instantiate_context(context, replacement):
	"""Instantiate the given context with the hole replacement"""

	head, *args = context

	match head:
		case Op.HOLE:
			return replacement
		case Op.VAR | Op.LIT:
			return context
		case Op.CTX:
			return head, args[0], instantiate_context(args[1], replacement)
		case _:
			return head, *(instantiate_context(arg, replacement) for arg in args)


def instantiate_formula(formula, replacements):
	"""Instantiate the contexts of a formula"""

	head, *args = formula

	match head:
		case Op.VAR | Op.LIT:
			return formula

		case Op.CTX:
			# Instantiate the argument
			arg = instantiate_formula(args[1], replacements)

			# replacements is a partial function, the context is only replaced
			# if the instantiation is defined for this variable
			if replacement := replacements.get(args[0]):
				return instantiate_context(replacement, arg)

			return head, args[0], arg

		case Op.HOLE:
			raise ValueError('instantiate_formula applied to formula with holes')

		case _:
			# Instantiate recursively
			return head, *(instantiate_formula(arg, replacements) for arg in args)


class Problem:
	"""Abstract equivalence problem"""

	HAS_SIMPLIFIED = False
	HAS_AUTOMATA = False

	def __init__(self, left, right, logic, any_formula=False):
		self.transformer = Transformer(any_formula=any_formula, logic=logic)

		# Original formulae
		self.left = left
		self.right = right

		# Translated formulae
		self.gen_left, self.gen_right, self.gen_cond = self.transformer.translate(left, right)

		# Models computed when solving the problem
		self.lnr_model = None
		self.rnl_model = None

	def _simplify(self, canonical, lnr_valuation, rnl_valuation):
		"""Simplify the canonical instantiation with the models"""

		lnr_simplified = self.transformer.simplify_context(canonical, lnr_valuation) if lnr_valuation else None
		rnl_simplified = self.transformer.simplify_context(canonical, rnl_valuation) if rnl_valuation else None

		if lnr_valuation is None:
			canonical = rnl_simplified
		elif rnl_valuation is None or lnr_simplified == rnl_simplified:
			canonical = lnr_simplified
		else:
			canonical = (lnr_simplified, rnl_simplified)

		return canonical
