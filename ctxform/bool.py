#
# Equivalence problem for the propositional calculus
#

import pysat.formula as sat
from pysat.solvers import Solver

from .common import Op, Problem, instantiate_formula
from .transform import InvalidFormulaError

# Mapping from propositional operators to PySAT constructors
PYSAT_MAP = {
	Op.NEGATION: sat.Neg,
	Op.DISJUNCTION: sat.Or,
	Op.CONJUNCTION: sat.And,
	Op.IMPLICATION: sat.Implies,
	Op.EXCLUSION: sat.XOr,
	Op.EQUIVALENCE: sat.Equals,
}

# Index of hole as a PySAT variable
_HOLE_INDEX = 1


def to_pysat(ast, var_map):
	"""Translate a formula (without context) to PySAT"""

	head, *args = ast

	match head:
		case Op.LIT:
			return sat.Atom(args[0])

		case Op.VAR:
			var_id = var_map.setdefault(args[0], len(var_map))
			return sat.Atom(var_id)

		case Op.CTX:
			raise ValueError('cannot convert context to PySAT')

		case Op.HOLE:
			return sat.Atom(_HOLE_INDEX)

		case _:
			# The constructor of the corresponding PySAT term
			sat_head = PYSAT_MAP.get(head)

			# The parser for propositional logic is the same used for
			# LTL, so LTL operators may have been used by mistake
			if sat_head is None:
				raise InvalidFormulaError(f'not a Boolean formula: {head}')

			return sat_head(*(to_pysat(arg, var_map) for arg in args))


def from_pysat(valuation, var_map):
	"""Convert a PySAT valuation to Boolean-valued dictionary"""

	if valuation is None:
		return None

	return {var: value >= 0 for value in valuation
	        if (var := var_map.get(abs(value))) is not None}


def print_valuation(valuation):
	"""Convert a valuation as a dictionary to a string"""

	if valuation is None:
		return None

	if not valuation:
		return 'true'

	def clean(s):
		return s.strip('"')

	return ' ∧ '.join((clean(var) if value else f'¬ {clean(var)}')
	                  for var, value in valuation.items())


class BoolSpec:
	"""Specification for the Boolean transformation"""

	@staticmethod
	def wrap_premise(premise):
		# Boolean premises are not wrapped
		return premise


class BoolProblem(Problem):
	"""Equivalence problem for propositional logic"""

	def __init__(self, left, right, any_formula=False):
		super().__init__(left, right, BoolSpec, any_formula=any_formula)

		# Variable mapping
		self.var_map = {0: None, _HOLE_INDEX: '🕳'}

	def _satisfiable(self, form):
		"""Check whether a formula is satisfiable with PySAT"""

		if form == sat.PYSAT_TRUE:
			return True, ()

		if form == sat.PYSAT_FALSE:
			return False, None

		with Solver(bootstrap_with=form) as solver:
			satisfiable = solver.solve()
			model = solver.get_model()

		return satisfiable, model

	def _solve_both(self, cnf_lnr, cnf_rnl):
		"""Solve both formulae and constructs the model with PySAT"""

		lnr, lnr_model = self._satisfiable(cnf_lnr)
		rnl, rnl_model = self._satisfiable(cnf_rnl)

		self.result = not rnl and not lnr

		reverse_map = {v: k for k, v in self.var_map.items()}

		return (from_pysat(lnr_model, reverse_map),
		        from_pysat(rnl_model, reverse_map))

	def solve(self, timeout=None):
		"""Solve with the equisatisfiable formula"""

		sat_left = to_pysat(self.gen_left, self.var_map)
		sat_right = to_pysat(self.gen_right, self.var_map)
		sat_cond = to_pysat(self.gen_cond, self.var_map)

		cnf_lnr = sat.And(sat_left, sat_cond, sat.Neg(sat_right)).simplified()
		cnf_rnl = sat.And(sat_right, sat_cond, sat.Neg(sat_left)).simplified()

		self.lnr_model, self.rnl_model = self._solve_both(cnf_lnr, cnf_rnl)

		return (self.lnr_model is None and self.rnl_model is None,
		        print_valuation(self.lnr_model),
		        print_valuation(self.rnl_model))

	def solve_with_context(self, simplify=False, timeout=None):
		"""Obtain witnesses and study their satisfaction"""

		# Obtain the canonical contexts
		# (if solve has been run, we can simplify them here)
		canonical = self.transformer.canonical_context()

		# Instantiate the formula with the canonical context
		left_inst = instantiate_formula(self.left, canonical)
		right_inst = instantiate_formula(self.right, canonical)

		# Build the PySAT formula to be checked
		sat_left = to_pysat(left_inst, self.var_map).simplified()
		sat_right = to_pysat(right_inst, self.var_map).simplified()

		cnf_lnr = (sat_left & sat.Neg(sat_right)).simplified()
		cnf_rnl = (sat_right & sat.Neg(sat_left)).simplified()

		self.lnr_model, self.rnl_model = self._solve_both(cnf_lnr, cnf_rnl)

		# Simplify witnesses if requested
		if simplify and (self.lnr_model or self.rnl_model):
			canonical = self._simplify(canonical, self.lnr_model, self.rnl_model)

		return canonical, self.result

	def canonical_context(self, simplified=False):
		"""Obtain the canonical context (possibly simplified after running solve or witnesses)"""

		canonical = self.transformer.canonical_context()

		if simplified and (self.lnr_model or self.rnl_model):
			canonical = self._simplify(canonical, self.lnr_model, self.rnl_model)

		return canonical
