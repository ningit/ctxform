#
# Equivalence problem for LTL
#

import itertools

import spot

from .common import Op, Problem, instantiate_formula
from .tfeval import Valuation

SPOT_MAP = {
	Op.NEGATION: spot.formula_Not,
	Op.DISJUNCTION: spot.formula_Or,
	Op.CONJUNCTION: spot.formula_And,
	Op.IMPLICATION: spot.formula_Implies,
	Op.EXCLUSION: spot.formula_Xor,
	Op.EQUIVALENCE: spot.formula_Equiv,
	Op.NEXT: spot.formula_X,
	Op.EVENTUALLY: spot.formula_F,
	Op.ALWAYS: spot.formula_G,
	Op.UNTIL: spot.formula_U,
	Op.WUNTIL: spot.formula_W,
	Op.RELEASE: spot.formula_R,
	Op.SRELEASE: spot.formula_M,
}


def to_spot(ast):
	"""Translate a formula (without context) to Spot"""

	head, *args = ast

	match head:
		case Op.LIT:
			return spot.formula_tt() if args[0] else spot.formula_ff()

		case Op.VAR:
			return spot.formula(args[0])

		case Op.CTX:
			raise ValueError('cannot convert context to Spot')

		case Op.HOLE:
			return spot.formula('"🕳"')

		case _:
			spot_args = [to_spot(arg) for arg in args]

			if head in (Op.CONJUNCTION, Op.DISJUNCTION):
				return SPOT_MAP[head](spot_args)
			else:
				return SPOT_MAP[head](*spot_args)


def bdd_get_varmap(bdd):
	"""Get the variable mapping of a BDD"""

	formula, varmap = spot.bdd_to_formula(bdd), {}

	if formula.kind() not in (spot.op_ap, spot.op_Not, spot.op_And):
		raise ValueError('BDD is not a conjunction')

	if formula.kind() != spot.op_And:
		formula = (formula,)

	for clause in formula:
		if clause.kind() == spot.op_ap:
			varmap[str(clause)] = True
		elif clause.kind() == spot.op_Not:
			arg, = clause

			if arg.kind() != spot.op_ap:
				raise ValueError('BDD is not a disjunction of literals')

			varmap[str(arg)] = False
		else:
			raise ValueError(f'BDD is not a disjunction of literals: {clause}')

	return varmap


def trace_from_spot(trace):
	"""Convert a counterexample trace from Spot"""

	prefix = [bdd_get_varmap(bdd) for bdd in trace.prefix]
	cycle = [bdd_get_varmap(bdd) for bdd in trace.cycle]

	return prefix, cycle


def get_invariants(trace):
	"""Get the invariant atomic proposition values of a trace"""

	prefix, cycle = trace
	invariants, conflicting = {}, set()

	# We keep in invariants the variable and values that
	# are maintained during the whole run
	for step in itertools.chain(prefix, cycle):
		for var, value in step.items():
			# If the variable is new and not conflicting, take this value
			if (old_value := invariants.get(var)) is None:
				if var not in conflicting:
					invariants[var] = value
			# If the variable is known and its value differs, remove it from the invariants
			elif old_value != value:
				invariants.pop(var)
				conflicting.add(var)

	return invariants


class LTLSpec:
	"""Specification for the LTL transformation"""

	@staticmethod
	def wrap_premise(premise):
		return Op.ALWAYS, premise


