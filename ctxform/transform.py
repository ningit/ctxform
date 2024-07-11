#
# Transform formulas to check satisfaction/equivalence
#

import itertools

from .parser import Operator as Op
from .printer import pretty_print
from .tfsimp import simplify


class InvalidFormulaError(Exception):
	"""Not a valid formula for the current purpose"""

	def __init__(self, text):
		super().__init__(text)


class Transformer:
	"""Transform formulas with contexts to standard formulas"""

	def __init__(self, any_formula, logic):
		# Associate each context to a dictionary from the arguments of its
		# occurrences to the corresponding atomic proposition
		self.ctx_map = {}

		# Associate each atomic proposition name to its context variable and argument
		self.ctx_ap_map = {}

		# Whether the context are assumed to be monotonic
		self.monotonic = not any_formula
		# Information structure for the given logic
		self.logic = logic

	def _translate(self, ast):
		"""Translate formulae by removing contexts"""

		head, *args = ast

		match head:
			case Op.VAR | Op.LIT:
				return ast

			case Op.CTX:
				# Translated argument (done first because of nested contexts)
				arg = self._translate(args[1])

				# Have we already seen this argument for this context?
				repl_var = self.ctx_map.get(args[0], {}).get(arg)

				if repl_var is None:
					# Use the context as the name of its variable
					arg_str = pretty_print(arg, color=False).replace('"', '')
					repl_var = f'"{args[0]}[{arg_str}]"'

					# Link the argument in the context dictionary to its variable
					self.ctx_map.setdefault(args[0], {})[arg] = repl_var
					# And the variable to the context and argument
					self.ctx_ap_map[repl_var] = (args[0], arg)

				return Op.VAR, repl_var

			case _:
				# Translate the arguments recursively
				return head, *(self._translate(arg) for arg in args)

	def _make_side(self):
		"""Build the consistency (monotonicity/functionality) condition"""

		formula = None

		if self.monotonic:  # Monotonic formula -> implication
			selector, operator = itertools.permutations, Op.IMPLICATION
		else:  # Any formula -> equivalence
			selector, operator = itertools.combinations, Op.EQUIVALENCE

		# For each context, generate its consistency requirements
		for args in self.ctx_map.values():
			for (p_arg, p_var), (q_arg, q_var) in selector(args.items(), r=2):
				# The premise is wrapped depending on the logic (usually with an always)
				premise = self.logic.wrap_premise((operator, p_arg, q_arg))
				conclusion = operator, (Op.VAR, p_var), (Op.VAR, q_var)

				# The whole implication is also wrapped depending on the logic
				clause = self.logic.wrap_premise((Op.IMPLICATION, premise, conclusion))

				# All clauses are put together in a conjunction
				formula = clause if formula is None else (Op.CONJUNCTION, formula, clause)

		# If there are no clauses, return true (i.e. the identity element of conjunction)
		return formula if formula else (Op.LIT, True)

	def translate(self, left, right):
		"""Obtain translated formulas with the condition apart"""

		left_trans = self._translate(left)
		right_trans = self._translate(right)
		cond = self._make_side()

		return left_trans, right_trans, cond

	def canonical_context(self):
		"""Construct the canonical contexts for this problem"""

		replacements = {}

		operator = Op.IMPLICATION if self.monotonic else Op.EQUIVALENCE

		# Build a separate formula with holes for each context variable
		for ctx_var, args in self.ctx_map.items():
			formula = None

			# Add a clause for each occurrence of the context variable
			for arg, var in args.items():
				# The premise is wrapped depending on the logic
				premise = self.logic.wrap_premise((operator, (Op.HOLE,), arg))
				clause = Op.IMPLICATION, premise, (Op.VAR, var)

				# All clauses are put together in a conjunction
				formula = clause if formula is None else (Op.CONJUNCTION, formula, clause)

			replacements[ctx_var] = formula

		return replacements

	def simplify_context(self, context, valuation):
		"""Simplify the given context with a valuation as argument"""

		return {ctx_var: simplify(formula, valuation) for ctx_var, formula in context.items()}