class LTLProblem(Problem):
	"""Equivalence problem for LTL"""

	HAS_SIMPLIFIED = True
	HAS_AUTOMATA = True

	def __init__(self, left, right, any_formula=False):
		super().__init__(left, right, LTLSpec, any_formula=any_formula)

		# Spot formulae
		self.spot_left, self.spot_right, self.spot_cond = map(spot.formula.simplify, map(to_spot, (
			self.gen_left, self.gen_right, self.gen_cond)))

		self.aut_left = None
		self.aut_right = None
		self.aut_cond = None
		self.aut_not_left = None
		self.aut_not_right = None

	def solve(self, timeout=None):
		"""Solve the problem"""

		# All automata that we need
		self.aut_left = self.spot_left.translate()
		self.aut_right = self.spot_right.translate()
		self.aut_cond = self.spot_cond.translate()
		self.aut_not_left = spot.formula_Not(self.spot_left).translate()
		self.aut_not_right = spot.formula_Not(self.spot_right).translate()

		self.lnr_model = spot.product(self.aut_left, self.aut_not_right).intersecting_word(self.aut_cond)
		self.rnl_model = spot.product(self.aut_right, self.aut_not_left).intersecting_word(self.aut_cond)

		return (self.lnr_model is None and self.rnl_model is None), self.lnr_model, self.rnl_model

	def solve_with_context(self, simplify=False, timeout=None):
		"""Obtain witnesses and study their satisfaction"""

		canonical = self.transformer.canonical_context()

		left_inst = instantiate_formula(self.left, canonical)
		right_inst = instantiate_formula(self.right, canonical)

		spot_left = to_spot(left_inst)
		spot_right = to_spot(right_inst)

		self.aut_left = spot_left.translate()
		self.aut_right = spot_right.translate()
		self.aut_not_left = spot.formula_Not(spot_left).translate()
		self.aut_not_right = spot.formula_Not(spot_right).translate()

		self.lnr_model = self.aut_left.intersecting_word(self.aut_not_right)
		self.rnl_model = self.aut_right.intersecting_word(self.aut_not_left)

		equivalent = (not self.lnr_model and not self.rnl_model)

		# Simplify if requested
		if simplify:
			canonical = self.canonical_context(simplified=True, canonical=canonical)

		return canonical, equivalent

	def canonical_context(self, simplified=False, *, canonical=None):
		"""Obtain the canonical context (perhaps simplified after running solve or witnesses)"""

		# We reuse this function in solve_with_context, so we allow
		# receiving the canonical context to avoid computing it twice
		if canonical is None:
			canonical = self.transformer.canonical_context()

		if simplified and (self.lnr_model or self.rnl_model):
			# We only simplify with the values that are maintained along the path
			lnr_model = get_invariants(trace_from_spot(self.lnr_model)) if self.lnr_model else None
			rnl_model = get_invariants(trace_from_spot(self.rnl_model)) if self.rnl_model else None

			canonical = self._simplify(canonical, lnr_model, rnl_model)

		return canonical


class LTLProblem2(LTLProblem):
	"""Extension of LTLProblem with support for X-only counterexamples"""

	@staticmethod
	def ap_number(n: int, length: int, prefix='x_'):
		result = (Op.VAR, f'{prefix}0') if n & 1 else (Op.NEGATION, (Op.VAR, f'{prefix}0'))
		n >>= 1

		for k in range(1, length):
			clause = (Op.VAR, f'{prefix}{k}')

			if not (n & 1):
				clause = (Op.NEGATION, clause)

			result = (Op.CONJUNCTION, clause, result)
			n >>= 1

		return result

	@staticmethod
	def formula_from_trace(base, trace, ignore_zero=False):
		"""Generate a formula from a trace"""

		formula = None

		for value in trace:
			clause = None

			if value:
				clause = base

			elif value is False and not ignore_zero:
				clause = Op.NEGATION, base

			if clause is not None:
				formula = clause if formula is None else (Op.CONJUNCTION, formula, clause)

			base = Op.NEXT, base

		return formula if formula else (Op.LIT, True)

	def witness_run(self, run):
		"""Get a witness based on a run"""

		# Counterexample (maps of propositions to true/false)
		prefix = [bdd_get_varmap(step) for step in run.prefix]
		cycle = [bdd_get_varmap(step) for step in run.cycle]

		valuation = Valuation.from_trace(prefix, cycle)

		# Add additional elements to the valuation
		for ctx_var, variants in self.transformer.ctx_map.items():
			for arg, var_name in variants.items():
				valuation.d[(Op.CTX, ctx_var, arg)] = valuation.d[var_name]

		ap_map = self.transformer.ctx_ap_map

		for _, arg in ap_map.values():
			if arg not in valuation.d:
				valuation.d[arg] = valuation.evaluate(arg)

		witnesses = {}
		aps = valuation.get_vars()  # set(ap_map.keys())

		for ctx_var, variants in self.transformer.ctx_map.items():
			clauses = {}
			formula = None

			for arg, var_name in variants.items():
				prefix, cycle = valuation.d[var_name]

				# Check clauses to be added for ctx_var
				for k, v in enumerate(itertools.chain(prefix, cycle)):
					if v:
						clause = clauses.get(k)
						new_clause = self.formula_from_trace((Op.HOLE,), valuation.values(arg, k), ignore_zero=True)

						clauses[k] = new_clause if clause is None else (Op.DISJUNCTION, clause, new_clause)

			for k, clause in clauses.items():
				# Create the conjunction of atomic propositions
				for ap in aps:
					ap_clause = self.formula_from_trace((Op.VAR, ap), valuation.values(ap, k))
					clause = (Op.CONJUNCTION, clause, ap_clause)

				formula = clause if formula is None else (Op.DISJUNCTION, formula, clause)

			witnesses[ctx_var] = formula if formula else (Op.LIT, False)

		# print(valuation)

		left_inst = instantiate_formula(self.left, witnesses)
		right_inst = instantiate_formula(self.right, witnesses)

		return witnesses, spot.are_equivalent(to_spot(left_inst), to_spot(right_inst))
